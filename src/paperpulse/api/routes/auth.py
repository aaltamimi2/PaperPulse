"""Authentication routes."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from paperpulse.api.deps import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DBSession,
    create_access_token,
    get_password_hash,
    verify_password,
)
from paperpulse.api.schemas import MessageResponse, Token, UserCreate, UserResponse
from paperpulse.db.models import User

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    db: DBSession,
    user_in: UserCreate,
) -> User:
    """Register a new user account.

    Args:
        db: Database session
        user_in: User registration data

    Returns:
        Created user

    Raises:
        HTTPException: If email already registered
    """
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == user_in.email)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=user_in.email,
        name=user_in.name,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return user


@router.post("/token", response_model=Token)
async def login(
    db: DBSession,
    form_data: OAuth2PasswordRequestForm,
) -> Token:
    """Authenticate and get an access token.

    Args:
        db: Database session
        form_data: OAuth2 form with username (email) and password

    Returns:
        JWT access token

    Raises:
        HTTPException: If credentials are invalid
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == form_data.username)
    )
    user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return Token(access_token=access_token)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    db: DBSession,
    token: str,
) -> MessageResponse:
    """Verify user email address.

    Note: This is a placeholder. In production, implement email verification
    with a proper token system.

    Args:
        db: Database session
        token: Email verification token

    Returns:
        Success message
    """
    # TODO: Implement proper email verification with token validation
    return MessageResponse(message="Email verification not yet implemented")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    db: DBSession,
    email: str,
) -> MessageResponse:
    """Request password reset.

    Note: This is a placeholder. In production, implement password reset
    with email confirmation.

    Args:
        db: Database session
        email: User email address

    Returns:
        Success message (always returns success to avoid email enumeration)
    """
    # TODO: Implement proper password reset with email
    return MessageResponse(
        message="If an account exists with this email, a password reset link will be sent"
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    db: DBSession,
    token: str,
    new_password: str,
) -> MessageResponse:
    """Reset password using token.

    Note: This is a placeholder. In production, implement with proper token validation.

    Args:
        db: Database session
        token: Password reset token
        new_password: New password

    Returns:
        Success message
    """
    # TODO: Implement proper password reset with token validation
    return MessageResponse(message="Password reset not yet implemented")
