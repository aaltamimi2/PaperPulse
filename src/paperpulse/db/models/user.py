"""User and research profile models."""

from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from paperpulse.db.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """User account."""

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255))

    # Email preferences
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    immediate_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    research_profiles: Mapped[list["ResearchProfile"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id!r}, email={self.email!r})>"


class ResearchProfile(Base, UUIDMixin, TimestampMixin):
    """User's research profile for paper matching."""

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user: Mapped["User"] = relationship(back_populates="research_profiles")

    # Profile metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    interest_categories: Mapped[list["InterestCategory"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ResearchProfile(id={self.id!r}, name={self.name!r})>"


class InterestCategory(Base, UUIDMixin, TimestampMixin):
    """Specific research interest category within a profile."""

    profile_id: Mapped[str] = mapped_column(
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile: Mapped["ResearchProfile"] = relationship(back_populates="interest_categories")

    # Category definition
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Matching criteria
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    excluded_keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    followed_authors: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    followed_journals: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Semantic matching
    profile_embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(768))
    embedding_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Scoring weights (can override defaults)
    weight_semantic: Mapped[float] = mapped_column(default=0.4)
    weight_keyword: Mapped[float] = mapped_column(default=0.3)
    weight_author: Mapped[float] = mapped_column(default=0.2)
    weight_novelty: Mapped[float] = mapped_column(default=0.1)

    # Thresholds
    threshold_immediate: Mapped[float] = mapped_column(default=0.8)
    threshold_weekly: Mapped[float] = mapped_column(default=0.5)

    def __repr__(self) -> str:
        return f"<InterestCategory(id={self.id!r}, name={self.name!r})>"
