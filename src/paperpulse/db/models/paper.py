"""Paper model for storing academic papers."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from paperpulse.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from paperpulse.db.models.feed import RSSFeed


class Paper(Base, UUIDMixin, TimestampMixin):
    """Academic paper metadata and embeddings."""

    # Core identifiers
    doi: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Metadata
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    journal: Mapped[Optional[str]] = mapped_column(String(512))
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Source tracking
    source_feed_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("r_s_s_feeds.id", ondelete="SET NULL"),
    )
    source_feed: Mapped[Optional["RSSFeed"]] = relationship(back_populates="papers")

    # AI processing
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(768))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100))
    summary: Mapped[Optional[str]] = mapped_column(Text)

    # Deduplication
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    __table_args__ = (
        Index("ix_papers_published_date", "published_date"),
        Index(
            "ix_papers_embedding_cosine",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<Paper(id={self.id!r}, title={self.title[:50]!r}...)>"
