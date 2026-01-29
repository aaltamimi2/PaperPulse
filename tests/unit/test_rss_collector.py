"""Unit tests for RSS collector."""

import pytest
import respx
from httpx import Response

from paperpulse.collectors.base import CollectedPaper
from paperpulse.collectors.rss_collector import RSSCollector


class TestCollectedPaper:
    """Tests for CollectedPaper dataclass."""

    def test_content_hash_with_doi(self) -> None:
        """Content hash should use DOI when available."""
        paper = CollectedPaper(
            title="Test Paper",
            url="https://example.com/paper",
            doi="10.1021/test.123",
        )
        hash1 = paper.content_hash()

        paper2 = CollectedPaper(
            title="Different Title",
            url="https://different.com/paper",
            doi="10.1021/test.123",
        )
        hash2 = paper2.content_hash()

        assert hash1 == hash2

    def test_content_hash_without_doi(self) -> None:
        """Content hash should use title + author when no DOI."""
        paper = CollectedPaper(
            title="Test Paper",
            url="https://example.com/paper",
            authors=["John Smith"],
        )
        hash1 = paper.content_hash()

        paper2 = CollectedPaper(
            title="test paper",  # lowercase
            url="https://different.com",
            authors=["john smith"],  # lowercase
        )
        hash2 = paper2.content_hash()

        assert hash1 == hash2

    def test_content_hash_different_papers(self) -> None:
        """Different papers should have different hashes."""
        paper1 = CollectedPaper(
            title="Paper One",
            url="https://example.com/1",
            authors=["Author A"],
        )
        paper2 = CollectedPaper(
            title="Paper Two",
            url="https://example.com/2",
            authors=["Author B"],
        )

        assert paper1.content_hash() != paper2.content_hash()


class TestRSSCollector:
    """Tests for RSSCollector."""

    @pytest.fixture
    def collector(self) -> RSSCollector:
        """Create a collector instance."""
        return RSSCollector()

    @pytest.mark.asyncio
    @respx.mock
    async def test_collect_success(
        self,
        collector: RSSCollector,
        sample_rss_feed: str,
    ) -> None:
        """Collector should parse valid RSS feed."""
        respx.get("https://example.com/feed.rss").mock(
            return_value=Response(200, text=sample_rss_feed)
        )

        result = await collector.collect(
            feed_id="test-feed",
            feed_url="https://example.com/feed.rss",
            feed_name="Test Feed",
        )
        await collector.close()

        assert result.success
        assert result.error is None
        assert len(result.papers) == 2
        assert result.feed_id == "test-feed"
        assert result.feed_name == "Test Feed"

    @pytest.mark.asyncio
    @respx.mock
    async def test_collect_parses_paper_metadata(
        self,
        collector: RSSCollector,
        sample_rss_feed: str,
    ) -> None:
        """Collector should extract paper metadata correctly."""
        respx.get("https://example.com/feed.rss").mock(
            return_value=Response(200, text=sample_rss_feed)
        )

        result = await collector.collect(
            feed_id="test-feed",
            feed_url="https://example.com/feed.rss",
            feed_name="Test Feed",
        )
        await collector.close()

        paper = result.papers[0]
        assert paper.title == "Machine Learning Collective Variables for Enhanced Sampling"
        assert paper.doi == "10.1021/acs.jctc.2024.001"
        assert "John Smith" in paper.authors
        assert "Jane Doe" in paper.authors
        assert "neural networks" in paper.abstract
        assert paper.source_feed_id == "test-feed"

    @pytest.mark.asyncio
    @respx.mock
    async def test_collect_atom_feed(
        self,
        collector: RSSCollector,
        sample_atom_feed: str,
    ) -> None:
        """Collector should handle Atom feeds."""
        respx.get("https://example.com/feed.atom").mock(
            return_value=Response(200, text=sample_atom_feed)
        )

        result = await collector.collect(
            feed_id="test-feed",
            feed_url="https://example.com/feed.atom",
            feed_name="Test Feed",
        )
        await collector.close()

        assert result.success
        assert len(result.papers) == 1
        paper = result.papers[0]
        assert paper.title == "Nanocomposite Materials for Energy Storage"
        assert "Bob Wilson" in paper.authors
        assert "Carol Brown" in paper.authors

    @pytest.mark.asyncio
    @respx.mock
    async def test_collect_http_error(self, collector: RSSCollector) -> None:
        """Collector should handle HTTP errors gracefully."""
        respx.get("https://example.com/feed.rss").mock(
            return_value=Response(404, text="Not Found")
        )

        result = await collector.collect(
            feed_id="test-feed",
            feed_url="https://example.com/feed.rss",
            feed_name="Test Feed",
        )
        await collector.close()

        assert not result.success
        assert "404" in result.error
        assert len(result.papers) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_collect_invalid_xml(
        self,
        collector: RSSCollector,
        invalid_xml: str,
    ) -> None:
        """Collector should handle invalid XML gracefully."""
        respx.get("https://example.com/feed.rss").mock(
            return_value=Response(200, text=invalid_xml)
        )

        result = await collector.collect(
            feed_id="test-feed",
            feed_url="https://example.com/feed.rss",
            feed_name="Test Feed",
        )
        await collector.close()

        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    @respx.mock
    async def test_collect_conditional_get_304(
        self,
        collector: RSSCollector,
    ) -> None:
        """Collector should handle 304 Not Modified."""
        respx.get("https://example.com/feed.rss").mock(
            return_value=Response(304, text="")
        )

        result = await collector.collect(
            feed_id="test-feed",
            feed_url="https://example.com/feed.rss",
            feed_name="Test Feed",
            etag='"abc123"',
        )
        await collector.close()

        assert result.success
        assert len(result.papers) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_feed_valid(
        self,
        collector: RSSCollector,
        sample_rss_feed: str,
    ) -> None:
        """Validate should return True for valid feed."""
        respx.get("https://example.com/feed.rss").mock(
            return_value=Response(200, text=sample_rss_feed)
        )

        is_valid, error = await collector.validate_feed("https://example.com/feed.rss")
        await collector.close()

        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_feed_empty(
        self,
        collector: RSSCollector,
        empty_feed: str,
    ) -> None:
        """Validate should return False for empty feed."""
        respx.get("https://example.com/feed.rss").mock(
            return_value=Response(200, text=empty_feed)
        )

        is_valid, error = await collector.validate_feed("https://example.com/feed.rss")
        await collector.close()

        assert is_valid is False
        assert "no entries" in error.lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_validate_feed_http_error(self, collector: RSSCollector) -> None:
        """Validate should return False for HTTP errors."""
        respx.get("https://example.com/feed.rss").mock(
            return_value=Response(500, text="Server Error")
        )

        is_valid, error = await collector.validate_feed("https://example.com/feed.rss")
        await collector.close()

        assert is_valid is False
        assert "500" in error


class TestRSSCollectorDOIExtraction:
    """Tests for DOI extraction logic."""

    @pytest.fixture
    def collector(self) -> RSSCollector:
        return RSSCollector()

    def test_extract_doi_from_prism_doi(self, collector: RSSCollector) -> None:
        """Should extract DOI from prism:doi field."""
        entry = {"prism_doi": "10.1021/acs.jctc.2024.001"}
        doi = collector._extract_doi(entry)
        assert doi == "10.1021/acs.jctc.2024.001"

    def test_extract_doi_from_dc_identifier(self, collector: RSSCollector) -> None:
        """Should extract DOI from dc:identifier field."""
        entry = {"dc_identifier": "10.1021/acs.jctc.2024.001"}
        doi = collector._extract_doi(entry)
        assert doi == "10.1021/acs.jctc.2024.001"

    def test_extract_doi_from_link(self, collector: RSSCollector) -> None:
        """Should extract DOI from link href."""
        entry = {
            "links": [
                {"href": "https://doi.org/10.1021/acs.jctc.2024.001"}
            ]
        }
        doi = collector._extract_doi(entry)
        assert doi == "10.1021/acs.jctc.2024.001"

    def test_extract_doi_from_url_in_identifier(self, collector: RSSCollector) -> None:
        """Should extract DOI embedded in URL."""
        entry = {"dc_identifier": "https://doi.org/10.1021/acs.jctc.2024.001"}
        doi = collector._extract_doi(entry)
        assert doi == "10.1021/acs.jctc.2024.001"

    def test_extract_doi_none_when_missing(self, collector: RSSCollector) -> None:
        """Should return None when no DOI found."""
        entry = {"title": "Some Paper", "link": "https://example.com/paper"}
        doi = collector._extract_doi(entry)
        assert doi is None
