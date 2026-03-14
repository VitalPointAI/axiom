"""Diagnosis helpers for balance reconciliation.

Extracted from reconcile.py for maintainability.

Provides heuristic diagnosis of balance discrepancies in 4 categories:
  1. missing_staking_rewards — NEAR staking rewards not fully indexed
  2. uncounted_fees — transaction fees missing from ACB tracking
  3. unindexed_period — large time gaps in indexed transactions
  4. classification_error — own-wallet transfers not marked as internal_transfer
"""

import logging
from decimal import Decimal
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Chain divisors for converting raw amounts to human units (imported from reconcile
# to avoid duplication — kept here so diagnosis.py is self-contained for testing)
_YOCTO_NEAR = Decimal("1" + "0" * 24)  # 10^24

# Chain divisors mirror the ones in reconcile.py
_CHAIN_DIVISORS = {
    "near": _YOCTO_NEAR,
    "ethereum": Decimal("1" + "0" * 18),
    "polygon": Decimal("1" + "0" * 18),
    "cronos": Decimal("1" + "0" * 18),
    "optimism": Decimal("1" + "0" * 18),
}


class ReconcileDiagnoser:
    """Heuristic diagnosis engine for balance reconciliation discrepancies.

    Each ``diagnose_*`` method inspects the database and returns a
    ``(category, detail_dict, confidence)`` tuple, or ``None`` when the
    heuristic does not apply.

    Args:
        pool: psycopg2 connection pool shared with BalanceReconciler.
    """

    def __init__(self, pool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Public dispatcher
    # ------------------------------------------------------------------

    def auto_diagnose(
        self,
        user_id: int,
        wallet_id: int,
        chain: str,
        difference: Decimal,
    ) -> Tuple[str, dict, Decimal]:
        """Auto-diagnose discrepancy cause using 4 heuristics.

        Runs heuristics in priority order and returns the first match
        with confidence > 0.5.

        Diagnosis categories:
          1. missing_staking_rewards (NEAR only)
          2. uncounted_fees
          3. unindexed_period
          4. classification_error

        Args:
            user_id: User ID.
            wallet_id: Wallet ID.
            chain: Chain name.
            difference: actual - expected balance.

        Returns:
            Tuple of (category, detail_dict, confidence).
        """
        # 1. Missing staking rewards (NEAR only)
        if chain == "near":
            result = self.diagnose_missing_staking(wallet_id)
            if result and result[2] > Decimal("0.5"):
                return result

        # 2. Uncounted fees
        result = self.diagnose_uncounted_fees(wallet_id, chain, difference)
        if result and result[2] > Decimal("0.5"):
            return result

        # 3. Unindexed period
        result = self.diagnose_unindexed_period(wallet_id, chain)
        if result and result[2] > Decimal("0.5"):
            return result

        # 4. Classification error
        result = self.diagnose_classification_error(user_id, wallet_id)
        if result and result[2] > Decimal("0.5"):
            return result

        return ("unknown", {}, Decimal("0.0"))

    # ------------------------------------------------------------------
    # Individual diagnosis heuristics
    # ------------------------------------------------------------------

    def diagnose_missing_staking(
        self, wallet_id: int
    ) -> Optional[Tuple[str, dict, Decimal]]:
        """Check if missing staking rewards explain discrepancy.

        Compares staking reward count against expected epoch count.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Count actual rewards recorded
            cur.execute(
                """
                SELECT COUNT(*) FROM staking_events
                WHERE wallet_id = %s AND event_type = 'reward'
                """,
                (wallet_id,),
            )
            reward_count = cur.fetchone()[0]

            # Count epochs where staked balance > 0
            cur.execute(
                """
                SELECT COUNT(DISTINCT epoch_height) FROM epoch_snapshots
                WHERE wallet_id = %s AND staked_balance > 0
                """,
                (wallet_id,),
            )
            epoch_count = cur.fetchone()[0]
            cur.close()

            if epoch_count == 0:
                return None

            gap_pct = Decimal("0")
            if epoch_count > 0:
                gap_pct = (
                    Decimal(str(epoch_count - reward_count))
                    / Decimal(str(epoch_count))
                    * Decimal("100")
                )

            if gap_pct > Decimal("20"):
                confidence = Decimal("0.70")
            elif gap_pct > Decimal("10"):
                confidence = Decimal("0.50")
            else:
                return None

            detail = {
                "reward_count": reward_count,
                "expected_epoch_count": epoch_count,
                "gap_pct": float(gap_pct),
            }
            return ("missing_staking_rewards", detail, confidence)
        finally:
            self.pool.putconn(conn)

    def diagnose_uncounted_fees(
        self, wallet_id: int, chain: str, difference: Decimal
    ) -> Optional[Tuple[str, dict, Decimal]]:
        """Check if uncounted fees explain discrepancy.

        Compares total fees from transactions table against fees tracked
        in ACB disposal events.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Total fees from transactions
            cur.execute(
                """
                SELECT COALESCE(SUM(COALESCE(fee, 0)), 0)
                FROM transactions
                WHERE wallet_id = %s AND chain = %s AND direction = 'out'
                """,
                (wallet_id, chain),
            )
            total_fees_raw = Decimal(str(cur.fetchone()[0]))

            # Convert to human units
            divisor = _CHAIN_DIVISORS.get(chain, _YOCTO_NEAR)
            total_fees_onchain = total_fees_raw / divisor

            # Total fees tracked in ACB (fee disposals)
            cur.execute(
                """
                SELECT COALESCE(SUM(units_disposed), 0)
                FROM acb_snapshots
                WHERE wallet_id = %s AND event = 'fee'
                """,
                (wallet_id,),
            )
            total_fees_tracked = Decimal(str(cur.fetchone()[0]))
            cur.close()

            fee_gap = abs(total_fees_onchain - total_fees_tracked)

            if fee_gap == Decimal("0"):
                return None

            # Check if fee gap is close to balance difference
            if abs(difference) > Decimal("0"):
                ratio = fee_gap / abs(difference)
                if Decimal("0.8") <= ratio <= Decimal("1.2"):
                    confidence = Decimal("0.75")
                elif Decimal("0.5") <= ratio <= Decimal("1.5"):
                    confidence = Decimal("0.55")
                else:
                    return None
            else:
                return None

            detail = {
                "total_fees_onchain": float(total_fees_onchain),
                "total_fees_tracked": float(total_fees_tracked),
            }
            return ("uncounted_fees", detail, confidence)
        finally:
            self.pool.putconn(conn)

    def diagnose_unindexed_period(
        self, wallet_id: int, chain: str
    ) -> Optional[Tuple[str, dict, Decimal]]:
        """Check if there are large time gaps in indexed transactions.

        A gap > 7 days (604800 seconds) suggests unindexed period.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT block_timestamp
                FROM transactions
                WHERE wallet_id = %s AND chain = %s
                    AND block_timestamp IS NOT NULL
                ORDER BY block_timestamp ASC
                """,
                (wallet_id, chain),
            )
            timestamps = [row[0] for row in cur.fetchall()]
            cur.close()

            if len(timestamps) < 2:
                return None

            max_gap = 0
            gap_start = None
            gap_end = None

            for i in range(1, len(timestamps)):
                gap = timestamps[i] - timestamps[i - 1]
                if gap > max_gap:
                    max_gap = gap
                    gap_start = timestamps[i - 1]
                    gap_end = timestamps[i]

            # 7 days = 604800 seconds
            if max_gap > 604800:
                gap_days = max_gap / 86400
                detail = {
                    "gap_start": gap_start,
                    "gap_end": gap_end,
                    "gap_days": round(gap_days, 1),
                }
                return ("unindexed_period", detail, Decimal("0.60"))

            return None
        finally:
            self.pool.putconn(conn)

    def diagnose_classification_error(
        self, user_id: int, wallet_id: int
    ) -> Optional[Tuple[str, dict, Decimal]]:
        """Check for transfers to own wallets not classified as internal.

        Counts outgoing transfers where counterparty is another of the
        user's own wallet addresses but classification is not
        'internal_transfer'.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Get all user wallet addresses
            cur.execute(
                "SELECT account_id FROM wallets WHERE user_id = %s",
                (user_id,),
            )
            own_addresses = {row[0].lower() for row in cur.fetchall() if row[0]}

            if not own_addresses:
                cur.close()
                return None

            # Find outgoing transactions to own addresses
            cur.execute(
                """
                SELECT t.id, t.counterparty, tc.category
                FROM transactions t
                LEFT JOIN transaction_classifications tc ON tc.transaction_id = t.id
                WHERE t.wallet_id = %s AND t.direction = 'out'
                    AND t.counterparty IS NOT NULL
                """,
                (wallet_id,),
            )
            misclassified = 0
            for row in cur.fetchall():
                counterparty = (row[1] or "").lower()
                category = row[2]
                if (
                    counterparty in own_addresses
                    and category != "internal_transfer"
                ):
                    misclassified += 1

            cur.close()

            if misclassified > 0:
                detail = {"misclassified_transfer_count": misclassified}
                return ("classification_error", detail, Decimal("0.65"))

            return None
        finally:
            self.pool.putconn(conn)
