"""Portfolio summary endpoint.

Endpoint:
  GET /api/portfolio/summary — holdings from latest ACB snapshots + staking positions

Uses latest ACB snapshot per (user_id, token_symbol) to derive holdings.
Staking positions from latest staking_events per validator.
All endpoints filter by user_id for multi-user isolation.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

import db.crypto as _crypto
from api.dependencies import get_effective_user_with_dek, get_pool_dep
from api.schemas.portfolio import HoldingResponse, PortfolioSummary, StakingPosition

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


# ---------------------------------------------------------------------------
# GET /api/portfolio/summary
# ---------------------------------------------------------------------------


def _dec_str(raw) -> str:
    """Decrypt raw BYTEA from psycopg2 using the current context DEK.

    If raw is already a str (e.g. in tests where mocks return plaintext),
    return it unchanged — EncryptedBytes.process_result_value() operates on bytes only.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    v = _crypto.EncryptedBytes().process_result_value(bytes(raw), None)
    return str(v) if v is not None else None


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Return portfolio holdings from latest ACB snapshots + active staking positions.

    D-07: token_symbol, validator_id, event_type, amount are all encrypted.
    SQL fetches all rows; Python decrypts and aggregates.

    Holdings: latest acb_snapshot per (user_id, token_symbol), using a window
    function to get the most recent row per token.

    Staking: latest staking_events per validator from the user's wallets.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            # D-07: token_symbol, units_after, acb_per_unit_cad, total_cost_cad are encrypted.
            # Fetch all rows ordered by block_timestamp DESC; Python finds latest per token.
            cur.execute(
                """
                SELECT
                    token_symbol,
                    units_after,
                    acb_per_unit_cad,
                    total_cost_cad,
                    block_timestamp
                FROM acb_snapshots
                WHERE user_id = %s
                ORDER BY block_timestamp DESC
                """,
                (user_id,),
            )
            acb_rows_raw = cur.fetchall()

            # D-07: event_type and validator_id are encrypted in staking_events.
            # Fetch all staking events for user's wallets; filter in Python.
            cur.execute(
                """
                SELECT
                    se.validator_id,
                    se.amount,
                    se.event_type,
                    se.created_at
                FROM staking_events se
                JOIN wallets w ON w.id = se.wallet_id
                WHERE w.user_id = %s
                ORDER BY se.created_at DESC
                """,
                (user_id,),
            )
            staking_rows_raw = cur.fetchall()
            return acb_rows_raw, staking_rows_raw
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        acb_rows_raw, staking_rows_raw = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    # Decrypt ACB rows and find latest per token
    acb_by_token: dict = {}
    for symbol_raw, units_raw, acb_raw, cost_raw, block_ts in acb_rows_raw:
        symbol = _dec_str(symbol_raw)
        if symbol is None:
            continue
        if symbol in acb_by_token:
            continue  # Already have latest (ordered DESC)
        units = _dec_str(units_raw)
        acb_per = _dec_str(acb_raw)
        total_cost = _dec_str(cost_raw)
        acb_by_token[symbol] = (units or "0", acb_per or "0", total_cost or "0")

    holdings = [
        HoldingResponse(
            token_symbol=sym,
            quantity=str(data[0]),
            acb_per_unit=str(data[1]),
            total_acb=str(data[2]),
            chain="NEAR",
        )
        for sym, data in acb_by_token.items()
    ]

    # Decrypt staking events and find latest 'deposit' per validator (in-memory)
    latest_deposit: dict = {}  # validator_id -> (amount, created_at)
    for validator_raw, amount_raw, event_type_raw, created_at in staking_rows_raw:
        event_type = _dec_str(event_type_raw)
        if event_type != "deposit":
            continue
        validator = _dec_str(validator_raw) or "unknown"
        if validator not in latest_deposit:
            # First occurrence is latest (ordered by created_at DESC)
            amount = _dec_str(amount_raw) or "0"
            latest_deposit[validator] = amount

    staking_positions = [
        StakingPosition(
            validator_id=v_id,
            staked_amount=amount,
            token_symbol="NEAR",
        )
        for v_id, amount in latest_deposit.items()
    ]

    return PortfolioSummary(
        holdings=holdings,
        staking_positions=staking_positions,
        total_holdings_count=len(holdings),
    )


# ---------------------------------------------------------------------------
# Stub GET "" for unauthenticated 401 guard (required by conftest auth tests)
# ---------------------------------------------------------------------------


@router.get(
    "",
    summary="Portfolio summary (stub)",
    description=(
        "Not yet implemented. Returns 501. "
        "Use /api/portfolio/summary for holdings and staking positions. "
        "This endpoint exists to enforce authentication; unauthenticated callers receive 401."
    ),
)
async def get_portfolio_stub(user=Depends(get_effective_user_with_dek)):
    """Stub root endpoint — enforces auth so unauthenticated returns 401.

    STUB: Portfolio root endpoint is not implemented. Use /api/portfolio/summary
    for holdings and staking positions. This endpoint exists only to enforce
    authentication for unauthenticated access tests.
    """
    raise HTTPException(status_code=501, detail="Portfolio staking positions: not yet implemented")
