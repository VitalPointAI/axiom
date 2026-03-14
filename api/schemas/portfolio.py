"""Pydantic schemas for portfolio summary endpoints."""

from typing import List

from pydantic import BaseModel


class HoldingResponse(BaseModel):
    """A token holding derived from latest ACB snapshot."""

    token_symbol: str
    quantity: str          # Decimal as string for precision
    acb_per_unit: str      # Decimal as string
    total_acb: str         # Decimal as string (total cost basis in CAD)
    chain: str


class StakingPosition(BaseModel):
    """An active staking position."""

    validator_id: str
    staked_amount: str     # Decimal as string
    token_symbol: str


class PortfolioSummary(BaseModel):
    """Full portfolio summary response."""

    holdings: List[HoldingResponse]
    staking_positions: List[StakingPosition]
    total_holdings_count: int
