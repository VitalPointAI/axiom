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

import db.crypto as _crypto
from api.dependencies import get_effective_user_with_dek, get_pool_dep

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


def _dec_str(raw) -> Optional[str]:
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


@router.get("/api/staking/transactions")
async def get_staking_transactions(
    year: Optional[int] = Query(default=None),
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Return all staking-related transactions (stake, unstake, reward).

    D-07: SQL filters only on cleartext columns (user_id, chain, block_timestamp for year).
    tc.category is encrypted — fetched as raw BYTEA and filtered in-memory.
    """
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

            # D-07: Removed tc.category IN (...) — category is encrypted.
            # Fetch raw category BYTEA and filter in Python.
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

    for tx_hash_raw, method_name_raw, counterparty_raw, amount_raw, block_ts, direction_raw, category_raw, wallet_addr_raw, wallet_label_raw in rows:
        # Decrypt encrypted columns
        tx_hash = _dec_str(tx_hash_raw) or ""
        counterparty = _dec_str(counterparty_raw) or ""
        wallet_addr = _dec_str(wallet_addr_raw) or ""
        category = _dec_str(category_raw)

        # In-memory filter: only staking categories (D-07)
        if category not in ("stake", "unstake", "reward"):
            continue

        unix_ts = _ts_to_unix(block_ts)
        near_amount = _near_human(_dec_str(amount_raw))

        tx_type = category

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
            "wallet": wallet_label_raw or wallet_addr,
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
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Return staking rewards summary — by year, by validator, and monthly.

    D-07: tc.category is encrypted; fetch all NEAR txs joined with classifications,
    decrypt category in Python, then aggregate only 'reward' rows in-memory.
    """
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

            # D-07: Fetch all rows (no category filter in SQL) — decrypt & aggregate in Python
            cur.execute(
                f"""
                SELECT t.block_timestamp, t.amount, t.counterparty, tc.category
                FROM transactions t
                JOIN transaction_classifications tc
                    ON tc.transaction_id = t.id AND tc.user_id = t.user_id
                WHERE t.user_id = %s AND t.chain = 'near'
                  {year_filter}
                ORDER BY t.block_timestamp ASC
                """,
                params_base,
            )
            return cur.fetchall()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        all_rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    # Aggregate in-memory after decryption
    by_year_map: dict[int, dict] = {}
    by_validator_map: dict[str, dict] = {}
    by_month_map: dict[str, Decimal] = {}

    for block_ts, amount_raw, counterparty_raw, category_raw in all_rows:
        category = _dec_str(category_raw)
        if category != "reward":
            continue

        amount_str = _dec_str(amount_raw)
        try:
            amount_dec = Decimal(amount_str) if amount_str else Decimal(0)
        except Exception:
            amount_dec = Decimal(0)

        counterparty = _dec_str(counterparty_raw) or "unknown"
        ts_sec = block_ts / 1e9 if block_ts and block_ts > 1e18 else (block_ts or 0)

        import datetime as _dt
        try:
            dt = _dt.datetime.utcfromtimestamp(ts_sec)
            yr = dt.year
            month_str = dt.strftime("%Y-%m")
        except Exception:
            yr = 0
            month_str = "unknown"

        # Year aggregate
        if yr not in by_year_map:
            by_year_map[yr] = {"total_raw": Decimal(0), "count": 0}
        by_year_map[yr]["total_raw"] += amount_dec
        by_year_map[yr]["count"] += 1

        # Validator aggregate
        if counterparty not in by_validator_map:
            by_validator_map[counterparty] = {
                "total_raw": Decimal(0), "first_ts": block_ts, "last_ts": block_ts,
            }
        by_validator_map[counterparty]["total_raw"] += amount_dec
        by_validator_map[counterparty]["last_ts"] = max(by_validator_map[counterparty]["last_ts"] or 0, block_ts or 0)

        # Monthly
        if year and yr == year:
            by_month_map[month_str] = by_month_map.get(month_str, Decimal(0)) + amount_dec

    summary = []
    grand_total_near = 0.0
    grand_total_days = 0
    for yr, data in sorted(by_year_map.items()):
        near_val = _near_human(data["total_raw"])
        grand_total_near += near_val
        grand_total_days += data["count"]
        summary.append({
            "tax_year": yr,
            "total_near": near_val,
            "total_usd": 0,
            "total_cad": 0,
            "days": data["count"],
        })

    validators = sorted(by_validator_map.items(), key=lambda x: -x[1]["total_raw"])
    validators_out = []
    for v_id, vdata in validators:
        validators_out.append({
            "validator": v_id or "unknown",
            "total_near": _near_human(vdata["total_raw"]),
            "total_usd": 0,
            "total_cad": 0,
            "start_date": _unix_to_iso(_ts_to_unix(vdata["first_ts"]))[:10],
            "end_date": _unix_to_iso(_ts_to_unix(vdata["last_ts"]))[:10],
        })

    monthly_data = []
    for month, total_raw in sorted(by_month_map.items()):
        monthly_data.append({
            "month": month,
            "total_near": _near_human(total_raw),
            "total_usd": 0,
            "total_cad": 0,
        })

    return {
        "summary": summary,
        "byValidator": validators_out,
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
    user: dict = Depends(get_effective_user_with_dek),
):
    """Multichain staking overview — placeholder."""
    return {"chains": [], "totalValueUsd": 0}


@router.get("/api/validators")
async def get_validators(
    poolId: Optional[str] = Query(default=None),
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Return validators the user has staked with.

    D-07: tc.category and t.counterparty are encrypted. Fetch all NEAR staking txs
    and aggregate in-memory after decryption.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            # D-07: Removed tc.category IN (...) and t.counterparty = %s — both encrypted.
            # Fetch all NEAR transactions with classifications, decrypt + filter in Python.
            cur.execute(
                """
                SELECT t.counterparty, t.amount, t.block_timestamp, tc.category
                FROM transactions t
                JOIN transaction_classifications tc
                    ON tc.transaction_id = t.id AND tc.user_id = t.user_id
                WHERE t.user_id = %s AND t.chain = 'near'
                ORDER BY t.block_timestamp ASC
                """,
                (user_id,),
            )
            return cur.fetchall()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    # Aggregate in-memory after decryption (D-07)
    validator_data: dict[str, dict] = {}

    for counterparty_raw, amount_raw, block_ts, category_raw in rows:
        category = _dec_str(category_raw)
        if category not in ("stake", "unstake", "reward"):
            continue

        validator = _dec_str(counterparty_raw) or "unknown"

        # In-memory filter by poolId (counterparty is encrypted)
        if poolId and validator != poolId:
            continue

        amount_str = _dec_str(amount_raw)
        try:
            amount_dec = Decimal(amount_str) if amount_str else Decimal(0)
        except Exception:
            amount_dec = Decimal(0)

        if validator not in validator_data:
            validator_data[validator] = {
                "tx_count": 0,
                "total_rewards": Decimal(0),
                "total_staked": Decimal(0),
                "total_unstaked": Decimal(0),
                "first_ts": block_ts,
                "last_ts": block_ts,
            }
        vd = validator_data[validator]
        vd["tx_count"] += 1
        vd["last_ts"] = max(vd["last_ts"] or 0, block_ts or 0)
        if category == "reward":
            vd["total_rewards"] += amount_dec
        elif category == "stake":
            vd["total_staked"] += amount_dec
        elif category == "unstake":
            vd["total_unstaked"] += amount_dec

    validators = []
    for v_id, vd in sorted(validator_data.items(), key=lambda x: -x[1]["total_rewards"]):
        validators.append({
            "poolId": v_id,
            "txCount": vd["tx_count"],
            "totalRewards": _near_human(vd["total_rewards"]),
            "totalStaked": _near_human(vd["total_staked"]),
            "totalUnstaked": _near_human(vd["total_unstaked"]),
            "firstSeen": _unix_to_iso(_ts_to_unix(vd["first_ts"]))[:10],
            "lastSeen": _unix_to_iso(_ts_to_unix(vd["last_ts"]))[:10],
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
