"""Scoring pipeline for paper relevance."""

from paperpulse.scoring.base import AggregatedScore, ScoreResult, ScoringContext
from paperpulse.scoring.embeddings import EmbeddingService, cosine_similarity
from paperpulse.scoring.pipeline import ScoringConfig, ScoringPipeline
from paperpulse.scoring.scorers import (
    AuthorScorer,
    KeywordScorer,
    NoveltyScorer,
    SemanticScorer,
)

__all__ = [
    "AggregatedScore",
    "AuthorScorer",
    "EmbeddingService",
    "KeywordScorer",
    "NoveltyScorer",
    "ScoreResult",
    "ScoringConfig",
    "ScoringContext",
    "ScoringPipeline",
    "SemanticScorer",
    "cosine_similarity",
]
