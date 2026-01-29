"""Scoring pipeline that aggregates multiple scorers."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from paperpulse.scoring.base import AggregatedScore, BaseScorer, ScoreResult, ScoringContext
from paperpulse.scoring.embeddings import EmbeddingService
from paperpulse.scoring.scorers import (
    AuthorScorer,
    CitationScorer,
    JournalScorer,
    KeywordScorer,
    NoveltyScorer,
    RecencyScorer,
    SemanticScorer,
)
from paperpulse.scoring.tfidf import FieldOfStudyScorer, TFIDFScorer

logger = structlog.get_logger(__name__)


@dataclass
class ScoringConfig:
    """Configuration for the scoring pipeline.

    Phase 2 updated weights to incorporate new scorers:
    - Semantic: 0.30 (down from 0.40)
    - Keyword: 0.15 (down from 0.30)
    - Author: 0.15 (down from 0.20)
    - Novelty: 0.05 (down from 0.10)
    - Citation: 0.15 (NEW)
    - Recency: 0.10 (NEW)
    - TF-IDF: 0.05 (NEW)
    - Field of Study: 0.05 (NEW)
    """

    # Original scorer weights (adjusted for Phase 2)
    weight_semantic: float = 0.30
    weight_keyword: float = 0.15
    weight_author: float = 0.15
    weight_novelty: float = 0.05

    # Phase 2: New scorer weights
    weight_citation: float = 0.15
    weight_recency: float = 0.10
    weight_tfidf: float = 0.05
    weight_field_of_study: float = 0.05

    # Priority thresholds
    threshold_immediate: float = 0.8  # High priority - immediate notification
    threshold_weekly: float = 0.5  # Medium priority - weekly digest
    threshold_monthly: float = 0.3  # Low priority - monthly roundup

    # Feature flags
    enable_semantic: bool = True
    enable_keyword: bool = True
    enable_author: bool = True
    enable_novelty: bool = True
    enable_citation: bool = True
    enable_recency: bool = True
    enable_tfidf: bool = True
    enable_field_of_study: bool = True

    # TF-IDF specific settings
    tfidf_model_path: Optional[Path] = None

    # Citation scorer settings
    citation_high_threshold: int = 50
    citation_very_high_threshold: int = 200

    # Recency scorer settings
    recency_half_life_days: int = 90
    recency_max_age_days: int = 730

    def validate(self) -> None:
        """Validate configuration."""
        total = 0.0
        weights = [
            (self.enable_semantic, self.weight_semantic, "semantic"),
            (self.enable_keyword, self.weight_keyword, "keyword"),
            (self.enable_author, self.weight_author, "author"),
            (self.enable_novelty, self.weight_novelty, "novelty"),
            (self.enable_citation, self.weight_citation, "citation"),
            (self.enable_recency, self.weight_recency, "recency"),
            (self.enable_tfidf, self.weight_tfidf, "tfidf"),
            (self.enable_field_of_study, self.weight_field_of_study, "field_of_study"),
        ]

        for enabled, weight, name in weights:
            if enabled:
                total += weight

        if abs(total - 1.0) > 0.01:
            enabled_weights = {name: weight for enabled, weight, name in weights if enabled}
            logger.warning(
                "Scorer weights do not sum to 1.0",
                total=total,
                weights=enabled_weights,
            )


class ScoringPipeline:
    """Pipeline for scoring papers against research profiles.

    The pipeline aggregates scores from multiple scorers:
    - SemanticScorer: Embedding-based similarity
    - KeywordScorer: Keyword presence matching
    - AuthorScorer: Followed author matching
    - NoveltyScorer: Novelty indicators
    - CitationScorer: Citation metrics (Phase 2)
    - RecencyScorer: Publication recency (Phase 2)
    - TFIDFScorer: TF-IDF similarity (Phase 2)
    - FieldOfStudyScorer: Field overlap (Phase 2)
    """

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
        self._tfidf_scorer: Optional[TFIDFScorer] = None

        # Original scorers
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

        # Phase 2 scorers
        if self.config.enable_citation:
            scorer = CitationScorer(
                high_citation_threshold=self.config.citation_high_threshold,
                very_high_threshold=self.config.citation_very_high_threshold,
            )
            scorer.default_weight = self.config.weight_citation
            self.scorers.append(scorer)

        if self.config.enable_recency:
            scorer = RecencyScorer(
                decay_half_life_days=self.config.recency_half_life_days,
                max_age_days=self.config.recency_max_age_days,
            )
            scorer.default_weight = self.config.weight_recency
            self.scorers.append(scorer)

        if self.config.enable_tfidf:
            self._tfidf_scorer = TFIDFScorer(
                model_path=self.config.tfidf_model_path,
            )
            self._tfidf_scorer.default_weight = self.config.weight_tfidf
            self.scorers.append(self._tfidf_scorer)

        if self.config.enable_field_of_study:
            scorer = FieldOfStudyScorer()
            scorer.default_weight = self.config.weight_field_of_study
            self.scorers.append(scorer)

    async def fit_tfidf(self, papers: list[dict]) -> None:
        """Fit the TF-IDF scorer on a corpus of papers.

        Args:
            papers: List of paper dicts with 'title' and 'abstract'
        """
        if self._tfidf_scorer is not None:
            await self._tfidf_scorer.fit_papers(papers)

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
                   Phase 2 fields: citation_count, influential_citation_count,
                   published_date, year, fields_of_study, venue
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
                # Original paper fields
                paper_title=paper.get("title", ""),
                paper_abstract=paper.get("abstract"),
                paper_authors=paper.get("authors", []),
                paper_journal=paper.get("journal"),
                paper_embedding=paper.get("embedding"),
                # Phase 2 paper fields
                paper_published_date=paper.get("published_date"),
                paper_year=paper.get("year"),
                paper_citation_count=paper.get("citation_count"),
                paper_influential_citation_count=paper.get("influential_citation_count"),
                paper_fields_of_study=paper.get("fields_of_study", []),
                paper_venue=paper.get("venue"),
                # Original profile fields
                profile_name=profile.get("name", ""),
                profile_description=profile.get("description"),
                profile_keywords=profile.get("keywords", []),
                profile_excluded_keywords=profile.get("excluded_keywords", []),
                profile_followed_authors=profile.get("followed_authors", []),
                profile_followed_journals=profile.get("followed_journals", []),
                profile_embedding=profile_embedding,
                # Phase 2 profile fields
                profile_fields_of_study=profile.get("fields_of_study", []),
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
