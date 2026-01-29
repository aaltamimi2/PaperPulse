"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# =============================================================================
# Authentication Schemas
# =============================================================================


class Token(BaseModel):
    """JWT access token response."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Decoded token payload."""

    user_id: Optional[str] = None


# =============================================================================
# User Schemas
# =============================================================================


class UserCreate(BaseModel):
    """Request schema for user registration."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseModel):
    """Request schema for updating user profile."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None


class UserPreferencesUpdate(BaseModel):
    """Request schema for updating user preferences."""

    digest_enabled: Optional[bool] = None
    immediate_alerts_enabled: Optional[bool] = None
    digest_frequency: Optional[Literal["daily", "weekly", "monthly"]] = None
    digest_day: Optional[int] = Field(None, ge=0, le=31)
    digest_hour: Optional[int] = Field(None, ge=0, le=23)
    timezone: Optional[str] = Field(None, max_length=50)


class UserResponse(BaseModel):
    """Response schema for user data."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    email_verified: bool
    digest_enabled: bool
    immediate_alerts_enabled: bool
    digest_frequency: str
    digest_day: int
    digest_hour: int
    timezone: str
    created_at: datetime
    updated_at: datetime


class UserWithProfilesResponse(UserResponse):
    """Response schema for user with research profiles."""

    research_profiles: list["ResearchProfileResponse"] = []


# =============================================================================
# Interest Category Schemas
# =============================================================================


class ScoringWeights(BaseModel):
    """Configurable scoring weights for an interest category."""

    weight_semantic: float = Field(0.30, ge=0.0, le=1.0)
    weight_keyword: float = Field(0.15, ge=0.0, le=1.0)
    weight_author: float = Field(0.15, ge=0.0, le=1.0)
    weight_novelty: float = Field(0.05, ge=0.0, le=1.0)
    weight_citation: float = Field(0.15, ge=0.0, le=1.0)
    weight_recency: float = Field(0.10, ge=0.0, le=1.0)
    weight_tfidf: float = Field(0.05, ge=0.0, le=1.0)
    weight_field_of_study: float = Field(0.05, ge=0.0, le=1.0)


class InterestCategoryCreate(BaseModel):
    """Request schema for creating an interest category."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    followed_authors: list[str] = Field(default_factory=list)
    followed_journals: list[str] = Field(default_factory=list)
    fields_of_study: list[str] = Field(default_factory=list)
    threshold_immediate: float = Field(0.8, ge=0.0, le=1.0)
    threshold_weekly: float = Field(0.5, ge=0.0, le=1.0)
    scoring_weights: Optional[ScoringWeights] = None


class InterestCategoryUpdate(BaseModel):
    """Request schema for updating an interest category."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    excluded_keywords: Optional[list[str]] = None
    followed_authors: Optional[list[str]] = None
    followed_journals: Optional[list[str]] = None
    fields_of_study: Optional[list[str]] = None
    threshold_immediate: Optional[float] = Field(None, ge=0.0, le=1.0)
    threshold_weekly: Optional[float] = Field(None, ge=0.0, le=1.0)
    scoring_weights: Optional[ScoringWeights] = None


class InterestCategoryResponse(BaseModel):
    """Response schema for interest category data."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    keywords: list[str]
    excluded_keywords: list[str]
    followed_authors: list[str]
    followed_journals: list[str]
    fields_of_study: list[str]
    weight_semantic: float
    weight_keyword: float
    weight_author: float
    weight_novelty: float
    weight_citation: float
    weight_recency: float
    weight_tfidf: float
    weight_field_of_study: float
    threshold_immediate: float
    threshold_weekly: float
    embedding_updated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Research Profile Schemas
# =============================================================================


class ResearchProfileCreate(BaseModel):
    """Request schema for creating a research profile."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: bool = True
    interests: list[InterestCategoryCreate] = Field(default_factory=list)


class ResearchProfileUpdate(BaseModel):
    """Request schema for updating a research profile."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ResearchProfileResponse(BaseModel):
    """Response schema for research profile data."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ResearchProfileWithInterestsResponse(ResearchProfileResponse):
    """Response schema for research profile with interest categories."""

    interest_categories: list[InterestCategoryResponse] = []


# =============================================================================
# Paper Schemas
# =============================================================================


class PaperResponse(BaseModel):
    """Response schema for paper data."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    url: str
    authors: list[str]
    abstract: Optional[str]
    doi: Optional[str]
    arxiv_id: Optional[str]
    pubmed_id: Optional[str]
    semantic_scholar_id: Optional[str]
    journal: Optional[str]
    venue: Optional[str]
    published_date: Optional[datetime]
    year: Optional[int]
    citation_count: Optional[int]
    influential_citation_count: Optional[int]
    fields_of_study: list[str]


class ScoredPaperResponse(BaseModel):
    """Response schema for paper with relevance score."""

    paper: PaperResponse
    total_score: float
    priority: str
    score_breakdown: dict[str, float]


# =============================================================================
# Digest Schemas
# =============================================================================


class DigestPreviewResponse(BaseModel):
    """Response schema for digest preview."""

    profile_name: str
    interest_name: str
    papers: list[ScoredPaperResponse]
    total_papers: int
    immediate_count: int
    weekly_count: int


# =============================================================================
# Generic Schemas
# =============================================================================


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class PaginatedResponse(BaseModel):
    """Generic paginated response."""

    items: list
    total: int
    page: int
    per_page: int
    pages: int


# Update forward references
UserWithProfilesResponse.model_rebuild()
ResearchProfileWithInterestsResponse.model_rebuild()
