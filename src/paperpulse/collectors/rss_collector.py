"""RSS feed collector for academic papers."""

import re
from datetime import datetime, timezone
from typing import Optional
from xml.etree.ElementTree import ParseError

import feedparser
import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from paperpulse.collectors.base import BaseCollector, CollectedPaper, CollectorResult
from paperpulse.core.config import RSSSettings, get_settings

logger = structlog.get_logger(__name__)


class RSSCollector(BaseCollector):
    """Collector for RSS/Atom feeds from academic publishers."""

    def __init__(self, settings: Optional[RSSSettings] = None):
        """Initialize the RSS collector.

        Args:
            settings: RSS configuration settings
        """
        self.settings = settings or get_settings().rss
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.fetch_timeout_seconds),
                headers={"User-Agent": self.settings.user_agent},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _fetch_feed(
        self,
        url: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> tuple[str, dict[str, str]]:
        """Fetch feed content with conditional GET support.

        Args:
            url: Feed URL
            etag: Previous ETag for conditional request
            last_modified: Previous Last-Modified for conditional request

        Returns:
            Tuple of (content, response_headers)
        """
        client = await self._get_client()

        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        response = await client.get(url, headers=headers)

        if response.status_code == 304:
            # Not modified
            return "", {"status": "304"}

        response.raise_for_status()

        return response.text, {
            "etag": response.headers.get("ETag", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
        }

    def _parse_feed(self, content: str) -> feedparser.FeedParserDict:
        """Parse RSS/Atom feed content.

        Args:
            content: Raw feed XML content

        Returns:
            Parsed feed dictionary
        """
        feed = feedparser.parse(content)

        if feed.bozo and not feed.entries:
            # Feed parsing failed completely
            error = feed.bozo_exception
            if isinstance(error, ParseError):
                raise ValueError(f"Invalid XML: {error}")
            raise ValueError(f"Feed parsing error: {error}")

        return feed

    def _extract_doi(self, entry: dict) -> Optional[str]:
        """Extract DOI from feed entry."""
        # Check dc:identifier or prism:doi
        for key in ["dc_identifier", "prism_doi", "doi"]:
            if key in entry:
                doi = entry[key]
                if doi.startswith("10."):
                    return doi
                # Extract DOI from URL
                match = re.search(r"10\.\d{4,}/[^\s]+", doi)
                if match:
                    return match.group(0)

        # Check links for DOI
        for link in entry.get("links", []):
            href = link.get("href", "")
            if "doi.org" in href:
                match = re.search(r"10\.\d{4,}/[^\s]+", href)
                if match:
                    return match.group(0)

        return None

    def _extract_authors(self, entry: dict) -> list[str]:
        """Extract author names from feed entry."""
        authors = []

        # Check authors field (Atom)
        if "authors" in entry:
            for author in entry["authors"]:
                name = author.get("name", "")
                if name:
                    authors.append(name)

        # Check author field (RSS)
        elif "author" in entry:
            authors.append(entry["author"])

        # Check dc:creator
        elif "dc_creator" in entry:
            creator = entry["dc_creator"]
            if isinstance(creator, list):
                authors.extend(creator)
            else:
                authors.append(creator)

        return authors

    def _extract_abstract(self, entry: dict) -> Optional[str]:
        """Extract abstract from feed entry."""
        # Check description/summary
        for key in ["summary", "description", "dc_description"]:
            if key in entry:
                content = entry[key]
                if isinstance(content, dict):
                    content = content.get("value", "")
                if content:
                    # Clean HTML tags (basic)
                    clean = re.sub(r"<[^>]+>", "", content)
                    clean = clean.strip()
                    if len(clean) > 50:  # Skip very short descriptions
                        return clean

        return None

    def _parse_date(self, entry: dict) -> Optional[datetime]:
        """Parse publication date from feed entry."""
        for key in ["published_parsed", "updated_parsed", "dc_date_parsed"]:
            if key in entry and entry[key]:
                try:
                    return datetime(*entry[key][:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue

        # Try parsing date strings
        for key in ["published", "updated", "dc_date", "prism_publicationdate"]:
            if key in entry:
                try:
                    from dateutil.parser import parse

                    return parse(entry[key])
                except (ValueError, TypeError):
                    continue

        return None

    def _entry_to_paper(
        self,
        entry: dict,
        feed_id: str,
        journal_name: Optional[str] = None,
    ) -> CollectedPaper:
        """Convert a feed entry to a CollectedPaper.

        Args:
            entry: Parsed feed entry
            feed_id: Source feed ID
            journal_name: Journal name to use if not in entry

        Returns:
            CollectedPaper instance
        """
        # Get URL (prefer DOI link)
        url = entry.get("link", "")
        for link in entry.get("links", []):
            if "doi.org" in link.get("href", ""):
                url = link["href"]
                break

        return CollectedPaper(
            title=entry.get("title", "Untitled"),
            url=url,
            authors=self._extract_authors(entry),
            abstract=self._extract_abstract(entry),
            doi=self._extract_doi(entry),
            journal=entry.get("prism_publicationname") or journal_name,
            published_date=self._parse_date(entry),
            source_feed_id=feed_id,
        )

    async def collect(
        self,
        feed_id: str,
        feed_url: str,
        feed_name: str = "",
        journal_name: Optional[str] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> CollectorResult:
        """Collect papers from an RSS feed.

        Args:
            feed_id: Database ID of the feed
            feed_url: URL of the RSS feed
            feed_name: Human-readable feed name
            journal_name: Journal name for papers
            etag: Previous ETag for conditional request
            last_modified: Previous Last-Modified for conditional request

        Returns:
            CollectorResult with collected papers
        """
        log = logger.bind(feed_id=feed_id, feed_url=feed_url)

        try:
            log.info("Fetching RSS feed")
            content, headers = await self._fetch_feed(feed_url, etag, last_modified)

            if headers.get("status") == "304":
                log.info("Feed not modified since last fetch")
                return CollectorResult(
                    feed_id=feed_id,
                    feed_name=feed_name,
                    papers=[],
                )

            log.debug("Parsing feed content")
            feed = self._parse_feed(content)

            # Extract journal name from feed if not provided
            if not journal_name:
                journal_name = feed.feed.get("title", "")

            papers = []
            for entry in feed.entries:
                try:
                    paper = self._entry_to_paper(entry, feed_id, journal_name)
                    papers.append(paper)
                except Exception as e:
                    log.warning("Failed to parse entry", error=str(e), entry_title=entry.get("title"))

            log.info("Feed collection complete", paper_count=len(papers))

            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name,
                papers=papers,
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
            log.error("Feed fetch failed", error=error_msg)
            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name,
                error=error_msg,
            )

        except Exception as e:
            log.error("Feed collection failed", error=str(e))
            return CollectorResult(
                feed_id=feed_id,
                feed_name=feed_name,
                error=str(e),
            )

    async def validate_feed(self, feed_url: str) -> tuple[bool, Optional[str]]:
        """Validate that a feed URL is accessible and valid.

        Args:
            feed_url: URL to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            content, _ = await self._fetch_feed(feed_url)
            feed = self._parse_feed(content)

            if not feed.entries:
                return False, "Feed contains no entries"

            return True, None

        except httpx.HTTPStatusError as e:
            return False, f"HTTP {e.response.status_code}: {e.response.reason_phrase}"

        except ValueError as e:
            return False, str(e)

        except Exception as e:
            return False, f"Unexpected error: {e}"
