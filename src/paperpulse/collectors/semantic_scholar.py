"""Semantic Scholar API collector for academic papers."""

import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from paperpulse.collectors.base import BaseCollector, CollectedPaper, CollectorResult
from paperpulse.core.config import SemanticScholarSettings, get_settings

logger = structlog.get_logger(__name__)

# Default fields to retrieve from Semantic Scholar
DEFAULT_FIELDS = [
    "paperId",
    "title",
    "abstract",
    "authors",
    "year",
    "citationCount",
    "influentialCitationCount",
    "venue",
    "publicationDate",
    "externalIds",
    "s2FieldsOfStudy",
    "url",
]


class SemanticScholarCollector(BaseCollector):
    """Collector for papers from Semantic Scholar API.

    Semantic Scholar provides:
    - Paper search by keywords/topics
    - Author information and papers
    - Citation metrics (citationCount, influentialCitationCount)
    - Paper recommendations based on seed papers
    - Fields of study classification

    API Docs: https://api.semanticscholar.org/api-docs/
    """

    def __init__(self, settings: Optional[SemanticScholarSettings] = None):
        """Initialize the Semantic Scholar collector.

        Args:
            settings: Semantic Scholar configuration settings
        """
        self.settings = settings or get_settings().semantic_scholar
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = asyncio.Semaphore(1)
        self._last_request_time: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"User-Agent": "PaperPulse/1.0 (Academic Paper Aggregator)"}
            api_key = self.settings.api_key.get_secret_value()
            if api_key:
                headers["x-api-key"] = api_key

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.timeout_seconds),
                headers=headers,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        async with self._rate_limiter:
            now = asyncio.get_event_loop().time()
            min_interval = 1.0 / self.settings.rate_limit_per_second
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        """Make a rate-limited request to the API.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data

        Returns:
            Response JSON as dict
        """
        await self._rate_limit()
        client = await self._get_client()

        url = f"{self.settings.base_url}{endpoint}"
        response = await client.request(method, url, params=params, json=json_data)
        response.raise_for_status()

        return response.json()

    def _parse_paper(self, data: dict) -> CollectedPaper:
        """Parse Semantic Scholar paper data into CollectedPaper.

        Args:
            data: Paper data from API response

        Returns:
            CollectedPaper instance
        """
        # Extract authors
        authors = []
        for author in data.get("authors", []):
            name = author.get("name", "")
            if name:
                authors.append(name)

        # Extract external IDs
        external_ids = data.get("externalIds", {}) or {}
        doi = external_ids.get("DOI")
        arxiv_id = external_ids.get("ArXiv")
        pubmed_id = external_ids.get("PubMed")

        # Parse publication date
        published_date = None
        pub_date_str = data.get("publicationDate")
        if pub_date_str:
            try:
                published_date = datetime.strptime(pub_date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

        # Extract fields of study
        fields_of_study = []
        for field in data.get("s2FieldsOfStudy", []) or []:
            category = field.get("category", "")
            if category:
                fields_of_study.append(category)

        # Build URL
        url = data.get("url") or f"https://www.semanticscholar.org/paper/{data.get('paperId', '')}"

        return CollectedPaper(
            title=data.get("title", "Untitled"),
            url=url,
            authors=authors,
            abstract=data.get("abstract"),
            doi=doi,
            arxiv_id=arxiv_id,
            pubmed_id=pubmed_id,
            semantic_scholar_id=data.get("paperId"),
            journal=data.get("venue"),
            venue=data.get("venue"),
            published_date=published_date,
            year=data.get("year"),
            citation_count=data.get("citationCount"),
            influential_citation_count=data.get("influentialCitationCount"),
            fields_of_study=fields_of_study,
            source_type="semantic_scholar",
        )

    async def search_papers(
        self,
        query: str,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        fields_of_study: Optional[list[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CollectedPaper]:
        """Search for papers by keyword query.

        Args:
            query: Search query string
            year_start: Filter papers published after this year
            year_end: Filter papers published before this year
            fields_of_study: Filter by fields (e.g., ["Computer Science", "Medicine"])
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of CollectedPaper instances
        """
        log = logger.bind(query=query, limit=limit)
        log.info("Searching Semantic Scholar")

        params = {
            "query": query,
            "limit": min(limit, self.settings.max_results_per_query),
            "offset": offset,
            "fields": ",".join(DEFAULT_FIELDS),
        }

        # Add year filter
        if year_start or year_end:
            year_filter = f"{year_start or ''}-{year_end or ''}"
            params["year"] = year_filter

        # Add fields of study filter
        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)

        try:
            data = await self._request("GET", "/paper/search", params=params)
            papers = []

            for paper_data in data.get("data", []):
                try:
                    paper = self._parse_paper(paper_data)
                    papers.append(paper)
                except Exception as e:
                    log.warning("Failed to parse paper", error=str(e))

            log.info("Search complete", paper_count=len(papers))
            return papers

        except httpx.HTTPStatusError as e:
            log.error("Search failed", status=e.response.status_code)
            return []

    async def get_paper(self, paper_id: str) -> Optional[CollectedPaper]:
        """Get a single paper by its Semantic Scholar ID.

        Args:
            paper_id: Semantic Scholar paper ID

        Returns:
            CollectedPaper or None if not found
        """
        log = logger.bind(paper_id=paper_id)

        try:
            params = {"fields": ",".join(DEFAULT_FIELDS)}
            data = await self._request("GET", f"/paper/{paper_id}", params=params)
            return self._parse_paper(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                log.warning("Paper not found")
            else:
                log.error("Get paper failed", status=e.response.status_code)
            return None

    async def get_author_papers(
        self,
        author_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CollectedPaper]:
        """Get papers by a specific author.

        Args:
            author_id: Semantic Scholar author ID
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of CollectedPaper instances
        """
        log = logger.bind(author_id=author_id, limit=limit)
        log.info("Fetching author papers")

        params = {
            "limit": min(limit, self.settings.max_results_per_query),
            "offset": offset,
            "fields": ",".join(DEFAULT_FIELDS),
        }

        try:
            data = await self._request("GET", f"/author/{author_id}/papers", params=params)
            papers = []

            for paper_data in data.get("data", []):
                try:
                    paper = self._parse_paper(paper_data)
                    papers.append(paper)
                except Exception as e:
                    log.warning("Failed to parse paper", error=str(e))

            log.info("Fetch complete", paper_count=len(papers))
            return papers

        except httpx.HTTPStatusError as e:
            log.error("Fetch author papers failed", status=e.response.status_code)
            return []

    async def get_recommendations(
        self,
        paper_ids: list[str],
        limit: int = 20,
    ) -> list[CollectedPaper]:
        """Get paper recommendations based on seed papers.

        Args:
            paper_ids: List of Semantic Scholar paper IDs to base recommendations on
            limit: Maximum number of recommendations

        Returns:
            List of recommended CollectedPaper instances
        """
        log = logger.bind(seed_count=len(paper_ids), limit=limit)
        log.info("Fetching paper recommendations")

        if not paper_ids:
            return []

        params = {
            "limit": min(limit, self.settings.max_results_per_query),
            "fields": ",".join(DEFAULT_FIELDS),
        }

        json_data = {"positivePaperIds": paper_ids[:5]}  # API limits to 5 seeds

        try:
            data = await self._request(
                "POST", "/recommendations/v1/papers", params=params, json_data=json_data
            )
            papers = []

            for paper_data in data.get("recommendedPapers", []):
                try:
                    paper = self._parse_paper(paper_data)
                    papers.append(paper)
                except Exception as e:
                    log.warning("Failed to parse paper", error=str(e))

            log.info("Recommendations complete", paper_count=len(papers))
            return papers

        except httpx.HTTPStatusError as e:
            log.error("Recommendations failed", status=e.response.status_code)
            return []

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
            feed_url: Search query to execute
            feed_name: Human-readable feed name
            **kwargs: Additional search parameters (year_start, year_end, etc.)

        Returns:
            CollectorResult with collected papers
        """
        log = logger.bind(feed_id=feed_id, query=feed_url)
        log.info("Collecting from Semantic Scholar")

        try:
            papers = await self.search_papers(
                query=feed_url,
                year_start=kwargs.get("year_start"),
                year_end=kwargs.get("year_end"),
                fields_of_study=kwargs.get("fields_of_study"),
                limit=kwargs.get("limit", self.settings.max_results_per_query),
            )

            # Set source feed ID
            for paper in papers:
                paper.source_feed_id = feed_id

            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name or f"Semantic Scholar: {feed_url}",
                papers=papers,
            )

        except Exception as e:
            log.error("Collection failed", error=str(e))
            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name or f"Semantic Scholar: {feed_url}",
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
            papers = await self.search_papers(query=feed_url, limit=1)
            if not papers:
                return False, "Query returned no results"
            return True, None

        except httpx.HTTPStatusError as e:
            return False, f"HTTP {e.response.status_code}: {e.response.reason_phrase}"

        except Exception as e:
            return False, f"Unexpected error: {e}"
