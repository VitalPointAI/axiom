"""Pydantic schemas for wallet endpoints."""

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator

# NEAR account IDs: alphanumeric characters, dots, and hyphens (1–64 chars).
# Implicit accounts are 64 hex chars; named accounts contain dots.
_NEAR_ACCOUNT_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")

# EVM addresses: '0x' followed by exactly 40 hex characters.
_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class WalletCreate(BaseModel):
    """Request body for creating a new wallet."""

    chain: str = "NEAR"
    account_id: str

    @field_validator("account_id")
    @classmethod
    def validate_account_id(cls, v: str, info) -> str:
        # chain is declared before account_id so info.data contains it by now.
        chain = (info.data.get("chain") or "NEAR").upper() if info.data else "NEAR"
        if chain == "NEAR":
            if not _NEAR_ACCOUNT_RE.match(v):
                raise ValueError(
                    "Invalid NEAR account ID. Must be 1–64 characters containing only "
                    "alphanumeric characters, dots, underscores, or hyphens."
                )
        elif chain in ("ETH", "EVM", "ETHEREUM", "POLYGON", "BASE", "ARBITRUM", "OPTIMISM"):
            if not _EVM_ADDRESS_RE.match(v):
                raise ValueError(
                    "Invalid EVM address. Must be '0x' followed by 40 hexadecimal characters."
                )
        return v


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


class WalletsListResponse(BaseModel):
    """Wrapped list of wallets."""

    wallets: List[WalletResponse]


class SyncStatusResponse(BaseModel):
    """Pipeline stage progress for a wallet."""

    wallet_id: int
    stage: str  # Indexing | Classifying | Cost Basis | Verifying | Done | Idle
    pct: int    # 0-100
    detail: str
    jobs: List[JobSummary] = []
