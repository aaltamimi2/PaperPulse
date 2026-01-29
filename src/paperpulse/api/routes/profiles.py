"""Research profile and interest category routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from paperpulse.api.deps import CurrentUser, DBSession
from paperpulse.api.schemas import (
    InterestCategoryCreate,
    InterestCategoryResponse,
    InterestCategoryUpdate,
    MessageResponse,
    ResearchProfileCreate,
    ResearchProfileUpdate,
    ResearchProfileWithInterestsResponse,
)
from paperpulse.db.models import InterestCategory, ResearchProfile

router = APIRouter(tags=["profiles"])


# =============================================================================
# Research Profile Endpoints
# =============================================================================


@router.get("/", response_model=list[ResearchProfileWithInterestsResponse])
async def list_profiles(
    current_user: CurrentUser,
    db: DBSession,
) -> list[ResearchProfile]:
    """List all research profiles for the current user.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        List of research profiles with interest categories
    """
    result = await db.execute(
        select(ResearchProfile)
        .where(ResearchProfile.user_id == current_user.id)
        .options(selectinload(ResearchProfile.interest_categories))
        .order_by(ResearchProfile.created_at)
    )
    return list(result.scalars().all())


@router.post("/", response_model=ResearchProfileWithInterestsResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    current_user: CurrentUser,
    db: DBSession,
    profile_in: ResearchProfileCreate,
) -> ResearchProfile:
    """Create a new research profile.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_in: Profile creation data

    Returns:
        Created research profile
    """
    # Create profile
    profile = ResearchProfile(
        user_id=current_user.id,
        name=profile_in.name,
        description=profile_in.description,
        is_active=profile_in.is_active,
    )
    db.add(profile)
    await db.flush()

    # Create interest categories if provided
    for interest_in in profile_in.interests:
        interest = _create_interest_from_schema(profile.id, interest_in)
        db.add(interest)

    await db.flush()
    await db.refresh(profile)

    # Reload with relationships
    result = await db.execute(
        select(ResearchProfile)
        .where(ResearchProfile.id == profile.id)
        .options(selectinload(ResearchProfile.interest_categories))
    )
    return result.scalar_one()


@router.get("/{profile_id}", response_model=ResearchProfileWithInterestsResponse)
async def get_profile(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
) -> ResearchProfile:
    """Get a specific research profile.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID

    Returns:
        Research profile with interest categories

    Raises:
        HTTPException: If profile not found or not owned by user
    """
    profile = await _get_user_profile(db, current_user.id, profile_id)
    return profile


@router.patch("/{profile_id}", response_model=ResearchProfileWithInterestsResponse)
async def update_profile(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
    profile_update: ResearchProfileUpdate,
) -> ResearchProfile:
    """Update a research profile.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID
        profile_update: Fields to update

    Returns:
        Updated research profile
    """
    profile = await _get_user_profile(db, current_user.id, profile_id)

    if profile_update.name is not None:
        profile.name = profile_update.name
    if profile_update.description is not None:
        profile.description = profile_update.description
    if profile_update.is_active is not None:
        profile.is_active = profile_update.is_active

    await db.flush()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", response_model=MessageResponse)
async def delete_profile(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
) -> MessageResponse:
    """Delete a research profile.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID

    Returns:
        Success message
    """
    profile = await _get_user_profile(db, current_user.id, profile_id)
    await db.delete(profile)
    await db.flush()

    return MessageResponse(message="Profile deleted successfully")


# =============================================================================
# Interest Category Endpoints
# =============================================================================


@router.get("/{profile_id}/interests", response_model=list[InterestCategoryResponse])
async def list_interests(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
) -> list[InterestCategory]:
    """List all interest categories for a profile.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID

    Returns:
        List of interest categories
    """
    # Verify profile ownership
    await _get_user_profile(db, current_user.id, profile_id)

    result = await db.execute(
        select(InterestCategory)
        .where(InterestCategory.profile_id == profile_id)
        .order_by(InterestCategory.created_at)
    )
    return list(result.scalars().all())


@router.post("/{profile_id}/interests", response_model=InterestCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_interest(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
    interest_in: InterestCategoryCreate,
) -> InterestCategory:
    """Create a new interest category.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID
        interest_in: Interest category creation data

    Returns:
        Created interest category
    """
    # Verify profile ownership
    await _get_user_profile(db, current_user.id, profile_id)

    interest = _create_interest_from_schema(profile_id, interest_in)
    db.add(interest)
    await db.flush()
    await db.refresh(interest)

    return interest


@router.get("/{profile_id}/interests/{interest_id}", response_model=InterestCategoryResponse)
async def get_interest(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
    interest_id: str,
) -> InterestCategory:
    """Get a specific interest category.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID
        interest_id: Interest category ID

    Returns:
        Interest category
    """
    interest = await _get_user_interest(db, current_user.id, profile_id, interest_id)
    return interest


@router.patch("/{profile_id}/interests/{interest_id}", response_model=InterestCategoryResponse)
async def update_interest(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
    interest_id: str,
    interest_update: InterestCategoryUpdate,
) -> InterestCategory:
    """Update an interest category.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID
        interest_id: Interest category ID
        interest_update: Fields to update

    Returns:
        Updated interest category
    """
    interest = await _get_user_interest(db, current_user.id, profile_id, interest_id)

    if interest_update.name is not None:
        interest.name = interest_update.name
    if interest_update.description is not None:
        interest.description = interest_update.description
    if interest_update.keywords is not None:
        interest.keywords = interest_update.keywords
    if interest_update.excluded_keywords is not None:
        interest.excluded_keywords = interest_update.excluded_keywords
    if interest_update.followed_authors is not None:
        interest.followed_authors = interest_update.followed_authors
    if interest_update.followed_journals is not None:
        interest.followed_journals = interest_update.followed_journals
    if interest_update.fields_of_study is not None:
        interest.fields_of_study = interest_update.fields_of_study
    if interest_update.threshold_immediate is not None:
        interest.threshold_immediate = interest_update.threshold_immediate
    if interest_update.threshold_weekly is not None:
        interest.threshold_weekly = interest_update.threshold_weekly

    # Update scoring weights if provided
    if interest_update.scoring_weights is not None:
        weights = interest_update.scoring_weights
        interest.weight_semantic = weights.weight_semantic
        interest.weight_keyword = weights.weight_keyword
        interest.weight_author = weights.weight_author
        interest.weight_novelty = weights.weight_novelty
        interest.weight_citation = weights.weight_citation
        interest.weight_recency = weights.weight_recency
        interest.weight_tfidf = weights.weight_tfidf
        interest.weight_field_of_study = weights.weight_field_of_study

    await db.flush()
    await db.refresh(interest)
    return interest


@router.delete("/{profile_id}/interests/{interest_id}", response_model=MessageResponse)
async def delete_interest(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
    interest_id: str,
) -> MessageResponse:
    """Delete an interest category.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID
        interest_id: Interest category ID

    Returns:
        Success message
    """
    interest = await _get_user_interest(db, current_user.id, profile_id, interest_id)
    await db.delete(interest)
    await db.flush()

    return MessageResponse(message="Interest category deleted successfully")


@router.post("/{profile_id}/interests/{interest_id}/generate-embedding", response_model=InterestCategoryResponse)
async def generate_interest_embedding(
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str,
    interest_id: str,
) -> InterestCategory:
    """Generate or update the embedding for an interest category.

    Uses the interest's name, description, and keywords to create
    a semantic embedding for paper matching.

    Args:
        current_user: Current authenticated user
        db: Database session
        profile_id: Profile ID
        interest_id: Interest category ID

    Returns:
        Updated interest category with new embedding
    """
    interest = await _get_user_interest(db, current_user.id, profile_id, interest_id)

    # Generate embedding using the embedding service
    from paperpulse.scoring.embeddings import EmbeddingService

    embedding_service = EmbeddingService()
    embedding = await embedding_service.embed_research_profile(
        name=interest.name,
        description=interest.description,
        keywords=interest.keywords,
    )

    interest.profile_embedding = embedding
    interest.embedding_updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(interest)
    return interest


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_user_profile(
    db: DBSession,
    user_id: str,
    profile_id: str,
) -> ResearchProfile:
    """Get a profile owned by the user.

    Args:
        db: Database session
        user_id: User ID
        profile_id: Profile ID

    Returns:
        Research profile

    Raises:
        HTTPException: If profile not found or not owned by user
    """
    result = await db.execute(
        select(ResearchProfile)
        .where(
            ResearchProfile.id == profile_id,
            ResearchProfile.user_id == user_id,
        )
        .options(selectinload(ResearchProfile.interest_categories))
    )
    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research profile not found",
        )

    return profile


async def _get_user_interest(
    db: DBSession,
    user_id: str,
    profile_id: str,
    interest_id: str,
) -> InterestCategory:
    """Get an interest category owned by the user.

    Args:
        db: Database session
        user_id: User ID
        profile_id: Profile ID
        interest_id: Interest category ID

    Returns:
        Interest category

    Raises:
        HTTPException: If interest not found or not owned by user
    """
    # First verify profile ownership
    await _get_user_profile(db, user_id, profile_id)

    result = await db.execute(
        select(InterestCategory)
        .where(
            InterestCategory.id == interest_id,
            InterestCategory.profile_id == profile_id,
        )
    )
    interest = result.scalar_one_or_none()

    if interest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interest category not found",
        )

    return interest


def _create_interest_from_schema(
    profile_id: str,
    interest_in: InterestCategoryCreate,
) -> InterestCategory:
    """Create an InterestCategory from a schema.

    Args:
        profile_id: Profile ID
        interest_in: Interest category creation data

    Returns:
        InterestCategory instance
    """
    weights = interest_in.scoring_weights or InterestCategoryCreate().model_fields.get(
        "scoring_weights"
    )

    interest = InterestCategory(
        profile_id=profile_id,
        name=interest_in.name,
        description=interest_in.description,
        keywords=interest_in.keywords,
        excluded_keywords=interest_in.excluded_keywords,
        followed_authors=interest_in.followed_authors,
        followed_journals=interest_in.followed_journals,
        fields_of_study=interest_in.fields_of_study,
        threshold_immediate=interest_in.threshold_immediate,
        threshold_weekly=interest_in.threshold_weekly,
    )

    # Set scoring weights if provided
    if interest_in.scoring_weights is not None:
        weights = interest_in.scoring_weights
        interest.weight_semantic = weights.weight_semantic
        interest.weight_keyword = weights.weight_keyword
        interest.weight_author = weights.weight_author
        interest.weight_novelty = weights.weight_novelty
        interest.weight_citation = weights.weight_citation
        interest.weight_recency = weights.weight_recency
        interest.weight_tfidf = weights.weight_tfidf
        interest.weight_field_of_study = weights.weight_field_of_study

    return interest
