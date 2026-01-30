"""Track sent papers to avoid repeating across digest runs."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# History file location
HISTORY_PATH = Path.home() / ".paperpulse" / "sent_papers.json"


def get_history_path() -> Path:
    """Get the history file path, creating directory if needed."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    return HISTORY_PATH


def load_history() -> dict:
    """Load sent papers history from disk."""
    path = get_history_path()
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"sent_papers": {}, "last_run": None}


def save_history(history: dict) -> None:
    """Save history to disk."""
    path = get_history_path()
    with open(path, "w") as f:
        json.dump(history, f, indent=2, default=str)


def get_paper_key(paper: dict) -> str:
    """Generate a unique key for a paper."""
    # Use DOI if available, otherwise title hash
    if paper.get("doi"):
        return f"doi:{paper['doi']}"
    if paper.get("arxiv_id"):
        return f"arxiv:{paper['arxiv_id']}"
    # Fallback to normalized title
    title = paper.get("title", "").lower().strip()
    return f"title:{title[:100]}"


def is_paper_sent(paper: dict, days_to_check: int = 7) -> bool:
    """Check if a paper was already sent within the last N days."""
    history = load_history()
    sent = history.get("sent_papers", {})

    key = get_paper_key(paper)
    if key not in sent:
        return False

    # Check if it was sent within the lookback period
    sent_date = datetime.fromisoformat(sent[key])
    cutoff = datetime.now() - timedelta(days=days_to_check)
    return sent_date > cutoff


def mark_paper_sent(paper: dict) -> None:
    """Mark a paper as sent."""
    history = load_history()
    sent = history.get("sent_papers", {})

    key = get_paper_key(paper)
    sent[key] = datetime.now().isoformat()

    history["sent_papers"] = sent
    save_history(history)


def mark_papers_sent(papers: list[dict]) -> None:
    """Mark multiple papers as sent."""
    history = load_history()
    sent = history.get("sent_papers", {})

    now = datetime.now().isoformat()
    for paper in papers:
        key = get_paper_key(paper)
        sent[key] = now

    history["sent_papers"] = sent
    history["last_run"] = now
    save_history(history)


def filter_unsent_papers(papers: list[dict], days_to_check: int = 7) -> list[dict]:
    """Filter out papers that were already sent."""
    history = load_history()
    sent = history.get("sent_papers", {})
    cutoff = datetime.now() - timedelta(days=days_to_check)

    unsent = []
    for paper in papers:
        key = get_paper_key(paper)
        if key not in sent:
            unsent.append(paper)
        else:
            sent_date = datetime.fromisoformat(sent[key])
            if sent_date <= cutoff:
                unsent.append(paper)  # Old enough to show again

    return unsent


def cleanup_old_history(days_to_keep: int = 30) -> int:
    """Remove entries older than N days. Returns count of removed entries."""
    history = load_history()
    sent = history.get("sent_papers", {})
    cutoff = datetime.now() - timedelta(days=days_to_keep)

    old_count = len(sent)
    sent = {
        key: date for key, date in sent.items()
        if datetime.fromisoformat(date) > cutoff
    }
    new_count = len(sent)

    history["sent_papers"] = sent
    save_history(history)

    return old_count - new_count


def get_last_run() -> Optional[datetime]:
    """Get the timestamp of the last digest run."""
    history = load_history()
    last_run = history.get("last_run")
    if last_run:
        return datetime.fromisoformat(last_run)
    return None
