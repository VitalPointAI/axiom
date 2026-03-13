"""
SuperficialLossReport — lists all superficial losses denied under ITA s.54.

Queries capital_gains_ledger WHERE is_superficial_loss = TRUE for the given
user and tax year. Produces a CSV for accountant review showing denied amounts.

Exports:
    SuperficialLossReport
"""

import logging
from decimal import Decimal
from pathlib import Path

from reports.engine import ReportEngine, fmt_cad, fmt_units

logger = logging.getLogger(__name__)

SUPERFICIAL_HEADERS = [
    'Date',
    'Token',
    'Units Disposed',
    'Proceeds (CAD)',
    'ACB Used (CAD)',
    'Original Loss (CAD)',
    'Denied Loss (CAD)',
    'Needs Review',
]


class SuperficialLossReport(ReportEngine):
    """Superficial Loss Report listing all CRA ITA s.54 denied losses.

    Inherits gate check, pool wiring, and CSV writing from ReportEngine.
    """

    def generate(
        self,
        user_id: int,
        tax_year: int,
        output_dir: str,
        year_end_month: int = 12,
    ) -> dict:
        """Generate superficial losses CSV.

        Queries capital_gains_ledger for all rows where is_superficial_loss = TRUE
        for the given user and tax year, ordered by disposal_date.

        Args:
            user_id: User to generate report for.
            tax_year: Tax year to filter by (capital_gains_ledger.tax_year column).
            output_dir: Directory to write CSV into.
            year_end_month: Not used for filtering (tax_year column used), but
                passed to _check_gate for consistency.

        Returns:
            dict with keys: total_denied_cad (Decimal), count (int), entries (list).
        """
        self._check_gate(user_id, tax_year)

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    disposal_date,
                    token_symbol,
                    units_disposed,
                    proceeds_cad,
                    acb_used_cad,
                    gain_loss_cad,
                    denied_loss_cad,
                    needs_review
                FROM capital_gains_ledger
                WHERE user_id = %s
                  AND tax_year = %s
                  AND is_superficial_loss = TRUE
                ORDER BY disposal_date ASC
                """,
                (user_id, tax_year),
            )
            rows = cur.fetchall()
            cur.close()
        finally:
            self.pool.putconn(conn)

        total_denied = Decimal('0')
        entries = []
        csv_rows = []

        for row in rows:
            (
                disposal_date,
                token_symbol,
                units_disposed,
                proceeds_cad,
                acb_used_cad,
                gain_loss_cad,
                denied_loss_cad,
                needs_review,
            ) = row

            denied = Decimal(str(denied_loss_cad)) if denied_loss_cad is not None else Decimal('0')
            total_denied += denied

            entries.append({
                'disposal_date': disposal_date,
                'token_symbol': token_symbol,
                'units_disposed': units_disposed,
                'proceeds_cad': proceeds_cad,
                'acb_used_cad': acb_used_cad,
                'gain_loss_cad': gain_loss_cad,
                'denied_loss_cad': denied,
                'needs_review': needs_review,
            })

            csv_rows.append((
                str(disposal_date),
                str(token_symbol),
                fmt_units(units_disposed),
                fmt_cad(proceeds_cad),
                fmt_cad(acb_used_cad),
                fmt_cad(gain_loss_cad),
                fmt_cad(denied),
                'Yes' if needs_review else 'No',
            ))

        output_path = str(Path(output_dir) / f'superficial_losses_{tax_year}.csv')
        self.write_csv(output_path, SUPERFICIAL_HEADERS, csv_rows)

        logger.info(
            "SuperficialLossReport: user_id=%s tax_year=%s count=%d total_denied=%s",
            user_id, tax_year, len(csv_rows), total_denied,
        )

        return {
            'total_denied_cad': total_denied,
            'count': len(csv_rows),
            'entries': entries,
        }
