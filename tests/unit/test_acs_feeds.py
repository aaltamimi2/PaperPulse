"""Unit tests for ACS feeds configuration."""

import pytest

from paperpulse.collectors.acs_feeds import (
    ACS_FEEDS,
    ACSFeedConfig,
    get_feed_by_code,
    get_feeds_by_category,
    get_ml_chemistry_feeds,
    get_polymer_md_feeds,
)


class TestACSFeedConfig:
    """Tests for ACSFeedConfig dataclass."""

    def test_feed_url_generation(self) -> None:
        """Feed URL should be generated correctly."""
        config = ACSFeedConfig(
            journal_code="jctcce",
            journal_name="J. Chemical Theory and Computation",
            description="Computational chemistry",
            categories=["computation"],
        )
        assert config.feed_url == "https://pubs.acs.org/action/showFeed?type=axatoc&feed=rss&jc=jctcce"

    def test_display_name(self) -> None:
        """Display name should include ACS prefix."""
        config = ACSFeedConfig(
            journal_code="test",
            journal_name="Test Journal",
            description="Test",
            categories=[],
        )
        assert config.display_name == "ACS - Test Journal"


class TestACSFeedsRegistry:
    """Tests for ACS feeds registry."""

    def test_all_feeds_have_required_fields(self) -> None:
        """All feeds should have required fields populated."""
        for code, feed in ACS_FEEDS.items():
            assert feed.journal_code, f"Missing journal_code for {code}"
            assert feed.journal_name, f"Missing journal_name for {code}"
            assert feed.description, f"Missing description for {code}"
            assert isinstance(feed.categories, list), f"categories not a list for {code}"

    def test_jctc_feed_exists(self) -> None:
        """JCTC feed should be configured."""
        assert "jctc" in ACS_FEEDS
        feed = ACS_FEEDS["jctc"]
        assert "Theory" in feed.journal_name
        assert "computation" in feed.categories

    def test_macromolecules_feed_exists(self) -> None:
        """Macromolecules feed should be configured."""
        assert "macromolecules" in ACS_FEEDS
        feed = ACS_FEEDS["macromolecules"]
        assert "polymers" in feed.categories


class TestFeedFiltering:
    """Tests for feed filtering functions."""

    def test_get_feeds_by_category_polymers(self) -> None:
        """Should return feeds with 'polymers' category."""
        feeds = get_feeds_by_category("polymers")
        assert len(feeds) > 0
        for feed in feeds:
            assert "polymers" in feed.categories

    def test_get_feeds_by_category_unknown(self) -> None:
        """Should return empty list for unknown category."""
        feeds = get_feeds_by_category("nonexistent-category")
        assert feeds == []

    def test_get_polymer_md_feeds(self) -> None:
        """Should return feeds relevant to polymer MD."""
        feeds = get_polymer_md_feeds()
        assert len(feeds) > 0

        # Should include JCTC
        feed_codes = [f.journal_code for f in feeds]
        # Note: journal_code in config differs from dict key
        journal_names = [f.journal_name for f in feeds]
        assert any("Theory" in name for name in journal_names)

    def test_get_ml_chemistry_feeds(self) -> None:
        """Should return feeds relevant to ML in chemistry."""
        feeds = get_ml_chemistry_feeds()
        assert len(feeds) > 0


class TestFeedLookup:
    """Tests for feed lookup functions."""

    def test_get_feed_by_code_exists(self) -> None:
        """Should return feed config for valid code."""
        feed = get_feed_by_code("jctc")
        assert feed is not None
        assert "Theory" in feed.journal_name

    def test_get_feed_by_code_not_found(self) -> None:
        """Should return None for invalid code."""
        feed = get_feed_by_code("nonexistent")
        assert feed is None

    def test_all_feed_urls_valid(self) -> None:
        """All feed URLs should be valid HTTPS URLs."""
        for code, feed in ACS_FEEDS.items():
            url = feed.feed_url
            assert url.startswith("https://"), f"URL for {code} should be HTTPS"
            assert "pubs.acs.org" in url, f"URL for {code} should be on ACS domain"
