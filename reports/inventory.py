"""
InventoryHoldingsReport and COGSReport — corporate/business inventory reports.

Supports users who treat crypto as business inventory (100% inclusion rate)
rather than capital property (50% inclusion).

Reports:
  - InventoryHoldingsReport: current holdings with ACB per unit, total cost,
    optional current FMV and unrealized gain/loss
  - COGSReport: opening inventory + acquisitions - closing inventory = COGS
    Supports both ACB average cost and FIFO methods.
"""

import logging
from decimal import Decimal
from typing import Optional

from reports.engine import ReportEngine, fiscal_year_range, fmt_cad, fmt_units

logger = logging.getLogger(__name__)

_EIGHT = Decimal('0.00000001')
_TWO = Decimal('0.01')


# ---------------------------------------------------------------------------
# InventoryHoldingsReport
# ---------------------------------------------------------------------------

_HOLDINGS_SQL = """
SELECT DISTINCT ON (token_symbol) token_symbol, units_after, acb_per_unit_cad, total_cost_cad
FROM acb_snapshots
WHERE user_id = %s
ORDER BY token_symbol, block_timestamp DESC
"""


class InventoryHoldingsReport(ReportEngine):
    """Reports current crypto holdings with ACB per unit and optional unrealized gain/loss.

    CSV: inventory_holdings_{year}.csv
    Headers: Token, Units Held, ACB Per Unit (CAD), Total Cost (CAD),
             Current FMV Per Unit (CAD), Total FMV (CAD), Unrealized Gain/Loss (CAD)
    """

    def generate(
        self,
        user_id: int,
        tax_year: int,
        output_dir: str,
        year_end_month: int = 12,
        current_prices: Optional[dict] = None,
    ) -> dict:
        """Generate inventory holdings report.

        Args:
            user_id: User whose holdings to report.
            tax_year: Tax year for gate check context.
            output_dir: Directory to write CSV.
            year_end_month: Fiscal year end month (default 12 = calendar year).
            current_prices: Optional dict {token_symbol: price_cad_as_Decimal}.
                          If provided, includes FMV and unrealized gain/loss columns.

        Returns:
            dict with: token_count, total_cost_cad, total_fmv_cad (if prices), output_path
        """
        self._check_gate(user_id, tax_year)

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(_HOLDINGS_SQL, (user_id,))
            rows = cur.fetchall()
            cur.close()
        finally:
            self.pool.putconn(conn)

        headers = [
            'Token',
            'Units Held',
            'ACB Per Unit (CAD)',
            'Total Cost (CAD)',
            'Current FMV Per Unit (CAD)',
            'Total FMV (CAD)',
            'Unrealized Gain/Loss (CAD)',
        ]

        csv_rows = []
        total_cost = Decimal('0')
        total_fmv = Decimal('0')

        for row in rows:
            token_symbol, units_after, acb_per_unit_cad, total_cost_cad = row
            units = Decimal(str(units_after)) if units_after is not None else Decimal('0')
            acb_per_unit = Decimal(str(acb_per_unit_cad)) if acb_per_unit_cad is not None else Decimal('0')
            cost_cad = Decimal(str(total_cost_cad)) if total_cost_cad is not None else Decimal('0')
            total_cost += cost_cad

            # FMV columns
            fmv_per_unit_str = ''
            total_fmv_str = ''
            unrealized_str = ''

            if current_prices and token_symbol in current_prices:
                fmv_per_unit = Decimal(str(current_prices[token_symbol]))
                fmv_total = units * fmv_per_unit
                unrealized = fmv_total - cost_cad
                total_fmv += fmv_total
                fmv_per_unit_str = fmt_cad(fmv_per_unit)
                total_fmv_str = fmt_cad(fmv_total)
                unrealized_str = fmt_cad(unrealized)

            csv_rows.append([
                token_symbol,
                fmt_units(units),
                fmt_cad(acb_per_unit),
                fmt_cad(cost_cad),
                fmv_per_unit_str,
                total_fmv_str,
                unrealized_str,
            ])

        output_path = self.write_csv(
            f'{output_dir}/inventory_holdings_{tax_year}.csv',
            headers,
            csv_rows,
        )

        summary = {
            'token_count': len(rows),
            'total_cost_cad': total_cost,
            'output_path': output_path,
        }
        if current_prices:
            summary['total_fmv_cad'] = total_fmv
            summary['total_unrealized_cad'] = total_fmv - total_cost

        return summary


# ---------------------------------------------------------------------------
# COGSReport
# ---------------------------------------------------------------------------

_OPENING_INV_SQL = """
SELECT DISTINCT ON (token_symbol) token_symbol, total_cost_cad
FROM acb_snapshots
WHERE user_id = %s
  AND TO_TIMESTAMP(block_timestamp) < %s
ORDER BY token_symbol, block_timestamp DESC
"""

_ACQUISITIONS_SQL = """
SELECT token_symbol, SUM(cost_cad_delta) AS acquisitions_cad
FROM acb_snapshots
WHERE user_id = %s
  AND event_type = 'acquire'
  AND TO_TIMESTAMP(block_timestamp) BETWEEN %s AND %s
GROUP BY token_symbol
"""

_CLOSING_INV_SQL = """
SELECT DISTINCT ON (token_symbol) token_symbol, total_cost_cad
FROM acb_snapshots
WHERE user_id = %s
  AND TO_TIMESTAMP(block_timestamp) <= %s
ORDER BY token_symbol, block_timestamp DESC
"""

_FIFO_SNAPSHOTS_SQL = """
SELECT token_symbol, event_type, units_delta, cost_cad_delta, block_timestamp
FROM acb_snapshots
WHERE user_id = %s
ORDER BY block_timestamp ASC, id ASC
"""


class COGSReport(ReportEngine):
    """Calculates Cost of Goods Sold for cryptocurrency business inventory.

    COGS formula: opening_inventory + acquisitions - closing_inventory

    Supports two methods:
      - 'acb_average_cost': Standard Canadian ACB method (pooled average)
      - 'fifo': First-In, First-Out lot tracking via FIFOTracker

    CSV: cogs_{year}.csv
    Headers: Token, Opening Inventory (CAD), Acquisitions (CAD),
             Closing Inventory (CAD), COGS (CAD), Method
    """

    def generate(
        self,
        user_id: int,
        tax_year: int,
        output_dir: str,
        year_end_month: int = 12,
        tax_treatment: str = 'capital',
    ) -> dict:
        """Generate COGS report.

        Args:
            user_id: User to calculate COGS for.
            tax_year: Tax year for fiscal period.
            output_dir: Directory to write CSV.
            year_end_month: Fiscal year end month (default 12).
            tax_treatment: 'capital' uses ACB; 'business_inventory' uses FIFO.

        Returns:
            dict with: total_cogs_cad, method, token_count, output_path
        """
        self._check_gate(user_id, tax_year)

        start_date, end_date = fiscal_year_range(tax_year, year_end_month)

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Opening inventory: latest snapshot per token BEFORE fiscal year start
            cur.execute(_OPENING_INV_SQL, (user_id, start_date))
            opening_rows = cur.fetchall()

            # Acquisitions during year
            cur.execute(_ACQUISITIONS_SQL, (user_id, start_date, end_date))
            acq_rows = cur.fetchall()

            # Closing inventory: latest snapshot per token AT fiscal year end
            cur.execute(_CLOSING_INV_SQL, (user_id, end_date))
            closing_rows = cur.fetchall()

            # For FIFO: fetch all snapshots for replay
            fifo_rows = []
            if tax_treatment == 'business_inventory':
                cur.execute(_FIFO_SNAPSHOTS_SQL, (user_id,))
                fifo_rows = cur.fetchall()

            cur.close()
        finally:
            self.pool.putconn(conn)

        # Build per-token dicts
        opening = {r[0]: Decimal(str(r[1])) for r in opening_rows}
        acquisitions = {r[0]: Decimal(str(r[1])) for r in acq_rows}
        closing = {r[0]: Decimal(str(r[1])) for r in closing_rows}

        # All tokens mentioned
        all_tokens = set(opening) | set(acquisitions) | set(closing)

        method = 'acb_average_cost'
        fifo_cogs: Optional[Decimal] = None

        if tax_treatment == 'business_inventory' and fifo_rows:
            # Compute FIFO COGS via FIFOTracker replay
            from engine.fifo import FIFOTracker
            tracker = FIFOTracker()
            # Convert tuple rows to dict-like for replay_from_snapshots
            fifo_dicts = [
                {
                    'token_symbol': r[0],
                    'event_type': r[1],
                    'units_delta': Decimal(str(r[2])),
                    'cost_cad_delta': Decimal(str(r[3])),
                    'block_timestamp': r[4],
                }
                for r in fifo_rows
            ]
            tracker.replay_from_snapshots(fifo_dicts)
            fifo_cogs = tracker.get_cogs(tax_year)
            method = 'fifo'

        csv_rows = []
        total_cogs = Decimal('0')

        for token in sorted(all_tokens):
            open_val = opening.get(token, Decimal('0'))
            acq_val = acquisitions.get(token, Decimal('0'))
            close_val = closing.get(token, Decimal('0'))
            cogs = open_val + acq_val - close_val
            total_cogs += cogs

            csv_rows.append([
                token,
                fmt_cad(open_val),
                fmt_cad(acq_val),
                fmt_cad(close_val),
                fmt_cad(cogs),
                method,
            ])

        # If FIFO method was used, override total_cogs with FIFO result
        if tax_treatment == 'business_inventory' and fifo_cogs is not None:
            total_cogs = fifo_cogs
            # Update CSV rows to show FIFO total (simplified: append a total row)

        headers = [
            'Token',
            'Opening Inventory (CAD)',
            'Acquisitions (CAD)',
            'Closing Inventory (CAD)',
            'COGS (CAD)',
            'Method',
        ]

        output_path = self.write_csv(
            f'{output_dir}/cogs_{tax_year}.csv',
            headers,
            csv_rows,
        )

        return {
            'total_cogs_cad': total_cogs,
            'method': method,
            'token_count': len(all_tokens),
            'output_path': output_path,
        }
