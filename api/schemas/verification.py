"""Pydantic schemas for verification dashboard endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class IssueGroup(BaseModel):
    """Summary of verification issues grouped by diagnosis category."""

    category: str
    count: int
    severity: str  # "high" | "medium" | "low"
    description: str
    suggested_action: str


class VerificationSummary(BaseModel):
    """Response for GET /api/verification/summary."""

    groups: List[IssueGroup]
    total_issues: int
    needs_review_count: int


class VerificationIssue(BaseModel):
    """A single verification issue with full detail."""

    id: int
    wallet_id: int
    account_id: Optional[str] = None
    token_symbol: str
    verification_type: str
    status: str
    expected_balance: Optional[str] = None
    actual_balance: Optional[str] = None
    discrepancy: Optional[str] = None
    diagnosis_category: Optional[str] = None
    diagnosis_detail: Optional[Dict[str, Any]] = None
    needs_review: bool
    created_at: str


class ResolveRequest(BaseModel):
    """Request body for POST /api/verification/resolve/{id}."""

    resolution_notes: Optional[str] = None
    mark_reviewed: bool = True


class NeedsReviewCountResponse(BaseModel):
    """Response for GET /api/verification/needs-review-count."""

    total: int
    verification_results: int
    transaction_classifications: int
    capital_gains_ledger: int
