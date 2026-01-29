"""FastAPI dependencies for database sessions and authentication."""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from paperpulse.core.config import get_settings
from paperpulse.db.models import User
from paperpulse.db.session import get_session_factory

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token.

    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time

    Returns:
        Encoded JWT token
    """
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token.

    Args:
        token: JWT token string

    Returns:
        Decoded token data or None if invalid
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
        )
        return payload
    except JWTError:
        return None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Yields:
        AsyncSession for database operations
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Type alias for database session dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DBSession,
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
) -> User:
    """Get the current authenticated user.

    Args:
        db: Database session
        token: JWT token from Authorization header

    Returns:
        Current user

    Raises:
        HTTPException: If not authenticated or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # Get user from database
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.research_profiles))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_current_user_optional(
    db: DBSession,
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
) -> Optional[User]:
    """Get the current user if authenticated, None otherwise.

    Args:
        db: Database session
        token: JWT token from Authorization header

    Returns:
        Current user or None
    """
    if token is None:
        return None

    payload = decode_access_token(token)
    if payload is None:
        return None

    user_id: str = payload.get("sub")
    if user_id is None:
        return None

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.research_profiles))
    )
    return result.scalar_one_or_none()


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[Optional[User], Depends(get_current_user_optional)]


async def get_verified_user(current_user: CurrentUser) -> User:
    """Get the current user, requiring email verification.

    Args:
        current_user: Current authenticated user

    Returns:
        Verified user

    Raises:
        HTTPException: If email not verified
    """
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )
    return current_user


VerifiedUser = Annotated[User, Depends(get_verified_user)]
