"""
IncomeReport — generates income summary CSVs for a Canadian tax year.

Produces two CSVs:
  - income_summary_{year}.csv: all income events in detail (ordered by income_date)
  - income_by_month_{year}.csv: grouped by month + source_type + token_symbol

Also returns a summary dict with totals broken down by source and by month.

Inherits ReportEngine for gate check, pool wiring, and CSV helpers.
"""

import logging
import os
from decimal import Decimal
from typing import Optional

from reports.engine import ReportEngine, fmt_cad, fmt_units

logger = logging.getLogger(__name__)

# CSV headers
_DETAIL_HEADERS = [
    'Date',
    'Source Type',
    'Token',
    'Units Received',
    'FMV USD',
    'FMV CAD',
    'ACB Added CAD',
]

_MONTHLY_HEADERS = [
    'Month',
    'Source Type',
    'Token',
    'Total Units',
    'Total FMV CAD',
    'Event Count',
]

_DETAIL_QUERY = """
SELECT income_date, source_type, token_symbol,
       units_received, fmv_usd, fmv_cad, acb_added_cad
FROM income_ledger
WHERE user_id = %s AND tax_year = %s
ORDER BY income_date
"""

_SUMMARY_QUERY = """
SELECT DATE_TRUNC('month', income_date) AS month, source_type, token_symbol,
       SUM(units_received) AS total_units, SUM(fmv_cad) AS total_fmv_cad,
       COUNT(*) AS event_count
FROM income_ledger
WHERE user_id = %s AND tax_year = %s
GROUP BY DATE_TRUNC('month', income_date), source_type, token_symbol
ORDER BY month, source_type, token_symbol
"""


class IncomeReport(ReportEngine):
    """Generates income reports from income_ledger.

    Usage:
        report = IncomeReport(pool)
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
        """Generate income report CSVs and return summary dict.

        Calls _check_gate() first to block on unresolved needs_review items.
        Writes detail CSV and monthly summary CSV.

        Args:
            user_id: User to generate report for.
            tax_year: Tax year (calendar year label).
            output_dir: Directory to write CSV files to.
            year_end_month: Fiscal year end month (default 12 = calendar year).
            excluded_wallet_ids: Optional list of wallet_ids to exclude (future use).

        Returns:
            Summary dict with: total_income_cad, by_source (dict), by_month (dict),
            event_count, flagged_count.
        """
        gate_result = self._check_gate(user_id, tax_year)
        flagged_count = gate_result['flagged_count']

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Detail query: all income rows ordered by date
            cur.execute(_DETAIL_QUERY, (user_id, tax_year))
            detail_rows = cur.fetchall()

            # Summary query: grouped by month + source_type + token_symbol
            cur.execute(_SUMMARY_QUERY, (user_id, tax_year))
            summary_rows = cur.fetchall()

            cur.close()
        finally:
            self.pool.putconn(conn)

        # Build summary dict
        summary = self._calculate_summary(detail_rows, summary_rows, flagged_count)

        # Write CSVs
        self._write_detail_csv(output_dir, tax_year, detail_rows, flagged_count)
        self._write_monthly_csv(output_dir, tax_year, summary_rows)

        return summary

    def _calculate_summary(
        self,
        detail_rows: list,
        summary_rows: list,
        flagged_count: int,
    ) -> dict:
        """Calculate summary totals from income rows.

        Args:
            detail_rows: All income_ledger rows for the tax year.
            summary_rows: Grouped-by-month rows from DB.
            flagged_count: Number of needs_review items.

        Returns:
            Summary dict.
        """
        total_income_cad = Decimal('0')
        by_source = {}
        by_month = {}
        event_count = 0

        for row in summary_rows:
            month, source_type, token_symbol, total_units, total_fmv_cad, count = row
            fmv = Decimal(str(total_fmv_cad)) if total_fmv_cad is not None else Decimal('0')
            cnt = int(count) if count else 0

            total_income_cad += fmv
            event_count += cnt

            # by_source: dict of source_type -> total fmv_cad
            if source_type not in by_source:
                by_source[source_type] = Decimal('0')
            by_source[source_type] += fmv

            # by_month: dict of month string -> total fmv_cad
            month_key = str(month.date()) if hasattr(month, 'date') else str(month)
            if month_key not in by_month:
                by_month[month_key] = Decimal('0')
            by_month[month_key] += fmv

        return {
            'total_income_cad': total_income_cad,
            'by_source': by_source,
            'by_month': by_month,
            'event_count': event_count,
            'flagged_count': flagged_count,
        }

    def _write_detail_csv(
        self,
        output_dir: str,
        tax_year: int,
        rows: list,
        flagged_count: int,
    ) -> str:
        """Write detail income CSV.

        File: income_summary_{year}.csv
        If specialist_override and flagged_count > 0, appends a NOTE footnote row.

        Args:
            output_dir: Directory for output.
            tax_year: Tax year label for filename.
            rows: Detail rows from income_ledger.
            flagged_count: Number of needs_review items.

        Returns:
            Path written.
        """
        output_path = os.path.join(output_dir, f'income_summary_{tax_year}.csv')
        data_rows = []

        for row in rows:
            (income_date, source_type, token_symbol,
             units_received, fmv_usd, fmv_cad, acb_added_cad) = row

            data_rows.append([
                str(income_date),
                source_type,
                token_symbol,
                fmt_units(units_received),
                fmt_cad(fmv_usd),
                fmt_cad(fmv_cad),
                fmt_cad(acb_added_cad),
            ])

        # Append specialist footnote if applicable
        if self.specialist_override and flagged_count > 0:
            data_rows.append([
                f'NOTE: {flagged_count} items flagged for specialist review',
                '', '', '', '', '', '',
            ])

        return self.write_csv(output_path, _DETAIL_HEADERS, data_rows)

    def _write_monthly_csv(
        self,
        output_dir: str,
        tax_year: int,
        rows: list,
    ) -> str:
        """Write monthly income summary CSV.

        File: income_by_month_{year}.csv

        Args:
            output_dir: Directory for output.
            tax_year: Tax year label for filename.
            rows: Grouped-by-month rows from DB.

        Returns:
            Path written.
        """
        output_path = os.path.join(output_dir, f'income_by_month_{tax_year}.csv')
        data_rows = []

        for row in rows:
            month, source_type, token_symbol, total_units, total_fmv_cad, count = row
            month_str = str(month.date()) if hasattr(month, 'date') else str(month)

            data_rows.append([
                month_str,
                source_type,
                token_symbol,
                fmt_units(total_units),
                fmt_cad(total_fmv_cad),
                str(int(count)) if count is not None else '0',
            ])

        return self.write_csv(output_path, _MONTHLY_HEADERS, data_rows)
