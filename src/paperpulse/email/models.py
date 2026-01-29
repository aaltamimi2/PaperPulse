"""Data models for email digests."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DigestPaper:
    """A paper entry in a digest section."""

    title: str
    url: str
    authors: list[str] = field(default_factory=list)
    journal: Optional[str] = None
    published_date: Optional[datetime] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None

    # Scoring info
    relevance_score: float = 0.0
    priority: str = "low"  # immediate, weekly, monthly, low

    # AI-generated content
    summary: Optional[str] = None  # 2-3 sentence summary
    why_relevant: Optional[str] = None  # "Why this matters" explanation
    relevance_tags: list[str] = field(default_factory=list)  # Auto-generated tags

    @property
    def authors_display(self) -> str:
        """Format authors for display."""
        if not self.authors:
            return "Unknown"
        if len(self.authors) <= 3:
            return ", ".join(self.authors)
        return f"{self.authors[0]} et al."

    @property
    def score_percent(self) -> int:
        """Score as percentage for display."""
        return int(self.relevance_score * 100)


@dataclass
class DigestSection:
    """A section of the digest for one research interest."""

    interest_name: str
    interest_description: Optional[str] = None
    papers: list[DigestPaper] = field(default_factory=list)

    # Section stats
    total_papers_found: int = 0
    immediate_count: int = 0
    weekly_count: int = 0

    @property
    def has_papers(self) -> bool:
        """Check if section has any papers."""
        return len(self.papers) > 0

    @property
    def top_papers(self) -> list[DigestPaper]:
        """Get top 5 papers by relevance."""
        return sorted(self.papers, key=lambda p: p.relevance_score, reverse=True)[:5]

    @property
    def high_priority_papers(self) -> list[DigestPaper]:
        """Get papers with immediate or weekly priority."""
        return [p for p in self.papers if p.priority in ("immediate", "weekly")]


@dataclass
class SuggestedAuthor:
    """An author suggested to follow."""
    name: str
    paper_count: int
    sample_paper: Optional[str] = None


@dataclass
class Digest:
    """Complete email digest with multiple interest sections."""

    user_name: str
    user_email: str
    digest_type: str = "weekly"  # weekly, daily, immediate
    generated_at: datetime = field(default_factory=datetime.now)

    # Content sections (one per research interest)
    sections: list[DigestSection] = field(default_factory=list)

    # Period covered
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    # Metadata
    total_papers: int = 0
    total_new_papers: int = 0

    # Author tracking
    followed_authors: list[str] = field(default_factory=list)
    suggested_authors: list[SuggestedAuthor] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        """Check if digest has any papers."""
        return any(section.has_papers for section in self.sections)

    @property
    def subject_line(self) -> str:
        """Generate email subject line."""
        paper_count = sum(len(s.papers) for s in self.sections)
        if self.digest_type == "immediate":
            return f"🔬 PaperPulse: High-priority paper alert ({paper_count} papers)"
        elif self.digest_type == "daily":
            return f"📰 PaperPulse Daily: {paper_count} new papers"
        else:
            return f"📚 PaperPulse Weekly Digest: {paper_count} papers across {len(self.sections)} interests"

    def get_section(self, interest_name: str) -> Optional[DigestSection]:
        """Get a section by interest name."""
        for section in self.sections:
            if section.interest_name == interest_name:
                return section
        return None

    def add_section(self, section: DigestSection) -> None:
        """Add a section to the digest."""
        self.sections.append(section)
        self.total_papers += len(section.papers)
