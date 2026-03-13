"""
ReportEngine — base class for all Axiom tax report modules.

Provides:
  - ReportBlockedError: raised when gate check finds unresolved needs_review items
  - ReportEngine: base class with gate check, pool wiring, CSV write helper
  - fiscal_year_range(): returns (start_date, end_date) for a tax year
  - fmt_cad(): formats Decimal to 2 decimal places string ('' for None)
  - fmt_units(): formats Decimal to 8 decimal places string ('' for None)

Pool pattern follows DiscrepancyReporter in verify/report.py:
  conn = pool.getconn() / pool.putconn(conn) in try/finally.
"""

import calendar
import csv
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (module-level, importable without instantiating ReportEngine)
# ---------------------------------------------------------------------------

def fiscal_year_range(tax_year: int, year_end_month: int = 12):
    """Return (start_date, end_date) for a fiscal year.

    For calendar year (year_end_month=12): Jan 1 to Dec 31 of tax_year.
    For other year-end months: (tax_year-1, month+1, 1) to (tax_year, month, last_day).

    Examples:
        fiscal_year_range(2025, 12) -> (date(2025,1,1), date(2025,12,31))
        fiscal_year_range(2025, 3)  -> (date(2024,4,1), date(2025,3,31))

    Args:
        tax_year: The tax year (year the fiscal year ends in).
        year_end_month: Last month of the fiscal year (1-12, default 12).

    Returns:
        Tuple of (start_date, end_date).
    """
    if year_end_month == 12:
        start = date(tax_year, 1, 1)
        end = date(tax_year, 12, 31)
    else:
        start_month = year_end_month + 1
        start_year = tax_year - 1
        start = date(start_year, start_month, 1)
        _, last_day = calendar.monthrange(tax_year, year_end_month)
        end = date(tax_year, year_end_month, last_day)
    return start, end


def fmt_cad(value) -> str:
    """Format a Decimal (or None) to a 2-decimal-place CAD string.

    Returns '' for None.
    """
    if value is None:
        return ''
    d = Decimal(str(value))
    return str(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def fmt_units(value) -> str:
    """Format a Decimal (or None) to an 8-decimal-place units string.

    Returns '' for None. Uses ROUND_HALF_UP for tax precision.
    """
    if value is None:
        return ''
    d = Decimal(str(value))
    return str(d.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ReportBlockedError(Exception):
    """Raised when report generation is blocked due to unresolved needs_review items.

    Attributes:
        user_id: The user whose report was blocked.
        tax_year: The tax year that was blocked.
        flagged_count: Number of items flagged for review.
    """

    def __init__(self, user_id: int, tax_year: int, flagged_count: int):
        self.user_id = user_id
        self.tax_year = tax_year
        self.flagged_count = flagged_count
        super().__init__(
            f"Report blocked for user_id={user_id} tax_year={tax_year}: "
            f"{flagged_count} items need review. "
            "Resolve all needs_review items or use specialist_override=True."
        )


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class ReportEngine:
    """Base class for Axiom tax report modules.

    Subclasses inherit:
      - _check_gate(): needs_review gate check
      - write_csv(): stdlib csv writer with directory creation
      - pool wiring pattern

    Args:
        pool: psycopg2 connection pool.
        specialist_override: If True, bypass the gate check and log a WARNING.
    """

    def __init__(self, pool, specialist_override: bool = False):
        self.pool = pool
        self.specialist_override = specialist_override

    def _check_gate(self, user_id: int, tax_year: int) -> dict:
        """Check for unresolved needs_review items before report generation.

        Queries:
          1. capital_gains_ledger: needs_review=TRUE for user + tax_year
          2. acb_snapshots: needs_review=TRUE for user within fiscal year date range
             (scoped via TO_TIMESTAMP(block_timestamp) compared to fiscal year dates)

        If flagged_count > 0 and specialist_override=False: raises ReportBlockedError.
        If specialist_override=True and flagged_count > 0: logs WARNING, returns result.

        Args:
            user_id: User to check.
            tax_year: Tax year (calendar year, i.e. year_end_month=12 assumed for gate).

        Returns:
            dict with keys: blocked (bool), flagged_count (int).

        Raises:
            ReportBlockedError: If blocked and not specialist_override.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Query 1: capital_gains_ledger needs_review count
            cur.execute(
                """
                SELECT COUNT(*) FROM capital_gains_ledger
                WHERE user_id = %s AND tax_year = %s AND needs_review = TRUE
                """,
                (user_id, tax_year),
            )
            cgl_row = cur.fetchone()
            cgl_count = cgl_row[0] if cgl_row else 0

            # Query 2: acb_snapshots needs_review count within fiscal year
            # Use calendar year range for gate check (Jan 1 – Dec 31)
            start_date, end_date = fiscal_year_range(tax_year, 12)
            cur.execute(
                """
                SELECT COUNT(*) FROM acb_snapshots
                WHERE user_id = %s
                  AND needs_review = TRUE
                  AND TO_TIMESTAMP(block_timestamp) BETWEEN %s AND %s
                """,
                (user_id, start_date, end_date),
            )
            acb_row = cur.fetchone()
            acb_count = acb_row[0] if acb_row else 0

            cur.close()
        finally:
            self.pool.putconn(conn)

        flagged_count = (cgl_count or 0) + (acb_count or 0)

        if flagged_count > 0:
            if self.specialist_override:
                logger.warning(
                    "specialist_override=True for user_id=%s tax_year=%s: "
                    "%d items flagged for review — proceeding anyway.",
                    user_id, tax_year, flagged_count,
                )
            else:
                raise ReportBlockedError(user_id, tax_year, flagged_count)

        return {'blocked': False, 'flagged_count': flagged_count}

    def write_csv(self, output_path: str, headers: list, rows: list) -> str:
        """Write a CSV file with given headers and rows.

        Creates parent directories if they do not exist. Uses stdlib csv.writer.

        Args:
            output_path: Full file path to write.
            headers: List of column header strings.
            rows: List of tuples/lists for data rows.

        Returns:
            The output_path written.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        return str(path)
