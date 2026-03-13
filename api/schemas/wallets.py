"""Pydantic schemas for wallet endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class WalletCreate(BaseModel):
    """Request body for creating a new wallet."""

    account_id: str
    chain: str = "NEAR"


class JobSummary(BaseModel):
    """Abbreviated job summary for sync status response."""

    id: int
    job_type: str
    status: str
    progress_fetched: Optional[int] = None
    progress_total: Optional[int] = None


class WalletResponse(BaseModel):
    """Response schema for a wallet."""

    id: int
    account_id: str
    chain: str
    sync_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SyncStatusResponse(BaseModel):
    """Pipeline stage progress for a wallet."""

    wallet_id: int
    stage: str  # Indexing | Classifying | Cost Basis | Verifying | Done | Idle
    pct: int    # 0-100
    detail: str
    jobs: List[JobSummary] = []
