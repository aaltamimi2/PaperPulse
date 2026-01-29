"""PubMed/NCBI Entrez API collector for academic papers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from paperpulse.collectors.base import BaseCollector, CollectedPaper, CollectorResult
from paperpulse.core.config import PubMedSettings, get_settings

logger = structlog.get_logger(__name__)

# PubMed E-utilities base URL
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedCollector(BaseCollector):
    """Collector for papers from PubMed using NCBI E-utilities.

    PubMed provides:
    - Medical and life sciences literature
    - MeSH (Medical Subject Headings) term search
    - Date-range filtering
    - Abstract retrieval

    API Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
    """

    def __init__(self, settings: Optional[PubMedSettings] = None):
        """Initialize the PubMed collector.

        Args:
            settings: PubMed configuration settings
        """
        self.settings = settings or get_settings().pubmed
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = asyncio.Semaphore(1)
        self._last_request_time: float = 0
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.timeout_seconds),
                headers={"User-Agent": f"{self.settings.tool_name}/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and executor."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
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

    def _get_base_params(self) -> dict:
        """Get base parameters for NCBI requests."""
        params = {
            "tool": self.settings.tool_name,
            "email": self.settings.email,
        }
        api_key = self.settings.api_key.get_secret_value()
        if api_key:
            params["api_key"] = api_key
        return params

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _request(self, endpoint: str, params: dict) -> str:
        """Make a rate-limited request to E-utilities.

        Args:
            endpoint: E-utilities endpoint (esearch.fcgi, efetch.fcgi, etc.)
            params: Query parameters

        Returns:
            Response text
        """
        await self._rate_limit()
        client = await self._get_client()

        url = f"{EUTILS_BASE}/{endpoint}"
        all_params = {**self._get_base_params(), **params}
        response = await client.get(url, params=all_params)
        response.raise_for_status()

        return response.text

    async def _search_ids(
        self,
        query: str,
        limit: int = 100,
        days_back: Optional[int] = None,
    ) -> list[str]:
        """Search PubMed and return PMIDs.

        Args:
            query: PubMed search query
            limit: Maximum number of results
            days_back: Limit to papers published in last N days

        Returns:
            List of PubMed IDs (PMIDs)
        """
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": min(limit, self.settings.max_results_per_query),
            "retmode": "xml",
            "sort": "pub_date",
        }

        # Add date filter
        if days_back:
            params["reldate"] = days_back
            params["datetype"] = "edat"  # Entrez date

        xml_text = await self._request("esearch.fcgi", params)

        # Parse XML response
        root = ElementTree.fromstring(xml_text)
        id_list = root.find("IdList")
        if id_list is None:
            return []

        return [id_elem.text for id_elem in id_list.findall("Id") if id_elem.text]

    async def _fetch_papers(self, pmids: list[str]) -> list[dict]:
        """Fetch paper details for given PMIDs.

        Args:
            pmids: List of PubMed IDs

        Returns:
            List of paper data dicts
        """
        if not pmids:
            return []

        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }

        xml_text = await self._request("efetch.fcgi", params)

        # Parse XML response
        papers = []
        root = ElementTree.fromstring(xml_text)

        for article in root.findall(".//PubmedArticle"):
            try:
                paper_data = self._parse_article(article)
                if paper_data:
                    papers.append(paper_data)
            except Exception as e:
                logger.warning("Failed to parse PubMed article", error=str(e))

        return papers

    def _parse_article(self, article: ElementTree.Element) -> Optional[dict]:
        """Parse a PubmedArticle XML element.

        Args:
            article: PubmedArticle XML element

        Returns:
            Parsed paper data dict
        """
        medline = article.find("MedlineCitation")
        if medline is None:
            return None

        pmid_elem = medline.find("PMID")
        pmid = pmid_elem.text if pmid_elem is not None else None

        article_elem = medline.find("Article")
        if article_elem is None:
            return None

        # Title
        title_elem = article_elem.find("ArticleTitle")
        title = "".join(title_elem.itertext()) if title_elem is not None else "Untitled"

        # Abstract
        abstract = None
        abstract_elem = article_elem.find("Abstract")
        if abstract_elem is not None:
            abstract_parts = []
            for text_elem in abstract_elem.findall("AbstractText"):
                label = text_elem.get("Label", "")
                text = "".join(text_elem.itertext())
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            abstract = " ".join(abstract_parts)

        # Authors
        authors = []
        author_list = article_elem.find("AuthorList")
        if author_list is not None:
            for author in author_list.findall("Author"):
                last_name = author.findtext("LastName", "")
                fore_name = author.findtext("ForeName", "")
                if last_name:
                    name = f"{fore_name} {last_name}".strip()
                    authors.append(name)

        # Journal
        journal_elem = article_elem.find("Journal")
        journal = None
        if journal_elem is not None:
            journal = journal_elem.findtext("Title")

        # Publication date
        pub_date = None
        pub_date_elem = article_elem.find(".//PubDate")
        if pub_date_elem is not None:
            year = pub_date_elem.findtext("Year")
            month = pub_date_elem.findtext("Month", "01")
            day = pub_date_elem.findtext("Day", "01")

            if year:
                # Convert month name to number if needed
                month_map = {
                    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
                }
                month = month_map.get(month, month)

                try:
                    pub_date = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    try:
                        pub_date = datetime.strptime(f"{year}-{month}-01", "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                    except ValueError:
                        pass

        # DOI
        doi = None
        article_ids = article.find(".//ArticleIdList")
        if article_ids is not None:
            for id_elem in article_ids.findall("ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = id_elem.text
                    break

        # MeSH terms (as fields of study)
        mesh_terms = []
        mesh_list = medline.find("MeshHeadingList")
        if mesh_list is not None:
            for mesh in mesh_list.findall("MeshHeading"):
                descriptor = mesh.find("DescriptorName")
                if descriptor is not None and descriptor.text:
                    mesh_terms.append(descriptor.text)

        return {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "journal": journal,
            "pub_date": pub_date,
            "doi": doi,
            "mesh_terms": mesh_terms,
            "year": pub_date.year if pub_date else None,
        }

    def _to_collected_paper(self, data: dict) -> CollectedPaper:
        """Convert parsed data to CollectedPaper.

        Args:
            data: Parsed paper data dict

        Returns:
            CollectedPaper instance
        """
        pmid = data.get("pmid", "")
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

        return CollectedPaper(
            title=data.get("title", "Untitled"),
            url=url,
            authors=data.get("authors", []),
            abstract=data.get("abstract"),
            doi=data.get("doi"),
            pubmed_id=pmid,
            journal=data.get("journal"),
            published_date=data.get("pub_date"),
            year=data.get("year"),
            fields_of_study=data.get("mesh_terms", []),
            source_type="pubmed",
        )

    async def search_papers(
        self,
        query: str,
        mesh_terms: Optional[list[str]] = None,
        days_back: Optional[int] = None,
        limit: int = 100,
    ) -> list[CollectedPaper]:
        """Search PubMed for papers.

        Args:
            query: Search query string
            mesh_terms: MeSH terms to include in search
            days_back: Limit to papers published in last N days
            limit: Maximum number of results

        Returns:
            List of CollectedPaper instances
        """
        log = logger.bind(query=query, limit=limit)
        log.info("Searching PubMed")

        # Build query with MeSH terms
        full_query = query
        if mesh_terms:
            mesh_query = " OR ".join(f'"{term}"[MeSH Terms]' for term in mesh_terms)
            full_query = f"({query}) AND ({mesh_query})"

        try:
            # First, search for PMIDs
            pmids = await self._search_ids(full_query, limit=limit, days_back=days_back)
            log.debug("Found PMIDs", count=len(pmids))

            if not pmids:
                return []

            # Fetch paper details in batches
            batch_size = 100
            all_papers = []

            for i in range(0, len(pmids), batch_size):
                batch = pmids[i : i + batch_size]
                papers_data = await self._fetch_papers(batch)
                all_papers.extend(papers_data)

            # Convert to CollectedPaper
            papers = [self._to_collected_paper(data) for data in all_papers]

            log.info("Search complete", paper_count=len(papers))
            return papers

        except Exception as e:
            log.error("Search failed", error=str(e))
            return []

    async def get_paper(self, pmid: str) -> Optional[CollectedPaper]:
        """Get a single paper by PubMed ID.

        Args:
            pmid: PubMed ID

        Returns:
            CollectedPaper or None if not found
        """
        log = logger.bind(pmid=pmid)

        try:
            papers_data = await self._fetch_papers([pmid])
            if not papers_data:
                log.warning("Paper not found")
                return None

            return self._to_collected_paper(papers_data[0])

        except Exception as e:
            log.error("Get paper failed", error=str(e))
            return None

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
            **kwargs: Additional search parameters (mesh_terms, days_back, etc.)

        Returns:
            CollectorResult with collected papers
        """
        log = logger.bind(feed_id=feed_id, query=feed_url)
        log.info("Collecting from PubMed")

        if not self.settings.email:
            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name or f"PubMed: {feed_url}",
                error="PubMed requires an email address. Set PUBMED_EMAIL in environment.",
            )

        try:
            papers = await self.search_papers(
                query=feed_url,
                mesh_terms=kwargs.get("mesh_terms"),
                days_back=kwargs.get("days_back"),
                limit=kwargs.get("limit", self.settings.max_results_per_query),
            )

            # Set source feed ID
            for paper in papers:
                paper.source_feed_id = feed_id

            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name or f"PubMed: {feed_url}",
                papers=papers,
            )

        except Exception as e:
            log.error("Collection failed", error=str(e))
            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name or f"PubMed: {feed_url}",
                error=str(e),
            )

    async def validate_feed(self, feed_url: str) -> tuple[bool, Optional[str]]:
        """Validate that a search query returns results.

        Args:
            feed_url: Search query to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.settings.email:
            return False, "PubMed requires an email address. Set PUBMED_EMAIL in environment."

        try:
            pmids = await self._search_ids(query=feed_url, limit=1)
            if not pmids:
                return False, "Query returned no results"
            return True, None

        except httpx.HTTPStatusError as e:
            return False, f"HTTP {e.response.status_code}: {e.response.reason_phrase}"

        except Exception as e:
            return False, f"Unexpected error: {e}"
