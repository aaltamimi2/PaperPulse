"""Scoring pipeline for paper relevance."""

from paperpulse.scoring.base import AggregatedScore, ScoreResult, ScoringContext
from paperpulse.scoring.embeddings import EmbeddingService, cosine_similarity
from paperpulse.scoring.pipeline import ScoringConfig, ScoringPipeline
from paperpulse.scoring.scorers import (
    AuthorScorer,
    CitationScorer,
    KeywordScorer,
    NoveltyScorer,
    RecencyScorer,
    SemanticScorer,
)
from paperpulse.scoring.tfidf import FieldOfStudyScorer, TFIDFScorer

__all__ = [
    # Base classes
    "AggregatedScore",
    "ScoreResult",
    "ScoringConfig",
    "ScoringContext",
    "ScoringPipeline",
    # Embedding utilities
    "EmbeddingService",
    "cosine_similarity",
    # Original scorers
    "AuthorScorer",
    "KeywordScorer",
    "NoveltyScorer",
    "SemanticScorer",
    # Phase 2 scorers
    "CitationScorer",
    "RecencyScorer",
    "TFIDFScorer",
    "FieldOfStudyScorer",
]
