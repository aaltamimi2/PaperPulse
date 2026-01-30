"""Track paper feedback - read status, thumbs up/down ratings."""

import json
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Feedback storage
FEEDBACK_PATH = Path.home() / ".paperpulse" / "feedback.json"


def get_feedback_path() -> Path:
    """Get the feedback file path, creating directory if needed."""
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    return FEEDBACK_PATH


def load_feedback() -> dict:
    """Load feedback data from disk."""
    path = get_feedback_path()
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {
        "papers": {},  # paper_id -> {read, rating, read_at, rated_at, title, sent_at}
        "tokens": {},  # token -> paper_id (for secure links)
    }


def save_feedback(data: dict) -> None:
    """Save feedback to disk."""
    path = get_feedback_path()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_paper_id(paper: dict) -> str:
    """Generate consistent paper ID."""
    if paper.get("doi"):
        return f"doi:{paper['doi']}"
    if paper.get("arxiv_id"):
        return f"arxiv:{paper['arxiv_id']}"
    title = paper.get("title", "").lower().strip()
    return f"title:{hashlib.md5(title.encode()).hexdigest()[:16]}"


def generate_token(paper_id: str) -> str:
    """Generate a secure token for a paper action."""
    data = load_feedback()
    token = secrets.token_urlsafe(16)
    data["tokens"][token] = paper_id
    save_feedback(data)
    return token


def get_paper_from_token(token: str) -> Optional[str]:
    """Get paper_id from token."""
    data = load_feedback()
    return data.get("tokens", {}).get(token)


def register_paper(paper: dict) -> str:
    """Register a paper and return its ID."""
    data = load_feedback()
    paper_id = get_paper_id(paper)

    if paper_id not in data["papers"]:
        data["papers"][paper_id] = {
            "title": paper.get("title", "Unknown"),
            "url": paper.get("url", ""),
            "sent_at": datetime.now().isoformat(),
            "read": False,
            "rating": None,  # None, "up", or "down"
            "relevance_score": paper.get("relevance_score", 0),
        }
        save_feedback(data)

    return paper_id


def mark_as_read(paper_id: str) -> bool:
    """Mark a paper as read."""
    data = load_feedback()
    if paper_id in data["papers"]:
        data["papers"][paper_id]["read"] = True
        data["papers"][paper_id]["read_at"] = datetime.now().isoformat()
        save_feedback(data)
        return True
    return False


def rate_paper(paper_id: str, rating: str) -> bool:
    """Rate a paper (up/down)."""
    if rating not in ("up", "down"):
        return False

    data = load_feedback()
    if paper_id in data["papers"]:
        data["papers"][paper_id]["rating"] = rating
        data["papers"][paper_id]["rated_at"] = datetime.now().isoformat()
        save_feedback(data)
        return True
    return False


def get_unread_papers(days: int = 7) -> list[dict]:
    """Get unread papers from the last N days."""
    data = load_feedback()
    cutoff = datetime.now() - timedelta(days=days)

    unread = []
    for paper_id, info in data.get("papers", {}).items():
        if info.get("read"):
            continue
        sent_at = datetime.fromisoformat(info.get("sent_at", "2000-01-01"))
        if sent_at > cutoff:
            unread.append({
                "paper_id": paper_id,
                **info
            })

    # Sort by relevance score descending
    unread.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return unread


def get_feedback_stats(days: int = 30) -> dict:
    """Get feedback statistics for tuning."""
    data = load_feedback()
    cutoff = datetime.now() - timedelta(days=days)

    stats = {
        "total_sent": 0,
        "total_read": 0,
        "thumbs_up": 0,
        "thumbs_down": 0,
        "read_rate": 0,
        "positive_rate": 0,
        # For learning: average scores for up vs down rated papers
        "avg_score_thumbs_up": [],
        "avg_score_thumbs_down": [],
    }

    for paper_id, info in data.get("papers", {}).items():
        sent_at = datetime.fromisoformat(info.get("sent_at", "2000-01-01"))
        if sent_at < cutoff:
            continue

        stats["total_sent"] += 1
        if info.get("read"):
            stats["total_read"] += 1

        rating = info.get("rating")
        score = info.get("relevance_score", 0)
        if rating == "up":
            stats["thumbs_up"] += 1
            stats["avg_score_thumbs_up"].append(score)
        elif rating == "down":
            stats["thumbs_down"] += 1
            stats["avg_score_thumbs_down"].append(score)

    if stats["total_sent"] > 0:
        stats["read_rate"] = stats["total_read"] / stats["total_sent"]

    rated = stats["thumbs_up"] + stats["thumbs_down"]
    if rated > 0:
        stats["positive_rate"] = stats["thumbs_up"] / rated

    # Calculate averages
    if stats["avg_score_thumbs_up"]:
        stats["avg_score_thumbs_up"] = sum(stats["avg_score_thumbs_up"]) / len(stats["avg_score_thumbs_up"])
    else:
        stats["avg_score_thumbs_up"] = None

    if stats["avg_score_thumbs_down"]:
        stats["avg_score_thumbs_down"] = sum(stats["avg_score_thumbs_down"]) / len(stats["avg_score_thumbs_down"])
    else:
        stats["avg_score_thumbs_down"] = None

    return stats


def get_keyword_feedback() -> dict:
    """Analyze which keywords correlate with positive/negative feedback."""
    data = load_feedback()

    keyword_stats = {}  # keyword -> {"up": count, "down": count}

    for paper_id, info in data.get("papers", {}).items():
        rating = info.get("rating")
        if not rating:
            continue

        title = info.get("title", "").lower()
        # Extract simple keywords from title
        words = set(title.split())

        for word in words:
            if len(word) < 4:  # Skip short words
                continue
            if word not in keyword_stats:
                keyword_stats[word] = {"up": 0, "down": 0}
            keyword_stats[word][rating] += 1

    return keyword_stats
