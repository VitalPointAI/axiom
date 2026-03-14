"""
CapitalGainsReport — generates capital gains CSVs for a Canadian tax year.

Produces two CSVs:
  - capital_gains_{year}.csv: chronological by disposal_date
  - capital_gains_{year}_by_token.csv: grouped/aggregated by token_symbol

Also returns a summary dict with totals and 50% inclusion rate calculation.

Inherits ReportEngine for gate check, pool wiring, and CSV helpers.
"""

import logging
import os
from decimal import Decimal
from typing import Optional

from reports.engine import ReportEngine, fiscal_year_range, fmt_cad, fmt_units

logger = logging.getLogger(__name__)

# CSV headers
_CHRONO_HEADERS = [
    'Date',
    'Token',
    'Units Disposed',
    'Proceeds (CAD)',
    'ACB Used (CAD)',
    'Fees (CAD)',
    'Gain/Loss (CAD)',
    'Superficial Loss',
    'Denied Loss (CAD)',
    'Needs Review',
]

_GROUPED_HEADERS = [
    'Token',
    'Total Units Disposed',
    'Total Proceeds (CAD)',
    'Total ACB Used (CAD)',
    'Total Fees (CAD)',
    'Total Gain/Loss (CAD)',
    'Superficial Loss Count',
    'Total Denied (CAD)',
    'Disposition Count',
]

_DISPOSAL_QUERY = """
SELECT cgl.disposal_date, cgl.token_symbol, cgl.units_disposed,
       cgl.proceeds_cad, cgl.acb_used_cad, cgl.fees_cad,
       cgl.gain_loss_cad, cgl.is_superficial_loss, cgl.denied_loss_cad,
       cgl.needs_review
FROM capital_gains_ledger cgl
WHERE cgl.user_id = %s AND cgl.tax_year = %s
ORDER BY cgl.disposal_date, cgl.id
"""

_OPENING_ACB_QUERY = """
SELECT token_symbol, total_cost_cad
FROM acb_snapshots
WHERE user_id = %s
  AND block_timestamp < %s
ORDER BY token_symbol, block_timestamp DESC
"""


class CapitalGainsReport(ReportEngine):
    """Generates capital gains reports from capital_gains_ledger.

    Usage:
        report = CapitalGainsReport(pool)
        summary = report.generate(user_id=1, tax_year=2024, output_dir='/tmp/reports')
    """

    def generate(
        self,
        user_id: int,
        tax_year: int,
        output_dir: str,
        year_end_month: int = 12,
        excluded_wallet_ids: Optional[list] = None,
    ) -> dict:
        """Generate capital gains report CSVs and return summary dict.

        Calls _check_gate() first to block on unresolved needs_review items.
        Writes chronological CSV and grouped-by-token CSV.

        Args:
            user_id: User to generate report for.
            tax_year: Tax year (calendar year label).
            output_dir: Directory to write CSV files to.
            year_end_month: Fiscal year end month (default 12 = calendar year).
            excluded_wallet_ids: Optional list of wallet_ids to exclude.

        Returns:
            Summary dict with: total_proceeds, total_acb_used, total_fees,
            total_gains, total_losses, net_gain_loss, taxable_amount,
            superficial_losses_denied, opening_acb_cad, flagged_count.
        """
        gate_result = self._check_gate(user_id, tax_year)
        flagged_count = gate_result['flagged_count']

        start_date, end_date = fiscal_year_range(tax_year, year_end_month)

        # Compute opening ACB epoch before acquiring connection
        try:
            from datetime import datetime as _dt, timezone as _tz
            _dt_obj = _dt(start_date.year, start_date.month, start_date.day, tzinfo=_tz.utc)
            start_epoch = int(_dt_obj.timestamp())
        except Exception:
            start_epoch = 0

        conn = self.pool.getconn()
        try:
            # Named cursor for server-side streaming of the main disposal query
            # (avoids loading all rows into memory for large result sets)
            named_cur = conn.cursor(name="capital_gains_stream")
            named_cur.itersize = 1000
            named_cur.execute(_DISPOSAL_QUERY, (user_id, tax_year))

            # Small opening ACB query stays as regular fetchall (tiny result set)
            acb_cur = conn.cursor()
            acb_cur.execute(_OPENING_ACB_QUERY, (user_id, start_epoch))
            opening_rows = acb_cur.fetchall()
            acb_cur.close()

            # Stream rows into memory for summary calculation and CSV writing
            rows = list(named_cur)
            named_cur.close()
        finally:
            self.pool.putconn(conn)

        # Build opening ACB map (latest snapshot per token before fiscal year start)
        opening_acb_map = {}
        for token_symbol, total_cost_cad in opening_rows:
            if token_symbol not in opening_acb_map:
                opening_acb_map[token_symbol] = Decimal(str(total_cost_cad)) if total_cost_cad is not None else Decimal('0')

        # Calculate summary
        summary = self._calculate_summary(rows, opening_acb_map, flagged_count)

        # Write CSVs
        self._write_chronological_csv(output_dir, tax_year, rows, flagged_count)
        self._write_grouped_csv(output_dir, tax_year, rows)

        return summary

    def _calculate_summary(self, rows: list, opening_acb_map: dict, flagged_count: int) -> dict:
        """Calculate summary totals from disposal rows.

        Args:
            rows: Raw rows from capital_gains_ledger query.
            opening_acb_map: Dict of token_symbol -> opening ACB (prior year carryforward).
            flagged_count: Number of needs_review items (from gate check).

        Returns:
            Summary dict.
        """
        total_proceeds = Decimal('0')
        total_acb_used = Decimal('0')
        total_fees = Decimal('0')
        total_gains = Decimal('0')
        total_losses = Decimal('0')
        superficial_losses_denied = Decimal('0')

        for row in rows:
            (disposal_date, token_symbol, units_disposed, proceeds_cad,
             acb_used_cad, fees_cad, gain_loss_cad, is_superficial_loss,
             denied_loss_cad, needs_review) = row

            proceeds = Decimal(str(proceeds_cad)) if proceeds_cad is not None else Decimal('0')
            acb = Decimal(str(acb_used_cad)) if acb_used_cad is not None else Decimal('0')
            fees = Decimal(str(fees_cad)) if fees_cad is not None else Decimal('0')
            gain_loss = Decimal(str(gain_loss_cad)) if gain_loss_cad is not None else Decimal('0')
            denied = Decimal(str(denied_loss_cad)) if denied_loss_cad is not None else Decimal('0')

            total_proceeds += proceeds
            total_acb_used += acb
            total_fees += fees

            if gain_loss > Decimal('0'):
                total_gains += gain_loss
            else:
                total_losses += gain_loss

            if is_superficial_loss and denied_loss_cad is not None:
                superficial_losses_denied += denied

        net_gain_loss = total_gains + total_losses  # losses are negative
        taxable_amount = net_gain_loss * Decimal('0.50')

        # opening_acb_cad: sum of all per-token opening ACBs
        opening_acb_cad = sum(opening_acb_map.values(), Decimal('0'))

        return {
            'total_proceeds': total_proceeds,
            'total_acb_used': total_acb_used,
            'total_fees': total_fees,
            'total_gains': total_gains,
            'total_losses': total_losses,
            'net_gain_loss': net_gain_loss,
            'taxable_amount': taxable_amount,
            'superficial_losses_denied': superficial_losses_denied,
            'opening_acb_cad': opening_acb_cad,
            'flagged_count': flagged_count,
        }

    def _write_chronological_csv(
        self,
        output_dir: str,
        tax_year: int,
        rows: list,
        flagged_count: int,
    ) -> str:
        """Write chronological capital gains CSV.

        File: capital_gains_{year}.csv
        If specialist_override and flagged_count > 0, appends a NOTE footnote row.

        Args:
            output_dir: Directory for output.
            tax_year: Tax year label for filename.
            rows: Disposal rows from DB.
            flagged_count: Number of needs_review items.

        Returns:
            Path written.
        """
        output_path = os.path.join(output_dir, f'capital_gains_{tax_year}.csv')
        data_rows = []

        for row in rows:
            (disposal_date, token_symbol, units_disposed, proceeds_cad,
             acb_used_cad, fees_cad, gain_loss_cad, is_superficial_loss,
             denied_loss_cad, needs_review) = row

            data_rows.append([
                str(disposal_date),
                token_symbol,
                fmt_units(units_disposed),
                fmt_cad(proceeds_cad),
                fmt_cad(acb_used_cad),
                fmt_cad(fees_cad),
                fmt_cad(gain_loss_cad),
                'Yes' if is_superficial_loss else 'No',
                fmt_cad(denied_loss_cad),
                'Yes' if needs_review else 'No',
            ])

        # Append specialist footnote if applicable
        if self.specialist_override and flagged_count > 0:
            data_rows.append([
                f'NOTE: {flagged_count} items flagged for specialist review',
                '', '', '', '', '', '', '', '', '',
            ])

        return self.write_csv(output_path, _CHRONO_HEADERS, data_rows)

    def _write_grouped_csv(
        self,
        output_dir: str,
        tax_year: int,
        rows: list,
    ) -> str:
        """Write grouped-by-token capital gains CSV.

        File: capital_gains_{year}_by_token.csv
        Aggregates proceeds, ACB used, fees, gain/loss, superficial loss count, denied.

        Args:
            output_dir: Directory for output.
            tax_year: Tax year label for filename.
            rows: Disposal rows from DB.

        Returns:
            Path written.
        """
        output_path = os.path.join(output_dir, f'capital_gains_{tax_year}_by_token.csv')

        # Aggregate by token_symbol
        token_data = {}
        for row in rows:
            (disposal_date, token_symbol, units_disposed, proceeds_cad,
             acb_used_cad, fees_cad, gain_loss_cad, is_superficial_loss,
             denied_loss_cad, needs_review) = row

            if token_symbol not in token_data:
                token_data[token_symbol] = {
                    'total_units': Decimal('0'),
                    'total_proceeds': Decimal('0'),
                    'total_acb': Decimal('0'),
                    'total_fees': Decimal('0'),
                    'total_gain_loss': Decimal('0'),
                    'superficial_count': 0,
                    'total_denied': Decimal('0'),
                    'count': 0,
                }
            t = token_data[token_symbol]
            t['total_units'] += Decimal(str(units_disposed)) if units_disposed is not None else Decimal('0')
            t['total_proceeds'] += Decimal(str(proceeds_cad)) if proceeds_cad is not None else Decimal('0')
            t['total_acb'] += Decimal(str(acb_used_cad)) if acb_used_cad is not None else Decimal('0')
            t['total_fees'] += Decimal(str(fees_cad)) if fees_cad is not None else Decimal('0')
            t['total_gain_loss'] += Decimal(str(gain_loss_cad)) if gain_loss_cad is not None else Decimal('0')
            if is_superficial_loss:
                t['superficial_count'] += 1
                t['total_denied'] += Decimal(str(denied_loss_cad)) if denied_loss_cad is not None else Decimal('0')
            t['count'] += 1

        data_rows = []
        for token_symbol in sorted(token_data.keys()):
            t = token_data[token_symbol]
            data_rows.append([
                token_symbol,
                fmt_units(t['total_units']),
                fmt_cad(t['total_proceeds']),
                fmt_cad(t['total_acb']),
                fmt_cad(t['total_fees']),
                fmt_cad(t['total_gain_loss']),
                str(t['superficial_count']),
                fmt_cad(t['total_denied']),
                str(t['count']),
            ])

        return self.write_csv(output_path, _GROUPED_HEADERS, data_rows)
