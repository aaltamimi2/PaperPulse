"""RSS Feed model for tracking paper sources."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from paperpulse.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from paperpulse.db.models.paper import Paper


class RSSFeed(Base, UUIDMixin, TimestampMixin):
    """RSS feed source configuration."""

    # Feed identification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Publisher info
    publisher: Mapped[Optional[str]] = mapped_column(String(255))
    journal_name: Mapped[Optional[str]] = mapped_column(String(512))

    # Feed status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_successful_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    # Feed metadata (from RSS)
    feed_title: Mapped[Optional[str]] = mapped_column(String(512))
    feed_link: Mapped[Optional[str]] = mapped_column(String(2048))
    etag: Mapped[Optional[str]] = mapped_column(String(255))
    last_modified: Mapped[Optional[str]] = mapped_column(String(255))

    # Relationships
    papers: Mapped[list["Paper"]] = relationship(back_populates="source_feed")

    def __repr__(self) -> str:
        return f"<RSSFeed(id={self.id!r}, name={self.name!r})>"

    def mark_success(self, now: Optional[datetime] = None) -> None:
        """Mark a successful fetch."""
        from datetime import datetime, timezone

        now = now or datetime.now(timezone.utc)
        self.last_fetched_at = now
        self.last_successful_fetch_at = now
        self.consecutive_failures = 0
        self.last_error = None

    def mark_failure(self, error: str, now: Optional[datetime] = None) -> None:
        """Mark a failed fetch."""
        from datetime import datetime, timezone

        now = now or datetime.now(timezone.utc)
        self.last_fetched_at = now
        self.consecutive_failures += 1
        self.last_error = error
