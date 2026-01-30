"""Reading list management API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["reading-lists"])


# ==================== Request/Response Models ====================

class CreateListRequest(BaseModel):
    """Request for creating a reading list."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="")
    tags: list[str] = Field(default=[])
    color: str = Field(default="#4285f4")
    icon: str = Field(default="📚")
    is_default: bool = Field(default=False)


class UpdateListRequest(BaseModel):
    """Request for updating a reading list."""

    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_default: Optional[bool] = None


class AddPaperRequest(BaseModel):
    """Request for adding a paper to a reading list."""

    paper: dict = Field(..., description="Paper data with title, authors, etc.")
    status: str = Field(default="to_read")
    priority: str = Field(default="medium")
    notes: str = Field(default="")
    tags: list[str] = Field(default=[])
    source: str = Field(default="")


class UpdatePaperRequest(BaseModel):
    """Request for updating a paper in a reading list."""

    status: Optional[str] = None
    priority: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    due_date: Optional[str] = None


class MovePaperRequest(BaseModel):
    """Request for moving a paper between lists."""

    target_list_id: str


class ReadingListItemResponse(BaseModel):
    """Reading list item response."""

    item_id: str
    paper_id: str
    title: str
    authors: list[str]
    status: str
    priority: str
    added_at: str
    notes: str
    tags: list[str]
    rating: Optional[int]
    relevance_score: Optional[float]


class ReadingListResponse(BaseModel):
    """Reading list response."""

    list_id: str
    name: str
    description: str
    tags: list[str]
    color: str
    icon: str
    is_default: bool
    is_archived: bool
    item_count: int
    created_at: str
    updated_at: str


class ReadingListDetailResponse(ReadingListResponse):
    """Detailed reading list response with items."""

    items: list[ReadingListItemResponse]
    stats: dict


class SearchResult(BaseModel):
    """Search result."""

    list_id: str
    list_name: str
    item: ReadingListItemResponse


# ==================== Helper Functions ====================

def get_service(user_id: str = "default"):
    """Get or create a ReadingListService instance."""
    from paperpulse.reading_lists import ReadingListService
    return ReadingListService(user_id=user_id)


def item_to_response(item) -> ReadingListItemResponse:
    """Convert ReadingListItem to response model."""
    return ReadingListItemResponse(
        item_id=item.item_id,
        paper_id=item.paper_id,
        title=item.title,
        authors=item.authors,
        status=item.status.value,
        priority=item.priority.value,
        added_at=item.added_at.isoformat(),
        notes=item.notes,
        tags=item.tags,
        rating=item.rating,
        relevance_score=item.relevance_score,
    )


def list_to_response(reading_list) -> ReadingListResponse:
    """Convert ReadingList to response model."""
    return ReadingListResponse(
        list_id=reading_list.list_id,
        name=reading_list.name,
        description=reading_list.description,
        tags=reading_list.tags,
        color=reading_list.color,
        icon=reading_list.icon,
        is_default=reading_list.is_default,
        is_archived=reading_list.is_archived,
        item_count=len(reading_list.items),
        created_at=reading_list.created_at.isoformat(),
        updated_at=reading_list.updated_at.isoformat(),
    )


def list_to_detail_response(reading_list) -> ReadingListDetailResponse:
    """Convert ReadingList to detailed response model."""
    return ReadingListDetailResponse(
        list_id=reading_list.list_id,
        name=reading_list.name,
        description=reading_list.description,
        tags=reading_list.tags,
        color=reading_list.color,
        icon=reading_list.icon,
        is_default=reading_list.is_default,
        is_archived=reading_list.is_archived,
        item_count=len(reading_list.items),
        created_at=reading_list.created_at.isoformat(),
        updated_at=reading_list.updated_at.isoformat(),
        items=[item_to_response(item) for item in reading_list.items],
        stats=reading_list.get_stats().to_dict(),
    )


# ==================== List Management Endpoints ====================

@router.get("/", response_model=list[ReadingListResponse])
async def get_all_lists(
    include_archived: bool = Query(default=False),
    user_id: str = Query(default="default"),
):
    """Get all reading lists for the user."""
    service = get_service(user_id)
    lists = service.get_all_lists(include_archived=include_archived)
    return [list_to_response(l) for l in lists]


@router.post("/", response_model=ReadingListResponse)
async def create_list(
    request: CreateListRequest,
    user_id: str = Query(default="default"),
):
    """Create a new reading list."""
    service = get_service(user_id)

    reading_list = service.create_list(
        name=request.name,
        description=request.description,
        tags=request.tags,
        color=request.color,
        icon=request.icon,
        is_default=request.is_default,
    )

    return list_to_response(reading_list)


@router.get("/default", response_model=ReadingListDetailResponse)
async def get_default_list(user_id: str = Query(default="default")):
    """Get the default reading list."""
    service = get_service(user_id)
    reading_list = service.get_default_list()

    if not reading_list:
        raise HTTPException(status_code=404, detail="No default list found")

    return list_to_detail_response(reading_list)


@router.get("/stats")
async def get_global_stats(user_id: str = Query(default="default")):
    """Get statistics across all reading lists."""
    service = get_service(user_id)
    return service.get_global_stats()


@router.get("/{list_id}", response_model=ReadingListDetailResponse)
async def get_list(
    list_id: str,
    user_id: str = Query(default="default"),
):
    """Get a specific reading list with all items."""
    service = get_service(user_id)
    reading_list = service.get_list(list_id)

    if not reading_list:
        raise HTTPException(status_code=404, detail="List not found")

    return list_to_detail_response(reading_list)


@router.patch("/{list_id}", response_model=ReadingListResponse)
async def update_list(
    list_id: str,
    request: UpdateListRequest,
    user_id: str = Query(default="default"),
):
    """Update a reading list's properties."""
    service = get_service(user_id)

    reading_list = service.update_list(
        list_id=list_id,
        name=request.name,
        description=request.description,
        tags=request.tags,
        color=request.color,
        icon=request.icon,
        is_default=request.is_default,
    )

    if not reading_list:
        raise HTTPException(status_code=404, detail="List not found")

    return list_to_response(reading_list)


@router.delete("/{list_id}")
async def delete_list(
    list_id: str,
    force: bool = Query(default=False),
    user_id: str = Query(default="default"),
):
    """Delete a reading list."""
    service = get_service(user_id)

    if not service.delete_list(list_id, force=force):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete non-empty list. Use force=true to delete anyway.",
        )

    return {"message": "List deleted successfully"}


@router.post("/{list_id}/archive")
async def archive_list(
    list_id: str,
    user_id: str = Query(default="default"),
):
    """Archive a reading list."""
    service = get_service(user_id)
    reading_list = service.archive_list(list_id)

    if not reading_list:
        raise HTTPException(status_code=404, detail="List not found")

    return {"message": "List archived successfully"}


@router.post("/{list_id}/unarchive")
async def unarchive_list(
    list_id: str,
    user_id: str = Query(default="default"),
):
    """Unarchive a reading list."""
    service = get_service(user_id)
    reading_list = service.unarchive_list(list_id)

    if not reading_list:
        raise HTTPException(status_code=404, detail="List not found")

    return {"message": "List unarchived successfully"}


# ==================== Paper Management Endpoints ====================

@router.post("/{list_id}/papers", response_model=ReadingListItemResponse)
async def add_paper(
    list_id: str,
    request: AddPaperRequest,
    user_id: str = Query(default="default"),
):
    """Add a paper to a reading list."""
    from paperpulse.reading_lists import Priority, ReadingStatus

    service = get_service(user_id)

    try:
        status = ReadingStatus(request.status)
        priority = Priority(request.priority)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    item = service.add_paper(
        list_id=list_id,
        paper=request.paper,
        status=status,
        priority=priority,
        notes=request.notes,
        tags=request.tags,
        source=request.source,
    )

    if not item:
        raise HTTPException(status_code=404, detail="List not found")

    return item_to_response(item)


@router.post("/default/papers", response_model=ReadingListItemResponse)
async def add_paper_to_default(
    request: AddPaperRequest,
    user_id: str = Query(default="default"),
):
    """Add a paper to the default reading list."""
    from paperpulse.reading_lists import Priority, ReadingStatus

    service = get_service(user_id)

    try:
        status = ReadingStatus(request.status)
        priority = Priority(request.priority)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    item = service.add_paper_to_default(
        paper=request.paper,
        status=status,
        priority=priority,
        notes=request.notes,
        tags=request.tags,
        source=request.source,
    )

    if not item:
        raise HTTPException(status_code=404, detail="No default list found")

    return item_to_response(item)


@router.patch("/{list_id}/papers/{item_id}", response_model=ReadingListItemResponse)
async def update_paper(
    list_id: str,
    item_id: str,
    request: UpdatePaperRequest,
    user_id: str = Query(default="default"),
):
    """Update a paper's status, priority, or other properties."""
    from paperpulse.reading_lists import Priority, ReadingStatus

    service = get_service(user_id)

    reading_list = service.get_list(list_id)
    if not reading_list:
        raise HTTPException(status_code=404, detail="List not found")

    item = reading_list.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Paper not found in list")

    # Update status
    if request.status:
        try:
            status = ReadingStatus(request.status)
            service.update_paper_status(list_id, item_id, status, request.rating)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Update priority
    if request.priority:
        try:
            priority = Priority(request.priority)
            service.update_paper_priority(list_id, item_id, priority)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Update notes
    if request.notes is not None:
        service.add_paper_notes(list_id, item_id, request.notes)

    # Update tags
    if request.tags is not None:
        service.add_paper_tags(list_id, item_id, request.tags)

    # Refresh item
    reading_list = service.get_list(list_id)
    item = reading_list.get_item(item_id)

    return item_to_response(item)


@router.delete("/{list_id}/papers/{item_id}")
async def remove_paper(
    list_id: str,
    item_id: str,
    user_id: str = Query(default="default"),
):
    """Remove a paper from a reading list."""
    service = get_service(user_id)

    if not service.remove_paper(list_id, item_id):
        raise HTTPException(status_code=404, detail="Paper not found in list")

    return {"message": "Paper removed successfully"}


@router.post("/{list_id}/papers/{item_id}/move", response_model=ReadingListItemResponse)
async def move_paper(
    list_id: str,
    item_id: str,
    request: MovePaperRequest,
    user_id: str = Query(default="default"),
):
    """Move a paper to another reading list."""
    service = get_service(user_id)

    item = service.move_paper(list_id, request.target_list_id, item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Paper or target list not found")

    return item_to_response(item)


@router.post("/{list_id}/papers/{item_id}/copy", response_model=ReadingListItemResponse)
async def copy_paper(
    list_id: str,
    item_id: str,
    request: MovePaperRequest,
    user_id: str = Query(default="default"),
):
    """Copy a paper to another reading list."""
    service = get_service(user_id)

    item = service.copy_paper(list_id, request.target_list_id, item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Paper or target list not found")

    return item_to_response(item)


# ==================== Search and Filter Endpoints ====================

@router.get("/search/papers", response_model=list[SearchResult])
async def search_papers(
    query: str = Query(..., min_length=1),
    list_ids: Optional[str] = Query(default=None, description="Comma-separated list IDs"),
    status: Optional[str] = Query(default=None),
    tags: Optional[str] = Query(default=None, description="Comma-separated tags"),
    user_id: str = Query(default="default"),
):
    """Search for papers across reading lists."""
    from paperpulse.reading_lists import ReadingStatus

    service = get_service(user_id)

    # Parse filters
    list_id_list = list_ids.split(",") if list_ids else None
    tag_list = tags.split(",") if tags else None
    status_filter = None
    if status:
        try:
            status_filter = [ReadingStatus(status)]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    results = service.search_papers(
        query=query,
        list_ids=list_id_list,
        status_filter=status_filter,
        tag_filter=tag_list,
    )

    return [
        SearchResult(
            list_id=reading_list.list_id,
            list_name=reading_list.name,
            item=item_to_response(item),
        )
        for reading_list, item in results
    ]


@router.get("/filter/status/{status}", response_model=list[SearchResult])
async def filter_by_status(
    status: str,
    list_id: Optional[str] = Query(default=None),
    user_id: str = Query(default="default"),
):
    """Get all papers with a specific status."""
    from paperpulse.reading_lists import ReadingStatus

    service = get_service(user_id)

    try:
        reading_status = ReadingStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    results = service.get_papers_by_status(reading_status, list_id)

    return [
        SearchResult(
            list_id=reading_list.list_id,
            list_name=reading_list.name,
            item=item_to_response(item),
        )
        for reading_list, item in results
    ]


@router.get("/filter/tag/{tag}", response_model=list[SearchResult])
async def filter_by_tag(
    tag: str,
    list_id: Optional[str] = Query(default=None),
    user_id: str = Query(default="default"),
):
    """Get all papers with a specific tag."""
    service = get_service(user_id)
    results = service.get_papers_by_tag(tag, list_id)

    return [
        SearchResult(
            list_id=reading_list.list_id,
            list_name=reading_list.name,
            item=item_to_response(item),
        )
        for reading_list, item in results
    ]


@router.get("/suggest/next")
async def suggest_next_paper(
    list_id: Optional[str] = Query(default=None),
    user_id: str = Query(default="default"),
):
    """Get a suggestion for the next paper to read."""
    service = get_service(user_id)
    result = service.suggest_next_paper(list_id)

    if not result:
        return {"message": "No papers to read"}

    reading_list, item = result

    return {
        "list_id": reading_list.list_id,
        "list_name": reading_list.name,
        "suggested_paper": item_to_response(item),
    }


# ==================== Export Endpoints ====================

@router.get("/{list_id}/export/bibtex")
async def export_bibtex(
    list_id: str,
    status: Optional[str] = Query(default=None),
    user_id: str = Query(default="default"),
):
    """Export reading list to BibTeX format."""
    from fastapi.responses import PlainTextResponse

    from paperpulse.reading_lists import ReadingStatus

    service = get_service(user_id)

    status_filter = None
    if status:
        try:
            status_filter = [ReadingStatus(status)]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    bibtex = service.export_to_bibtex(list_id, status_filter=status_filter)

    if not bibtex:
        raise HTTPException(status_code=404, detail="List not found or empty")

    return PlainTextResponse(
        content=bibtex,
        media_type="application/x-bibtex",
        headers={"Content-Disposition": f"attachment; filename={list_id}.bib"},
    )


@router.get("/{list_id}/export/ris")
async def export_ris(
    list_id: str,
    status: Optional[str] = Query(default=None),
    user_id: str = Query(default="default"),
):
    """Export reading list to RIS format."""
    from fastapi.responses import PlainTextResponse

    from paperpulse.reading_lists import ReadingStatus

    service = get_service(user_id)

    status_filter = None
    if status:
        try:
            status_filter = [ReadingStatus(status)]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    ris = service.export_to_ris(list_id, status_filter=status_filter)

    if not ris:
        raise HTTPException(status_code=404, detail="List not found or empty")

    return PlainTextResponse(
        content=ris,
        media_type="application/x-research-info-systems",
        headers={"Content-Disposition": f"attachment; filename={list_id}.ris"},
    )


@router.get("/{list_id}/export/json")
async def export_json(
    list_id: str,
    include_stats: bool = Query(default=True),
    user_id: str = Query(default="default"),
):
    """Export reading list to JSON format."""
    import json

    from fastapi.responses import PlainTextResponse

    service = get_service(user_id)

    json_data = service.export_to_json(list_id, include_stats=include_stats)

    if json_data == "{}":
        raise HTTPException(status_code=404, detail="List not found")

    return PlainTextResponse(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={list_id}.json"},
    )


@router.post("/import/json", response_model=ReadingListResponse)
async def import_json(
    json_data: str,
    user_id: str = Query(default="default"),
):
    """Import a reading list from JSON."""
    service = get_service(user_id)

    reading_list = service.import_from_json(json_data)

    if not reading_list:
        raise HTTPException(status_code=400, detail="Failed to import reading list")

    return list_to_response(reading_list)


# ==================== List Operations ====================

@router.post("/merge", response_model=ReadingListResponse)
async def merge_lists(
    source_list_ids: list[str],
    target_name: str,
    delete_sources: bool = Query(default=False),
    user_id: str = Query(default="default"),
):
    """Merge multiple reading lists into a new one."""
    service = get_service(user_id)

    merged = service.merge_lists(
        source_list_ids=source_list_ids,
        target_name=target_name,
        delete_sources=delete_sources,
    )

    if not merged:
        raise HTTPException(status_code=400, detail="Failed to merge lists")

    return list_to_response(merged)


@router.post("/{list_id}/split", response_model=ReadingListResponse)
async def split_list_by_tag(
    list_id: str,
    tag: str,
    new_list_name: Optional[str] = Query(default=None),
    user_id: str = Query(default="default"),
):
    """Split papers with a specific tag into a new list."""
    service = get_service(user_id)

    new_list = service.split_list_by_tag(
        list_id=list_id,
        tag=tag,
        new_list_name=new_list_name,
    )

    if not new_list:
        raise HTTPException(status_code=404, detail="List not found")

    return list_to_response(new_list)
