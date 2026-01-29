"""User profile management for PaperPulse."""

import json
from pathlib import Path
from typing import Optional

# Default profile location
PROFILE_PATH = Path.home() / ".paperpulse" / "profile.json"


def get_profile_path() -> Path:
    """Get the profile file path, creating directory if needed."""
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return PROFILE_PATH


def load_profile() -> dict:
    """Load user profile from disk."""
    path = get_profile_path()
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {
        "followed_authors": [],
        "interests": [],
    }


def save_profile(profile: dict) -> None:
    """Save user profile to disk."""
    path = get_profile_path()
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)


def get_followed_authors() -> list[str]:
    """Get list of followed authors."""
    profile = load_profile()
    return profile.get("followed_authors", [])


def add_followed_author(name: str) -> bool:
    """Add an author to the followed list.

    Returns True if added, False if already exists.
    """
    profile = load_profile()
    authors = profile.get("followed_authors", [])

    # Check if already followed (case-insensitive)
    name_lower = name.lower()
    for existing in authors:
        if existing.lower() == name_lower:
            return False

    authors.append(name)
    profile["followed_authors"] = authors
    save_profile(profile)
    return True


def remove_followed_author(name: str) -> bool:
    """Remove an author from the followed list.

    Returns True if removed, False if not found.
    """
    profile = load_profile()
    authors = profile.get("followed_authors", [])

    # Find and remove (case-insensitive)
    name_lower = name.lower()
    for i, existing in enumerate(authors):
        if existing.lower() == name_lower:
            authors.pop(i)
            profile["followed_authors"] = authors
            save_profile(profile)
            return True

    return False


def add_authors_from_suggestions(suggestions: list[str]) -> list[str]:
    """Add multiple authors from suggestions.

    Returns list of authors that were added.
    """
    added = []
    for name in suggestions:
        if add_followed_author(name):
            added.append(name)
    return added


def init_default_authors(authors: list[str]) -> None:
    """Initialize profile with default authors if empty."""
    profile = load_profile()
    if not profile.get("followed_authors"):
        profile["followed_authors"] = authors
        save_profile(profile)
