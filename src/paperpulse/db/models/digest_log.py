"""DigestLog model for tracking sent digest emails."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from paperpulse.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from paperpulse.db.models.user import User


class DigestLog(Base, UUIDMixin, TimestampMixin):
    """Log of sent digest emails for analytics and debugging.

    Tracks each digest sent to users including:
    - What papers were included
    - Email delivery status
    - User engagement (opens, clicks)
    """

    # User relationship
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user: Mapped["User"] = relationship(back_populates="digest_logs")

    # Digest metadata
    digest_type: Mapped[str] = mapped_column(String(20), nullable=False)  # daily, weekly, monthly, immediate
    digest_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Content statistics
    papers_included: Mapped[int] = mapped_column(Integer, default=0)
    sections_included: Mapped[int] = mapped_column(Integer, default=0)
    immediate_count: Mapped[int] = mapped_column(Integer, default=0)
    weekly_count: Mapped[int] = mapped_column(Integer, default=0)

    # Paper IDs included (for reference)
    paper_ids: Mapped[Optional[list]] = mapped_column(JSON)

    # Email delivery
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    email_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, sent, failed, bounced
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Engagement tracking (optional, for email tracking pixels/links)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    clicked_links: Mapped[int] = mapped_column(Integer, default=0)
    last_clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Email metadata
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    email_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)

    def __repr__(self) -> str:
        return f"<DigestLog(id={self.id!r}, user_id={self.user_id!r}, type={self.digest_type!r})>"


class JobLog(Base, UUIDMixin, TimestampMixin):
    """Log of scheduled job executions for monitoring.

    Tracks each job run for debugging and performance monitoring.
    """

    # Job identification
    job_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # collect, digest, alert, embedding

    # Execution timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[float]] = mapped_column()

    # Status
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Statistics (job-specific)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)
    items_created: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Additional details
    details: Mapped[Optional[dict]] = mapped_column(JSON)

    def __repr__(self) -> str:
        return f"<JobLog(id={self.id!r}, job={self.job_name!r}, status={self.status!r})>"
