"""Reading list service for managing paper collections.

This module provides the core service for creating, managing, and exporting
reading lists with full persistence support.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from paperpulse.reading_lists.models import (
    Priority,
    ReadingList,
    ReadingListItem,
    ReadingListStats,
    ReadingStatus,
)

logger = logging.getLogger(__name__)


class ReadingListService:
    """Service for managing reading lists.

    Features:
    - Create, update, and delete reading lists
    - Add/remove papers with status tracking
    - Tag and priority management
    - Full-text search across lists
    - Export to BibTeX, RIS, and JSON formats
    - List merging and splitting
    - Smart suggestions (next paper to read)
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        user_id: str = "default",
    ):
        """Initialize the reading list service.

        Args:
            storage_dir: Directory for storing reading list data
            user_id: User identifier for multi-user support
        """
        self.storage_dir = storage_dir or Path.home() / ".paperpulse" / "reading_lists"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id

        # In-memory cache of lists
        self._lists: dict[str, ReadingList] = {}
        self._load_all_lists()

    def _get_user_dir(self) -> Path:
        """Get the storage directory for the current user."""
        user_dir = self.storage_dir / self.user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _load_all_lists(self) -> None:
        """Load all reading lists from disk."""
        user_dir = self._get_user_dir()

        for list_file in user_dir.glob("*.json"):
            try:
                with open(list_file, "r") as f:
                    data = json.load(f)
                    reading_list = ReadingList.from_dict(data)
                    self._lists[reading_list.list_id] = reading_list
            except Exception as e:
                logger.warning(f"Failed to load reading list {list_file}: {e}")

        logger.info(f"Loaded {len(self._lists)} reading lists for user {self.user_id}")

        # Create default list if none exists
        if not self._lists:
            self.create_list("My Reading List", "Default reading list", is_default=True)

    def _save_list(self, reading_list: ReadingList) -> None:
        """Save a reading list to disk."""
        user_dir = self._get_user_dir()
        list_file = user_dir / f"{reading_list.list_id}.json"

        try:
            with open(list_file, "w") as f:
                json.dump(reading_list.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save reading list {reading_list.list_id}: {e}")
            raise

    def _delete_list_file(self, list_id: str) -> None:
        """Delete a reading list file from disk."""
        user_dir = self._get_user_dir()
        list_file = user_dir / f"{list_id}.json"

        if list_file.exists():
            list_file.unlink()

    # ==================== List Management ====================

    def create_list(
        self,
        name: str,
        description: str = "",
        tags: list[str] = None,
        color: str = "#4285f4",
        icon: str = "📚",
        is_default: bool = False,
    ) -> ReadingList:
        """Create a new reading list.

        Args:
            name: List name
            description: List description
            tags: List-level tags
            color: Color for UI display
            icon: Emoji icon
            is_default: Whether this is the default list for quick adds

        Returns:
            The created ReadingList
        """
        # If setting as default, unset other defaults
        if is_default:
            for existing_list in self._lists.values():
                if existing_list.is_default:
                    existing_list.is_default = False
                    self._save_list(existing_list)

        reading_list = ReadingList(
            list_id="",  # Will be auto-generated
            name=name,
            description=description,
            user_id=self.user_id,
            tags=tags or [],
            color=color,
            icon=icon,
            is_default=is_default,
        )

        self._lists[reading_list.list_id] = reading_list
        self._save_list(reading_list)

        logger.info(f"Created reading list: {name} ({reading_list.list_id})")
        return reading_list

    def get_list(self, list_id: str) -> Optional[ReadingList]:
        """Get a reading list by ID."""
        return self._lists.get(list_id)

    def get_all_lists(self, include_archived: bool = False) -> list[ReadingList]:
        """Get all reading lists.

        Args:
            include_archived: Whether to include archived lists

        Returns:
            List of reading lists
        """
        lists = list(self._lists.values())

        if not include_archived:
            lists = [l for l in lists if not l.is_archived]

        return sorted(lists, key=lambda l: l.updated_at, reverse=True)

    def get_default_list(self) -> Optional[ReadingList]:
        """Get the default reading list."""
        for reading_list in self._lists.values():
            if reading_list.is_default:
                return reading_list

        # Return first non-archived list if no default
        for reading_list in self._lists.values():
            if not reading_list.is_archived:
                return reading_list

        return None

    def update_list(
        self,
        list_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        color: Optional[str] = None,
        icon: Optional[str] = None,
        is_default: Optional[bool] = None,
    ) -> Optional[ReadingList]:
        """Update a reading list's properties.

        Args:
            list_id: List to update
            name: New name (if provided)
            description: New description (if provided)
            tags: New tags (if provided)
            color: New color (if provided)
            icon: New icon (if provided)
            is_default: Set as default (if provided)

        Returns:
            Updated reading list or None if not found
        """
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return None

        if name is not None:
            reading_list.name = name
        if description is not None:
            reading_list.description = description
        if tags is not None:
            reading_list.tags = tags
        if color is not None:
            reading_list.color = color
        if icon is not None:
            reading_list.icon = icon
        if is_default is not None:
            if is_default:
                # Unset other defaults
                for other_list in self._lists.values():
                    if other_list.list_id != list_id and other_list.is_default:
                        other_list.is_default = False
                        self._save_list(other_list)
            reading_list.is_default = is_default

        reading_list.updated_at = datetime.now()
        self._save_list(reading_list)

        return reading_list

    def delete_list(self, list_id: str, force: bool = False) -> bool:
        """Delete a reading list.

        Args:
            list_id: List to delete
            force: Force delete even if not empty

        Returns:
            True if deleted, False otherwise
        """
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return False

        if reading_list.items and not force:
            logger.warning(f"Cannot delete non-empty list {list_id}. Use force=True.")
            return False

        del self._lists[list_id]
        self._delete_list_file(list_id)

        logger.info(f"Deleted reading list: {list_id}")
        return True

    def archive_list(self, list_id: str) -> Optional[ReadingList]:
        """Archive a reading list (soft delete)."""
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return None

        reading_list.is_archived = True
        reading_list.updated_at = datetime.now()
        self._save_list(reading_list)

        return reading_list

    def unarchive_list(self, list_id: str) -> Optional[ReadingList]:
        """Unarchive a reading list."""
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return None

        reading_list.is_archived = False
        reading_list.updated_at = datetime.now()
        self._save_list(reading_list)

        return reading_list

    # ==================== Paper Management ====================

    def add_paper(
        self,
        list_id: str,
        paper: dict,
        status: ReadingStatus = ReadingStatus.TO_READ,
        priority: Priority = Priority.MEDIUM,
        notes: str = "",
        tags: list[str] = None,
        source: str = "",
    ) -> Optional[ReadingListItem]:
        """Add a paper to a reading list.

        Args:
            list_id: Target list ID
            paper: Paper dictionary
            status: Initial status
            priority: Initial priority
            notes: Initial notes
            tags: Tags to apply
            source: Where the paper was found

        Returns:
            The created ReadingListItem or None if list not found
        """
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return None

        item = reading_list.add_paper(
            paper, status=status, priority=priority, notes=notes, tags=tags or [], source=source
        )
        self._save_list(reading_list)

        return item

    def add_paper_to_default(
        self,
        paper: dict,
        **kwargs,
    ) -> Optional[ReadingListItem]:
        """Add a paper to the default reading list."""
        default_list = self.get_default_list()
        if not default_list:
            return None

        return self.add_paper(default_list.list_id, paper, **kwargs)

    def remove_paper(self, list_id: str, item_id: str) -> bool:
        """Remove a paper from a reading list."""
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return False

        result = reading_list.remove_paper(item_id)
        if result:
            self._save_list(reading_list)

        return result

    def move_paper(
        self,
        source_list_id: str,
        target_list_id: str,
        item_id: str,
    ) -> Optional[ReadingListItem]:
        """Move a paper from one list to another.

        Args:
            source_list_id: Source list
            target_list_id: Target list
            item_id: Item to move

        Returns:
            The moved item in the target list, or None if failed
        """
        source_list = self._lists.get(source_list_id)
        target_list = self._lists.get(target_list_id)

        if not source_list or not target_list:
            return None

        item = source_list.get_item(item_id)
        if not item:
            return None

        # Create new item in target list
        new_item = ReadingListItem(
            item_id="",  # Will be regenerated
            paper_id=item.paper_id,
            title=item.title,
            authors=item.authors,
            abstract=item.abstract,
            url=item.url,
            doi=item.doi,
            arxiv_id=item.arxiv_id,
            status=item.status,
            priority=item.priority,
            notes=item.notes,
            tags=item.tags,
            highlights=item.highlights,
            rating=item.rating,
            source=item.source,
            relevance_score=item.relevance_score,
            started_at=item.started_at,
            finished_at=item.finished_at,
        )

        target_list.items.append(new_item)
        target_list.updated_at = datetime.now()

        # Remove from source
        source_list.remove_paper(item_id)

        self._save_list(source_list)
        self._save_list(target_list)

        return new_item

    def copy_paper(
        self,
        source_list_id: str,
        target_list_id: str,
        item_id: str,
    ) -> Optional[ReadingListItem]:
        """Copy a paper to another list (keeping the original)."""
        source_list = self._lists.get(source_list_id)
        target_list = self._lists.get(target_list_id)

        if not source_list or not target_list:
            return None

        item = source_list.get_item(item_id)
        if not item:
            return None

        # Create copy in target list
        paper_dict = {
            "title": item.title,
            "authors": item.authors,
            "abstract": item.abstract,
            "url": item.url,
            "doi": item.doi,
            "arxiv_id": item.arxiv_id,
            "relevance_score": item.relevance_score,
        }

        new_item = target_list.add_paper(
            paper_dict,
            status=item.status,
            priority=item.priority,
            notes=item.notes,
            tags=item.tags,
            source=f"Copied from {source_list.name}",
        )

        self._save_list(target_list)

        return new_item

    def update_paper_status(
        self,
        list_id: str,
        item_id: str,
        status: ReadingStatus,
        rating: Optional[int] = None,
    ) -> Optional[ReadingListItem]:
        """Update a paper's reading status.

        Args:
            list_id: List containing the paper
            item_id: Paper item ID
            status: New status
            rating: Rating (for finished papers)

        Returns:
            Updated item or None
        """
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return None

        item = reading_list.get_item(item_id)
        if not item:
            return None

        if status == ReadingStatus.READING:
            item.mark_started()
        elif status == ReadingStatus.FINISHED:
            item.mark_finished(rating)
        elif status == ReadingStatus.SKIPPED:
            item.mark_skipped()
        else:
            item.status = status

        reading_list.updated_at = datetime.now()
        self._save_list(reading_list)

        return item

    def update_paper_priority(
        self,
        list_id: str,
        item_id: str,
        priority: Priority,
    ) -> Optional[ReadingListItem]:
        """Update a paper's priority."""
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return None

        item = reading_list.get_item(item_id)
        if not item:
            return None

        item.priority = priority
        reading_list.updated_at = datetime.now()
        self._save_list(reading_list)

        return item

    def add_paper_notes(
        self,
        list_id: str,
        item_id: str,
        note: str,
    ) -> Optional[ReadingListItem]:
        """Add a note to a paper."""
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return None

        item = reading_list.get_item(item_id)
        if not item:
            return None

        item.add_note(note)
        reading_list.updated_at = datetime.now()
        self._save_list(reading_list)

        return item

    def add_paper_tags(
        self,
        list_id: str,
        item_id: str,
        tags: list[str],
    ) -> Optional[ReadingListItem]:
        """Add tags to a paper."""
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return None

        item = reading_list.get_item(item_id)
        if not item:
            return None

        item.tags = list(set(item.tags + tags))
        reading_list.updated_at = datetime.now()
        self._save_list(reading_list)

        return item

    # ==================== Search and Filter ====================

    def search_papers(
        self,
        query: str,
        list_ids: list[str] = None,
        status_filter: list[ReadingStatus] = None,
        tag_filter: list[str] = None,
    ) -> list[tuple[ReadingList, ReadingListItem]]:
        """Search for papers across reading lists.

        Args:
            query: Search query (matches title, abstract, notes)
            list_ids: Lists to search (all if None)
            status_filter: Filter by status
            tag_filter: Filter by tags

        Returns:
            List of (list, item) tuples matching the query
        """
        results = []
        query_lower = query.lower()

        lists_to_search = (
            [self._lists[lid] for lid in list_ids if lid in self._lists]
            if list_ids
            else self._lists.values()
        )

        for reading_list in lists_to_search:
            if reading_list.is_archived:
                continue

            for item in reading_list.items:
                # Status filter
                if status_filter and item.status not in status_filter:
                    continue

                # Tag filter
                if tag_filter and not any(tag in item.tags for tag in tag_filter):
                    continue

                # Text search
                searchable = f"{item.title} {item.abstract} {item.notes}".lower()
                if query_lower in searchable:
                    results.append((reading_list, item))

        return results

    def get_papers_by_status(
        self,
        status: ReadingStatus,
        list_id: Optional[str] = None,
    ) -> list[tuple[ReadingList, ReadingListItem]]:
        """Get all papers with a specific status."""
        results = []

        lists_to_search = (
            [self._lists[list_id]] if list_id and list_id in self._lists else self._lists.values()
        )

        for reading_list in lists_to_search:
            for item in reading_list.get_items_by_status(status):
                results.append((reading_list, item))

        return results

    def get_papers_by_tag(
        self,
        tag: str,
        list_id: Optional[str] = None,
    ) -> list[tuple[ReadingList, ReadingListItem]]:
        """Get all papers with a specific tag."""
        results = []

        lists_to_search = (
            [self._lists[list_id]] if list_id and list_id in self._lists else self._lists.values()
        )

        for reading_list in lists_to_search:
            for item in reading_list.get_items_by_tag(tag):
                results.append((reading_list, item))

        return results

    def suggest_next_paper(self, list_id: Optional[str] = None) -> Optional[tuple[ReadingList, ReadingListItem]]:
        """Suggest the next paper to read based on priority and relevance.

        Considers:
        - Priority (urgent > high > medium > low)
        - Due date
        - Relevance score
        - Time in list (older items get slight boost)
        """
        candidates = []

        lists_to_search = (
            [self._lists[list_id]] if list_id and list_id in self._lists else self._lists.values()
        )

        for reading_list in lists_to_search:
            if reading_list.is_archived:
                continue

            for item in reading_list.items:
                if item.status != ReadingStatus.TO_READ:
                    continue

                # Calculate score
                score = 0.0

                # Priority weight
                priority_weights = {
                    Priority.URGENT: 100,
                    Priority.HIGH: 50,
                    Priority.MEDIUM: 20,
                    Priority.LOW: 5,
                }
                score += priority_weights.get(item.priority, 20)

                # Due date weight
                if item.due_date:
                    days_until_due = (item.due_date - datetime.now()).days
                    if days_until_due < 0:
                        score += 200  # Overdue
                    elif days_until_due < 7:
                        score += 50  # Due soon
                    elif days_until_due < 30:
                        score += 20

                # Relevance weight
                if item.relevance_score:
                    score += item.relevance_score * 0.5

                # Age weight (slight boost for older items)
                days_in_list = (datetime.now() - item.added_at).days
                score += min(days_in_list * 0.5, 20)

                candidates.append((score, reading_list, item))

        if not candidates:
            return None

        # Return highest scoring paper
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, reading_list, item = candidates[0]

        return reading_list, item

    # ==================== Export Functions ====================

    def export_to_bibtex(
        self,
        list_id: str,
        status_filter: list[ReadingStatus] = None,
    ) -> str:
        """Export a reading list to BibTeX format.

        Args:
            list_id: List to export
            status_filter: Only export papers with these statuses

        Returns:
            BibTeX string
        """
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return ""

        entries = []

        for item in reading_list.items:
            if status_filter and item.status not in status_filter:
                continue

            # Generate citation key
            first_author = item.authors[0].split()[-1] if item.authors else "Unknown"
            year = item.added_at.year
            title_word = item.title.split()[0] if item.title else "paper"
            cite_key = f"{first_author}{year}{title_word}".lower()

            # Build entry
            entry_type = "article"  # Default type

            fields = [f"  title = {{{item.title}}}"]

            if item.authors:
                authors_str = " and ".join(item.authors)
                fields.append(f"  author = {{{authors_str}}}")

            if item.doi:
                fields.append(f"  doi = {{{item.doi}}}")

            if item.url:
                fields.append(f"  url = {{{item.url}}}")

            if item.arxiv_id:
                fields.append(f"  eprint = {{{item.arxiv_id}}}")
                fields.append("  archiveprefix = {arXiv}")

            if item.abstract:
                abstract_clean = item.abstract.replace("\n", " ").replace("{", "").replace("}", "")
                fields.append(f"  abstract = {{{abstract_clean[:500]}}}")

            if item.notes:
                notes_clean = item.notes.replace("\n", " ").replace("{", "").replace("}", "")
                fields.append(f"  note = {{{notes_clean[:200]}}}")

            if item.tags:
                fields.append(f"  keywords = {{{', '.join(item.tags)}}}")

            entry = f"@{entry_type}{{{cite_key},\n" + ",\n".join(fields) + "\n}"
            entries.append(entry)

        return "\n\n".join(entries)

    def export_to_ris(
        self,
        list_id: str,
        status_filter: list[ReadingStatus] = None,
    ) -> str:
        """Export a reading list to RIS format.

        Args:
            list_id: List to export
            status_filter: Only export papers with these statuses

        Returns:
            RIS string
        """
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return ""

        entries = []

        for item in reading_list.items:
            if status_filter and item.status not in status_filter:
                continue

            lines = ["TY  - JOUR"]  # Default type

            lines.append(f"TI  - {item.title}")

            for author in item.authors:
                lines.append(f"AU  - {author}")

            if item.doi:
                lines.append(f"DO  - {item.doi}")

            if item.url:
                lines.append(f"UR  - {item.url}")

            if item.abstract:
                lines.append(f"AB  - {item.abstract[:1000]}")

            for tag in item.tags:
                lines.append(f"KW  - {tag}")

            if item.notes:
                lines.append(f"N1  - {item.notes[:500]}")

            lines.append("ER  -")

            entries.append("\n".join(lines))

        return "\n\n".join(entries)

    def export_to_json(
        self,
        list_id: str,
        include_stats: bool = True,
    ) -> str:
        """Export a reading list to JSON format."""
        reading_list = self._lists.get(list_id)
        if not reading_list:
            return "{}"

        data = reading_list.to_dict()

        if not include_stats:
            data.pop("stats", None)

        return json.dumps(data, indent=2)

    def import_from_json(self, json_data: str) -> Optional[ReadingList]:
        """Import a reading list from JSON.

        Args:
            json_data: JSON string

        Returns:
            Imported reading list
        """
        try:
            data = json.loads(json_data)
            reading_list = ReadingList.from_dict(data)

            # Assign new ID to avoid conflicts
            import uuid
            reading_list.list_id = str(uuid.uuid4())[:8]
            reading_list.user_id = self.user_id

            self._lists[reading_list.list_id] = reading_list
            self._save_list(reading_list)

            return reading_list
        except Exception as e:
            logger.error(f"Failed to import reading list: {e}")
            return None

    # ==================== Statistics ====================

    def get_global_stats(self) -> dict:
        """Get statistics across all reading lists."""
        total_lists = 0
        total_papers = 0
        total_to_read = 0
        total_reading = 0
        total_finished = 0
        total_skipped = 0
        all_tags: dict[str, int] = {}
        all_ratings: list[int] = []

        for reading_list in self._lists.values():
            if reading_list.is_archived:
                continue

            total_lists += 1
            stats = reading_list.get_stats()
            total_papers += stats.total_papers
            total_to_read += stats.to_read
            total_reading += stats.reading
            total_finished += stats.finished
            total_skipped += stats.skipped

            for tag, count in stats.top_tags:
                all_tags[tag] = all_tags.get(tag, 0) + count

            for item in reading_list.items:
                if item.rating:
                    all_ratings.append(item.rating)

        return {
            "total_lists": total_lists,
            "total_papers": total_papers,
            "status_breakdown": {
                "to_read": total_to_read,
                "reading": total_reading,
                "finished": total_finished,
                "skipped": total_skipped,
            },
            "completion_rate": total_finished / total_papers if total_papers > 0 else 0,
            "top_tags": sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:20],
            "avg_rating": sum(all_ratings) / len(all_ratings) if all_ratings else None,
        }

    # ==================== List Operations ====================

    def merge_lists(
        self,
        source_list_ids: list[str],
        target_name: str,
        delete_sources: bool = False,
    ) -> Optional[ReadingList]:
        """Merge multiple reading lists into a new one.

        Args:
            source_list_ids: Lists to merge
            target_name: Name for the merged list
            delete_sources: Whether to delete source lists after merging

        Returns:
            The merged reading list
        """
        merged = self.create_list(target_name, f"Merged from {len(source_list_ids)} lists")

        for list_id in source_list_ids:
            source_list = self._lists.get(list_id)
            if not source_list:
                continue

            for item in source_list.items:
                paper_dict = {
                    "title": item.title,
                    "authors": item.authors,
                    "abstract": item.abstract,
                    "url": item.url,
                    "doi": item.doi,
                    "arxiv_id": item.arxiv_id,
                    "relevance_score": item.relevance_score,
                }
                merged.add_paper(
                    paper_dict,
                    status=item.status,
                    priority=item.priority,
                    notes=item.notes,
                    tags=item.tags + [f"from:{source_list.name}"],
                    source=item.source or source_list.name,
                )

            # Merge list-level tags
            merged.tags = list(set(merged.tags + source_list.tags))

            if delete_sources:
                self.delete_list(list_id, force=True)

        self._save_list(merged)

        return merged

    def split_list_by_tag(
        self,
        list_id: str,
        tag: str,
        new_list_name: Optional[str] = None,
    ) -> Optional[ReadingList]:
        """Split papers with a specific tag into a new list.

        Args:
            list_id: Source list
            tag: Tag to filter by
            new_list_name: Name for new list (defaults to tag name)

        Returns:
            The new reading list containing tagged papers
        """
        source_list = self._lists.get(list_id)
        if not source_list:
            return None

        new_list = self.create_list(
            new_list_name or f"Papers tagged: {tag}",
            f"Split from {source_list.name} by tag '{tag}'",
        )

        items_to_move = []
        for item in source_list.items:
            if tag in item.tags:
                items_to_move.append(item)

        for item in items_to_move:
            self.move_paper(list_id, new_list.list_id, item.item_id)

        return new_list
