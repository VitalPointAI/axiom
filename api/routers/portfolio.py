"""Portfolio summary endpoint.

Endpoint:
  GET /api/portfolio/summary — holdings from latest ACB snapshots + staking positions

Uses latest ACB snapshot per (user_id, token_symbol) to derive holdings.
Staking positions from latest staking_events per validator.
All endpoints filter by user_id for multi-user isolation.
"""

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_pool_dep
from api.schemas.portfolio import HoldingResponse, PortfolioSummary, StakingPosition

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


# ---------------------------------------------------------------------------
# GET /api/portfolio/summary
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return portfolio holdings from latest ACB snapshots + active staking positions.

    Holdings: latest acb_snapshot per (user_id, token_symbol), using a window
    function to get the most recent row per token.

    Staking: latest staking_events per validator from the user's wallets.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            # Latest ACB snapshot per token using window function ROW_NUMBER
            cur.execute(
                """
                SELECT
                    token_symbol,
                    quantity,
                    acb_per_unit,
                    total_cost_cad,
                    chain
                FROM (
                    SELECT
                        token_symbol,
                        quantity,
                        acb_per_unit,
                        total_cost_cad,
                        chain,
                        ROW_NUMBER() OVER (
                            PARTITION BY token_symbol
                            ORDER BY as_of_date DESC
                        ) AS rn
                    FROM acb_snapshots
                    WHERE user_id = %s
                ) ranked
                WHERE rn = 1
                ORDER BY token_symbol
                """,
                (user_id,),
            )
            acb_rows = cur.fetchall()

            # Latest staking position per validator from user's wallets
            cur.execute(
                """
                SELECT
                    se.validator_id,
                    se.staked_amount,
                    se.token_symbol
                FROM staking_events se
                JOIN wallets w ON w.id = se.wallet_id
                WHERE w.user_id = %s
                  AND se.event_type = 'stake'
                  AND (se.validator_id, se.created_at) IN (
                      SELECT validator_id, MAX(created_at)
                      FROM staking_events se2
                      JOIN wallets w2 ON w2.id = se2.wallet_id
                      WHERE w2.user_id = %s
                      GROUP BY validator_id
                  )
                ORDER BY se.validator_id
                """,
                (user_id, user_id),
            )
            staking_rows = cur.fetchall()
            return acb_rows, staking_rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        acb_rows, staking_rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    holdings = [
        HoldingResponse(
            token_symbol=row[0],
            quantity=str(row[1]),
            acb_per_unit=str(row[2]),
            total_acb=str(row[3]),
            chain=str(row[4]) if row[4] else "NEAR",
        )
        for row in acb_rows
    ]

    staking_positions = [
        StakingPosition(
            validator_id=str(row[0]),
            staked_amount=str(row[1]),
            token_symbol=str(row[2]),
        )
        for row in staking_rows
    ]

    return PortfolioSummary(
        holdings=holdings,
        staking_positions=staking_positions,
        total_holdings_count=len(holdings),
    )


# ---------------------------------------------------------------------------
# Stub GET "" for unauthenticated 401 guard (required by conftest auth tests)
# ---------------------------------------------------------------------------


@router.get("")
async def get_portfolio_stub(user=Depends(get_effective_user)):
    """Stub root endpoint — enforces auth so unauthenticated returns 401."""
    return {}
