"""Paper collectors from various sources."""

from paperpulse.collectors.base import BaseCollector, CollectorResult
from paperpulse.collectors.rss_collector import RSSCollector

__all__ = ["BaseCollector", "CollectorResult", "RSSCollector"]
