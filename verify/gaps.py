"""Missing transaction detector for Axiom verification pipeline.

Identifies time periods where indexed transactions don't account for on-chain
balance changes, using monthly checkpoint comparison against archival NEAR RPC.

When gaps are found:
  1. Records in verification_results with diagnosis='unindexed_period'
  2. Queues targeted re-index jobs for the gap period
  3. Re-index triggers the full pipeline cascade: fetch -> classify -> ACB -> verify
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import requests

from config import FASTNEAR_ARCHIVAL_RPC, RECONCILIATION_TOLERANCES

logger = logging.getLogger(__name__)

# yoctoNEAR divisor (10^24)
YOCTO_DIVISOR = Decimal(10) ** 24

# Maximum monthly checkpoints per wallet (last 2 years)
MAX_CHECKPOINTS = 24

# Gap threshold multiplier (divergence > 2x tolerance = gap)
GAP_MULTIPLIER = Decimal("2")


class GapDetector:
    """Detects missing transactions via balance-series inference and archival RPC.

    Algorithm:
      1. Build chronological balance series from transactions table
      2. Sample at monthly checkpoints
      3. For each checkpoint, compare running balance delta to archival RPC
         balance delta (relative changes, not absolute -- archival is liquid only)
      4. Gap = divergence > 2x tolerance threshold
      5. Queue targeted re-index job for gap period

    Args:
        pool: psycopg2 connection pool
    """

    def __init__(self, pool):
        self.pool = pool

    def detect_gaps(self, user_id: int) -> dict:
        """Run gap detection for all NEAR wallets belonging to user.

        Gap detection is NEAR-only for now; EVM chains lack archival balance
        API in our stack.

        Args:
            user_id: User to scan

        Returns:
            Stats dict: {wallets_scanned, gaps_found, reindex_jobs_queued}
        """
        stats = {
            "wallets_scanned": 0,
            "gaps_found": 0,
            "reindex_jobs_queued": 0,
        }

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Get all NEAR wallets for this user
            cur.execute(
                "SELECT id, account_id FROM wallets WHERE user_id = %s AND chain = 'near'",
                (user_id,),
            )
            near_wallets = cur.fetchall()

            # Log note for EVM wallets (out of scope)
            cur.execute(
                "SELECT COUNT(*) FROM wallets WHERE user_id = %s AND chain != 'near'",
                (user_id,),
            )
            evm_count = cur.fetchone()[0]
            if evm_count > 0:
                logger.info(
                    "Gap detection not available for EVM chains in Phase 5 "
                    "(%d EVM wallets skipped for user_id=%s)",
                    evm_count, user_id,
                )

            for wallet_id, account_id in near_wallets:
                stats["wallets_scanned"] += 1
                try:
                    gaps = self._detect_wallet_gaps(
                        conn, user_id, wallet_id, account_id,
                    )
                    stats["gaps_found"] += len(gaps)
                    stats["reindex_jobs_queued"] += sum(
                        1 for g in gaps if g.get("reindex_queued")
                    )
                except Exception as exc:
                    logger.error(
                        "Gap detection failed for wallet_id=%s (%s): %s",
                        wallet_id, account_id, exc,
                    )

            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

        return stats

    def _detect_wallet_gaps(
        self, conn, user_id: int, wallet_id: int, account_id: str,
    ) -> list:
        """Detect gaps for a single NEAR wallet.

        Builds a monthly balance series from transactions, then compares
        relative balance changes against archival RPC at each checkpoint.

        Args:
            conn: Active DB connection (caller manages commit)
            user_id: User ID
            wallet_id: Wallet ID
            account_id: NEAR account ID (e.g., "vitalpointai.near")

        Returns:
            List of gap dicts with period info
        """
        cur = conn.cursor()

        # 1. Build balance series from transactions
        cur.execute(
            """
            SELECT block_timestamp, direction, amount, COALESCE(fee, 0) as fee
            FROM transactions
            WHERE wallet_id = %s AND chain = 'near'
            ORDER BY block_timestamp ASC
            """,
            (wallet_id,),
        )
        rows = cur.fetchall()

        if len(rows) < 2:
            logger.debug(
                "Wallet %s (%s): fewer than 2 transactions, skipping gap detection",
                wallet_id, account_id,
            )
            return []

        # 2. Create monthly checkpoints
        checkpoints = self._build_monthly_checkpoints(rows)

        if len(checkpoints) < 2:
            logger.debug(
                "Wallet %s (%s): fewer than 2 monthly checkpoints, skipping",
                wallet_id, account_id,
            )
            return []

        # Limit to last MAX_CHECKPOINTS to manage RPC calls
        if len(checkpoints) > MAX_CHECKPOINTS:
            checkpoints = checkpoints[-MAX_CHECKPOINTS:]

        # 3. Query archival RPC for each checkpoint
        archival_balances = {}
        for cp in checkpoints:
            block_height = cp["last_block_height"]
            if block_height is None:
                continue
            balance = self._get_archival_balance(account_id, block_height)
            if balance is not None:
                archival_balances[cp["month"]] = balance

        if len(archival_balances) < 2:
            logger.debug(
                "Wallet %s (%s): insufficient archival balances for comparison",
                wallet_id, account_id,
            )
            return []

        # 4. Compare relative changes between consecutive checkpoints
        tolerance = Decimal(RECONCILIATION_TOLERANCES.get("near", "0.01"))
        gap_threshold = GAP_MULTIPLIER * tolerance

        gaps = []
        sorted_cps = [cp for cp in checkpoints if cp["month"] in archival_balances]

        for i in range(1, len(sorted_cps)):
            prev_cp = sorted_cps[i - 1]
            curr_cp = sorted_cps[i]

            prev_month = prev_cp["month"]
            curr_month = curr_cp["month"]

            # Delta from indexed transactions
            delta_indexed = curr_cp["running_balance"] - prev_cp["running_balance"]

            # Delta from archival RPC
            delta_onchain = archival_balances[curr_month] - archival_balances[prev_month]

            # Gap = difference between the two deltas
            gap_amount = abs(delta_indexed - delta_onchain)

            if gap_amount > gap_threshold:
                gap_info = {
                    "gap_month": curr_month,
                    "gap_start_block": prev_cp["last_block_height"],
                    "gap_end_block": curr_cp["last_block_height"],
                    "delta_indexed": str(delta_indexed),
                    "delta_onchain": str(delta_onchain),
                    "gap_amount": str(gap_amount),
                    "reindex_queued": False,
                }

                # Record in verification_results
                cur.execute(
                    """
                    INSERT INTO verification_results
                        (user_id, wallet_id, chain, token_symbol,
                         diagnosis_category, diagnosis_detail,
                         diagnosis_confidence, status)
                    VALUES (%s, %s, 'near', 'NEAR',
                            'unindexed_period', %s::jsonb,
                            %s, 'open')
                    """,
                    (
                        user_id, wallet_id,
                        _json_dumps(gap_info),
                        Decimal("0.60"),
                    ),
                )

                # Queue targeted re-index
                queued = self._queue_reindex(
                    conn, user_id, wallet_id,
                    prev_cp["last_block_height"],
                    curr_cp["last_block_height"],
                )
                gap_info["reindex_queued"] = queued
                gaps.append(gap_info)

                logger.info(
                    "Gap detected for wallet_id=%s month=%s: "
                    "delta_indexed=%s delta_onchain=%s gap=%s",
                    wallet_id, curr_month,
                    delta_indexed, delta_onchain, gap_amount,
                )

        return gaps

    def _build_monthly_checkpoints(self, rows: list) -> list:
        """Build monthly balance checkpoints from transaction rows.

        Groups transactions by calendar month. For each month, computes
        the cumulative running balance and records the last block_height.

        Args:
            rows: List of (block_timestamp, direction, amount, fee) tuples
                  ordered by block_timestamp ASC

        Returns:
            List of checkpoint dicts:
              {month: "YYYY-MM", running_balance: Decimal, last_block_height: int}
        """
        running_balance = Decimal("0")
        monthly = {}  # "YYYY-MM" -> {running_balance, last_block_height}

        for block_timestamp, direction, amount, fee in rows:
            # Convert amount from yoctoNEAR to NEAR
            try:
                amount_near = Decimal(str(amount)) / YOCTO_DIVISOR
            except (InvalidOperation, TypeError):
                amount_near = Decimal("0")

            try:
                fee_near = Decimal(str(fee)) / YOCTO_DIVISOR
            except (InvalidOperation, TypeError):
                fee_near = Decimal("0")

            if direction == "in":
                running_balance += amount_near
            elif direction == "out":
                running_balance -= amount_near
            # Fees always reduce balance (deducted from sender)
            running_balance -= fee_near

            # Determine month key from block_timestamp
            # block_timestamp is stored as BIGINT (nanoseconds epoch for NEAR)
            try:
                ts = int(block_timestamp)
                # NEAR timestamps are nanoseconds; convert to seconds
                if ts > 1e15:
                    ts = ts // 1_000_000_000
                elif ts > 1e12:
                    ts = ts // 1_000
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                month_key = dt.strftime("%Y-%m")
                block_height_approx = ts  # Use timestamp as proxy for ordering
            except (ValueError, OSError, OverflowError):
                continue

            monthly[month_key] = {
                "month": month_key,
                "running_balance": running_balance,
                "last_block_height": block_height_approx,
            }

        # Sort by month and return
        return [monthly[k] for k in sorted(monthly.keys())]

    def _get_archival_balance(self, account_id: str, block_height: int) -> "Decimal | None":
        """Query archival NEAR RPC for liquid balance at a specific block height.

        Args:
            account_id: NEAR account (e.g., "vitalpointai.near")
            block_height: Block height to query

        Returns:
            Liquid balance in NEAR as Decimal, or None on error
        """
        try:
            resp = requests.post(
                FASTNEAR_ARCHIVAL_RPC,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "query",
                    "params": {
                        "request_type": "view_account",
                        "block_id": block_height,
                        "account_id": account_id,
                    },
                },
                timeout=15,
            )
            data = resp.json()

            if "error" in data:
                logger.warning(
                    "Archival RPC error for %s at block %s: %s",
                    account_id, block_height, data["error"],
                )
                return None

            result = data.get("result", {})
            amount_yocto = result.get("amount", "0")
            balance_near = Decimal(str(amount_yocto)) / YOCTO_DIVISOR
            return balance_near

        except requests.exceptions.Timeout:
            logger.warning(
                "Archival RPC timeout for %s at block %s",
                account_id, block_height,
            )
            return None
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Archival RPC request failed for %s at block %s: %s",
                account_id, block_height, exc,
            )
            return None
        except (KeyError, InvalidOperation, ValueError) as exc:
            logger.warning(
                "Archival RPC parse error for %s at block %s: %s",
                account_id, block_height, exc,
            )
            return None

    def _queue_reindex(
        self, conn, user_id: int, wallet_id: int,
        start_block: int, end_block: int,
    ) -> bool:
        """Queue a targeted re-index job for the identified gap period.

        Checks for existing pending jobs before inserting (dedup pattern).
        Cursor is set to start_block so NearFetcher resumes from there.

        Args:
            conn: Active DB connection
            user_id: User ID
            wallet_id: Wallet ID
            start_block: Block height at start of gap
            end_block: Block height at end of gap

        Returns:
            True if job was queued, False if skipped (existing pending job)
        """
        cur = conn.cursor()

        # Check for existing pending job (same dedup pattern as other handlers)
        cur.execute(
            """
            SELECT id FROM indexing_jobs
            WHERE wallet_id = %s AND job_type IN ('full_sync', 'incremental_sync')
              AND status IN ('queued', 'running')
            """,
            (wallet_id,),
        )
        existing = cur.fetchone()

        if existing is not None:
            logger.debug(
                "Skipping re-index for wallet_id=%s: existing pending job id=%s",
                wallet_id, existing[0],
            )
            return False

        # Queue targeted re-index job
        cur.execute(
            """
            INSERT INTO indexing_jobs
                (user_id, wallet_id, job_type, chain, status, priority, cursor)
            VALUES (%s, %s, 'full_sync', 'near', 'queued', 3, %s)
            """,
            (user_id, wallet_id, str(start_block)),
        )
        logger.info(
            "Queued re-index for wallet_id=%s blocks %s-%s",
            wallet_id, start_block, end_block,
        )
        return True


def _json_dumps(obj: dict) -> str:
    """Serialize dict to JSON string for JSONB insertion."""
    import json
    return json.dumps(obj)
