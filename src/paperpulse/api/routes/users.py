"""User management routes."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from paperpulse.api.deps import CurrentUser, DBSession, get_password_hash
from paperpulse.api.schemas import (
    MessageResponse,
    UserPreferencesUpdate,
    UserResponse,
    UserUpdate,
    UserWithProfilesResponse,
)
from paperpulse.db.models import User

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserWithProfilesResponse)
async def get_current_user_profile(
    current_user: CurrentUser,
    db: DBSession,
) -> User:
    """Get the current user's profile with research profiles.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        User profile with research profiles
    """
    # Reload with relationships
    result = await db.execute(
        select(User)
        .where(User.id == current_user.id)
        .options(selectinload(User.research_profiles))
    )
    return result.scalar_one()


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    current_user: CurrentUser,
    db: DBSession,
    user_update: UserUpdate,
) -> User:
    """Update the current user's profile.

    Args:
        current_user: Current authenticated user
        db: Database session
        user_update: Fields to update

    Returns:
        Updated user profile

    Raises:
        HTTPException: If email already in use
    """
    # Check if email is being changed and if it's already in use
    if user_update.email and user_update.email != current_user.email:
        result = await db.execute(
            select(User).where(User.email == user_update.email)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use",
            )
        current_user.email = user_update.email
        current_user.email_verified = False  # Require re-verification

    if user_update.name is not None:
        current_user.name = user_update.name

    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.patch("/me/preferences", response_model=UserResponse)
async def update_user_preferences(
    current_user: CurrentUser,
    db: DBSession,
    preferences: UserPreferencesUpdate,
) -> User:
    """Update the current user's email and digest preferences.

    Args:
        current_user: Current authenticated user
        db: Database session
        preferences: Preference fields to update

    Returns:
        Updated user profile
    """
    if preferences.digest_enabled is not None:
        current_user.digest_enabled = preferences.digest_enabled

    if preferences.immediate_alerts_enabled is not None:
        current_user.immediate_alerts_enabled = preferences.immediate_alerts_enabled

    if preferences.digest_frequency is not None:
        current_user.digest_frequency = preferences.digest_frequency

    if preferences.digest_day is not None:
        current_user.digest_day = preferences.digest_day

    if preferences.digest_hour is not None:
        current_user.digest_hour = preferences.digest_hour

    if preferences.timezone is not None:
        current_user.timezone = preferences.timezone

    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    current_user: CurrentUser,
    db: DBSession,
    current_password: str,
    new_password: str,
) -> MessageResponse:
    """Change the current user's password.

    Args:
        current_user: Current authenticated user
        db: Database session
        current_password: Current password for verification
        new_password: New password to set

    Returns:
        Success message

    Raises:
        HTTPException: If current password is incorrect
    """
    from paperpulse.api.deps import verify_password

    if current_user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have a password set",
        )

    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    current_user.hashed_password = get_password_hash(new_password)
    await db.flush()

    return MessageResponse(message="Password changed successfully")


@router.delete("/me", response_model=MessageResponse)
async def delete_current_user(
    current_user: CurrentUser,
    db: DBSession,
) -> MessageResponse:
    """Delete the current user's account.

    This permanently deletes the user and all associated data.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    await db.delete(current_user)
    await db.flush()

    return MessageResponse(message="Account deleted successfully")
