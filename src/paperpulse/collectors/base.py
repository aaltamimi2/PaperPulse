"""Base collector interface and common types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CollectedPaper:
    """Normalized paper data from any source."""

    title: str
    url: str
    authors: list[str] = field(default_factory=list)
    abstract: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    journal: Optional[str] = None
    published_date: Optional[datetime] = None
    source_feed_id: Optional[str] = None

    # Source identifiers (Phase 1)
    semantic_scholar_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    source_type: Optional[str] = None  # rss, semantic_scholar, pubmed, arxiv

    # Citation metrics (Phase 1)
    citation_count: Optional[int] = None
    influential_citation_count: Optional[int] = None
    fields_of_study: list[str] = field(default_factory=list)
    venue: Optional[str] = None
    year: Optional[int] = None

    def content_hash(self) -> str:
        """Generate a content hash for deduplication."""
        import hashlib

        # Use DOI if available, then other identifiers, then title + first author
        if self.doi:
            content = f"doi:{self.doi}"
        elif self.semantic_scholar_id:
            content = f"s2:{self.semantic_scholar_id}"
        elif self.pubmed_id:
            content = f"pmid:{self.pubmed_id}"
        elif self.arxiv_id:
            content = f"arxiv:{self.arxiv_id}"
        else:
            first_author = self.authors[0] if self.authors else ""
            content = f"title:{self.title.lower()}|author:{first_author.lower()}"

        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class CollectorResult:
    """Result from a collection operation."""

    feed_id: str
    feed_name: str
    papers: list[CollectedPaper] = field(default_factory=list)
    new_count: int = 0
    duplicate_count: int = 0
    error: Optional[str] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now())

    @property
    def success(self) -> bool:
        """Check if collection was successful."""
        return self.error is None

    @property
    def total_count(self) -> int:
        """Total papers found in feed."""
        return len(self.papers)


class BaseCollector(ABC):
    """Abstract base class for paper collectors."""

    @abstractmethod
    async def collect(self, feed_id: str, feed_url: str) -> CollectorResult:
        """Collect papers from a source.

        Args:
            feed_id: Database ID of the feed
            feed_url: URL to collect from

        Returns:
            CollectorResult with collected papers and statistics
        """
        pass

    @abstractmethod
    async def validate_feed(self, feed_url: str) -> tuple[bool, Optional[str]]:
        """Validate that a feed URL is accessible and valid.

        Args:
            feed_url: URL to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        pass
