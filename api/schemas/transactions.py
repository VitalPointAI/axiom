"""Pydantic schemas for transaction ledger and classification endpoints.

Exports:
    TransactionResponse         — single transaction in the unified ledger
    TransactionListResponse     — paginated ledger response
    TransactionFilters          — query parameters for GET /api/transactions
    ClassificationUpdate        — body for PATCH /api/transactions/{tx_hash}/classification
    ReviewQueueResponse         — body for GET /api/transactions/review
    ApplyChangesRequest         — body for POST /api/transactions/apply-changes
    ApplyChangesResponse        — response for POST /api/transactions/apply-changes
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# All known tax categories used across the Axiom pipeline.
_VALID_TAX_CATEGORIES = frozenset({
    # TaxCategory enum values
    "reward", "airdrop", "mining", "interest", "income", "bounty",
    "buy", "sell", "trade",
    "transfer_in", "transfer_out", "deposit", "withdrawal",
    "stake", "unstake",
    "liquidity_in", "liquidity_out",
    "loan_borrow", "loan_repay",
    "collateral_in", "collateral_out", "liquidation",
    "fee", "interest_paid",
    "gift_received", "gift_sent", "donation", "lost", "spam",
    "nft_mint", "nft_purchase", "nft_sale",
    "contract_deploy", "account_create", "internal", "unknown",
    # Additional categories used in scripts / classifiers
    "capital_gain", "capital_loss",
    "staking_income", "staking_deposit", "staking_reward",
    "unstake_return",
    "defi_deposit", "defi_withdrawal",
    "non_taxable", "fee_refund",
    "dao_withdrawal",
    "swap",
    "transfer",
    "loan_received",
    "liquidity_add", "liquidity_remove",
    "collateral_out",
    "delete_account_received",
})


# ---------------------------------------------------------------------------
# Transaction response
# ---------------------------------------------------------------------------


class TransactionResponse(BaseModel):
    """Single transaction entry in the unified ledger.

    Covers both on-chain (NEAR / EVM) and exchange transactions.
    """

    tx_hash: str
    chain: str
    timestamp: Optional[str] = None
    sender: Optional[str] = None
    receiver: Optional[str] = None
    amount: Optional[str] = None
    token_symbol: Optional[str] = None
    action_type: Optional[str] = None
    tax_category: Optional[str] = None
    sub_category: Optional[str] = None
    confidence_score: Optional[float] = None
    needs_review: bool = False
    reviewer_notes: Optional[str] = None
    source: str = "on_chain"  # "on_chain" | "exchange"


# ---------------------------------------------------------------------------
# Paginated ledger response
# ---------------------------------------------------------------------------


class TransactionListResponse(BaseModel):
    """Paginated response for GET /api/transactions."""

    transactions: List[TransactionResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ---------------------------------------------------------------------------
# Query filter parameters
# ---------------------------------------------------------------------------


class TransactionFilters(BaseModel):
    """Query parameters for the transaction ledger endpoint.

    Used as a Pydantic model for dependency injection via Query params.
    """

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    tax_category: Optional[str] = None
    asset: Optional[str] = None
    chain: Optional[str] = None
    needs_review: Optional[bool] = None
    search: Optional[str] = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=200)

    @field_validator("tax_category")
    @classmethod
    def validate_tax_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_TAX_CATEGORIES:
            raise ValueError(
                f"Invalid tax_category '{v}'. Must be one of: {sorted(_VALID_TAX_CATEGORIES)}"
            )
        return v


# ---------------------------------------------------------------------------
# Classification editing
# ---------------------------------------------------------------------------


class ClassificationUpdate(BaseModel):
    """Body for PATCH /api/transactions/{tx_hash}/classification.

    All fields are optional — only provided fields are updated.
    """

    tax_category: Optional[str] = None
    reviewer_notes: Optional[str] = None
    needs_review: Optional[bool] = None

    @field_validator("tax_category")
    @classmethod
    def validate_tax_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_TAX_CATEGORIES:
            raise ValueError(
                f"Invalid tax_category '{v}'. Must be one of: {sorted(_VALID_TAX_CATEGORIES)}"
            )
        return v


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------


class ReviewQueueResponse(BaseModel):
    """Response for GET /api/transactions/review.

    Items ordered by confidence_score ASC (least confident first) so the
    most uncertain classifications are presented first for human review.
    """

    items: List[TransactionResponse]
    counts_by_category: Dict[str, int]
    total: int


# ---------------------------------------------------------------------------
# Apply changes / trigger ACB recalculation
# ---------------------------------------------------------------------------


class ApplyChangesRequest(BaseModel):
    """Body for POST /api/transactions/apply-changes.

    If token_symbols is not provided, ACB recalculation runs for all tokens
    that have recent classification edits (updated_at > last calculate_acb
    job completion).
    """

    token_symbols: Optional[List[str]] = None


class ApplyChangesResponse(BaseModel):
    """Response for POST /api/transactions/apply-changes."""

    job_id: int
    message: str
    token_symbols: Optional[List[str]] = None
