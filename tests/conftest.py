"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_rss_feed() -> str:
    """Sample RSS feed XML for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/">
  <channel>
    <title>Journal of Chemical Theory and Computation</title>
    <link>https://pubs.acs.org/journal/jctcce</link>
    <description>Recent articles from JCTC</description>
    <item>
      <title>Machine Learning Collective Variables for Enhanced Sampling</title>
      <link>https://pubs.acs.org/doi/10.1021/acs.jctc.2024.001</link>
      <description>We present a novel approach to learning collective variables using neural networks for enhanced sampling molecular dynamics simulations.</description>
      <dc:creator>John Smith</dc:creator>
      <dc:creator>Jane Doe</dc:creator>
      <prism:doi>10.1021/acs.jctc.2024.001</prism:doi>
      <prism:publicationName>Journal of Chemical Theory and Computation</prism:publicationName>
      <pubDate>Mon, 15 Jan 2024 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Polymer Dynamics Simulations with GROMACS</title>
      <link>https://pubs.acs.org/doi/10.1021/acs.jctc.2024.002</link>
      <description>A comprehensive study of polymer chain dynamics using molecular dynamics simulations.</description>
      <dc:creator>Alice Johnson</dc:creator>
      <prism:doi>10.1021/acs.jctc.2024.002</prism:doi>
      <prism:publicationName>Journal of Chemical Theory and Computation</prism:publicationName>
      <pubDate>Tue, 16 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def sample_atom_feed() -> str:
    """Sample Atom feed XML for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ACS Applied Materials &amp; Interfaces</title>
  <link href="https://pubs.acs.org/journal/aamick"/>
  <entry>
    <title>Nanocomposite Materials for Energy Storage</title>
    <link href="https://pubs.acs.org/doi/10.1021/acsami.2024.001"/>
    <summary>Novel nanocomposite materials for next-generation batteries.</summary>
    <author>
      <name>Bob Wilson</name>
    </author>
    <author>
      <name>Carol Brown</name>
    </author>
    <published>2024-01-17T00:00:00Z</published>
  </entry>
</feed>"""


@pytest.fixture
def invalid_xml() -> str:
    """Invalid XML for testing error handling."""
    return """<?xml version="1.0"?>
<rss>
  <channel>
    <title>Broken Feed
    <!-- Missing closing tags -->
"""


@pytest.fixture
def empty_feed() -> str:
    """Empty RSS feed for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty Feed</title>
    <link>https://example.com</link>
  </channel>
</rss>"""
