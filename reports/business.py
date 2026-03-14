"""
BusinessIncomeStatement — corporate/business crypto income report.

Aggregates all revenue streams for business income view:
  - Crypto income (staking rewards, vesting, airdrops)
  - Capital gains (net)
  - COGS (if tax_treatment in ['business_inventory', 'hybrid'])
  - Fiat deposits/withdrawals from exchange records

Supports tax_treatment:
  - 'capital': Standard capital property treatment (50% inclusion)
  - 'business_inventory': Full business inventory (100% + COGS)
  - 'hybrid': Both views generated

CSV: business_income_{year}.csv
"""

import logging
from decimal import Decimal
from typing import Optional

from reports.engine import ReportEngine, fmt_cad

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_CRYPTO_INCOME_SQL = """
SELECT SUM(fmv_cad) AS total_income_cad
FROM income_ledger
WHERE user_id = %s AND tax_year = %s
"""

_CAPITAL_GAINS_SQL = """
SELECT SUM(gain_loss_cad) AS net_gain_loss_cad
FROM capital_gains_ledger
WHERE user_id = %s AND tax_year = %s
"""

_FIAT_FLOW_SQL = """
SELECT tx_type, SUM(quantity) AS total_cad
FROM exchange_transactions
WHERE user_id = %s
  AND tx_type IN ('fiat_deposit', 'fiat_withdrawal', 'deposit', 'withdrawal')
  AND UPPER(asset) IN ('CAD', 'USD')
  AND EXTRACT(YEAR FROM timestamp) = %s
GROUP BY tx_type
"""


class BusinessIncomeStatement(ReportEngine):
    """Business crypto income statement aggregating all revenue streams.

    Supports three tax treatments:
      - 'capital': Capital property (50% inclusion rate)
      - 'business_inventory': Business inventory (100% inclusion + COGS)
      - 'hybrid': Generates both views in the same CSV

    CSV: business_income_{year}.csv
    Headers: Category, Amount (CAD), Notes
    """

    def generate(
        self,
        user_id: int,
        tax_year: int,
        output_dir: str,
        year_end_month: int = 12,
        tax_treatment: str = 'capital',
    ) -> dict:
        """Generate business income statement.

        Args:
            user_id: User to report for.
            tax_year: Tax year.
            output_dir: Directory to write CSV.
            year_end_month: Fiscal year end month (default 12).
            tax_treatment: 'capital', 'business_inventory', or 'hybrid'.

        Returns:
            dict with: crypto_income_cad, capital_gains_net_cad,
                      fiat_deposits_cad, fiat_withdrawals_cad,
                      net_business_income_cad, output_path.
                      For 'hybrid': also includes 'capital_view' and 'business_view' keys.
        """
        self._check_gate(user_id, tax_year)

        # Fetch COGS if needed
        cogs_cad: Optional[Decimal] = None
        if tax_treatment in ('business_inventory', 'hybrid'):
            from reports.inventory import COGSReport
            cogs_report = COGSReport(self.pool, specialist_override=self.specialist_override)
            cogs_summary = cogs_report.generate(
                user_id=user_id,
                tax_year=tax_year,
                output_dir=output_dir,
                year_end_month=year_end_month,
                tax_treatment=tax_treatment if tax_treatment != 'hybrid' else 'capital',
            )
            cogs_cad = cogs_summary['total_cogs_cad']

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # 1. Crypto income from income_ledger
            cur.execute(_CRYPTO_INCOME_SQL, (user_id, tax_year))
            income_row = cur.fetchall()
            crypto_income = Decimal('0')
            if income_row and income_row[0][0] is not None:
                crypto_income = Decimal(str(income_row[0][0]))

            # 2. Capital gains (net)
            cur.execute(_CAPITAL_GAINS_SQL, (user_id, tax_year))
            gains_row = cur.fetchall()
            capital_gains_net = Decimal('0')
            if gains_row and gains_row[0][0] is not None:
                capital_gains_net = Decimal(str(gains_row[0][0]))

            # 3. Fiat flow from exchange_transactions
            cur.execute(_FIAT_FLOW_SQL, (user_id, tax_year))
            fiat_rows = cur.fetchall()
            cur.close()
        finally:
            self.pool.putconn(conn)

        fiat_deposits = Decimal('0')
        fiat_withdrawals = Decimal('0')
        for tx_type, total_cad in fiat_rows:
            if total_cad is None:
                continue
            amount = Decimal(str(total_cad))
            if tx_type in ('fiat_deposit', 'deposit'):
                fiat_deposits += amount
            elif tx_type in ('fiat_withdrawal', 'withdrawal'):
                fiat_withdrawals += amount

        # Build summary dict
        summary = {
            'crypto_income_cad': crypto_income,
            'capital_gains_net_cad': capital_gains_net,
            'fiat_deposits_cad': fiat_deposits,
            'fiat_withdrawals_cad': fiat_withdrawals,
            'tax_treatment': tax_treatment,
        }

        if tax_treatment == 'hybrid':
            # Capital view: 50% inclusion on gains
            capital_taxable = capital_gains_net * Decimal('0.50')
            capital_net = crypto_income + capital_taxable + fiat_deposits - fiat_withdrawals
            summary['capital_view'] = {
                'crypto_income_cad': crypto_income,
                'taxable_capital_gains_cad': capital_taxable,
                'fiat_net_cad': fiat_deposits - fiat_withdrawals,
                'net_business_income_cad': capital_net,
                'inclusion_rate': '50%',
            }
            # Business inventory view: 100% inclusion + COGS
            business_net = crypto_income + capital_gains_net + (cogs_cad or Decimal('0')) + fiat_deposits - fiat_withdrawals
            summary['business_view'] = {
                'crypto_income_cad': crypto_income,
                'capital_gains_net_cad': capital_gains_net,
                'cogs_cad': cogs_cad or Decimal('0'),
                'fiat_net_cad': fiat_deposits - fiat_withdrawals,
                'net_business_income_cad': business_net,
                'inclusion_rate': '100%',
            }
            net_income = capital_net  # use capital view as primary
        elif tax_treatment == 'business_inventory':
            summary['cogs_cad'] = cogs_cad or Decimal('0')
            net_income = crypto_income + capital_gains_net + (cogs_cad or Decimal('0')) + fiat_deposits - fiat_withdrawals
        else:
            # capital treatment: 50% inclusion
            net_income = crypto_income + (capital_gains_net * Decimal('0.50')) + fiat_deposits - fiat_withdrawals

        summary['net_business_income_cad'] = net_income

        # Write CSV
        csv_rows = self._build_csv_rows(summary, tax_treatment, cogs_cad)
        output_path = self.write_csv(
            f'{output_dir}/business_income_{tax_year}.csv',
            ['Category', 'Amount (CAD)', 'Notes'],
            csv_rows,
        )
        summary['output_path'] = output_path

        return summary

    def _build_csv_rows(
        self,
        summary: dict,
        tax_treatment: str,
        cogs_cad: Optional[Decimal],
    ) -> list:
        """Build CSV row data from summary dict."""
        rows = []

        if tax_treatment == 'hybrid':
            # Capital view section
            rows.append(['--- Capital Property View (50% Inclusion) ---', '', ''])
            cv = summary['capital_view']
            rows.append(['Crypto Income (Staking/Vesting)', fmt_cad(cv['crypto_income_cad']), ''])
            rows.append(['Capital Gains (Net, 50% included)', fmt_cad(cv['taxable_capital_gains_cad']), '50% inclusion rate'])
            rows.append(['Fiat Net (Deposits - Withdrawals)', fmt_cad(cv['fiat_net_cad']), ''])
            rows.append(['Net Business Income (Capital View)', fmt_cad(cv['net_business_income_cad']), ''])
            rows.append(['', '', ''])
            # Business inventory view section
            rows.append(['--- Business Inventory View (100% Inclusion) ---', '', ''])
            bv = summary['business_view']
            rows.append(['Crypto Income (Staking/Vesting)', fmt_cad(bv['crypto_income_cad']), ''])
            rows.append(['Capital Gains (Net, 100% included)', fmt_cad(bv['capital_gains_net_cad']), '100% inclusion rate'])
            rows.append(['COGS', fmt_cad(bv['cogs_cad']), 'Cost of Goods Sold'])
            rows.append(['Fiat Net (Deposits - Withdrawals)', fmt_cad(bv['fiat_net_cad']), ''])
            rows.append(['Net Business Income (Inventory View)', fmt_cad(bv['net_business_income_cad']), ''])
        else:
            rows.append(['Crypto Income (Staking/Vesting)', fmt_cad(summary['crypto_income_cad']), ''])
            if tax_treatment == 'capital':
                inclusion_note = '50% inclusion rate'
                cg_amount = summary['capital_gains_net_cad'] * Decimal('0.50')
            else:
                inclusion_note = '100% inclusion rate'
                cg_amount = summary['capital_gains_net_cad']
            rows.append(['Capital Gains (Net)', fmt_cad(cg_amount), inclusion_note])
            if cogs_cad is not None:
                rows.append(['COGS', fmt_cad(cogs_cad), 'Cost of Goods Sold'])
            rows.append(['Fiat Deposits', fmt_cad(summary['fiat_deposits_cad']), ''])
            rows.append(['Fiat Withdrawals', fmt_cad(summary['fiat_withdrawals_cad']), ''])
            rows.append(['Net Business Income', fmt_cad(summary['net_business_income_cad']), ''])

        return rows
