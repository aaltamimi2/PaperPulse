"""Base scorer interface and common types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScoringContext:
    """Context for scoring a paper against a research profile."""

    # Paper information
    paper_title: str
    paper_abstract: Optional[str] = None
    paper_authors: list[str] = field(default_factory=list)
    paper_journal: Optional[str] = None
    paper_embedding: Optional[list[float]] = None

    # Paper metadata (Phase 2: Enhanced metrics)
    paper_published_date: Optional[datetime] = None
    paper_year: Optional[int] = None
    paper_citation_count: Optional[int] = None
    paper_influential_citation_count: Optional[int] = None
    paper_fields_of_study: list[str] = field(default_factory=list)
    paper_venue: Optional[str] = None

    # Profile information
    profile_name: str = ""
    profile_description: Optional[str] = None
    profile_keywords: list[str] = field(default_factory=list)
    profile_excluded_keywords: list[str] = field(default_factory=list)
    profile_followed_authors: list[str] = field(default_factory=list)
    profile_followed_journals: list[str] = field(default_factory=list)
    profile_embedding: Optional[list[float]] = None
    profile_fields_of_study: list[str] = field(default_factory=list)


@dataclass
class ScoreResult:
    """Result from a single scorer."""

    scorer_name: str
    score: float  # 0.0 to 1.0
    weight: float  # Weight for aggregation
    details: dict = field(default_factory=dict)  # Explanation of score

    @property
    def weighted_score(self) -> float:
        """Get weighted score contribution."""
        return self.score * self.weight


@dataclass
class AggregatedScore:
    """Aggregated score from multiple scorers."""

    total_score: float  # 0.0 to 1.0
    component_scores: list[ScoreResult] = field(default_factory=list)
    priority: str = "low"  # "immediate", "weekly", "monthly", "low"

    def get_score_breakdown(self) -> dict[str, float]:
        """Get breakdown of scores by scorer."""
        return {s.scorer_name: s.score for s in self.component_scores}


class BaseScorer(ABC):
    """Abstract base class for paper relevance scorers."""

    name: str = "base"
    default_weight: float = 0.25

    @abstractmethod
    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score a paper's relevance to a research profile.

        Args:
            context: Scoring context with paper and profile info

        Returns:
            ScoreResult with score and details
        """
        pass
