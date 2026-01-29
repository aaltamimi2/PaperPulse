"""Paper collectors from various sources."""

from paperpulse.collectors.aggregator import AggregatorResult, PaperAggregator
from paperpulse.collectors.arxiv_collector import ArxivCollector
from paperpulse.collectors.base import BaseCollector, CollectedPaper, CollectorResult
from paperpulse.collectors.pubmed import PubMedCollector
from paperpulse.collectors.rss_collector import RSSCollector
from paperpulse.collectors.semantic_scholar import SemanticScholarCollector

__all__ = [
    # Base classes
    "BaseCollector",
    "CollectedPaper",
    "CollectorResult",
    # Collectors
    "RSSCollector",
    "SemanticScholarCollector",
    "PubMedCollector",
    "ArxivCollector",
    # Aggregator
    "PaperAggregator",
    "AggregatorResult",
]
