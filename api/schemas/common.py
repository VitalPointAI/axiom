"""Common Pydantic schemas shared across all API endpoints."""

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response wrapper.

    items: The current page of results.
    total: Total number of items matching the query (across all pages).
    page: Current page number (1-indexed).
    page_size: Number of items per page.
    has_more: True if there are additional pages.
    """

    items: List[T]
    total: int
    page: int
    page_size: int
    has_more: bool


class JobStatusResponse(BaseModel):
    """Job queue status response for polling long-running operations."""

    job_id: int
    job_type: str
    status: str  # queued | running | completed | failed | retrying
    progress_fetched: int
    progress_total: Optional[int] = None
    last_error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
