"""Multi-source paper aggregator with deduplication."""

import asyncio
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

import structlog

from paperpulse.collectors.base import BaseCollector, CollectedPaper, CollectorResult

logger = structlog.get_logger(__name__)


@dataclass
class AggregatorResult:
    """Result from aggregation operation."""

    papers: list[CollectedPaper] = field(default_factory=list)
    total_collected: int = 0
    duplicates_removed: int = 0
    source_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def unique_count(self) -> int:
        """Number of unique papers after deduplication."""
        return len(self.papers)


class PaperAggregator:
    """Aggregates papers from multiple collectors with smart deduplication.

    Deduplication strategies:
    - DOI matching (most reliable)
    - arXiv ID matching
    - Semantic Scholar ID matching
    - PubMed ID matching
    - Title similarity matching (fallback)

    The aggregator merges metadata from multiple sources for the same paper,
    preferring sources with more complete information.
    """

    def __init__(
        self,
        collectors: list[BaseCollector],
        title_similarity_threshold: float = 0.85,
        merge_metadata: bool = True,
    ):
        """Initialize the aggregator.

        Args:
            collectors: List of collectors to aggregate from
            title_similarity_threshold: Minimum title similarity for matching (0-1)
            merge_metadata: Whether to merge metadata from duplicate papers
        """
        self.collectors = collectors
        self.title_similarity_threshold = title_similarity_threshold
        self.merge_metadata = merge_metadata

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison.

        Args:
            title: Paper title

        Returns:
            Normalized title (lowercase, stripped)
        """
        # Remove common prefixes/suffixes and normalize whitespace
        title = title.lower().strip()
        # Remove leading/trailing punctuation
        title = title.strip(".,;:!?\"'")
        # Normalize whitespace
        title = " ".join(title.split())
        return title

    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles.

        Args:
            title1: First title
            title2: Second title

        Returns:
            Similarity score (0-1)
        """
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)
        return SequenceMatcher(None, norm1, norm2).ratio()

    def _find_duplicate_index(
        self,
        paper: CollectedPaper,
        existing_papers: list[CollectedPaper],
        id_index: dict[str, int],
    ) -> Optional[int]:
        """Find if a paper already exists in the collection.

        Args:
            paper: Paper to check
            existing_papers: List of existing papers
            id_index: Index of paper identifiers to list indices

        Returns:
            Index of duplicate paper, or None if not found
        """
        # Check by DOI (most reliable)
        if paper.doi:
            key = f"doi:{paper.doi}"
            if key in id_index:
                return id_index[key]

        # Check by arXiv ID
        if paper.arxiv_id:
            key = f"arxiv:{paper.arxiv_id}"
            if key in id_index:
                return id_index[key]

        # Check by Semantic Scholar ID
        if paper.semantic_scholar_id:
            key = f"s2:{paper.semantic_scholar_id}"
            if key in id_index:
                return id_index[key]

        # Check by PubMed ID
        if paper.pubmed_id:
            key = f"pmid:{paper.pubmed_id}"
            if key in id_index:
                return id_index[key]

        # Fallback: Check by title similarity
        for i, existing in enumerate(existing_papers):
            similarity = self._title_similarity(paper.title, existing.title)
            if similarity >= self.title_similarity_threshold:
                # Also check first author if available for extra confidence
                if paper.authors and existing.authors:
                    paper_first = paper.authors[0].lower().split()[-1]  # Last name
                    existing_first = existing.authors[0].lower().split()[-1]
                    if paper_first == existing_first:
                        return i
                elif similarity >= 0.95:  # Higher threshold without author match
                    return i

        return None

    def _add_to_index(self, paper: CollectedPaper, index: int, id_index: dict[str, int]) -> None:
        """Add paper identifiers to the index.

        Args:
            paper: Paper to index
            index: Index in the papers list
            id_index: Index to update
        """
        if paper.doi:
            id_index[f"doi:{paper.doi}"] = index
        if paper.arxiv_id:
            id_index[f"arxiv:{paper.arxiv_id}"] = index
        if paper.semantic_scholar_id:
            id_index[f"s2:{paper.semantic_scholar_id}"] = index
        if paper.pubmed_id:
            id_index[f"pmid:{paper.pubmed_id}"] = index

    def _merge_papers(self, existing: CollectedPaper, new: CollectedPaper) -> CollectedPaper:
        """Merge metadata from two paper records.

        Prefers non-None values. For lists, combines unique values.
        For citation counts, takes the maximum.

        Args:
            existing: Existing paper record
            new: New paper record to merge

        Returns:
            Merged paper record
        """
        # Helper to prefer non-None values
        def prefer_non_none(a, b):
            return a if a is not None else b

        # Helper to prefer non-empty strings
        def prefer_non_empty(a, b):
            return a if a else b

        # Merge identifiers (collect all)
        merged_doi = prefer_non_empty(existing.doi, new.doi)
        merged_arxiv = prefer_non_empty(existing.arxiv_id, new.arxiv_id)
        merged_s2 = prefer_non_empty(existing.semantic_scholar_id, new.semantic_scholar_id)
        merged_pmid = prefer_non_empty(existing.pubmed_id, new.pubmed_id)

        # Merge authors (prefer longer list)
        merged_authors = existing.authors if len(existing.authors) >= len(new.authors) else new.authors

        # Merge abstract (prefer longer)
        existing_abstract = existing.abstract or ""
        new_abstract = new.abstract or ""
        merged_abstract = existing_abstract if len(existing_abstract) >= len(new_abstract) else new_abstract

        # Merge fields of study (combine unique)
        merged_fields = list(set(existing.fields_of_study + new.fields_of_study))

        # Take maximum citation counts
        merged_citations = max(
            existing.citation_count or 0,
            new.citation_count or 0,
        ) or None
        merged_influential = max(
            existing.influential_citation_count or 0,
            new.influential_citation_count or 0,
        ) or None

        # Create merged paper
        return CollectedPaper(
            title=prefer_non_empty(existing.title, new.title),
            url=prefer_non_empty(existing.url, new.url),
            authors=merged_authors,
            abstract=merged_abstract or None,
            doi=merged_doi,
            arxiv_id=merged_arxiv,
            semantic_scholar_id=merged_s2,
            pubmed_id=merged_pmid,
            journal=prefer_non_empty(existing.journal, new.journal),
            venue=prefer_non_empty(existing.venue, new.venue),
            published_date=prefer_non_none(existing.published_date, new.published_date),
            year=prefer_non_none(existing.year, new.year),
            citation_count=merged_citations,
            influential_citation_count=merged_influential,
            fields_of_study=merged_fields,
            source_type=f"{existing.source_type},{new.source_type}",  # Track all sources
            source_feed_id=prefer_non_empty(existing.source_feed_id, new.source_feed_id),
        )

    def deduplicate(self, papers: list[CollectedPaper]) -> list[CollectedPaper]:
        """Remove duplicate papers from a list.

        Args:
            papers: List of papers (possibly with duplicates)

        Returns:
            List of unique papers
        """
        unique_papers: list[CollectedPaper] = []
        id_index: dict[str, int] = {}
        duplicates = 0

        for paper in papers:
            dup_index = self._find_duplicate_index(paper, unique_papers, id_index)

            if dup_index is not None:
                # Duplicate found
                duplicates += 1
                if self.merge_metadata:
                    # Merge metadata from both sources
                    unique_papers[dup_index] = self._merge_papers(
                        unique_papers[dup_index], paper
                    )
            else:
                # New unique paper
                index = len(unique_papers)
                unique_papers.append(paper)
                self._add_to_index(paper, index, id_index)

        logger.debug("Deduplication complete", total=len(papers), unique=len(unique_papers), duplicates=duplicates)
        return unique_papers

    async def collect_from_query(
        self,
        query: str,
        feed_id: str = "aggregated",
        **kwargs,
    ) -> AggregatorResult:
        """Collect papers from all collectors using the same query.

        Args:
            query: Search query to use for all collectors
            feed_id: Feed ID to assign to collected papers
            **kwargs: Additional parameters passed to collectors

        Returns:
            AggregatorResult with deduplicated papers
        """
        log = logger.bind(query=query, collector_count=len(self.collectors))
        log.info("Starting aggregated collection")

        all_papers: list[CollectedPaper] = []
        source_counts: dict[str, int] = {}
        errors: list[str] = []

        # Collect from all sources concurrently
        tasks = []
        for collector in self.collectors:
            collector_name = type(collector).__name__
            tasks.append(
                self._collect_with_name(collector, collector_name, feed_id, query, **kwargs)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for result, collector in zip(results, self.collectors):
            collector_name = type(collector).__name__

            if isinstance(result, Exception):
                error_msg = f"{collector_name}: {str(result)}"
                errors.append(error_msg)
                log.error("Collector failed", collector=collector_name, error=str(result))
                continue

            if result.error:
                errors.append(f"{collector_name}: {result.error}")
                continue

            source_counts[collector_name] = len(result.papers)
            all_papers.extend(result.papers)

        total_collected = len(all_papers)

        # Deduplicate
        unique_papers = self.deduplicate(all_papers)
        duplicates_removed = total_collected - len(unique_papers)

        log.info(
            "Aggregation complete",
            total_collected=total_collected,
            unique=len(unique_papers),
            duplicates=duplicates_removed,
        )

        return AggregatorResult(
            papers=unique_papers,
            total_collected=total_collected,
            duplicates_removed=duplicates_removed,
            source_counts=source_counts,
            errors=errors,
        )

    async def _collect_with_name(
        self,
        collector: BaseCollector,
        name: str,
        feed_id: str,
        query: str,
        **kwargs,
    ) -> CollectorResult:
        """Helper to collect with logging.

        Args:
            collector: Collector to use
            name: Collector name for logging
            feed_id: Feed ID
            query: Search query
            **kwargs: Additional parameters

        Returns:
            CollectorResult
        """
        log = logger.bind(collector=name)
        log.debug("Starting collection")

        try:
            result = await collector.collect(
                feed_id=feed_id,
                feed_url=query,
                **kwargs,
            )
            log.debug("Collection complete", paper_count=len(result.papers))
            return result
        except Exception as e:
            log.error("Collection failed", error=str(e))
            raise

    async def collect_from_configs(
        self,
        configs: list[dict],
    ) -> AggregatorResult:
        """Collect papers using different queries/configs per collector.

        Args:
            configs: List of config dicts with keys:
                - collector_index: Index of collector in self.collectors
                - query: Search query
                - feed_id: Feed ID
                - Additional kwargs for the collector

        Returns:
            AggregatorResult with deduplicated papers
        """
        log = logger.bind(config_count=len(configs))
        log.info("Starting configured aggregation")

        all_papers: list[CollectedPaper] = []
        source_counts: dict[str, int] = {}
        errors: list[str] = []

        # Create tasks from configs
        tasks = []
        task_meta = []

        for config in configs:
            idx = config.get("collector_index", 0)
            if idx >= len(self.collectors):
                errors.append(f"Invalid collector_index: {idx}")
                continue

            collector = self.collectors[idx]
            collector_name = type(collector).__name__

            query = config.get("query", "")
            feed_id = config.get("feed_id", "aggregated")

            # Extract kwargs (everything except collector_index, query, feed_id)
            kwargs = {k: v for k, v in config.items() if k not in ("collector_index", "query", "feed_id")}

            tasks.append(self._collect_with_name(collector, collector_name, feed_id, query, **kwargs))
            task_meta.append((collector_name, query))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for result, (collector_name, query) in zip(results, task_meta):
            if isinstance(result, Exception):
                error_msg = f"{collector_name} ({query}): {str(result)}"
                errors.append(error_msg)
                continue

            if result.error:
                errors.append(f"{collector_name} ({query}): {result.error}")
                continue

            # Aggregate counts by collector name
            current = source_counts.get(collector_name, 0)
            source_counts[collector_name] = current + len(result.papers)
            all_papers.extend(result.papers)

        total_collected = len(all_papers)

        # Deduplicate
        unique_papers = self.deduplicate(all_papers)
        duplicates_removed = total_collected - len(unique_papers)

        log.info(
            "Configured aggregation complete",
            total_collected=total_collected,
            unique=len(unique_papers),
            duplicates=duplicates_removed,
        )

        return AggregatorResult(
            papers=unique_papers,
            total_collected=total_collected,
            duplicates_removed=duplicates_removed,
            source_counts=source_counts,
            errors=errors,
        )

    async def close(self) -> None:
        """Close all collectors."""
        for collector in self.collectors:
            if hasattr(collector, "close"):
                await collector.close()
