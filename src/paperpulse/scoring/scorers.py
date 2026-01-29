"""Individual scorer implementations."""

import re
from typing import Optional

import structlog

from paperpulse.scoring.base import BaseScorer, ScoreResult, ScoringContext
from paperpulse.scoring.embeddings import EmbeddingService, cosine_similarity

logger = structlog.get_logger(__name__)


class SemanticScorer(BaseScorer):
    """Score papers based on semantic similarity using embeddings."""

    name = "semantic"
    default_weight = 0.4

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        """Initialize with embedding service.

        Args:
            embedding_service: Service for generating embeddings
        """
        self.embedding_service = embedding_service or EmbeddingService()

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score based on semantic similarity between paper and profile embeddings.

        Args:
            context: Scoring context with embeddings

        Returns:
            ScoreResult with cosine similarity score
        """
        paper_embedding = context.paper_embedding
        profile_embedding = context.profile_embedding

        # Generate embeddings if not provided
        if paper_embedding is None:
            paper_embedding = await self.embedding_service.embed_paper(
                context.paper_title,
                context.paper_abstract,
            )

        if profile_embedding is None:
            profile_embedding = await self.embedding_service.embed_research_profile(
                context.profile_name,
                context.profile_description,
                context.profile_keywords,
            )

        # Calculate cosine similarity
        similarity = cosine_similarity(paper_embedding, profile_embedding)

        # Scale up similarity for better differentiation
        # Mock/deterministic embeddings typically produce low similarities (0.1-0.4)
        # Scale to expand this range: 0.1 -> 0.25, 0.2 -> 0.5, 0.3 -> 0.75, 0.4 -> 1.0
        scaled_similarity = min(1.0, max(0.0, similarity) * 2.5)
        score = max(0.0, min(1.0, scaled_similarity))

        return ScoreResult(
            scorer_name=self.name,
            score=score,
            weight=self.default_weight,
            details={
                "cosine_similarity": similarity,
                "scaled_similarity": scaled_similarity,
                "paper_has_abstract": context.paper_abstract is not None,
            },
        )


class KeywordScorer(BaseScorer):
    """Score papers based on keyword matching."""

    name = "keyword"
    default_weight = 0.3

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score based on keyword presence in title and abstract.

        Args:
            context: Scoring context with keywords

        Returns:
            ScoreResult with keyword match score
        """
        if not context.profile_keywords:
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,  # Neutral score if no keywords defined
                weight=self.default_weight,
                details={"reason": "no_keywords_defined"},
            )

        # Combine title and abstract for searching
        text = context.paper_title.lower()
        if context.paper_abstract:
            text += " " + context.paper_abstract.lower()

        # Count keyword matches
        matched_keywords = []
        for keyword in context.profile_keywords:
            # Use word boundary matching for better accuracy
            pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
            if re.search(pattern, text):
                matched_keywords.append(keyword)

        # Check for excluded keywords (penalty)
        excluded_matches = []
        for excluded in context.profile_excluded_keywords:
            pattern = r"\b" + re.escape(excluded.lower()) + r"\b"
            if re.search(pattern, text):
                excluded_matches.append(excluded)

        # Calculate score using square root scaling for better partial match rewards
        # This makes 3/7 keywords = 0.65 instead of 0.43, rewarding partial matches more
        if context.profile_keywords:
            match_ratio = len(matched_keywords) / len(context.profile_keywords)
            # Square root scaling: sqrt(ratio) gives higher scores for partial matches
            # 1 keyword of 7 = 0.38, 2/7 = 0.53, 3/7 = 0.65, 4/7 = 0.76, 5/7 = 0.85
            import math
            scaled_ratio = math.sqrt(match_ratio)
        else:
            scaled_ratio = 0.0

        # Apply penalty for excluded keywords
        exclusion_penalty = min(0.5, len(excluded_matches) * 0.2)
        score = max(0.0, scaled_ratio - exclusion_penalty)

        return ScoreResult(
            scorer_name=self.name,
            score=score,
            weight=self.default_weight,
            details={
                "matched_keywords": matched_keywords,
                "excluded_matches": excluded_matches,
                "total_keywords": len(context.profile_keywords),
                "match_ratio": match_ratio,
            },
        )


class AuthorScorer(BaseScorer):
    """Score papers based on author matching."""

    name = "author"
    default_weight = 0.2

    def _normalize_author(self, name: str) -> str:
        """Normalize author name for comparison."""
        # Remove common suffixes, lowercase, remove extra spaces
        name = name.lower().strip()
        name = re.sub(r"\s+(jr\.?|sr\.?|iii?|iv)$", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\s+", " ", name)
        return name

    def _author_matches(self, author1: str, author2: str) -> bool:
        """Check if two author names match.

        Handles variations like "J. Smith" vs "John Smith" vs "Smith, J."
        """
        a1 = self._normalize_author(author1)
        a2 = self._normalize_author(author2)

        # Exact match
        if a1 == a2:
            return True

        # Extract last name (handles "Smith, John" and "John Smith")
        def get_parts(name: str) -> tuple[str, str]:
            if "," in name:
                parts = name.split(",", 1)
                return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
            parts = name.rsplit(" ", 1)
            if len(parts) == 2:
                return parts[1], parts[0]
            return name, ""

        last1, first1 = get_parts(a1)
        last2, first2 = get_parts(a2)

        # Last names must match
        if last1 != last2:
            return False

        # If one first name is initial, check if other starts with same letter
        if first1 and first2:
            if len(first1) <= 2 or len(first2) <= 2:
                return first1[0] == first2[0]
            return first1 == first2

        return True  # Same last name, one missing first name

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score based on author matching.

        Args:
            context: Scoring context with authors

        Returns:
            ScoreResult with author match score
        """
        if not context.profile_followed_authors:
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,  # Neutral if no authors followed
                weight=self.default_weight,
                details={"reason": "no_followed_authors"},
            )

        if not context.paper_authors:
            return ScoreResult(
                scorer_name=self.name,
                score=0.0,
                weight=self.default_weight,
                details={"reason": "paper_has_no_authors"},
            )

        # Find matching authors
        matched_authors = []
        for paper_author in context.paper_authors:
            for followed_author in context.profile_followed_authors:
                if self._author_matches(paper_author, followed_author):
                    matched_authors.append(paper_author)
                    break

        # Score based on number of matches
        # Having any followed author is significant
        if matched_authors:
            # First match is most important, diminishing returns for additional
            score = min(1.0, 0.7 + 0.1 * len(matched_authors))
        else:
            score = 0.0

        return ScoreResult(
            scorer_name=self.name,
            score=score,
            weight=self.default_weight,
            details={
                "matched_authors": matched_authors,
                "paper_authors": context.paper_authors,
                "followed_authors": context.profile_followed_authors,
            },
        )


class NoveltyScorer(BaseScorer):
    """Score papers based on novelty indicators."""

    name = "novelty"
    default_weight = 0.1

    # Keywords that suggest novel methods or findings
    NOVELTY_INDICATORS = [
        "novel",
        "new method",
        "new approach",
        "first",
        "breakthrough",
        "unprecedented",
        "innovative",
        "state-of-the-art",
        "outperforms",
        "surpasses",
        "introduces",
        "we propose",
        "we present",
        "we develop",
        "framework",
        "architecture",
    ]

    # Method-specific terms that indicate new techniques
    METHOD_INDICATORS = [
        "algorithm",
        "neural network",
        "deep learning",
        "machine learning",
        "transformer",
        "attention mechanism",
        "graph neural",
        "force field",
        "enhanced sampling",
        "free energy",
        "collective variable",
        "metadynamics",
        "replica exchange",
    ]

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score based on novelty indicators in paper.

        Args:
            context: Scoring context

        Returns:
            ScoreResult with novelty score
        """
        text = context.paper_title.lower()
        if context.paper_abstract:
            text += " " + context.paper_abstract.lower()

        # Check for novelty indicators
        novelty_matches = []
        for indicator in self.NOVELTY_INDICATORS:
            if indicator.lower() in text:
                novelty_matches.append(indicator)

        # Check for method indicators
        method_matches = []
        for indicator in self.METHOD_INDICATORS:
            if indicator.lower() in text:
                method_matches.append(indicator)

        # Calculate score
        novelty_score = min(1.0, len(novelty_matches) * 0.15)
        method_score = min(0.5, len(method_matches) * 0.1)

        # Combine scores
        score = min(1.0, novelty_score + method_score)

        return ScoreResult(
            scorer_name=self.name,
            score=score,
            weight=self.default_weight,
            details={
                "novelty_indicators": novelty_matches,
                "method_indicators": method_matches,
                "novelty_score": novelty_score,
                "method_score": method_score,
            },
        )


class JournalScorer(BaseScorer):
    """Score papers based on journal matching."""

    name = "journal"
    default_weight = 0.0  # Optional scorer, weight can be redistributed

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score based on journal matching.

        Args:
            context: Scoring context

        Returns:
            ScoreResult with journal match score
        """
        if not context.profile_followed_journals:
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,
                weight=self.default_weight,
                details={"reason": "no_followed_journals"},
            )

        if not context.paper_journal:
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,
                weight=self.default_weight,
                details={"reason": "paper_has_no_journal"},
            )

        # Normalize journal names for comparison
        paper_journal = context.paper_journal.lower().strip()

        for followed in context.profile_followed_journals:
            followed_norm = followed.lower().strip()
            if followed_norm in paper_journal or paper_journal in followed_norm:
                return ScoreResult(
                    scorer_name=self.name,
                    score=1.0,
                    weight=self.default_weight,
                    details={
                        "matched_journal": followed,
                        "paper_journal": context.paper_journal,
                    },
                )

        return ScoreResult(
            scorer_name=self.name,
            score=0.0,
            weight=self.default_weight,
            details={
                "paper_journal": context.paper_journal,
                "followed_journals": context.profile_followed_journals,
            },
        )


# =============================================================================
# Phase 2: Enhanced Relevance Metrics
# =============================================================================


class CitationScorer(BaseScorer):
    """Score papers based on citation metrics.

    Uses citation count and influential citation count to assess paper impact.
    Scores are normalized using field-aware thresholds.
    """

    name = "citation"
    default_weight = 0.15

    # Thresholds for normalization (can be adjusted per field)
    HIGH_CITATION_THRESHOLD = 50
    VERY_HIGH_CITATION_THRESHOLD = 200
    INFLUENTIAL_MULTIPLIER = 3.0  # Influential citations weighted more heavily

    def __init__(
        self,
        high_citation_threshold: int = 50,
        very_high_threshold: int = 200,
        influential_multiplier: float = 3.0,
    ):
        """Initialize citation scorer.

        Args:
            high_citation_threshold: Citations considered "high impact"
            very_high_threshold: Citations considered "very high impact"
            influential_multiplier: Weight multiplier for influential citations
        """
        self.high_threshold = high_citation_threshold
        self.very_high_threshold = very_high_threshold
        self.influential_multiplier = influential_multiplier

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score based on citation metrics.

        Scoring formula:
        - Base score from total citations (log-scaled)
        - Bonus from influential citations
        - New papers (no citations) get neutral score

        Args:
            context: Scoring context with citation data

        Returns:
            ScoreResult with citation-based score
        """
        citation_count = context.paper_citation_count
        influential_count = context.paper_influential_citation_count

        # Papers without citation data get neutral score
        if citation_count is None:
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,
                weight=self.default_weight,
                details={"reason": "no_citation_data"},
            )

        # Calculate base citation score using logarithmic scaling
        # This prevents papers with thousands of citations from dominating
        import math

        if citation_count == 0:
            base_score = 0.3  # New papers get a modest score
        else:
            # Log scale: log(1 + citations) / log(1 + threshold)
            log_citations = math.log1p(citation_count)
            log_threshold = math.log1p(self.very_high_threshold)
            base_score = min(1.0, log_citations / log_threshold)

        # Bonus for influential citations
        influential_bonus = 0.0
        if influential_count and influential_count > 0:
            # Influential citations are rarer and more meaningful
            influential_ratio = influential_count / max(citation_count, 1)
            influential_bonus = min(0.2, influential_ratio * 0.5)

        # Combine scores
        total_score = min(1.0, base_score * 0.8 + influential_bonus + 0.1)

        return ScoreResult(
            scorer_name=self.name,
            score=total_score,
            weight=self.default_weight,
            details={
                "citation_count": citation_count,
                "influential_citation_count": influential_count,
                "base_score": base_score,
                "influential_bonus": influential_bonus,
                "is_highly_cited": citation_count >= self.high_threshold,
            },
        )


class RecencyScorer(BaseScorer):
    """Score papers based on publication recency.

    Uses exponential decay to favor recent publications while not
    completely discarding older but relevant papers.
    """

    name = "recency"
    default_weight = 0.10

    def __init__(
        self,
        decay_half_life_days: int = 90,
        max_age_days: int = 730,
        new_paper_bonus: float = 0.1,
    ):
        """Initialize recency scorer.

        Args:
            decay_half_life_days: Days for score to decay by half
            max_age_days: Maximum age to consider (older papers get min score)
            new_paper_bonus: Bonus for very recent papers (< 7 days)
        """
        self.half_life = decay_half_life_days
        self.max_age = max_age_days
        self.new_paper_bonus = new_paper_bonus

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score based on publication date with exponential decay.

        Formula: score = exp(-0.693 * age_days / half_life)

        Args:
            context: Scoring context with publication date

        Returns:
            ScoreResult with recency score
        """
        from datetime import timezone
        import math

        pub_date = context.paper_published_date
        pub_year = context.paper_year

        # Try to get a date
        if pub_date is None and pub_year is not None:
            # Approximate with mid-year if only year is available
            from datetime import datetime as dt
            pub_date = dt(pub_year, 7, 1, tzinfo=timezone.utc)

        if pub_date is None:
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,
                weight=self.default_weight,
                details={"reason": "no_publication_date"},
            )

        # Ensure timezone-aware comparison
        from datetime import datetime as dt
        now = dt.now(timezone.utc)

        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)

        # Calculate age in days
        age_days = (now - pub_date).days

        # Handle future dates (preprints with future publication)
        if age_days < 0:
            age_days = 0

        # Cap at max age
        if age_days > self.max_age:
            score = 0.1  # Minimum score for very old papers
            return ScoreResult(
                scorer_name=self.name,
                score=score,
                weight=self.default_weight,
                details={
                    "age_days": age_days,
                    "capped_at_max": True,
                    "publication_date": pub_date.isoformat(),
                },
            )

        # Exponential decay: score = exp(-0.693 * age / half_life)
        # At age = half_life, score = 0.5
        decay_constant = 0.693 / self.half_life
        base_score = math.exp(-decay_constant * age_days)

        # Bonus for very recent papers (< 7 days)
        bonus = 0.0
        if age_days < 7:
            bonus = self.new_paper_bonus * (1 - age_days / 7)

        total_score = min(1.0, base_score + bonus)

        return ScoreResult(
            scorer_name=self.name,
            score=total_score,
            weight=self.default_weight,
            details={
                "age_days": age_days,
                "base_score": base_score,
                "new_paper_bonus": bonus,
                "publication_date": pub_date.isoformat(),
                "half_life_days": self.half_life,
            },
        )
