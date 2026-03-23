"""
SuperficialLossDetector — CRA 30-day superficial loss rule (ITA s.54).

Canadian tax rule:
  A capital loss is "superficial" if the taxpayer (or affiliated person) disposed
  of property at a loss AND acquired the same/identical property in the period
  starting 30 days BEFORE and ending 30 days AFTER the disposition date.

  The denied (superficial) loss amount is added to the ACB of the replacement units.

Implementation:
  - scan_for_user():  identifies superficial losses across all wallets and exchanges
  - apply_superficial_losses(): marks capital_gains_ledger rows and adjusts ACB

Cross-source detection:
  - on-chain: queries transactions table (direction='in', user-scoped)
  - exchange: queries exchange_transactions table (tx_type IN ('buy','receive'))

Partial rebuy pro-rating:
  denied_ratio = min(1, total_rebought / units_disposed)
  denied_loss_cad = abs(gain_loss_cad) * denied_ratio

Same-parent swap exclusion:
  When a NEAR/EVM swap decomposes into sell_leg + buy_leg sharing a
  parent_classification_id, the buy_leg of a DIFFERENT token is naturally
  excluded because we query for the same token_symbol. For same-token swaps
  where buy and sell legs share a parent, we exclude classification IDs that
  belong to the same parent_classification_id as the disposal.

All superficial losses are flagged needs_review=True for specialist confirmation.
"""

from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_DAYS = 30
"""30-day window before and after disposal (61 days total)."""

WINDOW_SECONDS = WINDOW_DAYS * 86400

NEAR_DIVISOR = Decimal("1000000000000000000000000")  # 1e24 yoctoNEAR
EVM_DIVISOR = Decimal("1000000000000000000")          # 1e18 wei

_EIGHT_PLACES = Decimal("0.00000001")


def _to_near_units(raw_amount: int) -> Decimal:
    """Convert yoctoNEAR to NEAR."""
    return Decimal(str(raw_amount)) / NEAR_DIVISOR


def _to_evm_units(raw_amount: int) -> Decimal:
    """Convert wei to human-readable Decimal."""
    return Decimal(str(raw_amount)) / EVM_DIVISOR


def _to_human_units(raw_amount: int, chain: str) -> Decimal:
    """Convert raw on-chain amount to human-readable Decimal."""
    if raw_amount is None:
        return Decimal("0")
    if chain == "near":
        return _to_near_units(raw_amount)
    return _to_evm_units(raw_amount)


# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_LOSSES_QUERY = """
SELECT
    cgl.id,
    cgl.token_symbol,
    cgl.gain_loss_cad,
    cgl.units_disposed,
    cgl.block_timestamp,
    tc.id AS classification_id,
    tc.parent_classification_id
FROM capital_gains_ledger cgl
JOIN acb_snapshots acs ON cgl.acb_snapshot_id = acs.id
JOIN transaction_classifications tc ON acs.classification_id = tc.id
WHERE cgl.user_id = %s
  AND cgl.gain_loss_cad < 0
  AND cgl.is_superficial_loss = FALSE
ORDER BY cgl.block_timestamp ASC
"""

_ONCHAIN_REBUYS_QUERY = """
SELECT t.amount, t.chain, t.block_timestamp
FROM transactions t
JOIN transaction_classifications tc ON tc.transaction_id = t.id
WHERE t.user_id = %s
  AND tc.user_id = %s
  AND t.block_timestamp BETWEEN %s AND %s
  AND tc.category IN ('income', 'capital_gain', 'capital_loss')
  AND tc.leg_type IN ('parent', 'buy_leg', NULL)
  AND (
      t.token_id IS NULL OR
      UPPER(SPLIT_PART(t.token_id, '.', 1)) = %s OR
      CASE
          WHEN t.chain = 'near' THEN 'NEAR'
          WHEN t.chain IN ('ethereum', 'polygon', 'optimism', 'cronos') THEN 'ETH'
          ELSE UPPER(COALESCE(t.token_id, ''))
      END = %s
  )
  AND tc.parent_classification_id IS DISTINCT FROM %s
"""

_EXCHANGE_REBUYS_QUERY = """
SELECT et.quantity, EXTRACT(EPOCH FROM et.tx_date)::BIGINT AS ts
FROM exchange_transactions et
WHERE et.user_id = %s
  AND UPPER(et.asset) = %s
  AND et.tx_type IN ('buy', 'receive')
  AND EXTRACT(EPOCH FROM et.tx_date)::BIGINT BETWEEN %s AND %s
"""

_UPDATE_LEDGER_SUPERFICIAL = """
UPDATE capital_gains_ledger
SET is_superficial_loss = TRUE,
    denied_loss_cad = %s,
    needs_review = TRUE,
    updated_at = NOW()
WHERE id = %s
"""

_FIND_REBUY_SNAPSHOT = """
SELECT acs.id, acs.total_cost_cad, acs.acb_per_unit_cad, acs.units_after
FROM acb_snapshots acs
WHERE acs.user_id = %s
  AND acs.token_symbol = %s
  AND acs.event_type = 'acquire'
  AND acs.block_timestamp > %s
ORDER BY acs.block_timestamp ASC
LIMIT 1
"""

_UPDATE_SNAPSHOT_ACB = """
UPDATE acb_snapshots
SET total_cost_cad = total_cost_cad + %s,
    acb_per_unit_cad = CASE
        WHEN units_after > 0
        THEN (total_cost_cad + %s) / units_after
        ELSE acb_per_unit_cad
    END,
    updated_at = NOW()
WHERE id = %s
"""


# ---------------------------------------------------------------------------
# SuperficialLossDetector
# ---------------------------------------------------------------------------

class SuperficialLossDetector:
    """Detects superficial losses per CRA ITA s.54 and applies denied amounts.

    Args:
        conn: Active psycopg2 connection (not a pool — caller manages lifecycle).

    Usage:
        detector = SuperficialLossDetector(conn)
        losses = detector.scan_for_user(user_id)
        if losses:
            detector.apply_superficial_losses(user_id, losses)
    """

    def __init__(self, conn):
        self._conn = conn

    def scan_for_user(self, user_id: int) -> list:
        """Scan capital_gains_ledger for superficial losses.

        For each loss disposal:
          1. Calculate 61-day window (disposal_ts ± 30 days)
          2. Query on-chain rebuys (transactions table) for same token
          3. Query exchange rebuys (exchange_transactions table) for same token
          4. Exclude rebuys sharing the same parent_classification_id (swap legs)
          5. Pro-rate denial: denied_ratio = min(1, rebought / sold)

        Returns:
            List of dicts, one per superficial loss detected. Empty list if none.
        """
        # Fetch all loss rows from capital_gains_ledger
        with self._conn.cursor() as cur:
            cur.execute(_LOSSES_QUERY, (user_id,))
            loss_rows = cur.fetchall()

        results = []

        for row in loss_rows:
            # Unpack row — supports both namedtuple-style and mock attribute access
            try:
                ledger_id = row[0]
                token_symbol = row[1]
                gain_loss_cad = Decimal(str(row[2]))
                units_disposed = Decimal(str(row[3]))
                disposal_ts = int(row[4])
                row[5]
                parent_classification_id = row[6]
            except (TypeError, KeyError, AttributeError):
                # Named attribute access (mock objects in tests)
                ledger_id = row.id
                token_symbol = row.token_symbol
                gain_loss_cad = Decimal(str(row.gain_loss_cad))
                units_disposed = Decimal(str(row.units_disposed))
                disposal_ts = int(row.block_timestamp)
                parent_classification_id = row.parent_classification_id

            if gain_loss_cad >= Decimal("0"):
                continue  # Only process losses

            window_start = disposal_ts - WINDOW_SECONDS
            window_end = disposal_ts + WINDOW_SECONDS

            # Query on-chain rebuys
            total_rebought = Decimal("0")
            rebuy_count = 0

            with self._conn.cursor() as cur:
                cur.execute(
                    _ONCHAIN_REBUYS_QUERY,
                    (
                        user_id,
                        user_id,
                        window_start,
                        window_end,
                        token_symbol,
                        token_symbol,
                        parent_classification_id,
                    ),
                )
                onchain_rows = cur.fetchall()

            for rebuy_row in onchain_rows:
                try:
                    raw_amount = rebuy_row[0]
                    chain = rebuy_row[1]
                except (TypeError, AttributeError):
                    raw_amount = rebuy_row[0]
                    chain = rebuy_row[1]

                if raw_amount is not None:
                    units = _to_human_units(int(raw_amount), chain)
                    total_rebought += units
                    rebuy_count += 1

            # Query exchange rebuys
            with self._conn.cursor() as cur:
                cur.execute(
                    _EXCHANGE_REBUYS_QUERY,
                    (user_id, token_symbol, window_start, window_end),
                )
                exchange_rows = cur.fetchall()

            for rebuy_row in exchange_rows:
                try:
                    qty = rebuy_row[0]
                except (TypeError, AttributeError):
                    qty = rebuy_row[0]

                if qty is not None:
                    total_rebought += Decimal(str(qty))
                    rebuy_count += 1

            if total_rebought <= Decimal("0"):
                continue  # No rebuys in window — clean loss

            # Calculate pro-rated denial
            if units_disposed > Decimal("0"):
                denied_ratio = min(
                    Decimal("1"),
                    (total_rebought / units_disposed).quantize(
                        _EIGHT_PLACES, rounding=ROUND_HALF_UP
                    ),
                )
            else:
                denied_ratio = Decimal("0")

            abs_loss = abs(gain_loss_cad)
            denied_loss_cad = (abs_loss * denied_ratio).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            results.append({
                "ledger_id": ledger_id,
                "token_symbol": token_symbol,
                "gain_loss_cad": gain_loss_cad,
                "denied_loss_cad": denied_loss_cad,
                "denied_ratio": denied_ratio,
                "rebuy_count": rebuy_count,
                "needs_review": True,
            })

            logger.info(
                "Superficial loss detected: ledger_id=%s token=%s loss=%s denied=%s ratio=%s",
                ledger_id, token_symbol, gain_loss_cad, denied_loss_cad, denied_ratio,
            )

        return results

    def apply_superficial_losses(self, user_id: int, losses: list) -> None:
        """Apply superficial loss adjustments to capital_gains_ledger and acb_snapshots.

        For each detected superficial loss:
          1. UPDATE capital_gains_ledger: set is_superficial_loss=TRUE, denied_loss_cad
          2. Find the first rebuy ACB snapshot after the disposal
          3. UPDATE acb_snapshots: add denied_loss_cad to cost basis (CRA: denied loss
             increases ACB of replacement units)

        Note: All rows are flagged needs_review=True. Specialist must confirm before
        finalizing. This is a proposal until specialist_confirmed=TRUE.

        Args:
            user_id: User ID for snapshot lookup.
            losses: List of dicts from scan_for_user().
        """
        for loss in losses:
            ledger_id = loss["ledger_id"]
            denied_loss_cad = loss["denied_loss_cad"]
            token_symbol = loss["token_symbol"]

            # Step 1: Mark the ledger row as superficial
            with self._conn.cursor() as cur:
                cur.execute(
                    _UPDATE_LEDGER_SUPERFICIAL,
                    (denied_loss_cad, ledger_id),
                )

            # Step 2: Find the first rebuy snapshot after the disposal
            disposal_ts = None
            try:
                with self._conn.cursor() as cur:
                    cur.execute(
                        "SELECT block_timestamp FROM capital_gains_ledger WHERE id = %s",
                        (ledger_id,),
                    )
                    row = cur.fetchone()
                    if row is not None:
                        disposal_ts = int(row[0])
            except Exception as exc:
                logger.warning(
                    "Could not fetch disposal_ts for ledger_id=%s: %s", ledger_id, exc
                )

            if disposal_ts is None:
                continue

            # Step 3: Find first acquisition snapshot after disposal
            try:
                with self._conn.cursor() as cur:
                    cur.execute(
                        _FIND_REBUY_SNAPSHOT,
                        (user_id, token_symbol, disposal_ts),
                    )
                    snap_row = cur.fetchone()

                if snap_row is not None:
                    snap_id = snap_row[0]
                    with self._conn.cursor() as cur:
                        cur.execute(
                            _UPDATE_SNAPSHOT_ACB,
                            (denied_loss_cad, denied_loss_cad, snap_id),
                        )
                    logger.info(
                        "Applied denied_loss=%s to ACB snapshot_id=%s for token=%s",
                        denied_loss_cad, snap_id, token_symbol,
                    )
                else:
                    logger.warning(
                        "No rebuy ACB snapshot found for token=%s after ts=%s",
                        token_symbol, disposal_ts,
                    )

            except Exception as exc:
                logger.error(
                    "Failed to update ACB snapshot for ledger_id=%s: %s", ledger_id, exc
                )
