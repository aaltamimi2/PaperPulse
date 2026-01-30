"""Data models for reading list management.

This module defines the core data structures for organizing papers into
reading lists with status tracking, notes, and tags.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ReadingStatus(str, Enum):
    """Status of a paper in a reading list."""

    TO_READ = "to_read"
    READING = "reading"
    FINISHED = "finished"
    SKIPPED = "skipped"
    REFERENCE = "reference"  # For papers kept as reference but not to be read in full


class Priority(str, Enum):
    """Priority level for reading list items."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ReadingListItem:
    """A paper in a reading list."""

    item_id: str  # Unique identifier for this list item
    paper_id: str  # DOI, arXiv ID, or title hash
    title: str
    authors: list[str]
    abstract: str = ""
    url: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None

    # Reading list specific fields
    status: ReadingStatus = ReadingStatus.TO_READ
    priority: Priority = Priority.MEDIUM
    added_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # User annotations
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    highlights: list[dict] = field(default_factory=list)  # [{text, color, page}]
    rating: Optional[int] = None  # 1-5 stars

    # Organization
    position: int = 0  # Order in list
    due_date: Optional[datetime] = None

    # Metadata
    source: str = ""  # Where this paper was found (arxiv, email digest, etc.)
    relevance_score: Optional[float] = None

    def __post_init__(self):
        if not self.item_id:
            self.item_id = str(uuid.uuid4())[:8]

    @classmethod
    def from_paper(cls, paper: dict, **kwargs) -> "ReadingListItem":
        """Create a reading list item from a paper dictionary."""
        # Extract paper ID
        paper_id = paper.get("doi") or paper.get("arxiv_id")
        if not paper_id:
            paper_id = f"title:{hashlib.md5(paper.get('title', '').encode()).hexdigest()[:12]}"

        # Extract authors
        authors = []
        for author in paper.get("authors", []):
            if isinstance(author, dict):
                authors.append(author.get("name", str(author)))
            else:
                authors.append(str(author))

        return cls(
            item_id=str(uuid.uuid4())[:8],
            paper_id=paper_id,
            title=paper.get("title", ""),
            authors=authors,
            abstract=paper.get("abstract", ""),
            url=paper.get("url") or paper.get("link"),
            doi=paper.get("doi"),
            arxiv_id=paper.get("arxiv_id"),
            relevance_score=paper.get("relevance_score") or paper.get("score"),
            **kwargs,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "item_id": self.item_id,
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract[:500] if self.abstract else "",
            "url": self.url,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "status": self.status.value,
            "priority": self.priority.value,
            "added_at": self.added_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "notes": self.notes,
            "tags": self.tags,
            "highlights": self.highlights,
            "rating": self.rating,
            "position": self.position,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "source": self.source,
            "relevance_score": self.relevance_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReadingListItem":
        """Create from dictionary."""
        # Parse dates
        added_at = data.get("added_at")
        if isinstance(added_at, str):
            added_at = datetime.fromisoformat(added_at)
        elif not added_at:
            added_at = datetime.now()

        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        finished_at = data.get("finished_at")
        if isinstance(finished_at, str):
            finished_at = datetime.fromisoformat(finished_at)

        due_date = data.get("due_date")
        if isinstance(due_date, str):
            due_date = datetime.fromisoformat(due_date)

        return cls(
            item_id=data.get("item_id", str(uuid.uuid4())[:8]),
            paper_id=data.get("paper_id", ""),
            title=data.get("title", ""),
            authors=data.get("authors", []),
            abstract=data.get("abstract", ""),
            url=data.get("url"),
            doi=data.get("doi"),
            arxiv_id=data.get("arxiv_id"),
            status=ReadingStatus(data.get("status", "to_read")),
            priority=Priority(data.get("priority", "medium")),
            added_at=added_at,
            started_at=started_at,
            finished_at=finished_at,
            notes=data.get("notes", ""),
            tags=data.get("tags", []),
            highlights=data.get("highlights", []),
            rating=data.get("rating"),
            position=data.get("position", 0),
            due_date=due_date,
            source=data.get("source", ""),
            relevance_score=data.get("relevance_score"),
        )

    def mark_started(self) -> None:
        """Mark the paper as currently being read."""
        self.status = ReadingStatus.READING
        self.started_at = datetime.now()

    def mark_finished(self, rating: Optional[int] = None) -> None:
        """Mark the paper as finished."""
        self.status = ReadingStatus.FINISHED
        self.finished_at = datetime.now()
        if rating:
            self.rating = rating

    def mark_skipped(self, reason: str = "") -> None:
        """Mark the paper as skipped."""
        self.status = ReadingStatus.SKIPPED
        if reason:
            self.notes = f"Skipped: {reason}\n{self.notes}"

    def add_note(self, note: str) -> None:
        """Add a note to the paper."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.notes = f"[{timestamp}] {note}\n{self.notes}"

    def add_highlight(self, text: str, color: str = "yellow", page: Optional[int] = None) -> None:
        """Add a highlight/annotation."""
        self.highlights.append({
            "text": text,
            "color": color,
            "page": page,
            "timestamp": datetime.now().isoformat(),
        })


@dataclass
class ReadingListStats:
    """Statistics for a reading list."""

    total_papers: int = 0
    to_read: int = 0
    reading: int = 0
    finished: int = 0
    skipped: int = 0
    reference: int = 0

    avg_time_to_finish_days: Optional[float] = None
    completion_rate: float = 0.0
    papers_finished_this_week: int = 0
    papers_finished_this_month: int = 0

    top_tags: list[tuple[str, int]] = field(default_factory=list)
    avg_rating: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_papers": self.total_papers,
            "to_read": self.to_read,
            "reading": self.reading,
            "finished": self.finished,
            "skipped": self.skipped,
            "reference": self.reference,
            "avg_time_to_finish_days": self.avg_time_to_finish_days,
            "completion_rate": self.completion_rate,
            "papers_finished_this_week": self.papers_finished_this_week,
            "papers_finished_this_month": self.papers_finished_this_month,
            "top_tags": self.top_tags[:10],
            "avg_rating": self.avg_rating,
        }


@dataclass
class ReadingList:
    """A collection of papers organized for reading."""

    list_id: str
    name: str
    description: str = ""
    user_id: str = "default"

    # List properties
    items: list[ReadingListItem] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # List-level tags
    color: str = "#4285f4"  # For UI display
    icon: str = "📚"  # Emoji icon

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_archived: bool = False
    is_default: bool = False  # Default list for quick adds

    # Sharing
    is_public: bool = False
    shared_with: list[str] = field(default_factory=list)  # User IDs

    def __post_init__(self):
        if not self.list_id:
            self.list_id = str(uuid.uuid4())[:8]

    def add_paper(
        self,
        paper: dict,
        status: ReadingStatus = ReadingStatus.TO_READ,
        priority: Priority = Priority.MEDIUM,
        notes: str = "",
        tags: list[str] = None,
        source: str = "",
    ) -> ReadingListItem:
        """Add a paper to the reading list.

        Args:
            paper: Paper dictionary with title, authors, abstract, etc.
            status: Initial reading status
            priority: Priority level
            notes: Initial notes
            tags: Tags to apply
            source: Where the paper was found

        Returns:
            The created ReadingListItem
        """
        # Check for duplicates
        paper_id = paper.get("doi") or paper.get("arxiv_id") or paper.get("title", "")
        for item in self.items:
            if item.paper_id == paper_id or item.title == paper.get("title"):
                return item  # Already in list

        item = ReadingListItem.from_paper(
            paper,
            status=status,
            priority=priority,
            notes=notes,
            tags=tags or [],
            source=source,
            position=len(self.items),
        )

        self.items.append(item)
        self.updated_at = datetime.now()

        return item

    def remove_paper(self, item_id: str) -> bool:
        """Remove a paper from the list."""
        for i, item in enumerate(self.items):
            if item.item_id == item_id:
                self.items.pop(i)
                self.updated_at = datetime.now()
                # Reorder remaining items
                for j, remaining in enumerate(self.items):
                    remaining.position = j
                return True
        return False

    def get_item(self, item_id: str) -> Optional[ReadingListItem]:
        """Get an item by ID."""
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def get_items_by_status(self, status: ReadingStatus) -> list[ReadingListItem]:
        """Get all items with a specific status."""
        return [item for item in self.items if item.status == status]

    def get_items_by_tag(self, tag: str) -> list[ReadingListItem]:
        """Get all items with a specific tag."""
        return [item for item in self.items if tag in item.tags]

    def get_items_by_priority(self, priority: Priority) -> list[ReadingListItem]:
        """Get all items with a specific priority."""
        return [item for item in self.items if item.priority == priority]

    def reorder_items(self, item_ids: list[str]) -> None:
        """Reorder items according to provided ID list."""
        id_to_item = {item.item_id: item for item in self.items}
        new_items = []

        for i, item_id in enumerate(item_ids):
            if item_id in id_to_item:
                item = id_to_item[item_id]
                item.position = i
                new_items.append(item)
                del id_to_item[item_id]

        # Add any items not in the list at the end
        for item in id_to_item.values():
            item.position = len(new_items)
            new_items.append(item)

        self.items = new_items
        self.updated_at = datetime.now()

    def get_stats(self) -> ReadingListStats:
        """Calculate statistics for this reading list."""
        stats = ReadingListStats(total_papers=len(self.items))

        # Count by status
        for item in self.items:
            if item.status == ReadingStatus.TO_READ:
                stats.to_read += 1
            elif item.status == ReadingStatus.READING:
                stats.reading += 1
            elif item.status == ReadingStatus.FINISHED:
                stats.finished += 1
            elif item.status == ReadingStatus.SKIPPED:
                stats.skipped += 1
            elif item.status == ReadingStatus.REFERENCE:
                stats.reference += 1

        # Completion rate
        if stats.total_papers > 0:
            stats.completion_rate = stats.finished / stats.total_papers

        # Average time to finish
        finish_times = []
        for item in self.items:
            if item.status == ReadingStatus.FINISHED and item.started_at and item.finished_at:
                days = (item.finished_at - item.started_at).days
                finish_times.append(days)

        if finish_times:
            stats.avg_time_to_finish_days = sum(finish_times) / len(finish_times)

        # Papers finished recently
        now = datetime.now()
        week_ago = now.replace(day=now.day - 7) if now.day > 7 else now.replace(month=now.month - 1, day=28)
        month_ago = now.replace(month=now.month - 1) if now.month > 1 else now.replace(year=now.year - 1, month=12)

        for item in self.items:
            if item.status == ReadingStatus.FINISHED and item.finished_at:
                if item.finished_at >= week_ago:
                    stats.papers_finished_this_week += 1
                if item.finished_at >= month_ago:
                    stats.papers_finished_this_month += 1

        # Top tags
        tag_counts: dict[str, int] = {}
        for item in self.items:
            for tag in item.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        stats.top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Average rating
        ratings = [item.rating for item in self.items if item.rating is not None]
        if ratings:
            stats.avg_rating = sum(ratings) / len(ratings)

        return stats

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "list_id": self.list_id,
            "name": self.name,
            "description": self.description,
            "user_id": self.user_id,
            "items": [item.to_dict() for item in self.items],
            "tags": self.tags,
            "color": self.color,
            "icon": self.icon,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_archived": self.is_archived,
            "is_default": self.is_default,
            "is_public": self.is_public,
            "shared_with": self.shared_with,
            "stats": self.get_stats().to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReadingList":
        """Create from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not created_at:
            created_at = datetime.now()

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif not updated_at:
            updated_at = datetime.now()

        items = [
            ReadingListItem.from_dict(item_data)
            for item_data in data.get("items", [])
        ]

        return cls(
            list_id=data.get("list_id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Untitled"),
            description=data.get("description", ""),
            user_id=data.get("user_id", "default"),
            items=items,
            tags=data.get("tags", []),
            color=data.get("color", "#4285f4"),
            icon=data.get("icon", "📚"),
            created_at=created_at,
            updated_at=updated_at,
            is_archived=data.get("is_archived", False),
            is_default=data.get("is_default", False),
            is_public=data.get("is_public", False),
            shared_with=data.get("shared_with", []),
        )
