"""
GainsCalculator — writes capital_gains_ledger and income_ledger rows.

Responsibilities:
  - record_disposal(): INSERT INTO capital_gains_ledger for each disposal event
  - record_income(): INSERT INTO income_ledger for each income event
  - clear_for_user(): DELETE existing ledger rows before a full replay

All monetary values use Decimal. tax_year is extracted from the disposal/income date.
"""

from decimal import Decimal
from datetime import datetime, timezone, date as date_type
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _ts_to_date(block_timestamp: int) -> date_type:
    """Convert Unix seconds to a date object (UTC)."""
    return datetime.fromtimestamp(block_timestamp, tz=timezone.utc).date()


_DISPOSAL_INSERT_SQL = """
INSERT INTO capital_gains_ledger (
    user_id, acb_snapshot_id, token_symbol, disposal_date, block_timestamp,
    units_disposed, proceeds_cad, acb_used_cad, fees_cad, gain_loss_cad,
    needs_review, tax_year
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (acb_snapshot_id) DO UPDATE SET
    disposal_date = EXCLUDED.disposal_date,
    block_timestamp = EXCLUDED.block_timestamp,
    units_disposed = EXCLUDED.units_disposed,
    proceeds_cad = EXCLUDED.proceeds_cad,
    acb_used_cad = EXCLUDED.acb_used_cad,
    fees_cad = EXCLUDED.fees_cad,
    gain_loss_cad = EXCLUDED.gain_loss_cad,
    needs_review = EXCLUDED.needs_review,
    tax_year = EXCLUDED.tax_year,
    updated_at = NOW()
RETURNING id
"""

_INCOME_INSERT_SQL = """
INSERT INTO income_ledger (
    user_id, source_type, staking_event_id, lockup_event_id, classification_id,
    token_symbol, income_date, block_timestamp,
    units_received, fmv_usd, fmv_cad, acb_added_cad, tax_year
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING id
"""


class GainsCalculator:
    """Writes capital gains and income ledger rows for a user.

    Takes a psycopg2 connection (not a pool — caller manages connection lifecycle).
    Designed to be instantiated once per calculate_for_user() call in ACBEngine.
    """

    def __init__(self, conn):
        """
        Args:
            conn: Active psycopg2 connection (not a pool).
        """
        self._conn = conn

    def record_disposal(
        self,
        user_id: int,
        acb_snapshot_id: int,
        token_symbol: str,
        block_timestamp: int,
        chain: str,
        units_disposed: Decimal,
        proceeds_cad: Decimal,
        acb_used_cad: Decimal,
        fees_cad: Decimal,
        gain_loss_cad: Decimal,
        needs_review: bool = False,
    ) -> Optional[int]:
        """Record a disposal event in capital_gains_ledger.

        Args:
            user_id: User who owns the disposal
            acb_snapshot_id: FK to acb_snapshots.id (UNIQUE constraint)
            token_symbol: e.g. 'NEAR', 'ETH'
            block_timestamp: Unix seconds (already normalised by ACBEngine)
            chain: 'near', 'ethereum', etc. (informational)
            units_disposed: Number of tokens disposed
            proceeds_cad: Total proceeds in CAD
            acb_used_cad: ACB used for these units
            fees_cad: Disposal fees in CAD
            gain_loss_cad: Realised gain (positive) or loss (negative)
            needs_review: Flag if data quality issues detected

        Returns:
            ledger row id, or None on error
        """
        disposal_date = _ts_to_date(block_timestamp)
        tax_year = disposal_date.year

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    _DISPOSAL_INSERT_SQL,
                    (
                        user_id,          # 0
                        acb_snapshot_id,  # 1
                        token_symbol,     # 2
                        disposal_date,    # 3
                        block_timestamp,  # 4
                        units_disposed,   # 5
                        proceeds_cad,     # 6
                        acb_used_cad,     # 7
                        fees_cad,         # 8
                        gain_loss_cad,    # 9
                        needs_review,     # 10
                        tax_year,         # 11
                    ),
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as exc:
            logger.error(
                "Failed to record disposal for user=%s snapshot=%s: %s",
                user_id, acb_snapshot_id, exc,
            )
            return None

    def record_income(
        self,
        user_id: int,
        source_type: str,
        token_symbol: str,
        block_timestamp: int,
        chain: str,
        units_received: Decimal,
        fmv_usd: Decimal,
        fmv_cad: Decimal,
        staking_event_id: Optional[int] = None,
        lockup_event_id: Optional[int] = None,
        classification_id: Optional[int] = None,
    ) -> Optional[int]:
        """Record an income event in income_ledger.

        acb_added_cad = fmv_cad (income FMV at receipt becomes cost basis).

        Args:
            user_id: User who received the income
            source_type: 'staking', 'vesting', 'airdrop', 'other'
            token_symbol: e.g. 'NEAR'
            block_timestamp: Unix seconds
            chain: 'near', 'ethereum', etc.
            units_received: Number of tokens received
            fmv_usd: Fair market value in USD at receipt
            fmv_cad: Fair market value in CAD at receipt
            staking_event_id: FK to staking_events.id if applicable
            lockup_event_id: FK to lockup_events.id if applicable
            classification_id: FK to transaction_classifications.id

        Returns:
            ledger row id, or None on error
        """
        income_date = _ts_to_date(block_timestamp)
        tax_year = income_date.year
        acb_added_cad = fmv_cad  # income FMV at receipt = cost basis

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    _INCOME_INSERT_SQL,
                    (
                        user_id,           # 0
                        source_type,       # 1
                        staking_event_id,  # 2
                        lockup_event_id,   # 3
                        classification_id, # 4
                        token_symbol,      # 5
                        income_date,       # 6
                        block_timestamp,   # 7
                        units_received,    # 8
                        fmv_usd,           # 9
                        fmv_cad,           # 10
                        acb_added_cad,     # 11
                        tax_year,          # 12
                    ),
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as exc:
            logger.error(
                "Failed to record income for user=%s type=%s: %s",
                user_id, source_type, exc,
            )
            return None

    def clear_for_user(self, user_id: int) -> None:
        """Delete all ledger rows for user before a full replay.

        Called by ACBEngine.calculate_for_user() before replaying transactions.
        """
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM capital_gains_ledger WHERE user_id = %s", (user_id,)
                )
                cur.execute(
                    "DELETE FROM income_ledger WHERE user_id = %s", (user_id,)
                )
        except Exception as exc:
            logger.error("Failed to clear ledgers for user=%s: %s", user_id, exc)
            raise
