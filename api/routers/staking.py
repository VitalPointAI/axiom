"""Staking API — staking transactions, rewards summary, and validators.

Endpoints:
  GET /api/staking/transactions — all staking-related transactions
  GET /api/staking              — rewards summary by year/validator/month
  GET /api/staking/multichain   — stub for multichain staking overview
  GET /api/validators           — tracked validators
  POST /api/validators          — add a validator to track
  DELETE /api/validators        — remove a tracked validator

Data source: transactions + transaction_classifications tables,
filtered to stake/unstake/reward categories.
"""

import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_pool_dep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["staking"])

NEAR_DIVISOR = Decimal("1000000000000000000000000")  # 1e24 yoctoNEAR
NEAR_TS_DIVISOR = 10**9

STAKING_CATEGORIES = ("stake", "unstake", "reward")


def _ts_to_unix(ts):
    """Convert NEAR nanosecond timestamp to Unix seconds."""
    if ts and ts > 1e18:
        return ts // NEAR_TS_DIVISOR
    return ts or 0


def _near_human(raw):
    """Convert yoctoNEAR to human NEAR."""
    if raw is None:
        return 0.0
    return float(Decimal(str(raw)) / NEAR_DIVISOR)


@router.get("/api/staking/transactions")
async def get_staking_transactions(
    year: Optional[int] = Query(default=None),
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return all staking-related transactions (stake, unstake, reward)."""
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            year_filter = ""
            params = [user_id]
            if year:
                year_filter = (
                    " AND EXTRACT(YEAR FROM TO_TIMESTAMP("
                    "   CASE WHEN t.block_timestamp > 1e18"
                    "     THEN t.block_timestamp / 1e9"
                    "     ELSE t.block_timestamp END"
                    " )) = %s"
                )
                params.append(year)

            cur.execute(
                f"""
                SELECT t.tx_hash, t.method_name, t.counterparty, t.amount,
                       t.block_timestamp, t.direction, tc.category,
                       w.account_id, w.label
                FROM transactions t
                JOIN transaction_classifications tc
                    ON tc.transaction_id = t.id AND tc.user_id = t.user_id
                JOIN wallets w ON w.id = t.wallet_id
                WHERE t.user_id = %s
                  AND t.chain = 'near'
                  AND tc.category IN ('stake', 'unstake', 'reward')
                  {year_filter}
                ORDER BY t.block_timestamp DESC
                """,
                params,
            )
            return cur.fetchall()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    transactions = []
    total_rewards = 0.0
    total_staked = 0.0
    total_unstaked = 0.0
    reward_count = 0
    stake_count = 0
    unstake_count = 0

    for tx_hash, method_name, counterparty, amount, block_ts, direction, category, wallet_addr, wallet_label in rows:
        unix_ts = _ts_to_unix(block_ts)
        near_amount = _near_human(amount)

        tx_type = category  # stake, unstake, reward

        if tx_type == "reward":
            total_rewards += near_amount
            reward_count += 1
        elif tx_type == "stake":
            total_staked += near_amount
            stake_count += 1
        elif tx_type == "unstake":
            total_unstaked += near_amount
            unstake_count += 1

        # Validator is the counterparty for staking txs
        validator = counterparty or ""

        transactions.append({
            "type": tx_type,
            "date": _unix_to_iso(unix_ts),
            "validator": validator,
            "wallet": wallet_label or wallet_addr,
            "amount_near": near_amount,
            "tx_hash": tx_hash,
        })

    return {
        "transactions": transactions,
        "stats": {
            "totalRewards": total_rewards,
            "totalStaked": total_staked,
            "totalUnstaked": total_unstaked,
            "rewardCount": reward_count,
            "stakeCount": stake_count,
            "unstakeCount": unstake_count,
        },
    }


@router.get("/api/staking")
async def get_staking_summary(
    year: Optional[int] = Query(default=None),
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return staking rewards summary — by year, by validator, and monthly."""
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            year_filter = ""
            params_base = [user_id]
            if year:
                year_filter = (
                    " AND EXTRACT(YEAR FROM TO_TIMESTAMP("
                    "   CASE WHEN t.block_timestamp > 1e18"
                    "     THEN t.block_timestamp / 1e9"
                    "     ELSE t.block_timestamp END"
                    " )) = %s"
                )
                params_base.append(year)

            # By year summary
            cur.execute(
                f"""
                SELECT EXTRACT(YEAR FROM TO_TIMESTAMP(
                    CASE WHEN t.block_timestamp > 1e18
                        THEN t.block_timestamp / 1e9
                        ELSE t.block_timestamp END
                ))::int AS yr,
                SUM(t.amount) AS total_raw,
                COUNT(*) AS days
                FROM transactions t
                JOIN transaction_classifications tc
                    ON tc.transaction_id = t.id AND tc.user_id = t.user_id
                WHERE t.user_id = %s AND t.chain = 'near'
                  AND tc.category = 'reward'
                  {year_filter}
                GROUP BY yr ORDER BY yr
                """,
                params_base,
            )
            by_year = cur.fetchall()

            # By validator
            cur.execute(
                f"""
                SELECT t.counterparty AS validator,
                       SUM(t.amount) AS total_raw,
                       MIN(t.block_timestamp) AS first_ts,
                       MAX(t.block_timestamp) AS last_ts
                FROM transactions t
                JOIN transaction_classifications tc
                    ON tc.transaction_id = t.id AND tc.user_id = t.user_id
                WHERE t.user_id = %s AND t.chain = 'near'
                  AND tc.category = 'reward'
                  {year_filter}
                GROUP BY t.counterparty ORDER BY total_raw DESC
                """,
                params_base,
            )
            by_validator = cur.fetchall()

            # Monthly (only if year specified)
            monthly = []
            if year:
                cur.execute(
                    """
                    SELECT TO_CHAR(TO_TIMESTAMP(
                        CASE WHEN t.block_timestamp > 1e18
                            THEN t.block_timestamp / 1e9
                            ELSE t.block_timestamp END
                    ), 'YYYY-MM') AS month,
                    SUM(t.amount) AS total_raw
                    FROM transactions t
                    JOIN transaction_classifications tc
                        ON tc.transaction_id = t.id AND tc.user_id = t.user_id
                    WHERE t.user_id = %s AND t.chain = 'near'
                      AND tc.category = 'reward'
                      AND EXTRACT(YEAR FROM TO_TIMESTAMP(
                          CASE WHEN t.block_timestamp > 1e18
                              THEN t.block_timestamp / 1e9
                              ELSE t.block_timestamp END
                      )) = %s
                    GROUP BY month ORDER BY month
                    """,
                    [user_id, year],
                )
                monthly = cur.fetchall()

            return by_year, by_validator, monthly
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        by_year, by_validator, monthly = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    summary = []
    grand_total_near = 0.0
    grand_total_days = 0
    for yr, total_raw, days in by_year:
        near_val = _near_human(total_raw)
        grand_total_near += near_val
        grand_total_days += days
        summary.append({
            "tax_year": yr,
            "total_near": near_val,
            "total_usd": 0,  # Would need price data
            "total_cad": 0,
            "days": days,
        })

    validators = []
    for validator, total_raw, first_ts, last_ts in by_validator:
        validators.append({
            "validator": validator or "unknown",
            "total_near": _near_human(total_raw),
            "total_usd": 0,
            "total_cad": 0,
            "start_date": _unix_to_iso(_ts_to_unix(first_ts))[:10],
            "end_date": _unix_to_iso(_ts_to_unix(last_ts))[:10],
        })

    monthly_data = []
    for month, total_raw in monthly:
        monthly_data.append({
            "month": month,
            "total_near": _near_human(total_raw),
            "total_usd": 0,
            "total_cad": 0,
        })

    return {
        "summary": summary,
        "byValidator": validators,
        "monthly": monthly_data,
        "totals": {
            "total_near": grand_total_near,
            "total_usd": 0,
            "total_cad": 0,
            "total_days": grand_total_days,
        },
    }


@router.get("/api/staking/multichain")
async def get_multichain_staking(
    user: dict = Depends(get_effective_user),
):
    """Multichain staking overview — placeholder."""
    return {"chains": [], "totalValueUsd": 0}


@router.get("/api/validators")
async def get_validators(
    poolId: Optional[str] = Query(default=None),
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return validators the user has staked with."""
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            pool_filter = ""
            params = [user_id]
            if poolId:
                pool_filter = " AND t.counterparty = %s"
                params.append(poolId)

            cur.execute(
                f"""
                SELECT t.counterparty AS validator,
                       COUNT(*) AS tx_count,
                       SUM(CASE WHEN tc.category = 'reward' THEN t.amount ELSE 0 END) AS total_rewards,
                       SUM(CASE WHEN tc.category = 'stake' THEN t.amount ELSE 0 END) AS total_staked,
                       SUM(CASE WHEN tc.category = 'unstake' THEN t.amount ELSE 0 END) AS total_unstaked,
                       MIN(t.block_timestamp) AS first_seen,
                       MAX(t.block_timestamp) AS last_seen
                FROM transactions t
                JOIN transaction_classifications tc
                    ON tc.transaction_id = t.id AND tc.user_id = t.user_id
                WHERE t.user_id = %s AND t.chain = 'near'
                  AND tc.category IN ('stake', 'unstake', 'reward')
                  {pool_filter}
                GROUP BY t.counterparty
                ORDER BY total_rewards DESC
                """,
                params,
            )
            return cur.fetchall()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    validators = []
    for validator, tx_count, rewards, staked, unstaked, first_ts, last_ts in rows:
        validators.append({
            "poolId": validator or "unknown",
            "txCount": tx_count,
            "totalRewards": _near_human(rewards),
            "totalStaked": _near_human(staked),
            "totalUnstaked": _near_human(unstaked),
            "firstSeen": _unix_to_iso(_ts_to_unix(first_ts))[:10],
            "lastSeen": _unix_to_iso(_ts_to_unix(last_ts))[:10],
        })

    return {"validators": validators}


def _unix_to_iso(ts):
    """Convert Unix timestamp to ISO date string."""
    from datetime import datetime, timezone
    if not ts or ts <= 0:
        return "1970-01-01T00:00:00Z"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OSError, ValueError):
        return "1970-01-01T00:00:00Z"
