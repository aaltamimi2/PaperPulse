"""Scoring pipeline that aggregates multiple scorers."""

from dataclasses import dataclass, field
from typing import Optional

import structlog

from paperpulse.scoring.base import AggregatedScore, BaseScorer, ScoreResult, ScoringContext
from paperpulse.scoring.embeddings import EmbeddingService
from paperpulse.scoring.scorers import (
    AuthorScorer,
    JournalScorer,
    KeywordScorer,
    NoveltyScorer,
    SemanticScorer,
)

logger = structlog.get_logger(__name__)


@dataclass
class ScoringConfig:
    """Configuration for the scoring pipeline."""

    # Scorer weights (must sum to 1.0)
    weight_semantic: float = 0.4
    weight_keyword: float = 0.3
    weight_author: float = 0.2
    weight_novelty: float = 0.1

    # Priority thresholds
    threshold_immediate: float = 0.8  # High priority - immediate notification
    threshold_weekly: float = 0.5  # Medium priority - weekly digest
    threshold_monthly: float = 0.3  # Low priority - monthly roundup

    # Feature flags
    enable_semantic: bool = True
    enable_keyword: bool = True
    enable_author: bool = True
    enable_novelty: bool = True

    def validate(self) -> None:
        """Validate configuration."""
        total = 0.0
        if self.enable_semantic:
            total += self.weight_semantic
        if self.enable_keyword:
            total += self.weight_keyword
        if self.enable_author:
            total += self.weight_author
        if self.enable_novelty:
            total += self.weight_novelty

        if abs(total - 1.0) > 0.01:
            logger.warning(
                "Scorer weights do not sum to 1.0",
                total=total,
                semantic=self.weight_semantic,
                keyword=self.weight_keyword,
                author=self.weight_author,
                novelty=self.weight_novelty,
            )


class ScoringPipeline:
    """Pipeline for scoring papers against research profiles."""

    def __init__(
        self,
        config: Optional[ScoringConfig] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """Initialize the scoring pipeline.

        Args:
            config: Scoring configuration
            embedding_service: Service for generating embeddings
        """
        self.config = config or ScoringConfig()
        self.config.validate()

        self.embedding_service = embedding_service or EmbeddingService()

        # Initialize scorers
        self.scorers: list[BaseScorer] = []

        if self.config.enable_semantic:
            scorer = SemanticScorer(self.embedding_service)
            scorer.default_weight = self.config.weight_semantic
            self.scorers.append(scorer)

        if self.config.enable_keyword:
            scorer = KeywordScorer()
            scorer.default_weight = self.config.weight_keyword
            self.scorers.append(scorer)

        if self.config.enable_author:
            scorer = AuthorScorer()
            scorer.default_weight = self.config.weight_author
            self.scorers.append(scorer)

        if self.config.enable_novelty:
            scorer = NoveltyScorer()
            scorer.default_weight = self.config.weight_novelty
            self.scorers.append(scorer)

    def _determine_priority(self, score: float) -> str:
        """Determine priority level based on score.

        Args:
            score: Aggregated score (0-1)

        Returns:
            Priority level string
        """
        if score >= self.config.threshold_immediate:
            return "immediate"
        elif score >= self.config.threshold_weekly:
            return "weekly"
        elif score >= self.config.threshold_monthly:
            return "monthly"
        else:
            return "low"

    async def score_paper(self, context: ScoringContext) -> AggregatedScore:
        """Score a single paper against a research profile.

        Args:
            context: Scoring context with paper and profile info

        Returns:
            Aggregated score with component breakdown
        """
        log = logger.bind(
            paper_title=context.paper_title[:50],
            profile_name=context.profile_name,
        )
        log.debug("Scoring paper")

        component_scores: list[ScoreResult] = []

        for scorer in self.scorers:
            try:
                result = await scorer.score(context)
                component_scores.append(result)
                log.debug(
                    "Scorer completed",
                    scorer=scorer.name,
                    score=result.score,
                    weighted=result.weighted_score,
                )
            except Exception as e:
                log.error("Scorer failed", scorer=scorer.name, error=str(e))
                # Use neutral score on failure
                component_scores.append(
                    ScoreResult(
                        scorer_name=scorer.name,
                        score=0.5,
                        weight=scorer.default_weight,
                        details={"error": str(e)},
                    )
                )

        # Calculate total weighted score
        total_score = sum(s.weighted_score for s in component_scores)
        total_score = max(0.0, min(1.0, total_score))

        priority = self._determine_priority(total_score)

        log.info(
            "Paper scored",
            total_score=total_score,
            priority=priority,
        )

        return AggregatedScore(
            total_score=total_score,
            component_scores=component_scores,
            priority=priority,
        )

    async def score_papers(
        self,
        papers: list[dict],
        profile: dict,
    ) -> list[tuple[dict, AggregatedScore]]:
        """Score multiple papers against a research profile.

        Args:
            papers: List of paper dictionaries with title, abstract, authors, etc.
            profile: Research profile dictionary

        Returns:
            List of (paper, score) tuples sorted by score descending
        """
        # Pre-compute profile embedding for efficiency
        profile_embedding = await self.embedding_service.embed_research_profile(
            name=profile.get("name", ""),
            description=profile.get("description"),
            keywords=profile.get("keywords", []),
        )

        results = []

        for paper in papers:
            context = ScoringContext(
                paper_title=paper.get("title", ""),
                paper_abstract=paper.get("abstract"),
                paper_authors=paper.get("authors", []),
                paper_journal=paper.get("journal"),
                paper_embedding=paper.get("embedding"),
                profile_name=profile.get("name", ""),
                profile_description=profile.get("description"),
                profile_keywords=profile.get("keywords", []),
                profile_excluded_keywords=profile.get("excluded_keywords", []),
                profile_followed_authors=profile.get("followed_authors", []),
                profile_followed_journals=profile.get("followed_journals", []),
                profile_embedding=profile_embedding,
            )

            score = await self.score_paper(context)
            results.append((paper, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1].total_score, reverse=True)

        return results

    async def filter_by_priority(
        self,
        papers: list[dict],
        profile: dict,
        min_priority: str = "weekly",
    ) -> list[tuple[dict, AggregatedScore]]:
        """Score and filter papers by minimum priority.

        Args:
            papers: List of paper dictionaries
            profile: Research profile dictionary
            min_priority: Minimum priority level ("immediate", "weekly", "monthly")

        Returns:
            Filtered and sorted list of (paper, score) tuples
        """
        priority_order = {"immediate": 0, "weekly": 1, "monthly": 2, "low": 3}
        min_level = priority_order.get(min_priority, 3)

        scored = await self.score_papers(papers, profile)

        return [
            (paper, score)
            for paper, score in scored
            if priority_order.get(score.priority, 3) <= min_level
        ]
