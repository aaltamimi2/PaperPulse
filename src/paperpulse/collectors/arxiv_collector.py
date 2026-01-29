"""arXiv API collector for academic papers."""

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

import arxiv
import structlog

from paperpulse.collectors.base import BaseCollector, CollectedPaper, CollectorResult
from paperpulse.core.config import ArxivSettings, get_settings

logger = structlog.get_logger(__name__)

# Common arXiv category mappings
ARXIV_CATEGORIES = {
    # Computer Science
    "cs.AI": "Artificial Intelligence",
    "cs.CL": "Computation and Language",
    "cs.CV": "Computer Vision and Pattern Recognition",
    "cs.LG": "Machine Learning",
    "cs.NE": "Neural and Evolutionary Computing",
    "cs.RO": "Robotics",
    "cs.SE": "Software Engineering",
    # Physics
    "physics.chem-ph": "Chemical Physics",
    "physics.comp-ph": "Computational Physics",
    "physics.bio-ph": "Biological Physics",
    "cond-mat": "Condensed Matter",
    "quant-ph": "Quantum Physics",
    # Mathematics
    "math.ST": "Statistics Theory",
    "stat.ML": "Machine Learning (Statistics)",
    # Biology
    "q-bio": "Quantitative Biology",
    # Economics/Finance
    "econ": "Economics",
    "q-fin": "Quantitative Finance",
}


class ArxivCollector(BaseCollector):
    """Collector for papers from arXiv using the arxiv package.

    arXiv provides:
    - Preprints across physics, mathematics, computer science, and more
    - Category-based search (cs.AI, physics.chem-ph, etc.)
    - Date filtering
    - Full text PDF access

    API Docs: https://info.arxiv.org/help/api/index.html
    """

    def __init__(self, settings: Optional[ArxivSettings] = None):
        """Initialize the arXiv collector.

        Args:
            settings: arXiv configuration settings
        """
        self.settings = settings or get_settings().arxiv
        self._rate_limiter = asyncio.Semaphore(1)
        self._last_request_time: float = 0
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._client = arxiv.Client(
            page_size=100,
            delay_seconds=1.0 / self.settings.rate_limit_per_second,
            num_retries=3,
        )

    async def close(self) -> None:
        """Close the executor."""
        self._executor.shutdown(wait=False)

    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        async with self._rate_limiter:
            now = asyncio.get_event_loop().time()
            min_interval = 1.0 / self.settings.rate_limit_per_second
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    def _extract_arxiv_id(self, entry_id: str) -> str:
        """Extract arXiv ID from entry URL.

        Args:
            entry_id: Full arXiv entry URL

        Returns:
            arXiv ID (e.g., "2301.00001")
        """
        # URL format: http://arxiv.org/abs/2301.00001v1
        match = re.search(r"arxiv.org/abs/([^v]+)", entry_id)
        if match:
            return match.group(1)
        return entry_id.split("/")[-1].split("v")[0]

    def _parse_result(self, result: arxiv.Result) -> CollectedPaper:
        """Parse an arXiv result into CollectedPaper.

        Args:
            result: arxiv.Result object

        Returns:
            CollectedPaper instance
        """
        # Extract arXiv ID
        arxiv_id = self._extract_arxiv_id(result.entry_id)

        # Get authors
        authors = [author.name for author in result.authors]

        # Map categories to fields of study
        fields = []
        for cat in result.categories:
            if cat in ARXIV_CATEGORIES:
                fields.append(ARXIV_CATEGORIES[cat])
            else:
                # Use the category itself if not mapped
                fields.append(cat)

        # Extract DOI if available
        doi = result.doi

        # Get publication date
        published_date = result.published.replace(tzinfo=timezone.utc) if result.published else None

        return CollectedPaper(
            title=result.title,
            url=result.entry_id,
            authors=authors,
            abstract=result.summary,
            doi=doi,
            arxiv_id=arxiv_id,
            journal=result.journal_ref,
            published_date=published_date,
            year=published_date.year if published_date else None,
            fields_of_study=fields,
            source_type="arxiv",
        )

    def _sync_search(
        self,
        query: str,
        categories: Optional[list[str]],
        max_results: int,
        sort_by: arxiv.SortCriterion,
    ) -> list[arxiv.Result]:
        """Synchronous search (run in executor).

        Args:
            query: Search query
            categories: arXiv categories to filter
            max_results: Maximum results to return
            sort_by: Sort criterion

        Returns:
            List of arxiv.Result objects
        """
        # Build search query
        search_query = query

        # Add category filter if specified
        if categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
            if search_query:
                search_query = f"({search_query}) AND ({cat_query})"
            else:
                search_query = cat_query

        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=arxiv.SortOrder.Descending,
        )

        return list(self._client.results(search))

    async def search_papers(
        self,
        query: str,
        categories: Optional[list[str]] = None,
        days_back: Optional[int] = None,
        limit: int = 100,
        sort_by: str = "submitted",
    ) -> list[CollectedPaper]:
        """Search arXiv for papers.

        Args:
            query: Search query string (supports arXiv query syntax)
            categories: arXiv categories to filter (e.g., ["cs.AI", "cs.LG"])
            days_back: Filter papers submitted in last N days (approximate via sorting)
            limit: Maximum number of results
            sort_by: Sort by "submitted", "updated", or "relevance"

        Returns:
            List of CollectedPaper instances
        """
        log = logger.bind(query=query, categories=categories, limit=limit)
        log.info("Searching arXiv")

        await self._rate_limit()

        # Map sort option
        sort_map = {
            "submitted": arxiv.SortCriterion.SubmittedDate,
            "updated": arxiv.SortCriterion.LastUpdatedDate,
            "relevance": arxiv.SortCriterion.Relevance,
        }
        sort_criterion = sort_map.get(sort_by, arxiv.SortCriterion.SubmittedDate)

        try:
            # Run search in executor (arxiv library is synchronous)
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                self._executor,
                self._sync_search,
                query,
                categories,
                min(limit, self.settings.max_results_per_query),
                sort_criterion,
            )

            # Filter by date if days_back is specified
            papers = []
            cutoff_date = None
            if days_back:
                from datetime import timedelta

                cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

            for result in results:
                paper = self._parse_result(result)

                # Apply date filter
                if cutoff_date and paper.published_date:
                    if paper.published_date < cutoff_date:
                        continue

                papers.append(paper)

            log.info("Search complete", paper_count=len(papers))
            return papers

        except Exception as e:
            log.error("Search failed", error=str(e))
            return []

    async def get_paper(self, arxiv_id: str) -> Optional[CollectedPaper]:
        """Get a single paper by arXiv ID.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2301.00001")

        Returns:
            CollectedPaper or None if not found
        """
        log = logger.bind(arxiv_id=arxiv_id)

        await self._rate_limit()

        try:
            loop = asyncio.get_event_loop()

            def fetch_single():
                search = arxiv.Search(id_list=[arxiv_id])
                results = list(self._client.results(search))
                return results[0] if results else None

            result = await loop.run_in_executor(self._executor, fetch_single)

            if result is None:
                log.warning("Paper not found")
                return None

            return self._parse_result(result)

        except Exception as e:
            log.error("Get paper failed", error=str(e))
            return None

    async def get_recent_by_category(
        self,
        categories: list[str],
        days_back: int = 7,
        limit: int = 100,
    ) -> list[CollectedPaper]:
        """Get recent papers in specified categories.

        Args:
            categories: arXiv categories (e.g., ["cs.AI", "cs.LG"])
            days_back: Number of days back to search
            limit: Maximum number of results

        Returns:
            List of CollectedPaper instances
        """
        return await self.search_papers(
            query="",
            categories=categories,
            days_back=days_back,
            limit=limit,
            sort_by="submitted",
        )

    async def collect(
        self,
        feed_id: str,
        feed_url: str,
        feed_name: str = "",
        **kwargs,
    ) -> CollectorResult:
        """Collect papers using a search query (implements BaseCollector interface).

        The feed_url should be a search query for this collector.

        Args:
            feed_id: Database ID of the feed
            feed_url: Search query to execute (or comma-separated categories)
            feed_name: Human-readable feed name
            **kwargs: Additional search parameters (categories, days_back, etc.)

        Returns:
            CollectorResult with collected papers
        """
        log = logger.bind(feed_id=feed_id, query=feed_url)
        log.info("Collecting from arXiv")

        try:
            # Check if feed_url is a category list or a query
            categories = kwargs.get("categories")
            if not categories and feed_url.startswith("cat:"):
                # Parse category from feed_url like "cat:cs.AI,cs.LG"
                cat_str = feed_url[4:]  # Remove "cat:" prefix
                categories = [c.strip() for c in cat_str.split(",")]
                query = ""
            else:
                query = feed_url

            papers = await self.search_papers(
                query=query,
                categories=categories,
                days_back=kwargs.get("days_back"),
                limit=kwargs.get("limit", self.settings.max_results_per_query),
            )

            # Set source feed ID
            for paper in papers:
                paper.source_feed_id = feed_id

            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name or f"arXiv: {feed_url}",
                papers=papers,
            )

        except Exception as e:
            log.error("Collection failed", error=str(e))
            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name or f"arXiv: {feed_url}",
                error=str(e),
            )

    async def validate_feed(self, feed_url: str) -> tuple[bool, Optional[str]]:
        """Validate that a search query returns results.

        Args:
            feed_url: Search query to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check if it's a category query
            if feed_url.startswith("cat:"):
                cat_str = feed_url[4:]
                categories = [c.strip() for c in cat_str.split(",")]
                papers = await self.search_papers(query="", categories=categories, limit=1)
            else:
                papers = await self.search_papers(query=feed_url, limit=1)

            if not papers:
                return False, "Query returned no results"
            return True, None

        except Exception as e:
            return False, f"Unexpected error: {e}"
