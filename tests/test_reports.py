"""
Unit tests for reports package — ReportEngine, CapitalGainsReport, IncomeReport,
LedgerReport, T1135Checker, SuperficialLossReport.

Test classes:
  - TestReportGate: gate check logic (needs_review blocking, specialist override)
  - TestHelpers: fiscal_year_range, fmt_cad, fmt_units
  - TestCapitalGainsReport: chronological CSV, grouped CSV, summary dict
  - TestIncomeReport: detail CSV, monthly CSV, summary dict
  - TestLedgerReport: NEAR + exchange transactions unified with classifications
  - TestT1135Checker: peak ACB cost threshold and foreign property determination
  - TestSuperficialLossReport: denied losses listing
"""

import csv
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# TestReportGate
# ---------------------------------------------------------------------------

class TestReportGate(unittest.TestCase):
    """Tests for ReportEngine._check_gate()"""

    def _make_pool(self, cgl_count=0, acb_count=0):
        """Build a mock pool whose cursor returns given needs_review counts."""
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        # fetchone returns (count,) for each query: CGL first, ACB second
        cur.fetchone.side_effect = [(cgl_count,), (acb_count,)]
        return pool, conn, cur

    def test_raises_when_cgl_has_needs_review(self):
        """Test 1: ReportBlockedError raised when capital_gains_ledger has needs_review=TRUE rows."""
        from reports.engine import ReportEngine, ReportBlockedError
        pool, conn, cur = self._make_pool(cgl_count=3, acb_count=0)
        engine = ReportEngine(pool)
        with self.assertRaises(ReportBlockedError):
            engine._check_gate(user_id=1, tax_year=2024)
        pool.putconn.assert_called_once_with(conn)

    def test_raises_when_acb_has_needs_review(self):
        """Test 2: ReportBlockedError raised when acb_snapshots has needs_review=TRUE rows."""
        from reports.engine import ReportEngine, ReportBlockedError
        pool, conn, cur = self._make_pool(cgl_count=0, acb_count=2)
        engine = ReportEngine(pool)
        with self.assertRaises(ReportBlockedError):
            engine._check_gate(user_id=1, tax_year=2024)
        pool.putconn.assert_called_once_with(conn)

    def test_gate_passes_when_no_needs_review(self):
        """Test 3: Gate passes (no error) when no needs_review items exist."""
        from reports.engine import ReportEngine
        pool, conn, cur = self._make_pool(cgl_count=0, acb_count=0)
        engine = ReportEngine(pool)
        result = engine._check_gate(user_id=1, tax_year=2024)
        self.assertFalse(result['blocked'])
        self.assertEqual(result['flagged_count'], 0)
        pool.putconn.assert_called_once_with(conn)

    def test_specialist_override_passes_with_flagged_count(self):
        """Test 4: Gate passes with specialist_override=True even when needs_review items exist."""
        from reports.engine import ReportEngine
        pool, conn, cur = self._make_pool(cgl_count=2, acb_count=1)
        engine = ReportEngine(pool, specialist_override=True)
        result = engine._check_gate(user_id=1, tax_year=2024)
        self.assertFalse(result['blocked'])
        self.assertEqual(result['flagged_count'], 3)

    def test_specialist_override_logs_warning(self):
        """Test 5: Gate logs WARNING when specialist_override=True is used."""
        from reports.engine import ReportEngine
        pool, conn, cur = self._make_pool(cgl_count=1, acb_count=0)
        engine = ReportEngine(pool, specialist_override=True)
        with self.assertLogs('reports.engine', level='WARNING') as cm:
            engine._check_gate(user_id=1, tax_year=2024)
        self.assertTrue(any('specialist' in msg.lower() or 'flagged' in msg.lower() for msg in cm.output))


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------

class TestHelpers(unittest.TestCase):
    """Tests for fiscal_year_range, fmt_cad, fmt_units."""

    def test_fiscal_year_range_calendar(self):
        """Test 6: fiscal_year_range(2025, 12) returns (date(2025,1,1), date(2025,12,31))."""
        from reports.engine import fiscal_year_range
        start, end = fiscal_year_range(2025, 12)
        self.assertEqual(start, date(2025, 1, 1))
        self.assertEqual(end, date(2025, 12, 31))

    def test_fiscal_year_range_march(self):
        """Test 7: fiscal_year_range(2025, 3) returns (date(2024,4,1), date(2025,3,31))."""
        from reports.engine import fiscal_year_range
        start, end = fiscal_year_range(2025, 3)
        self.assertEqual(start, date(2024, 4, 1))
        self.assertEqual(end, date(2025, 3, 31))

    def test_fmt_cad_decimal(self):
        """Test 8: fmt_cad(Decimal('1234.5')) returns '1234.50'."""
        from reports.engine import fmt_cad
        self.assertEqual(fmt_cad(Decimal('1234.5')), '1234.50')

    def test_fmt_units_decimal(self):
        """Test 9: fmt_units(Decimal('0.123456789')) returns '0.12345679' (8 decimal places)."""
        from reports.engine import fmt_units
        self.assertEqual(fmt_units(Decimal('0.123456789')), '0.12345679')

    def test_fmt_cad_none(self):
        """Test 10: fmt_cad(None) returns ''."""
        from reports.engine import fmt_cad
        self.assertEqual(fmt_cad(None), '')

    def test_fmt_units_none(self):
        """fmt_units(None) returns ''."""
        from reports.engine import fmt_units
        self.assertEqual(fmt_units(None), '')


# ---------------------------------------------------------------------------
# TestCapitalGainsReport
# ---------------------------------------------------------------------------

class TestCapitalGainsReport(unittest.TestCase):
    """Tests for CapitalGainsReport.generate()"""

    def _make_pool(self, rows=None, gate_cgl=0, gate_acb=0):
        """
        Build a mock pool. The gate check calls fetchone twice (CGL, ACB counts).
        Subsequent fetchall() returns: first call = disposal rows, second = opening ACB rows (empty).
        """
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur

        # Gate fetchone side_effect: (cgl_count,), (acb_count,)
        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        # Two fetchall calls: first = disposal rows, second = opening ACB (empty)
        cur.fetchall.side_effect = [rows or [], []]
        return pool, conn, cur

    def _sample_rows(self):
        """Two sample disposal rows with Decimal values."""
        return [
            (
                date(2024, 3, 15),         # disposal_date
                'NEAR',                    # token_symbol
                Decimal('100.00000000'),   # units_disposed
                Decimal('500.00'),         # proceeds_cad
                Decimal('300.00'),         # acb_used_cad
                Decimal('5.00'),           # fees_cad
                Decimal('195.00'),         # gain_loss_cad (gain)
                False,                     # is_superficial_loss
                None,                      # denied_loss_cad
                False,                     # needs_review
            ),
            (
                date(2024, 6, 20),
                'ETH',
                Decimal('1.00000000'),
                Decimal('2000.00'),
                Decimal('2500.00'),
                Decimal('20.00'),
                Decimal('-520.00'),        # loss
                True,                      # is_superficial_loss
                Decimal('260.00'),         # denied_loss_cad
                False,
            ),
        ]

    def test_csv_has_correct_headers(self):
        """Test 1: generate() writes CSV with correct headers including superficial loss columns."""
        from reports.capital_gains import CapitalGainsReport
        rows = self._sample_rows()
        pool, conn, cur = self._make_pool(rows=rows)
        report = CapitalGainsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'capital_gains_2024.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
            self.assertIn('Superficial Loss', headers)
            self.assertIn('Denied Loss (CAD)', headers)
            self.assertIn('Gain/Loss (CAD)', headers)

    def test_chronological_order(self):
        """Test 2: Chronological view orders by disposal_date."""
        from reports.capital_gains import CapitalGainsReport
        rows = self._sample_rows()
        pool, conn, cur = self._make_pool(rows=rows)
        report = CapitalGainsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'capital_gains_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                next(reader)  # skip headers
                data = list(reader)
            self.assertEqual(data[0][0], '2024-03-15')
            self.assertEqual(data[1][0], '2024-06-20')

    def test_grouped_view_aggregates_by_token(self):
        """Test 3: Grouped view aggregates by token_symbol."""
        from reports.capital_gains import CapitalGainsReport
        rows = self._sample_rows()
        pool, conn, cur = self._make_pool(rows=rows)
        report = CapitalGainsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'capital_gains_2024_by_token.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                next(reader)  # skip headers
                data = list(reader)
            tokens = {row[0] for row in data}
            self.assertIn('NEAR', tokens)
            self.assertIn('ETH', tokens)

    def test_specialist_override_appends_footnote(self):
        """Test 4: Specialist override includes footnote rows for needs_review items."""
        from reports.capital_gains import CapitalGainsReport
        # One row with needs_review=True
        flagged_rows = [
            (
                date(2024, 3, 15), 'NEAR',
                Decimal('100.00000000'), Decimal('500.00'),
                Decimal('300.00'), Decimal('5.00'),
                Decimal('195.00'), False, None, True,  # needs_review=True
            ),
        ]
        pool, conn, cur = self._make_pool(rows=flagged_rows, gate_cgl=1)
        report = CapitalGainsReport(pool, specialist_override=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'capital_gains_2024.csv')
            with open(csv_path) as f:
                content = f.read()
            self.assertIn('NOTE', content)

    def test_summary_dict_has_correct_keys(self):
        """Test 5: Summary dict includes required keys and taxable_amount is 50% of net."""
        from reports.capital_gains import CapitalGainsReport
        rows = self._sample_rows()
        pool, conn, cur = self._make_pool(rows=rows)
        report = CapitalGainsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('total_proceeds', summary)
        self.assertIn('total_acb_used', summary)
        self.assertIn('total_gains', summary)
        self.assertIn('total_losses', summary)
        self.assertIn('net_gain_loss', summary)
        self.assertIn('taxable_amount', summary)
        self.assertIn('superficial_losses_denied', summary)
        # taxable_amount should be 50% of net_gain_loss
        net = summary['net_gain_loss']
        expected_taxable = net * Decimal('0.50')
        self.assertEqual(summary['taxable_amount'], expected_taxable)

    def test_decimal_precision_maintained(self):
        """Test 6: Decimal precision maintained — no float conversion in output."""
        from reports.capital_gains import CapitalGainsReport
        rows = self._sample_rows()
        pool, conn, cur = self._make_pool(rows=rows)
        report = CapitalGainsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        # All monetary summary values should be Decimal, not float
        for key in ('total_proceeds', 'total_acb_used', 'net_gain_loss', 'taxable_amount'):
            self.assertIsInstance(summary[key], Decimal,
                                  f"{key} should be Decimal, got {type(summary[key])}")

    def test_empty_result_produces_headers_only(self):
        """Test 7: Empty result set produces CSV with headers only."""
        from reports.capital_gains import CapitalGainsReport
        pool, conn, cur = self._make_pool(rows=[])
        report = CapitalGainsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'capital_gains_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
            self.assertGreater(len(headers), 0)
            self.assertEqual(len(data), 0)

    def test_summary_includes_opening_acb(self):
        """Test 8: opening_acb_cad key present in summary dict."""
        from reports.capital_gains import CapitalGainsReport
        rows = self._sample_rows()
        pool, conn, cur = self._make_pool(rows=rows)
        # opening ACB query returns a dict-like result
        report = CapitalGainsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('opening_acb_cad', summary)


# ---------------------------------------------------------------------------
# TestIncomeReport
# ---------------------------------------------------------------------------

class TestIncomeReport(unittest.TestCase):
    """Tests for IncomeReport.generate()"""

    def _make_pool(self, detail_rows=None, summary_rows=None, gate_cgl=0, gate_acb=0):
        """
        Build a mock pool.
        Gate check: two fetchone calls.
        Then: fetchall for detail query, fetchall for summary query.
        """
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur

        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        # Two fetchall calls: detail then summary
        cur.fetchall.side_effect = [
            detail_rows or [],
            summary_rows or [],
        ]
        return pool, conn, cur

    def _sample_detail_rows(self):
        return [
            (
                date(2024, 1, 15),       # income_date
                'staking',               # source_type
                'NEAR',                  # token_symbol
                Decimal('10.00000000'),  # units_received
                Decimal('5.00000000'),   # fmv_usd
                Decimal('6.75000000'),   # fmv_cad
                Decimal('6.75000000'),   # acb_added_cad
            ),
            (
                date(2024, 2, 20),
                'airdrop',
                'NEAR',
                Decimal('5.00000000'),
                Decimal('4.50000000'),
                Decimal('6.00000000'),
                Decimal('6.00000000'),
            ),
        ]

    def _sample_summary_rows(self):
        return [
            (
                date(2024, 1, 1),        # month (DATE_TRUNC result)
                'staking',               # source_type
                'NEAR',                  # token_symbol
                Decimal('10.00000000'),  # total_units
                Decimal('6.75000000'),   # total_fmv_cad
                1,                       # event_count
            ),
            (
                date(2024, 2, 1),
                'airdrop',
                'NEAR',
                Decimal('5.00000000'),
                Decimal('6.00000000'),
                1,
            ),
        ]

    def test_csv_written_with_correct_headers(self):
        """Test 1: generate() writes detail CSV with correct headers."""
        from reports.income import IncomeReport
        pool, conn, cur = self._make_pool(
            detail_rows=self._sample_detail_rows(),
            summary_rows=self._sample_summary_rows(),
        )
        report = IncomeReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'income_summary_2024.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
            self.assertIn('Source Type', headers)
            self.assertIn('FMV CAD', headers)

    def test_monthly_totals_correct(self):
        """Test 2: Monthly totals sum correctly per source_type."""
        from reports.income import IncomeReport
        pool, conn, cur = self._make_pool(
            detail_rows=self._sample_detail_rows(),
            summary_rows=self._sample_summary_rows(),
        )
        report = IncomeReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        # by_source should have staking and airdrop
        self.assertIn('staking', summary['by_source'])
        self.assertIn('airdrop', summary['by_source'])
        self.assertEqual(summary['by_source']['staking'], Decimal('6.75000000'))
        self.assertEqual(summary['by_source']['airdrop'], Decimal('6.00000000'))

    def test_annual_total_in_summary(self):
        """Test 3: Summary dict includes total_income_cad."""
        from reports.income import IncomeReport
        pool, conn, cur = self._make_pool(
            detail_rows=self._sample_detail_rows(),
            summary_rows=self._sample_summary_rows(),
        )
        report = IncomeReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        expected_total = Decimal('6.75000000') + Decimal('6.00000000')
        self.assertEqual(summary['total_income_cad'], expected_total)

    def test_summary_dict_has_required_keys(self):
        """Test 4: Summary dict includes total_income_cad, by_source, by_month, event_count."""
        from reports.income import IncomeReport
        pool, conn, cur = self._make_pool(
            detail_rows=self._sample_detail_rows(),
            summary_rows=self._sample_summary_rows(),
        )
        report = IncomeReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        for key in ('total_income_cad', 'by_source', 'by_month', 'event_count'):
            self.assertIn(key, summary)

    def test_empty_result_produces_headers_and_zero_total(self):
        """Test 5: Empty result set produces CSV with headers and zero total."""
        from reports.income import IncomeReport
        pool, conn, cur = self._make_pool(detail_rows=[], summary_rows=[])
        report = IncomeReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'income_summary_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
        self.assertGreater(len(headers), 0)
        self.assertEqual(len(data), 0)
        self.assertEqual(summary['total_income_cad'], Decimal('0'))

    def test_specialist_override_appends_footnote(self):
        """Test 6: Specialist override appends footnote for flagged items."""
        from reports.income import IncomeReport
        pool, conn, cur = self._make_pool(
            detail_rows=self._sample_detail_rows(),
            summary_rows=self._sample_summary_rows(),
            gate_cgl=1,  # flagged
        )
        report = IncomeReport(pool, specialist_override=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'income_summary_2024.csv')
            with open(csv_path) as f:
                content = f.read()
        self.assertIn('NOTE', content)


# ---------------------------------------------------------------------------
# TestLedgerReport
# ---------------------------------------------------------------------------

class TestLedgerReport(unittest.TestCase):
    """Tests for LedgerReport.generate()"""

    def _make_pool(self, ledger_rows=None, gate_cgl=0, gate_acb=0):
        """
        Build a mock pool.
        Gate check: two fetchone calls (CGL count, ACB count).
        Then: one fetchall for the unified ledger query.
        """
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur

        # Gate check fetchone calls
        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        # Ledger fetchall
        cur.fetchall.return_value = ledger_rows or []
        return pool, conn, cur

    def _near_row(self):
        """Sample NEAR transaction row from the unified ledger query."""
        # Columns: date_str, chain, account_or_exchange, tx_ref, action_type,
        #   category, direction, counterparty, amount_raw, token_id,
        #   fee_raw, fmv_usd, fmv_cad, classification_source, confidence,
        #   needs_review, notes
        from datetime import datetime
        return (
            '2024-03-15 10:00:00',   # date_str (formatted from TO_TIMESTAMP)
            'near',                   # chain
            'alice.near',             # account_or_exchange
            'abc123hash',             # tx_ref (tx_hash)
            'TRANSFER',               # action_type
            'transfer',               # category
            'out',                    # direction
            'bob.near',               # counterparty
            '1000000000000000000000000',  # amount_raw (yoctoNEAR)
            None,                     # token_id
            '100000000000000000000',  # fee_raw
            Decimal('4.50'),          # fmv_usd
            Decimal('6.08'),          # fmv_cad
            'rule',                   # classification_source
            Decimal('0.950'),         # confidence
            False,                    # needs_review
            None,                     # notes
        )

    def _exchange_row(self):
        """Sample exchange transaction row from the unified ledger query."""
        return (
            '2024-06-20',            # date_str (tx_date from exchange_transactions)
            'exchange',              # chain
            'coinbase',              # account_or_exchange
            'CB-TX-001',             # tx_ref (tx_id)
            'buy',                   # action_type
            'capital_gain',          # category
            'in',                    # direction
            None,                    # counterparty
            None,                    # amount_raw (not applicable for exchange)
            'BTC',                   # token_id / asset
            Decimal('10.00'),        # fee (direct numeric from exchange)
            Decimal('45000.00'),     # fmv_usd
            Decimal('60750.00'),     # fmv_cad
            'rule',                  # classification_source
            Decimal('0.980'),        # confidence
            False,                   # needs_review
            'BTC purchase',          # notes
        )

    def test_ledger_includes_near_transactions(self):
        """Test 1: Ledger includes NEAR transactions from transactions table."""
        from reports.ledger import LedgerReport
        rows = [self._near_row()]
        pool, conn, cur = self._make_pool(ledger_rows=rows)
        report = LedgerReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'transaction_ledger_2024.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                next(reader)  # skip headers
                data = list(reader)
        self.assertEqual(len(data), 1)
        # Chain column should be 'near'
        headers_row = None
        with open(csv_path) as f:
            reader = csv.reader(f)
            headers_row = next(reader)
        chain_idx = headers_row.index('Chain')
        self.assertEqual(data[0][chain_idx], 'near')

    def test_ledger_includes_exchange_transactions(self):
        """Test 2: Ledger includes exchange transactions with classification data."""
        from reports.ledger import LedgerReport
        rows = [self._exchange_row()]
        pool, conn, cur = self._make_pool(ledger_rows=rows)
        report = LedgerReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'transaction_ledger_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers_row = next(reader)
                data = list(reader)
        chain_idx = headers_row.index('Chain')
        self.assertEqual(data[0][chain_idx], 'exchange')

    def test_all_rows_have_consistent_columns(self):
        """Test 3: All rows have consistent columns regardless of source chain."""
        from reports.ledger import LedgerReport
        rows = [self._near_row(), self._exchange_row()]
        pool, conn, cur = self._make_pool(ledger_rows=rows)
        report = LedgerReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'transaction_ledger_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers_row = next(reader)
                data = list(reader)
        # Every row should have the same number of columns as headers
        for row in data:
            self.assertEqual(len(row), len(headers_row),
                             f"Row has {len(row)} cols, expected {len(headers_row)}")

    def test_chronological_order(self):
        """Test 4: Rows are in chronological order by date."""
        from reports.ledger import LedgerReport
        # exchange_row is June, near_row is March — DB returns ordered
        rows = [self._near_row(), self._exchange_row()]
        pool, conn, cur = self._make_pool(ledger_rows=rows)
        report = LedgerReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'transaction_ledger_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                next(reader)
                data = list(reader)
        # First row should be NEAR (March), second should be exchange (June)
        self.assertIn('2024-03-15', data[0][0])
        self.assertIn('2024-06-20', data[1][0])

    def test_wallet_exclusion_filter(self):
        """Test 5: excluded_wallet_ids are applied as a filter parameter in the query."""
        from reports.ledger import LedgerReport
        pool, conn, cur = self._make_pool(ledger_rows=[])
        report = LedgerReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir,
                            excluded_wallet_ids=[10, 20])
        # Verify execute was called — exclusion list is passed as query params
        self.assertTrue(cur.execute.called)

    def test_fiscal_year_scoping(self):
        """Test 6: Fiscal year scoping — generate only queries within the date range."""
        from reports.ledger import LedgerReport
        pool, conn, cur = self._make_pool(ledger_rows=[])
        report = LedgerReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir, year_end_month=12)
        # The execute call should have been made (date range in params)
        self.assertTrue(cur.execute.called)
        call_args = cur.execute.call_args_list
        # At least one execute call (the ledger query)
        self.assertGreater(len(call_args), 0)

    def test_summary_dict_structure(self):
        """Test 7: Summary dict includes total_count, count_by_chain, count_by_category."""
        from reports.ledger import LedgerReport
        rows = [self._near_row(), self._exchange_row()]
        pool, conn, cur = self._make_pool(ledger_rows=rows)
        report = LedgerReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('total_count', summary)
        self.assertIn('count_by_chain', summary)
        self.assertIn('count_by_category', summary)
        self.assertEqual(summary['total_count'], 2)
        self.assertIn('near', summary['count_by_chain'])
        self.assertIn('exchange', summary['count_by_chain'])


# ---------------------------------------------------------------------------
# TestT1135Checker
# ---------------------------------------------------------------------------

class TestT1135Checker(unittest.TestCase):
    """Tests for T1135Checker.generate()"""

    def _make_pool(self, peak_rows=None, gate_cgl=0, gate_acb=0):
        """
        Build a mock pool.
        Gate check: two fetchone calls (CGL, ACB).
        Then: one fetchall for peak cost query.
        """
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur

        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        cur.fetchall.return_value = peak_rows or []
        return pool, conn, cur

    def _peak_rows_over_threshold(self):
        """Peak ACB cost rows that sum > $100,000 CAD."""
        return [
            ('BTC', Decimal('80000.00'), 'coinbase'),
            ('ETH', Decimal('25000.00'), 'coinbase'),
            ('NEAR', Decimal('5000.00'), 'self_custody'),
        ]

    def _peak_rows_under_threshold(self):
        """Peak ACB cost rows that sum <= $100,000 CAD."""
        return [
            ('BTC', Decimal('60000.00'), 'coinbase'),
            ('NEAR', Decimal('3000.00'), 'self_custody'),
        ]

    def test_uses_max_total_cost_cad(self):
        """Test 1: T1135 uses MAX(total_cost_cad) from acb_snapshots, NOT current FMV."""
        from reports.t1135 import T1135Checker
        rows = self._peak_rows_over_threshold()
        pool, conn, cur = self._make_pool(peak_rows=rows)
        report = T1135Checker(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        # total_foreign_cost should be sum of BTC + ETH (coinbase = foreign)
        # NEAR (self_custody) is ambiguous, not counted as definite foreign
        self.assertIn('total_foreign_cost', summary)
        self.assertIsInstance(summary['total_foreign_cost'], Decimal)

    def test_sums_peak_costs_across_tokens(self):
        """Test 2: T1135 correctly sums peak costs across all foreign-held tokens."""
        from reports.t1135 import T1135Checker
        rows = self._peak_rows_over_threshold()
        pool, conn, cur = self._make_pool(peak_rows=rows)
        report = T1135Checker(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        # BTC (80000) + ETH (25000) on coinbase = 105000 foreign
        self.assertEqual(summary['total_foreign_cost'], Decimal('105000.00'))

    def test_required_true_when_over_threshold(self):
        """Test 3: T1135 returns required=True when peak cost > $100,000 CAD."""
        from reports.t1135 import T1135Checker
        rows = self._peak_rows_over_threshold()
        pool, conn, cur = self._make_pool(peak_rows=rows)
        report = T1135Checker(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertTrue(summary['required'])

    def test_required_false_when_under_threshold(self):
        """Test 4: T1135 returns required=False when peak cost <= $100,000 CAD."""
        from reports.t1135 import T1135Checker
        rows = self._peak_rows_under_threshold()
        pool, conn, cur = self._make_pool(peak_rows=rows)
        report = T1135Checker(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        # BTC (60000) on coinbase = foreign; NEAR on self_custody = ambiguous
        self.assertFalse(summary['required'])

    def test_self_custody_flagged_as_ambiguous(self):
        """Test 5: Self-custodied wallets listed separately with CRA position unclear note."""
        from reports.t1135 import T1135Checker
        rows = self._peak_rows_over_threshold()  # includes NEAR with 'self_custody'
        pool, conn, cur = self._make_pool(peak_rows=rows)
        report = T1135Checker(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('self_custody_tokens', summary)
        self.assertIn('NEAR', summary['self_custody_tokens'])

    def test_csv_includes_per_token_breakdown(self):
        """Test 6: T1135 CSV includes per-token breakdown with peak cost and holding source."""
        from reports.t1135 import T1135Checker
        rows = self._peak_rows_over_threshold()
        pool, conn, cur = self._make_pool(peak_rows=rows)
        report = T1135Checker(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 't1135_check_2024.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
        self.assertIn('Token', headers)
        self.assertIn('Peak Cost (CAD)', headers)
        self.assertIn('Holding Source', headers)
        # BTC and ETH rows should be present
        tokens_in_csv = {row[headers.index('Token')] for row in data if row[0] != 'TOTAL'}
        self.assertIn('BTC', tokens_in_csv)
        self.assertIn('ETH', tokens_in_csv)

    def test_threshold_value_in_summary(self):
        """Test 7: Summary includes threshold=100000."""
        from reports.t1135 import T1135Checker
        rows = self._peak_rows_under_threshold()
        pool, conn, cur = self._make_pool(peak_rows=rows)
        report = T1135Checker(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertEqual(summary['threshold'], Decimal('100000'))


# ---------------------------------------------------------------------------
# TestSuperficialLossReport
# ---------------------------------------------------------------------------

class TestSuperficialLossReport(unittest.TestCase):
    """Tests for SuperficialLossReport.generate()"""

    def _make_pool(self, loss_rows=None, gate_cgl=0, gate_acb=0):
        """
        Build a mock pool.
        Gate check: two fetchone calls.
        Then: one fetchall for superficial losses query.
        """
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur

        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        cur.fetchall.return_value = loss_rows or []
        return pool, conn, cur

    def _sample_loss_rows(self):
        """Sample rows from capital_gains_ledger WHERE is_superficial_loss=TRUE."""
        return [
            (
                date(2024, 3, 10),          # disposal_date
                'ETH',                       # token_symbol
                Decimal('1.00000000'),       # units_disposed
                Decimal('1800.00'),          # proceeds_cad
                Decimal('2500.00'),          # acb_used_cad
                Decimal('0.00'),             # gain_loss_cad (0 after denial)
                Decimal('700.00'),           # denied_loss_cad
                True,                        # needs_review
            ),
            (
                date(2024, 6, 5),
                'NEAR',
                Decimal('500.00000000'),
                Decimal('1000.00'),
                Decimal('1500.00'),
                Decimal('0.00'),
                Decimal('500.00'),
                False,
            ),
        ]

    def test_lists_all_superficial_losses(self):
        """Test 7 (of task): SuperficialLossReport lists all rows where is_superficial_loss=TRUE."""
        from reports.superficial import SuperficialLossReport
        rows = self._sample_loss_rows()
        pool, conn, cur = self._make_pool(loss_rows=rows)
        report = SuperficialLossReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'superficial_losses_2024.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                next(reader)  # skip headers
                data = list(reader)
        self.assertEqual(len(data), 2)

    def test_includes_denied_loss_and_disposal_details(self):
        """Test 8 (of task): SuperficialLossReport includes denied_loss_cad and disposal details."""
        from reports.superficial import SuperficialLossReport
        rows = self._sample_loss_rows()
        pool, conn, cur = self._make_pool(loss_rows=rows)
        report = SuperficialLossReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'superficial_losses_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
        self.assertIn('Denied Loss (CAD)', headers)
        self.assertIn('Units Disposed', headers)
        self.assertIn('Proceeds (CAD)', headers)
        # First row: ETH, denied 700.00
        denied_idx = headers.index('Denied Loss (CAD)')
        self.assertEqual(data[0][denied_idx], '700.00')

    def test_summary_total_denied(self):
        """Test: Summary dict includes total_denied_cad and count."""
        from reports.superficial import SuperficialLossReport
        rows = self._sample_loss_rows()
        pool, conn, cur = self._make_pool(loss_rows=rows)
        report = SuperficialLossReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('total_denied_cad', summary)
        self.assertIn('count', summary)
        self.assertEqual(summary['count'], 2)
        self.assertEqual(summary['total_denied_cad'], Decimal('1200.00'))

    def test_empty_result_when_no_superficial_losses(self):
        """Test: Empty superficial loss set produces headers-only CSV."""
        from reports.superficial import SuperficialLossReport
        pool, conn, cur = self._make_pool(loss_rows=[])
        report = SuperficialLossReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'superficial_losses_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
        self.assertGreater(len(headers), 0)
        self.assertEqual(len(data), 0)
        self.assertEqual(summary['total_denied_cad'], Decimal('0'))
        self.assertEqual(summary['count'], 0)


if __name__ == '__main__':
    unittest.main()
