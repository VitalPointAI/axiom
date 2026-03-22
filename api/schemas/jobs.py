"""Pydantic schemas for job status endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    """Status of a single indexing job."""

    id: int
    job_type: str
    status: str                        # queued | running | completed | failed | retrying
    progress_fetched: Optional[int] = None
    progress_total: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ActiveJobsResponse(BaseModel):
    """All active jobs for the user with pipeline stage computation."""

    jobs: List[JobStatusResponse]
    pipeline_stage: str    # Indexing | Classifying | Cost Basis | Verifying | Done | Idle
    pipeline_pct: int      # 0-100
    estimated_minutes: Optional[int] = None  # Estimated time remaining, None if unknown
