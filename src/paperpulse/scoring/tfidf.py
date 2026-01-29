"""TF-IDF based keyword scoring for enhanced relevance matching."""

import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine

from paperpulse.scoring.base import BaseScorer, ScoreResult, ScoringContext

logger = structlog.get_logger(__name__)


class TFIDFScorer(BaseScorer):
    """Score papers using TF-IDF vectorization and cosine similarity.

    TF-IDF (Term Frequency-Inverse Document Frequency) provides better
    keyword matching than simple presence/absence by:
    - Weighting terms by their importance in the document (TF)
    - Down-weighting common terms that appear in many documents (IDF)
    - Using n-grams for phrase matching

    The scorer can be:
    1. Pre-fitted on a corpus for optimal IDF weights
    2. Used without fitting for on-the-fly comparison
    """

    name = "tfidf"
    default_weight = 0.10

    def __init__(
        self,
        max_features: int = 5000,
        ngram_range: tuple[int, int] = (1, 2),
        min_df: int = 2,
        max_df: float = 0.95,
        model_path: Optional[Path] = None,
    ):
        """Initialize TF-IDF scorer.

        Args:
            max_features: Maximum vocabulary size
            ngram_range: Range of n-grams to extract (1, 2) = unigrams and bigrams
            min_df: Minimum document frequency for terms
            max_df: Maximum document frequency ratio (filter very common terms)
            model_path: Path to load/save fitted vectorizer
        """
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.max_df = max_df
        self.model_path = model_path

        self._vectorizer: Optional[TfidfVectorizer] = None
        self._fitted = False

        # Try to load pre-fitted model
        if model_path and model_path.exists():
            self._load_model(model_path)

    def _create_vectorizer(self) -> TfidfVectorizer:
        """Create a new TF-IDF vectorizer."""
        return TfidfVectorizer(
            max_features=self.max_features,
            ngram_range=self.ngram_range,
            min_df=self.min_df if self._fitted else 1,
            max_df=self.max_df,
            stop_words="english",
            lowercase=True,
            strip_accents="unicode",
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9-]*[a-zA-Z0-9]\b|\b[a-zA-Z]\b",
        )

    def _load_model(self, path: Path) -> None:
        """Load a fitted vectorizer from disk.

        Args:
            path: Path to pickled vectorizer
        """
        try:
            with open(path, "rb") as f:
                self._vectorizer = pickle.load(f)
            self._fitted = True
            logger.info("Loaded TF-IDF model", path=str(path))
        except Exception as e:
            logger.warning("Failed to load TF-IDF model", error=str(e))
            self._vectorizer = None
            self._fitted = False

    def save_model(self, path: Path) -> None:
        """Save the fitted vectorizer to disk.

        Args:
            path: Path to save pickled vectorizer
        """
        if not self._fitted or self._vectorizer is None:
            raise ValueError("Cannot save unfitted model")

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self._vectorizer, f)
        logger.info("Saved TF-IDF model", path=str(path))

    async def fit_corpus(self, documents: list[str]) -> None:
        """Fit the TF-IDF vectorizer on a corpus of documents.

        This should be called with a representative set of paper
        abstracts/titles to learn the IDF weights.

        Args:
            documents: List of document texts (abstracts, titles, etc.)
        """
        if not documents:
            logger.warning("Cannot fit on empty corpus")
            return

        logger.info("Fitting TF-IDF on corpus", document_count=len(documents))

        self._vectorizer = self._create_vectorizer()
        self._vectorizer.fit(documents)
        self._fitted = True

        vocab_size = len(self._vectorizer.vocabulary_)
        logger.info("TF-IDF fitting complete", vocabulary_size=vocab_size)

    async def fit_papers(self, papers: list[dict]) -> None:
        """Fit the vectorizer on a list of paper dictionaries.

        Args:
            papers: List of paper dicts with 'title' and optional 'abstract'
        """
        documents = []
        for paper in papers:
            text = paper.get("title", "")
            abstract = paper.get("abstract")
            if abstract:
                text += " " + abstract
            if text.strip():
                documents.append(text)

        await self.fit_corpus(documents)

    def _prepare_text(self, context: ScoringContext) -> tuple[str, str]:
        """Prepare paper and profile text for comparison.

        Args:
            context: Scoring context

        Returns:
            Tuple of (paper_text, profile_text)
        """
        # Paper text
        paper_text = context.paper_title
        if context.paper_abstract:
            paper_text += " " + context.paper_abstract

        # Profile text - combine description, keywords, and fields
        profile_parts = []
        if context.profile_description:
            profile_parts.append(context.profile_description)
        if context.profile_keywords:
            profile_parts.append(" ".join(context.profile_keywords))
        if context.profile_fields_of_study:
            profile_parts.append(" ".join(context.profile_fields_of_study))

        profile_text = " ".join(profile_parts) if profile_parts else context.profile_name

        return paper_text, profile_text

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score using TF-IDF cosine similarity.

        If the vectorizer is fitted, uses learned IDF weights.
        Otherwise, performs on-the-fly TF-IDF comparison.

        Args:
            context: Scoring context

        Returns:
            ScoreResult with TF-IDF similarity score
        """
        paper_text, profile_text = self._prepare_text(context)

        if not paper_text.strip() or not profile_text.strip():
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,
                weight=self.default_weight,
                details={"reason": "insufficient_text"},
            )

        try:
            if self._fitted and self._vectorizer is not None:
                # Use pre-fitted vectorizer
                similarity = self._score_with_fitted(paper_text, profile_text)
            else:
                # On-the-fly comparison
                similarity = self._score_on_the_fly(paper_text, profile_text)

            # TF-IDF cosine similarity is already 0-1 for non-negative vectors
            score = max(0.0, min(1.0, similarity))

            return ScoreResult(
                scorer_name=self.name,
                score=score,
                weight=self.default_weight,
                details={
                    "cosine_similarity": similarity,
                    "used_fitted_model": self._fitted,
                    "paper_text_length": len(paper_text),
                    "profile_text_length": len(profile_text),
                },
            )

        except Exception as e:
            logger.error("TF-IDF scoring failed", error=str(e))
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,
                weight=self.default_weight,
                details={"error": str(e)},
            )

    def _score_with_fitted(self, paper_text: str, profile_text: str) -> float:
        """Score using pre-fitted vectorizer.

        Args:
            paper_text: Paper text
            profile_text: Profile text

        Returns:
            Cosine similarity score
        """
        # Transform texts using fitted vectorizer
        paper_vec = self._vectorizer.transform([paper_text])
        profile_vec = self._vectorizer.transform([profile_text])

        # Calculate cosine similarity
        similarity = sklearn_cosine(paper_vec, profile_vec)[0, 0]
        return float(similarity)

    def _score_on_the_fly(self, paper_text: str, profile_text: str) -> float:
        """Score without pre-fitted model using on-the-fly TF-IDF.

        Args:
            paper_text: Paper text
            profile_text: Profile text

        Returns:
            Cosine similarity score
        """
        # Create a temporary vectorizer
        temp_vectorizer = TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 2),
            stop_words="english",
            lowercase=True,
        )

        # Fit and transform both texts together
        try:
            vectors = temp_vectorizer.fit_transform([paper_text, profile_text])
            similarity = sklearn_cosine(vectors[0:1], vectors[1:2])[0, 0]
            return float(similarity)
        except ValueError:
            # Empty vocabulary (no valid terms)
            return 0.5


class FieldOfStudyScorer(BaseScorer):
    """Score papers based on matching fields of study.

    Uses overlap between paper's fields and profile's interests.
    """

    name = "field_of_study"
    default_weight = 0.05

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score based on field of study overlap.

        Args:
            context: Scoring context

        Returns:
            ScoreResult with field matching score
        """
        paper_fields = set(f.lower() for f in context.paper_fields_of_study)
        profile_fields = set(f.lower() for f in context.profile_fields_of_study)

        if not paper_fields or not profile_fields:
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,
                weight=self.default_weight,
                details={"reason": "no_fields_to_compare"},
            )

        # Calculate Jaccard similarity
        intersection = paper_fields & profile_fields
        union = paper_fields | profile_fields

        if not union:
            return ScoreResult(
                scorer_name=self.name,
                score=0.5,
                weight=self.default_weight,
                details={"reason": "empty_union"},
            )

        jaccard = len(intersection) / len(union)

        # Also calculate overlap coefficient (intersection / min size)
        # This handles cases where profile has few fields but paper matches them
        overlap = len(intersection) / min(len(paper_fields), len(profile_fields))

        # Use weighted combination favoring overlap
        score = 0.4 * jaccard + 0.6 * overlap

        return ScoreResult(
            scorer_name=self.name,
            score=score,
            weight=self.default_weight,
            details={
                "matching_fields": list(intersection),
                "paper_fields": list(paper_fields),
                "profile_fields": list(profile_fields),
                "jaccard_similarity": jaccard,
                "overlap_coefficient": overlap,
            },
        )
