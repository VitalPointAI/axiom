"""
PackageBuilder — orchestrates all Axiom tax reports into a deliverable tax package.

Creates output/{year}_tax_package/ flat folder containing:
  - CSV and PDF reports (capital gains, income, ledger, T1135, inventory, business income)
  - Koinly CSV export (year-specific + full history)
  - Accounting software exports (QuickBooks IIF, Xero CSV, Sage 50 CSV, double-entry CSV)
  - Tax summary PDF (combined one-pager)

Usage:
    from reports.generate import PackageBuilder
    builder = PackageBuilder(pool, specialist_override=False)
    manifest = builder.build(
        user_id=1,
        tax_year=2024,
        output_base='output',
        year_end_month=12,
        tax_treatment='capital',
    )
    # manifest = {
    #     'files': [...],
    #     'summaries': {...},
    #     'tax_year': 2024,
    #     'output_dir': 'output/2024_tax_package',
    # }

Tax treatment values:
    'capital'           — Standard capital property (50% inclusion, no COGS)
    'business_inventory' — Full business inventory (100%, COGS deductible)
    'hybrid'            — Both views generated
"""

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from db.audit import write_audit

from reports.engine import ReportEngine, ReportBlockedError, fmt_cad
from reports.capital_gains import CapitalGainsReport
from reports.income import IncomeReport
from reports.ledger import LedgerReport
from reports.t1135 import T1135Checker
from reports.superficial import SuperficialLossReport
from reports.export import KoinlyExport, AccountingExporter
from reports.inventory import InventoryHoldingsReport, COGSReport
from reports.business import BusinessIncomeStatement

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level data fingerprint helper (importable by API routers)
# ---------------------------------------------------------------------------


def get_data_fingerprint(conn, user_id: int) -> dict:
    """Query the current DB state fingerprint for a user.

    Returns a dict with:
        last_tx_timestamp: ISO string or None
        total_tx_count: int (on-chain + exchange)
        acb_snapshot_version: ISO string or None
        needs_review_count: int

    This function is module-level so it can be imported by api.routers.reports
    without instantiating PackageBuilder.
    """
    cur = conn.cursor()
    try:
        # 1. Last on-chain transaction timestamp
        cur.execute(
            "SELECT MAX(block_timestamp) FROM transactions WHERE user_id = %s",
            (user_id,),
        )
        last_tx_ts = cur.fetchone()[0]

        # 2. On-chain transaction count
        cur.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = %s",
            (user_id,),
        )
        onchain_count = cur.fetchone()[0] or 0

        # 3. ACB snapshot version
        cur.execute(
            "SELECT MAX(updated_at) FROM acb_snapshots WHERE user_id = %s",
            (user_id,),
        )
        acb_version = cur.fetchone()[0]

        # 4. Needs-review transaction classification count
        cur.execute(
            """
            SELECT COUNT(*) FROM transaction_classifications
            WHERE user_id = %s AND needs_review = TRUE
            """,
            (user_id,),
        )
        needs_review_count = cur.fetchone()[0] or 0

        # 5. Exchange transaction count
        cur.execute(
            "SELECT COUNT(*) FROM exchange_transactions WHERE user_id = %s",
            (user_id,),
        )
        exchange_count = cur.fetchone()[0] or 0

        total_tx_count = (onchain_count or 0) + (exchange_count or 0)

        # Normalise timestamp values to ISO strings
        def _to_iso(val):
            if val is None:
                return None
            if hasattr(val, 'isoformat'):
                return val.isoformat()
            return str(val)

        return {
            'last_tx_timestamp': _to_iso(last_tx_ts),
            'total_tx_count': total_tx_count,
            'acb_snapshot_version': _to_iso(acb_version),
            'needs_review_count': needs_review_count,
        }
    finally:
        cur.close()




# ---------------------------------------------------------------------------
# Module-level data fingerprint helper (importable by API routers)
# ---------------------------------------------------------------------------


def get_data_fingerprint(conn, user_id: int) -> dict:
    """Query the current DB state fingerprint for a user.

    Returns a dict with:
        last_tx_timestamp: ISO string or None
        total_tx_count: int (on-chain + exchange)
        acb_snapshot_version: ISO string or None
        needs_review_count: int

    This function is module-level so it can be imported by api.routers.reports
    without instantiating PackageBuilder.
    """
    cur = conn.cursor()
    try:
        # 1. Last on-chain transaction timestamp
        cur.execute(
            "SELECT MAX(block_timestamp) FROM transactions WHERE user_id = %s",
            (user_id,),
        )
        last_tx_ts = cur.fetchone()[0]

        # 2. On-chain transaction count
        cur.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = %s",
            (user_id,),
        )
        onchain_count = cur.fetchone()[0] or 0

        # 3. ACB snapshot version
        cur.execute(
            "SELECT MAX(updated_at) FROM acb_snapshots WHERE user_id = %s",
            (user_id,),
        )
        acb_version = cur.fetchone()[0]

        # 4. Needs-review transaction classification count
        cur.execute(
            """
            SELECT COUNT(*) FROM transaction_classifications
            WHERE user_id = %s AND needs_review = TRUE
            """,
            (user_id,),
        )
        needs_review_count = cur.fetchone()[0] or 0

        # 5. Exchange transaction count
        cur.execute(
            "SELECT COUNT(*) FROM exchange_transactions WHERE user_id = %s",
            (user_id,),
        )
        exchange_count = cur.fetchone()[0] or 0

        total_tx_count = (onchain_count or 0) + (exchange_count or 0)

        def _to_iso(val):
            if val is None:
                return None
            if hasattr(val, 'isoformat'):
                return val.isoformat()
            return str(val)

        return {
            'last_tx_timestamp': _to_iso(last_tx_ts),
            'total_tx_count': total_tx_count,
            'acb_snapshot_version': _to_iso(acb_version),
            'needs_review_count': needs_review_count,
        }
    finally:
        cur.close()

class PackageBuilder:
    """Orchestrates all tax reports into a complete deliverable tax package.

    Performs a single gate check at the top level, then instantiates each report
    module and calls generate(). Writes both CSV and PDF outputs for each report
    that has a template.

    Args:
        pool: psycopg2 connection pool.
        specialist_override: If True, bypass the gate check and log a WARNING.
    """

    def __init__(self, pool, specialist_override: bool = False):
        self.pool = pool
        self.specialist_override = specialist_override

    def build(
        self,
        user_id: int,
        tax_year: int,
        output_base: str = 'output',
        year_end_month: int = 12,
        tax_treatment: str = 'capital',
        excluded_wallet_ids: Optional[list] = None,
    ) -> dict:
        """Build the complete tax package for a user and tax year.

        Creates ``output_base/{year}_tax_package/`` flat folder and writes all reports.

        Args:
            user_id: User to generate reports for.
            tax_year: Tax year (calendar year label).
            output_base: Base output directory (default: 'output').
            year_end_month: Fiscal year end month (default 12 = calendar year).
            tax_treatment: One of 'capital', 'business_inventory', 'hybrid'.
            excluded_wallet_ids: Optional wallet IDs to exclude from reports.

        Returns:
            dict with keys:
                files: List of all generated file paths.
                summaries: Dict of report_name -> summary_dict.
                tax_year: int
                output_dir: str (the package directory path)

        Raises:
            ReportBlockedError: If gate check fails and specialist_override=False.
        """
        # 1. Create output directory
        output_dir = os.path.join(output_base, f'{tax_year}_tax_package')
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 2. Gate check — once at top level
        engine = ReportEngine(self.pool, specialist_override=self.specialist_override)
        gate_result = engine._check_gate(user_id, tax_year)
        flagged_count = gate_result['flagged_count']

        generated_date = datetime.now().strftime('%Y-%m-%d')
        files = []
        summaries = {}

        # ----------------------------------------------------------------
        # Capital Gains
        # ----------------------------------------------------------------
        cg_report = CapitalGainsReport(self.pool, specialist_override=self.specialist_override)
        # Bypass internal gate check since we already ran it
        cg_report._gate_checked = True
        cg_summary = self._run_generate(cg_report, user_id, tax_year, output_dir,
                                        year_end_month=year_end_month,
                                        excluded_wallet_ids=excluded_wallet_ids)
        summaries['capital_gains'] = cg_summary

        # PDF: capital_gains_{year}.pdf
        cg_pdf = engine.write_pdf(
            output_path=os.path.join(output_dir, f'capital_gains_{tax_year}.pdf'),
            template_name='capital_gains.html',
            context={
                'report_title': f'Capital Gains/Losses Report — {tax_year}',
                'tax_year': tax_year,
                'generated_date': generated_date,
                'specialist_override': self.specialist_override,
                'flagged_count': flagged_count,
                'total_proceeds': fmt_cad(cg_summary.get('total_proceeds', Decimal('0'))),
                'total_acb_used': fmt_cad(cg_summary.get('total_acb_used', Decimal('0'))),
                'total_fees': fmt_cad(cg_summary.get('total_fees', Decimal('0'))),
                'total_gains': fmt_cad(cg_summary.get('total_gains', Decimal('0'))),
                'total_losses': fmt_cad(cg_summary.get('total_losses', Decimal('0'))),
                'net_gain_loss': fmt_cad(cg_summary.get('net_gain_loss', Decimal('0'))),
                'taxable_amount': fmt_cad(cg_summary.get('taxable_amount', Decimal('0'))),
                'superficial_losses_denied': fmt_cad(cg_summary.get('superficial_losses_denied')),
                'rows': [],  # Rows rendered via CSV; PDF shows summary only
            },
        )
        files.append(cg_pdf)
        # CSV files
        files.extend(self._find_csv_files(output_dir, f'capital_gains_{tax_year}'))

        # ----------------------------------------------------------------
        # Income
        # ----------------------------------------------------------------
        inc_report = IncomeReport(self.pool, specialist_override=self.specialist_override)
        inc_summary = self._run_generate(inc_report, user_id, tax_year, output_dir,
                                         year_end_month=year_end_month,
                                         excluded_wallet_ids=excluded_wallet_ids)
        summaries['income'] = inc_summary

        # PDF: income_summary_{year}.pdf
        by_source_fmt = {k: fmt_cad(v) for k, v in inc_summary.get('by_source', {}).items()}
        inc_pdf = engine.write_pdf(
            output_path=os.path.join(output_dir, f'income_summary_{tax_year}.pdf'),
            template_name='income.html',
            context={
                'report_title': f'Income Summary — {tax_year}',
                'tax_year': tax_year,
                'generated_date': generated_date,
                'total_income': fmt_cad(inc_summary.get('total_income', Decimal('0'))),
                'by_source': by_source_fmt,
                'monthly_rows': [],
                'detail_rows': [],
            },
        )
        files.append(inc_pdf)
        files.extend(self._find_csv_files(output_dir, f'income_summary_{tax_year}'))
        files.extend(self._find_csv_files(output_dir, f'income_by_month_{tax_year}'))

        # ----------------------------------------------------------------
        # Ledger
        # ----------------------------------------------------------------
        ledger_report = LedgerReport(self.pool, specialist_override=self.specialist_override)
        ledger_summary = self._run_generate(ledger_report, user_id, tax_year, output_dir,
                                             year_end_month=year_end_month,
                                             excluded_wallet_ids=excluded_wallet_ids)
        summaries['ledger'] = ledger_summary
        files.extend(self._find_csv_files(output_dir, f'ledger_{tax_year}'))

        # ----------------------------------------------------------------
        # T1135 Check
        # ----------------------------------------------------------------
        t1135_checker = T1135Checker(self.pool, specialist_override=self.specialist_override)
        t1135_summary = self._run_generate(t1135_checker, user_id, tax_year, output_dir,
                                            year_end_month=year_end_month)
        summaries['t1135'] = t1135_summary

        # PDF: t1135_check_{year}.pdf
        t1135_pdf = engine.write_pdf(
            output_path=os.path.join(output_dir, f't1135_check_{tax_year}.pdf'),
            template_name='t1135.html',
            context={
                'report_title': f'T1135 Foreign Property Check — {tax_year}',
                'tax_year': tax_year,
                'generated_date': generated_date,
                'total_foreign_cost': fmt_cad(t1135_summary.get('total_foreign_cost', Decimal('0'))),
                't1135_required': t1135_summary.get('t1135_required', False),
                'token_rows': [],
                'self_custody_rows': [],
            },
        )
        files.append(t1135_pdf)
        files.extend(self._find_csv_files(output_dir, f't1135_{tax_year}'))

        # ----------------------------------------------------------------
        # Superficial Losses (always included — Koinly parity)
        # ----------------------------------------------------------------
        superficial_report = SuperficialLossReport(self.pool, specialist_override=self.specialist_override)
        superficial_summary = self._run_generate(superficial_report, user_id, tax_year, output_dir,
                                                  year_end_month=year_end_month)
        summaries['superficial_loss'] = superficial_summary
        files.extend(self._find_csv_files(output_dir, f'superficial_losses_{tax_year}'))

        # ----------------------------------------------------------------
        # Inventory Holdings
        # ----------------------------------------------------------------
        inv_report = InventoryHoldingsReport(self.pool, specialist_override=self.specialist_override)
        inv_summary = self._run_generate(inv_report, user_id, tax_year, output_dir,
                                          year_end_month=year_end_month)
        summaries['inventory'] = inv_summary

        # PDF: inventory_holdings_{year}.pdf
        inv_pdf = engine.write_pdf(
            output_path=os.path.join(output_dir, f'inventory_holdings_{tax_year}.pdf'),
            template_name='inventory.html',
            context={
                'report_title': f'Inventory Holdings — {tax_year}',
                'tax_year': tax_year,
                'generated_date': generated_date,
                'as_of_date': f'December 31, {tax_year}',
                'rows': [],
                'total_acb': fmt_cad(inv_summary.get('total_cost_cad', Decimal('0'))),
                'total_fmv': 'N/A',
                'total_unrealized': 'N/A',
            },
        )
        files.append(inv_pdf)
        files.extend(self._find_csv_files(output_dir, f'inventory_holdings_{tax_year}'))

        # ----------------------------------------------------------------
        # COGS and Business Income (conditional on tax_treatment)
        # ----------------------------------------------------------------
        if tax_treatment in ('business_inventory', 'hybrid'):
            cogs_report = COGSReport(self.pool, specialist_override=self.specialist_override)
            cogs_summary = self._run_generate(cogs_report, user_id, tax_year, output_dir,
                                               year_end_month=year_end_month,
                                               tax_treatment=tax_treatment)
            summaries['cogs'] = cogs_summary
            files.extend(self._find_csv_files(output_dir, f'cogs_{tax_year}'))

            biz_report = BusinessIncomeStatement(self.pool, specialist_override=self.specialist_override)
            biz_summary = self._run_generate(biz_report, user_id, tax_year, output_dir,
                                              year_end_month=year_end_month,
                                              tax_treatment=tax_treatment)
            summaries['business_income'] = biz_summary

            # PDF: business_income_{year}.pdf
            biz_pdf = engine.write_pdf(
                output_path=os.path.join(output_dir, f'business_income_{tax_year}.pdf'),
                template_name='business_income.html',
                context={
                    'report_title': f'Business Income Statement — {tax_year}',
                    'tax_year': tax_year,
                    'generated_date': generated_date,
                    'tax_treatment': tax_treatment,
                    'crypto_income': fmt_cad(biz_summary.get('crypto_income_cad', Decimal('0'))),
                    'trading_gains': fmt_cad(biz_summary.get('capital_gains_net_cad', Decimal('0'))),
                    'total_revenue': fmt_cad(biz_summary.get('net_business_income_cad', Decimal('0'))),
                    'cogs_available': True,
                    'opening_inventory': '0.00',
                    'acquisitions': '0.00',
                    'closing_inventory': '0.00',
                    'cogs': '0.00',
                    'net_business_income': fmt_cad(biz_summary.get('net_business_income_cad', Decimal('0'))),
                },
            )
            files.append(biz_pdf)
            files.extend(self._find_csv_files(output_dir, f'business_income_{tax_year}'))

        # ----------------------------------------------------------------
        # Koinly exports (year + full history)
        # ----------------------------------------------------------------
        koinly = KoinlyExport(self.pool, specialist_override=self.specialist_override)
        koinly_year = koinly.generate(user_id, tax_year, output_dir,
                                       year_end_month=year_end_month, full_history=False)
        summaries['koinly_year'] = koinly_year
        if koinly_year.get('file_path'):
            files.append(koinly_year['file_path'])

        koinly_full = koinly.generate(user_id, tax_year, output_dir,
                                       year_end_month=year_end_month, full_history=True)
        summaries['koinly_full'] = koinly_full
        if koinly_full.get('file_path'):
            files.append(koinly_full['file_path'])

        # ----------------------------------------------------------------
        # Accounting exports
        # ----------------------------------------------------------------
        acct = AccountingExporter(self.pool, specialist_override=self.specialist_override)
        acct_result = acct.generate_all(user_id, tax_year, output_dir,
                                         year_end_month=year_end_month)
        summaries['accounting'] = acct_result
        files.extend([v for v in acct_result.values() if isinstance(v, str)])

        # ----------------------------------------------------------------
        # Tax summary PDF (combined one-pager)
        # ----------------------------------------------------------------
        tax_summary_pdf = engine.write_pdf(
            output_path=os.path.join(output_dir, f'tax_summary_{tax_year}.pdf'),
            template_name='tax_summary.html',
            context={
                'report_title': f'Tax Summary — {tax_year}',
                'tax_year': tax_year,
                'generated_date': generated_date,
                'tax_treatment': tax_treatment,
                'cg': {
                    'total_proceeds': fmt_cad(cg_summary.get('total_proceeds', Decimal('0'))),
                    'total_acb_used': fmt_cad(cg_summary.get('total_acb_used', Decimal('0'))),
                    'total_fees': fmt_cad(cg_summary.get('total_fees', Decimal('0'))),
                    'net_gain_loss': fmt_cad(cg_summary.get('net_gain_loss', Decimal('0'))),
                    'taxable_amount': fmt_cad(cg_summary.get('taxable_amount', Decimal('0'))),
                    'superficial_losses_denied': fmt_cad(cg_summary.get('superficial_losses_denied')),
                },
                'inc': {
                    'total_income': fmt_cad(inc_summary.get('total_income', Decimal('0'))),
                    'by_source': by_source_fmt,
                },
                't1135': {
                    'total_foreign_cost': fmt_cad(t1135_summary.get('total_foreign_cost', Decimal('0'))),
                    't1135_required': t1135_summary.get('t1135_required', False),
                    'self_custody_ambiguous': t1135_summary.get('self_custody_ambiguous', False),
                    'self_custody_cost': fmt_cad(t1135_summary.get('self_custody_cost', Decimal('0'))),
                },
                'superficial': {
                    'count': superficial_summary.get('count', 0),
                    'total_denied': fmt_cad(superficial_summary.get('total_denied', Decimal('0'))),
                },
            },
        )
        files.append(tax_summary_pdf)

        # ----------------------------------------------------------------
        # MANIFEST.json — final step before return
        # ----------------------------------------------------------------
        conn = self.pool.getconn()
        try:
            self._write_manifest(output_dir, user_id, tax_year, conn)
            # Audit the report generation event
            write_audit(
                conn,
                user_id=user_id,
                entity_type="report_package",
                entity_id=None,
                action="report_generated",
                new_value={
                    "tax_year": tax_year,
                    "files_count": len(files),
                    "output_dir": output_dir,
                    "tax_treatment": tax_treatment,
                },
                actor_type="system",
            )
        finally:
            self.pool.putconn(conn)

        logger.info(
            "PackageBuilder complete: user_id=%s tax_year=%s files=%d output_dir=%s",
            user_id, tax_year, len(files), output_dir,
        )

        return {
            'files': files,
            'summaries': summaries,
            'tax_year': tax_year,
            'output_dir': output_dir,
        }

    # ----------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------

    def _get_data_fingerprint(self, conn, user_id: int) -> dict:
        """Delegate to module-level get_data_fingerprint().

        Kept as instance method for backward compatibility and to allow
        subclasses to override without changing the module-level helper.
        """
        return get_data_fingerprint(conn, user_id)

    def _write_manifest(self, output_dir: str, user_id: int, tax_year: int, conn) -> str:
        """Compute SHA-256 for every file in output_dir (excluding MANIFEST.json) and write manifest.

        Args:
            output_dir: Directory containing the tax package files.
            user_id: User the package was built for.
            tax_year: Tax year of this package.
            conn: Live psycopg2 connection for fingerprint queries.

        Returns:
            Absolute path of the written MANIFEST.json file.
        """
        pkg_path = Path(output_dir)
        file_entries = []
        for f in sorted(pkg_path.glob('*')):
            if not f.is_file():
                continue
            if f.name == 'MANIFEST.json':
                continue
            sha256 = hashlib.sha256(f.read_bytes()).hexdigest()
            file_entries.append({
                'filename': f.name,
                'sha256': sha256,
                'size_bytes': f.stat().st_size,
            })

        fingerprint = self._get_data_fingerprint(conn, user_id)

        manifest = {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'tax_year': tax_year,
            'user_id': user_id,
            'source_data_version': fingerprint,
            'files': file_entries,
        }

        manifest_path = str(pkg_path / 'MANIFEST.json')
        with open(manifest_path, 'w') as fh:
            fh.write(json.dumps(manifest, indent=2))

        logger.info(
            "MANIFEST.json written: user_id=%s tax_year=%s files=%d output_dir=%s",
            user_id, tax_year, len(file_entries), output_dir,
        )
        return manifest_path


    def _run_generate(self, report_instance, user_id, tax_year, output_dir, **kwargs):
        """Call report_instance.generate() with common args + extra kwargs.

        Skips the gate check re-run by temporarily setting specialist_override=True
        on the instance (gate was already run once at top level).
        """
        # Temporarily bypass internal gate check — already done at top level
        original_override = report_instance.specialist_override
        report_instance.specialist_override = True
        try:
            return report_instance.generate(
                user_id=user_id,
                tax_year=tax_year,
                output_dir=output_dir,
                **kwargs,
            )
        finally:
            report_instance.specialist_override = original_override

    @staticmethod
    def _find_csv_files(output_dir: str, prefix: str) -> list:
        """Find CSV files in output_dir that match a given prefix."""
        result = []
        try:
            for fname in os.listdir(output_dir):
                if fname.startswith(prefix) and fname.endswith('.csv'):
                    result.append(os.path.join(output_dir, fname))
        except FileNotFoundError:
            pass
        return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path as _Path
    _PROJECT_ROOT = _Path(__file__).parent.parent
    sys.path.insert(0, str(_PROJECT_ROOT))

    parser = argparse.ArgumentParser(
        description="Generate complete Axiom tax package for a given year."
    )
    parser.add_argument('--year', type=int,
                        default=datetime.now().year - 1,
                        help='Tax year (default: last year)')
    parser.add_argument('--output', default='output',
                        help='Output base directory (default: output)')
    parser.add_argument('--tax-treatment',
                        choices=['capital', 'business_inventory', 'hybrid'],
                        default='capital',
                        help='Tax treatment mode (default: capital)')
    parser.add_argument('--year-end-month', type=int, default=12,
                        help='Fiscal year end month 1-12 (default: 12)')
    parser.add_argument('--specialist-override', action='store_true',
                        help='Bypass gate check for specialist review')
    parser.add_argument('--user-id', type=int, default=1,
                        help='User ID to generate report for (default: 1)')
    args = parser.parse_args()

    from config import DATABASE_URL
    import psycopg2.pool
    pool = psycopg2.pool.SimpleConnectionPool(1, 3, DATABASE_URL)
    try:
        builder = PackageBuilder(pool, specialist_override=args.specialist_override)
        manifest = builder.build(
            user_id=args.user_id,
            tax_year=args.year,
            output_base=args.output,
            year_end_month=args.year_end_month,
            tax_treatment=args.tax_treatment,
        )
        print(f"Tax package complete: {manifest['output_dir']}")
        print(f"Files generated: {len(manifest['files'])}")
        for f in sorted(manifest['files']):
            print(f"  {f}")
    finally:
        pool.closeall()
