"""Pre-configured ACS (American Chemical Society) journal RSS feeds.

ACS provides RSS feeds for new articles at:
https://pubs.acs.org/page/follow.html

Feed URL pattern: https://pubs.acs.org/action/showFeed?type=axatoc&feed=rss&jc={journal_code}
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ACSFeedConfig:
    """Configuration for an ACS journal RSS feed."""

    journal_code: str
    journal_name: str
    description: str
    categories: list[str]  # For filtering by research area

    @property
    def feed_url(self) -> str:
        """Generate the RSS feed URL."""
        return f"https://pubs.acs.org/action/showFeed?type=axatoc&feed=rss&jc={self.journal_code}"

    @property
    def display_name(self) -> str:
        """Display name for the feed."""
        return f"ACS - {self.journal_name}"


# Comprehensive list of ACS journals relevant to materials science, chemistry, and AI
ACS_FEEDS: dict[str, ACSFeedConfig] = {
    # Materials Science & Engineering
    "acsami": ACSFeedConfig(
        journal_code="aamick",
        journal_name="ACS Applied Materials & Interfaces",
        description="Functional materials, interfaces, surfaces, and devices",
        categories=["materials", "interfaces", "polymers"],
    ),
    "acsapm": ACSFeedConfig(
        journal_code="aapmcd",
        journal_name="ACS Applied Polymer Materials",
        description="Polymer synthesis, characterization, and applications",
        categories=["polymers", "materials"],
    ),
    "macromolecules": ACSFeedConfig(
        journal_code="mamobx",
        journal_name="Macromolecules",
        description="Polymer synthesis, theory, and characterization",
        categories=["polymers", "theory", "synthesis"],
    ),
    "biomac": ACSFeedConfig(
        journal_code="bomaf6",
        journal_name="Biomacromolecules",
        description="Biopolymers and biomaterials",
        categories=["polymers", "biomaterials"],
    ),
    "langmuir": ACSFeedConfig(
        journal_code="langd5",
        journal_name="Langmuir",
        description="Surfaces, interfaces, colloids, and soft matter",
        categories=["surfaces", "interfaces", "soft-matter"],
    ),
    "nanoletters": ACSFeedConfig(
        journal_code="nalefd",
        journal_name="Nano Letters",
        description="Nanoscience and nanotechnology",
        categories=["nanomaterials", "materials"],
    ),
    "acsnano": ACSFeedConfig(
        journal_code="ancac3",
        journal_name="ACS Nano",
        description="Nanoscale materials and devices",
        categories=["nanomaterials", "materials"],
    ),
    "chemmater": ACSFeedConfig(
        journal_code="cmatex",
        journal_name="Chemistry of Materials",
        description="Materials chemistry and synthesis",
        categories=["materials", "synthesis"],
    ),
    # Physical Chemistry & Computation
    "jpcb": ACSFeedConfig(
        journal_code="jpcbfk",
        journal_name="J. Physical Chemistry B",
        description="Soft matter, biological systems, polymers",
        categories=["physical-chemistry", "soft-matter", "polymers", "simulations"],
    ),
    "jpca": ACSFeedConfig(
        journal_code="jpcafh",
        journal_name="J. Physical Chemistry A",
        description="Spectroscopy, dynamics, theory",
        categories=["physical-chemistry", "spectroscopy", "theory"],
    ),
    "jpcc": ACSFeedConfig(
        journal_code="jpccck",
        journal_name="J. Physical Chemistry C",
        description="Surfaces, interfaces, nanomaterials",
        categories=["physical-chemistry", "surfaces", "nanomaterials"],
    ),
    "jpclett": ACSFeedConfig(
        journal_code="jpclcd",
        journal_name="J. Physical Chemistry Letters",
        description="Communications in physical chemistry",
        categories=["physical-chemistry", "theory"],
    ),
    "jctc": ACSFeedConfig(
        journal_code="jctcce",
        journal_name="J. Chemical Theory and Computation",
        description="Computational chemistry, molecular dynamics, ML",
        categories=["computation", "simulations", "machine-learning", "theory"],
    ),
    "jcim": ACSFeedConfig(
        journal_code="jcisd8",
        journal_name="J. Chemical Information and Modeling",
        description="Cheminformatics, ML, molecular modeling",
        categories=["computation", "machine-learning", "modeling"],
    ),
    # General Chemistry
    "jacs": ACSFeedConfig(
        journal_code="jacsat",
        journal_name="J. American Chemical Society",
        description="Premier general chemistry journal",
        categories=["general", "synthesis", "materials"],
    ),
    "acscentral": ACSFeedConfig(
        journal_code="acscii",
        journal_name="ACS Central Science",
        description="Multidisciplinary chemistry research",
        categories=["general", "multidisciplinary"],
    ),
    # Energy
    "acsenergyletter": ACSFeedConfig(
        journal_code="aelccp",
        journal_name="ACS Energy Letters",
        description="Energy conversion and storage",
        categories=["energy", "materials"],
    ),
    "acsaem": ACSFeedConfig(
        journal_code="aaemcq",
        journal_name="ACS Applied Energy Materials",
        description="Energy materials and devices",
        categories=["energy", "materials"],
    ),
    # Catalysis
    "acscatal": ACSFeedConfig(
        journal_code="accacs",
        journal_name="ACS Catalysis",
        description="Heterogeneous, homogeneous, and biocatalysis",
        categories=["catalysis", "materials"],
    ),
    # Sustainability
    "suschemeng": ACSFeedConfig(
        journal_code="ascecg",
        journal_name="ACS Sustainable Chemistry & Engineering",
        description="Green chemistry and sustainability",
        categories=["sustainability", "green-chemistry"],
    ),
}


def get_feeds_by_category(category: str) -> list[ACSFeedConfig]:
    """Get all feeds matching a category.

    Args:
        category: Category to filter by

    Returns:
        List of matching feed configurations
    """
    return [feed for feed in ACS_FEEDS.values() if category in feed.categories]


def get_polymer_md_feeds() -> list[ACSFeedConfig]:
    """Get feeds relevant to polymer molecular dynamics simulations."""
    relevant_codes = [
        "jctc",  # J. Chem. Theory Comput. - MD methods, enhanced sampling
        "jpcb",  # J. Phys. Chem. B - Soft matter, polymers
        "macromolecules",  # Macromolecules - Polymer theory
        "acsapm",  # ACS Applied Polymer Materials
        "langmuir",  # Langmuir - Soft matter interfaces
        "jcim",  # J. Chem. Info. Model. - ML for chemistry
    ]
    return [ACS_FEEDS[code] for code in relevant_codes if code in ACS_FEEDS]


def get_ml_chemistry_feeds() -> list[ACSFeedConfig]:
    """Get feeds relevant to machine learning in chemistry."""
    relevant_codes = [
        "jctc",  # J. Chem. Theory Comput.
        "jcim",  # J. Chem. Info. Model.
        "jpclett",  # J. Phys. Chem. Letters
    ]
    return [ACS_FEEDS[code] for code in relevant_codes if code in ACS_FEEDS]


def get_all_feed_urls() -> dict[str, str]:
    """Get a mapping of feed names to URLs.

    Returns:
        Dict mapping display names to feed URLs
    """
    return {feed.display_name: feed.feed_url for feed in ACS_FEEDS.values()}


def get_feed_by_code(code: str) -> Optional[ACSFeedConfig]:
    """Get a specific feed configuration by journal code.

    Args:
        code: Short journal code (e.g., 'jctc', 'macromolecules')

    Returns:
        Feed configuration or None if not found
    """
    return ACS_FEEDS.get(code)
