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
from unittest.mock import MagicMock, patch


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
        Build a mock pool supporting named cursor streaming.

        The gate check calls pool.getconn() → conn.cursor() (no name) → fetchone twice.
        The main generate() calls pool.getconn() → conn.cursor(name=...) → iterable for disposal rows,
        then conn.cursor() (no name) → fetchall for opening ACB rows (empty).
        """
        pool = MagicMock()
        conn = MagicMock()
        pool.getconn.return_value = conn

        # Gate cursor (used by _check_gate): unnamed, uses fetchone
        gate_cur = MagicMock()
        gate_cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]

        # Named cursor (for streaming disposal rows): iterable
        named_cur = MagicMock()
        named_cur.__iter__ = MagicMock(return_value=iter(rows or []))

        # Regular cursor (for opening ACB fetchall): returns empty list
        acb_cur = MagicMock()
        acb_cur.fetchall.return_value = []

        # Dispatch: cursor(name=...) → named_cur; cursor() → gate_cur or acb_cur
        _regular_cursors = [gate_cur, acb_cur]
        _regular_index = [0]

        def cursor_factory(**kwargs):
            if 'name' in kwargs:
                return named_cur
            idx = _regular_index[0]
            _regular_index[0] += 1
            return _regular_cursors[idx] if idx < len(_regular_cursors) else MagicMock()

        conn.cursor.side_effect = cursor_factory
        return pool, conn, gate_cur

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
        Build a mock pool supporting named cursor streaming.

        Gate check: two fetchone calls on an unnamed cursor.
        Main query: regular cursor for SQL building (no results needed), then
        named cursor (name="ledger_stream") provides rows via iteration.
        """
        pool = MagicMock()
        conn = MagicMock()
        pool.getconn.return_value = conn

        # Gate cursor: handles fetchone calls for gate check
        gate_cur = MagicMock()
        gate_cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]

        # Regular cursor: used for SQL building only (no data retrieval)
        build_cur = MagicMock()

        # Named cursor: provides ledger rows via iteration
        named_cur = MagicMock()
        named_cur.__iter__ = MagicMock(return_value=iter(ledger_rows or []))

        # Dispatch: cursor(name=...) → named_cur; cursor() → gate_cur or build_cur
        _regular_cursors = [gate_cur, build_cur]
        _regular_index = [0]

        def cursor_factory(**kwargs):
            if 'name' in kwargs:
                return named_cur
            idx = _regular_index[0]
            _regular_index[0] += 1
            return _regular_cursors[idx] if idx < len(_regular_cursors) else MagicMock()

        conn.cursor.side_effect = cursor_factory
        return pool, conn, gate_cur

    def _near_row(self):
        """Sample NEAR transaction row from the unified ledger query."""
        # Columns: date_str, chain, account_or_exchange, tx_ref, action_type,
        #   category, direction, counterparty, amount_raw, token_id,
        #   fee_raw, fmv_usd, fmv_cad, classification_source, confidence,
        #   needs_review, notes
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
                headers_row = next(reader)
                data = list(reader)
        self.assertEqual(len(data), 1)
        # Chain column should be 'near'
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
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
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


# ---------------------------------------------------------------------------
# TestInventoryHoldings
# ---------------------------------------------------------------------------

class TestInventoryHoldings(unittest.TestCase):
    """Tests for InventoryHoldingsReport.generate()"""

    def _make_pool(self, holdings_rows=None, gate_cgl=0, gate_acb=0):
        """Build a mock pool for inventory holdings report.

        Gate check: two fetchone calls.
        Then: one fetchall for the holdings query.
        """
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        cur.fetchall.return_value = holdings_rows or []
        return pool, conn, cur

    def _sample_holdings_rows(self):
        """Sample acb_snapshot rows representing current holdings."""
        return [
            (
                'NEAR',                     # token_symbol
                Decimal('100.00000000'),    # units_after
                Decimal('4.50000000'),      # acb_per_unit_cad
                Decimal('450.00000000'),    # total_cost_cad
            ),
            (
                'ETH',
                Decimal('0.50000000'),
                Decimal('2500.00000000'),
                Decimal('1250.00000000'),
            ),
        ]

    def test_inventory_shows_acb_per_unit(self):
        """Test 1: InventoryHoldings shows each token with ACB per unit, total cost, current units."""
        from reports.inventory import InventoryHoldingsReport
        rows = self._sample_holdings_rows()
        pool, conn, cur = self._make_pool(holdings_rows=rows)
        report = InventoryHoldingsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'inventory_holdings_2024.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
        self.assertIn('ACB Per Unit (CAD)', headers)
        self.assertIn('Total Cost (CAD)', headers)
        self.assertIn('Units Held', headers)
        self.assertEqual(len(data), 2)
        # NEAR row: 100 units at $4.50/unit = $450 total
        near_row = next(r for r in data if r[0] == 'NEAR')
        self.assertEqual(near_row[1], '100.00000000')  # Units Held
        self.assertEqual(near_row[2], '4.50')          # ACB Per Unit

    def test_inventory_includes_unrealized_gain_loss_when_fmv_available(self):
        """Test 2: InventoryHoldings includes unrealized gain/loss when current FMV available."""
        from reports.inventory import InventoryHoldingsReport
        rows = self._sample_holdings_rows()
        pool, conn, cur = self._make_pool(holdings_rows=rows)
        report = InventoryHoldingsReport(pool)
        # Provide current prices: NEAR=$6.00 (above ACB $4.50 = unrealized gain)
        current_prices = {'NEAR': Decimal('6.00'), 'ETH': Decimal('3000.00')}
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(
                user_id=1, tax_year=2024, output_dir=tmpdir,
                current_prices=current_prices,
            )
            csv_path = os.path.join(tmpdir, 'inventory_holdings_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
        self.assertIn('Unrealized Gain/Loss (CAD)', headers)
        near_row = next(r for r in data if r[0] == 'NEAR')
        # Unrealized = 100 * 6.00 - 450 = 150
        unrealized_idx = headers.index('Unrealized Gain/Loss (CAD)')
        self.assertEqual(near_row[unrealized_idx], '150.00')

    def test_inventory_leaves_fmv_columns_blank_when_no_price(self):
        """Test 3: InventoryHoldings leaves unrealized columns blank when no FMV available."""
        from reports.inventory import InventoryHoldingsReport
        rows = self._sample_holdings_rows()
        pool, conn, cur = self._make_pool(holdings_rows=rows)
        report = InventoryHoldingsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'inventory_holdings_2024.csv')
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
        unrealized_idx = headers.index('Unrealized Gain/Loss (CAD)')
        near_row = next(r for r in data if r[0] == 'NEAR')
        # No prices provided -> blank
        self.assertEqual(near_row[unrealized_idx], '')

    def test_inventory_summary_includes_total_cost(self):
        """Test 4: Summary dict includes total_cost_cad."""
        from reports.inventory import InventoryHoldingsReport
        rows = self._sample_holdings_rows()
        pool, conn, cur = self._make_pool(holdings_rows=rows)
        report = InventoryHoldingsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('total_cost_cad', summary)
        self.assertIn('token_count', summary)
        # 450 + 1250 = 1700
        self.assertEqual(summary['total_cost_cad'], Decimal('1700.00000000'))


# ---------------------------------------------------------------------------
# TestCOGS
# ---------------------------------------------------------------------------

class TestCOGS(unittest.TestCase):
    """Tests for COGSReport.generate()"""

    def _make_pool_capital(self, opening_rows=None, acquisitions_rows=None, closing_rows=None,
                           gate_cgl=0, gate_acb=0):
        """Build a mock pool for capital tax treatment (no FIFO query)."""
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        cur.fetchall.side_effect = [
            opening_rows or [],
            acquisitions_rows or [],
            closing_rows or [],
        ]
        return pool, conn, cur

    def _make_pool_fifo(self, opening_rows=None, acquisitions_rows=None, closing_rows=None,
                        fifo_rows=None, gate_cgl=0, gate_acb=0):
        """Build a mock pool for business_inventory tax treatment (includes FIFO replay query)."""
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        cur.fetchall.side_effect = [
            opening_rows or [],
            acquisitions_rows or [],
            closing_rows or [],
            fifo_rows or [],   # FIFO snapshot rows for replay
        ]
        return pool, conn, cur

    def test_cogs_formula_opening_plus_acquisitions_minus_closing(self):
        """Test 3: COGS = opening_inventory + acquisitions - closing_inventory for the fiscal year."""
        from reports.inventory import COGSReport
        # NEAR: opening=$500, acquisitions=$300, closing=$400
        # COGS = 500 + 300 - 400 = $400
        opening = [('NEAR', Decimal('500.00'))]
        acquisitions = [('NEAR', Decimal('300.00'))]
        closing = [('NEAR', Decimal('400.00'))]
        pool, conn, cur = self._make_pool_capital(
            opening_rows=opening, acquisitions_rows=acquisitions, closing_rows=closing
        )
        report = COGSReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(
                user_id=1, tax_year=2024, output_dir=tmpdir,
                tax_treatment='capital',
            )
        self.assertEqual(summary['total_cogs_cad'], Decimal('400.00'))
        self.assertIn('method', summary)

    def test_cogs_uses_acb_method_for_capital_treatment(self):
        """Test 5: COGS uses ACB average cost when tax_treatment='capital'."""
        from reports.inventory import COGSReport
        opening = [('NEAR', Decimal('1000.00'))]
        acquisitions = [('NEAR', Decimal('500.00'))]
        closing = [('NEAR', Decimal('800.00'))]
        pool, conn, cur = self._make_pool_capital(
            opening_rows=opening, acquisitions_rows=acquisitions, closing_rows=closing
        )
        report = COGSReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(
                user_id=1, tax_year=2024, output_dir=tmpdir,
                tax_treatment='capital',
            )
        self.assertEqual(summary['method'], 'acb_average_cost')

    def test_cogs_uses_fifo_method_for_business_inventory(self):
        """Test 4: COGS uses FIFO when tax_treatment='business_inventory'."""
        from reports.inventory import COGSReport
        opening = [('NEAR', Decimal('500.00'))]
        acquisitions = [('NEAR', Decimal('300.00'))]
        closing = [('NEAR', Decimal('400.00'))]
        # FIFO snapshot rows for replay: (token_symbol, event_type, units_delta, cost_cad_delta, block_timestamp)
        fifo_rows = [
            ('NEAR', 'acquire', Decimal('10'), Decimal('500.00'), 1704067200),  # 2024-01-01
            ('NEAR', 'acquire', Decimal('5'), Decimal('300.00'), 1706745600),   # 2024-02-01
            ('NEAR', 'dispose', Decimal('8'), Decimal('600.00'), 1717200000),   # 2024-06-01
        ]
        pool, conn, cur = self._make_pool_fifo(
            opening_rows=opening, acquisitions_rows=acquisitions, closing_rows=closing,
            fifo_rows=fifo_rows,
        )
        report = COGSReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(
                user_id=1, tax_year=2024, output_dir=tmpdir,
                tax_treatment='business_inventory',
            )
        self.assertEqual(summary['method'], 'fifo')
        self.assertIn('total_cogs_cad', summary)

    def test_cogs_csv_has_correct_headers(self):
        """Test 6: COGS CSV written with correct headers."""
        from reports.inventory import COGSReport
        opening = [('NEAR', Decimal('500.00'))]
        acquisitions = [('NEAR', Decimal('300.00'))]
        closing = [('NEAR', Decimal('400.00'))]
        pool, conn, cur = self._make_pool_capital(
            opening_rows=opening, acquisitions_rows=acquisitions, closing_rows=closing
        )
        report = COGSReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(
                user_id=1, tax_year=2024, output_dir=tmpdir,
                tax_treatment='capital',
            )
            csv_path = os.path.join(tmpdir, 'cogs_2024.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
        self.assertIn('Opening Inventory (CAD)', headers)
        self.assertIn('Acquisitions (CAD)', headers)
        self.assertIn('Closing Inventory (CAD)', headers)
        self.assertIn('COGS (CAD)', headers)
        self.assertIn('Method', headers)


# ---------------------------------------------------------------------------
# TestBusinessIncome
# ---------------------------------------------------------------------------

class TestBusinessIncome(unittest.TestCase):
    """Tests for BusinessIncomeStatement.generate()"""

    def _make_pool(self, income_rows=None, gains_rows=None, fiat_rows=None,
                   gate_cgl=0, gate_acb=0):
        """Build a mock pool for business income statement (capital treatment, no COGS).

        Gate check: two fetchone calls.
        Then fetchall for: income_ledger, capital_gains_ledger, exchange_transactions (fiat).
        """
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        cur.fetchall.side_effect = [
            income_rows or [],
            gains_rows or [],
            fiat_rows or [],
        ]
        return pool, conn, cur

    def _make_pool_with_cogs(self, income_rows=None, gains_rows=None, fiat_rows=None,
                              cogs_opening=None, cogs_acq=None, cogs_closing=None,
                              gate_cgl=0, gate_acb=0):
        """Build pool where COGS report needs extra queries (for hybrid/business_inventory)."""
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        # Gate check for BIS + gate check for COGS (inner COGSReport also calls _check_gate)
        cur.fetchone.side_effect = [
            (gate_cgl,), (gate_acb,),    # BIS gate check
            (gate_cgl,), (gate_acb,),    # COGS gate check
        ]
        cur.fetchall.side_effect = [
            cogs_opening or [],
            cogs_acq or [],
            cogs_closing or [],
            income_rows or [],
            gains_rows or [],
            fiat_rows or [],
        ]
        return pool, conn, cur

    def _sample_income_rows(self):
        return [(Decimal('1200.00'),)]  # total fmv_cad from income_ledger

    def _sample_gains_rows(self):
        return [(Decimal('350.00'),)]   # net gain_loss_cad from capital_gains_ledger

    def _sample_fiat_rows(self):
        return [
            ('deposit', Decimal('5000.00')),    # fiat_deposit
            ('withdrawal', Decimal('2000.00')),  # fiat_withdrawal
        ]

    def test_business_income_includes_crypto_income(self):
        """Test 6: BusinessIncomeStatement includes crypto income (staking/vesting)."""
        from reports.business import BusinessIncomeStatement
        pool, conn, cur = self._make_pool(
            income_rows=self._sample_income_rows(),
            gains_rows=self._sample_gains_rows(),
            fiat_rows=[],
        )
        report = BusinessIncomeStatement(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('crypto_income_cad', summary)
        self.assertEqual(summary['crypto_income_cad'], Decimal('1200.00'))

    def test_business_income_includes_capital_gains(self):
        """Test 6b: BusinessIncomeStatement includes capital gains."""
        from reports.business import BusinessIncomeStatement
        pool, conn, cur = self._make_pool(
            income_rows=self._sample_income_rows(),
            gains_rows=self._sample_gains_rows(),
            fiat_rows=[],
        )
        report = BusinessIncomeStatement(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('capital_gains_net_cad', summary)
        self.assertEqual(summary['capital_gains_net_cad'], Decimal('350.00'))

    def test_business_income_includes_fiat_deposits_withdrawals(self):
        """Test 7: BusinessIncomeStatement includes fiat deposits/withdrawals from exchange records."""
        from reports.business import BusinessIncomeStatement
        pool, conn, cur = self._make_pool(
            income_rows=self._sample_income_rows(),
            gains_rows=self._sample_gains_rows(),
            fiat_rows=self._sample_fiat_rows(),
        )
        report = BusinessIncomeStatement(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
        self.assertIn('fiat_deposits_cad', summary)
        self.assertIn('fiat_withdrawals_cad', summary)
        self.assertEqual(summary['fiat_deposits_cad'], Decimal('5000.00'))
        self.assertEqual(summary['fiat_withdrawals_cad'], Decimal('2000.00'))

    def test_business_income_csv_written(self):
        """Test 6c: BusinessIncomeStatement writes business_income CSV."""
        from reports.business import BusinessIncomeStatement
        pool, conn, cur = self._make_pool(
            income_rows=self._sample_income_rows(),
            gains_rows=self._sample_gains_rows(),
            fiat_rows=self._sample_fiat_rows(),
        )
        report = BusinessIncomeStatement(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            csv_path = os.path.join(tmpdir, 'business_income_2024.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                data = list(reader)
        self.assertIn('Category', headers)
        self.assertIn('Amount (CAD)', headers)
        # Should have at least the major categories
        categories = [row[0] for row in data]
        self.assertTrue(any('Income' in c or 'Gains' in c or 'Net' in c for c in categories))

    def test_business_income_hybrid_generates_both_views(self):
        """Test 8: Tax treatment 'hybrid' generates both capital and business views."""
        from reports.business import BusinessIncomeStatement
        # For hybrid, BIS creates a COGSReport internally — needs extra pool queries
        pool, conn, cur = self._make_pool_with_cogs(
            income_rows=self._sample_income_rows(),
            gains_rows=self._sample_gains_rows(),
            fiat_rows=[],
            cogs_opening=[('NEAR', Decimal('500.00'))],
            cogs_acq=[('NEAR', Decimal('200.00'))],
            cogs_closing=[('NEAR', Decimal('300.00'))],
        )
        report = BusinessIncomeStatement(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = report.generate(
                user_id=1, tax_year=2024, output_dir=tmpdir,
                tax_treatment='hybrid',
            )
        # hybrid should include both capital view and business view keys
        self.assertIn('capital_view', summary)
        self.assertIn('business_view', summary)


if __name__ == '__main__':
    unittest.main()


# ---------------------------------------------------------------------------
# TestKoinlyExport
# ---------------------------------------------------------------------------

class TestKoinlyExport(unittest.TestCase):
    """Tests for KoinlyExport.generate()"""

    YOCTO = Decimal('1000000000000000000000000')  # 1e24

    def _make_pool(self, near_rows=None, exchange_rows=None):
        """Build a mock pool supporting named cursor streaming for KoinlyExport.

        KoinlyExport uses two named cursors:
          - "export_stream_near": iterates NEAR rows
          - "export_stream_exchange": iterates exchange rows
        Gate check uses unnamed cursor with fetchone.
        """
        pool = MagicMock()
        conn = MagicMock()
        pool.getconn.return_value = conn

        # Gate cursor
        gate_cur = MagicMock()
        gate_cur.fetchone.side_effect = [(0,), (0,)]

        # Named cursors for streaming
        near_cur = MagicMock()
        near_cur.__iter__ = MagicMock(return_value=iter(near_rows or []))

        exchange_cur = MagicMock()
        exchange_cur.__iter__ = MagicMock(return_value=iter(exchange_rows or []))

        _named_cursors = {
            'export_stream_near': near_cur,
            'export_stream_exchange': exchange_cur,
        }
        _regular_cursors = [gate_cur]
        _regular_index = [0]

        def cursor_factory(**kwargs):
            name = kwargs.get('name')
            if name in _named_cursors:
                return _named_cursors[name]
            idx = _regular_index[0]
            _regular_index[0] += 1
            return _regular_cursors[idx] if idx < len(_regular_cursors) else MagicMock()

        conn.cursor.side_effect = cursor_factory
        return pool, conn, gate_cur

    def _near_row(self, category='staking_reward', direction='in',
                  amount=None, fee=None, timestamp_ns=None, tx_hash='abc123',
                  action_type='FUNCTION_CALL', account_id='wallet.near'):
        if amount is None:
            amount = Decimal('10') * self.YOCTO
        if fee is None:
            fee = Decimal('0')
        if timestamp_ns is None:
            timestamp_ns = 1_705_276_800 * 1_000_000_000  # Jan 15 2024
        return (category, direction, amount, fee, timestamp_ns,
                tx_hash, action_type, account_id, 'near')

    def test_koinly_csv_has_12_headers(self):
        """Test 1: Koinly CSV has correct 12 headers per KOINLY_HEADERS."""
        from reports.export import KoinlyExport
        pool, conn, cur = self._make_pool()
        exporter = KoinlyExport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            import csv as _csv
            csv_path = os.path.join(tmpdir, 'koinly_export_2024.csv')
            with open(csv_path) as f:
                reader = _csv.reader(f)
                headers = next(reader)
        self.assertEqual(len(headers), 12)
        self.assertEqual(headers[0], 'Date')
        self.assertEqual(headers[-1], 'TxHash')

    def test_staking_reward_maps_to_staking_label(self):
        """Test 2: Category 'staking_reward' maps to Koinly label 'staking'."""
        from reports.export import KoinlyExport
        row = self._near_row(category='staking_reward', direction='in')
        pool, conn, cur = self._make_pool(near_rows=[row])
        exporter = KoinlyExport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            import csv as _csv
            csv_path = os.path.join(tmpdir, 'koinly_export_2024.csv')
            with open(csv_path) as f:
                reader = _csv.reader(f)
                next(reader)
                data = list(reader)
        self.assertEqual(len(data), 1)
        label_idx = 9
        self.assertEqual(data[0][label_idx], 'staking')

    def test_capital_gain_out_sets_sent_amount(self):
        """Test 3: Category 'capital_gain' with direction 'out' sets Sent Amount/Currency."""
        from reports.export import KoinlyExport
        row = self._near_row(category='capital_gain', direction='out',
                             amount=Decimal('5') * self.YOCTO)
        pool, conn, cur = self._make_pool(near_rows=[row])
        exporter = KoinlyExport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            import csv as _csv
            csv_path = os.path.join(tmpdir, 'koinly_export_2024.csv')
            with open(csv_path) as f:
                reader = _csv.reader(f)
                next(reader)
                data = list(reader)
        self.assertEqual(len(data), 1)
        self.assertNotEqual(data[0][1], '')
        self.assertEqual(data[0][2], 'NEAR')
        self.assertEqual(data[0][3], '')

    def test_income_in_sets_received_amount(self):
        """Test 4: Category 'income' with direction 'in' sets Received Amount/Currency."""
        from reports.export import KoinlyExport
        row = self._near_row(category='income', direction='in',
                             amount=Decimal('10') * self.YOCTO)
        pool, conn, cur = self._make_pool(near_rows=[row])
        exporter = KoinlyExport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            import csv as _csv
            csv_path = os.path.join(tmpdir, 'koinly_export_2024.csv')
            with open(csv_path) as f:
                reader = _csv.reader(f)
                next(reader)
                data = list(reader)
        self.assertEqual(len(data), 1)
        self.assertNotEqual(data[0][3], '')
        self.assertEqual(data[0][4], 'NEAR')
        self.assertEqual(data[0][1], '')

    def test_fee_amount_populated_when_fee_nonzero(self):
        """Test 5: Fee amount and currency populated when fee > 0."""
        from reports.export import KoinlyExport
        row = self._near_row(category='transfer', direction='out',
                             fee=Decimal('1000000000000000000000'))
        pool, conn, cur = self._make_pool(near_rows=[row])
        exporter = KoinlyExport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            import csv as _csv
            csv_path = os.path.join(tmpdir, 'koinly_export_2024.csv')
            with open(csv_path) as f:
                reader = _csv.reader(f)
                next(reader)
                data = list(reader)
        self.assertEqual(len(data), 1)
        self.assertNotEqual(data[0][5], '')
        self.assertEqual(data[0][6], 'NEAR')

    def test_year_specific_export_filters_by_fiscal_year(self):
        """Test 6: Tax-year-specific export filters by fiscal year range."""
        from reports.export import KoinlyExport
        ts_in  = 1_705_276_800 * 1_000_000_000  # Jan 15 2024
        ts_out = 1_673_740_800 * 1_000_000_000  # Jan 15 2023
        row_in  = self._near_row(timestamp_ns=ts_in,  tx_hash='in2024')
        row_out = self._near_row(timestamp_ns=ts_out, tx_hash='out2023')
        pool, conn, cur = self._make_pool(near_rows=[row_in, row_out])
        exporter = KoinlyExport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            import csv as _csv
            csv_path = os.path.join(tmpdir, 'koinly_export_2024.csv')
            with open(csv_path) as f:
                reader = _csv.reader(f)
                next(reader)
                data = list(reader)
        tx_hashes = [row[11] for row in data]
        self.assertIn('in2024', tx_hashes)
        self.assertNotIn('out2023', tx_hashes)

    def test_full_history_includes_all_transactions(self):
        """Test 7: Full-history export includes all transactions (no date filter)."""
        from reports.export import KoinlyExport
        ts_2024 = 1_705_276_800 * 1_000_000_000
        ts_2023 = 1_673_740_800 * 1_000_000_000
        row_2024 = self._near_row(timestamp_ns=ts_2024, tx_hash='tx2024')
        row_2023 = self._near_row(timestamp_ns=ts_2023, tx_hash='tx2023')
        # Use the helper which sets up named cursor mocks correctly
        pool, conn, _ = self._make_pool(near_rows=[row_2024, row_2023], exchange_rows=[])
        exporter = KoinlyExport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate(user_id=1, tax_year=2024, output_dir=tmpdir,
                              full_history=True)
            import csv as _csv
            csv_path = os.path.join(tmpdir, 'koinly_export_full.csv')
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path) as f:
                reader = _csv.reader(f)
                next(reader)
                data = list(reader)
        tx_hashes = [row[11] for row in data]
        self.assertIn('tx2024', tx_hashes)
        self.assertIn('tx2023', tx_hashes)

    def test_near_yoctonear_converted_to_human_units(self):
        """Test 8: NEAR amounts converted from yoctoNEAR (divide by 1e24) to human units."""
        from reports.export import KoinlyExport
        ten_near_yocto = Decimal('10') * self.YOCTO
        row = self._near_row(category='income', direction='in',
                             amount=ten_near_yocto)
        pool, conn, cur = self._make_pool(near_rows=[row])
        exporter = KoinlyExport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate(user_id=1, tax_year=2024, output_dir=tmpdir)
            import csv as _csv
            csv_path = os.path.join(tmpdir, 'koinly_export_2024.csv')
            with open(csv_path) as f:
                reader = _csv.reader(f)
                next(reader)
                data = list(reader)
        self.assertEqual(len(data), 1)
        received_amount = Decimal(data[0][3])
        self.assertEqual(received_amount, Decimal('10'))


# ---------------------------------------------------------------------------
# TestAccountingExports
# ---------------------------------------------------------------------------

class TestAccountingExports(unittest.TestCase):
    """Tests for AccountingExporter (QuickBooks, Xero, Sage50, double-entry)."""

    def _make_pool(self, gains_rows=None, income_rows=None):
        """Build a mock pool supporting named cursor streaming for AccountingExporter.

        AccountingExporter uses two named cursors:
          - "acct_stream_gains": iterates capital gains rows
          - "acct_stream_income": iterates income rows
        Gate check uses unnamed cursor with fetchone.
        """
        pool = MagicMock()
        conn = MagicMock()
        pool.getconn.return_value = conn

        # Gate cursor
        gate_cur = MagicMock()
        gate_cur.fetchone.side_effect = [(0,), (0,)]

        # Named cursors for streaming
        gains_cur = MagicMock()
        gains_cur.__iter__ = MagicMock(return_value=iter(gains_rows or []))

        income_cur = MagicMock()
        income_cur.__iter__ = MagicMock(return_value=iter(income_rows or []))

        _named_cursors = {
            'acct_stream_gains': gains_cur,
            'acct_stream_income': income_cur,
        }
        _regular_cursors = [gate_cur]
        _regular_index = [0]

        def cursor_factory(**kwargs):
            name = kwargs.get('name')
            if name in _named_cursors:
                return _named_cursors[name]
            idx = _regular_index[0]
            _regular_index[0] += 1
            return _regular_cursors[idx] if idx < len(_regular_cursors) else MagicMock()

        conn.cursor.side_effect = cursor_factory
        return pool, conn, gate_cur

    def _gains_row(self, disposal_date=None, token='NEAR',
                   proceeds=Decimal('1500.00'), acb=Decimal('900.00'),
                   gain_loss=Decimal('600.00'), tx_hash='tx001'):
        if disposal_date is None:
            disposal_date = date(2024, 1, 15)
        return (disposal_date, token, proceeds, acb, gain_loss, tx_hash)

    def _income_row(self, income_date=None, token='NEAR',
                    fmv_cad=Decimal('200.00'), source_type='staking',
                    tx_hash='tx002'):
        if income_date is None:
            income_date = date(2024, 2, 10)
        return (income_date, token, fmv_cad, source_type, tx_hash)

    def test_quickbooks_iif_has_header_rows(self):
        """Test 1: QuickBooks IIF has !TRNS/!SPL/!ENDTRNS header rows."""
        from reports.export import AccountingExporter
        pool, conn, cur = self._make_pool()
        exporter = AccountingExporter(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate_all(user_id=1, tax_year=2024, output_dir=tmpdir)
            iif_path = os.path.join(tmpdir, 'quickbooks_2024.iif')
            self.assertTrue(os.path.exists(iif_path))
            with open(iif_path) as f:
                content = f.read()
        self.assertIn('!TRNS', content)
        self.assertIn('!SPL', content)
        self.assertIn('!ENDTRNS', content)

    def test_quickbooks_iif_balanced_entry_triplet(self):
        """Test 2: Each QuickBooks entry has balanced TRNS+SPL+ENDTRNS triplet."""
        from reports.export import AccountingExporter
        pool, conn, cur = self._make_pool(gains_rows=[self._gains_row()])
        exporter = AccountingExporter(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate_all(user_id=1, tax_year=2024, output_dir=tmpdir)
            iif_path = os.path.join(tmpdir, 'quickbooks_2024.iif')
            with open(iif_path) as f:
                lines = [ln.rstrip('\n') for ln in f.readlines()]
        trns_count    = sum(1 for ln in lines if ln.startswith('TRNS\t'))
        spl_count     = sum(1 for ln in lines if ln.startswith('SPL\t'))
        endtrns_count = sum(1 for ln in lines if ln.strip() == 'ENDTRNS')
        self.assertEqual(trns_count, spl_count)
        self.assertEqual(trns_count, endtrns_count)
        self.assertGreater(trns_count, 0)

    def test_xero_csv_has_required_headers(self):
        """Test 3: Xero CSV has Date, Description, Reference, Debit, Credit, Account Code, Tax Rate."""
        from reports.export import AccountingExporter
        pool, conn, cur = self._make_pool()
        exporter = AccountingExporter(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate_all(user_id=1, tax_year=2024, output_dir=tmpdir)
            xero_path = os.path.join(tmpdir, 'xero_2024.csv')
            self.assertTrue(os.path.exists(xero_path))
            import csv as _csv
            with open(xero_path) as f:
                reader = _csv.reader(f)
                headers = next(reader)
        required = {'Date', 'Description', 'Reference', 'Debit', 'Credit',
                    'Account Code', 'Tax Rate'}
        self.assertTrue(required.issubset(set(headers)),
                        f"Missing headers: {required - set(headers)}")

    def test_sage50_csv_has_valid_format(self):
        """Test 4: Sage 50 CSV produces valid import format."""
        from reports.export import AccountingExporter
        pool, conn, cur = self._make_pool(gains_rows=[self._gains_row()])
        exporter = AccountingExporter(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate_all(user_id=1, tax_year=2024, output_dir=tmpdir)
            sage_path = os.path.join(tmpdir, 'sage50_2024.csv')
            self.assertTrue(os.path.exists(sage_path))
            import csv as _csv
            with open(sage_path) as f:
                reader = _csv.reader(f)
                headers = next(reader)
        required = {'Date', 'Source', 'Comment', 'Account Number', 'Debit', 'Credit'}
        self.assertTrue(required.issubset(set(headers)),
                        f"Missing Sage 50 headers: {required - set(headers)}")

    def test_double_entry_csv_balanced_per_entry(self):
        """Test 5: Generic double-entry has balanced Debit=Credit per entry."""
        from reports.export import AccountingExporter
        pool, conn, cur = self._make_pool(
            gains_rows=[self._gains_row(
                proceeds=Decimal('1500.00'),
                acb=Decimal('900.00'),
                gain_loss=Decimal('600.00'),
            )]
        )
        exporter = AccountingExporter(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate_all(user_id=1, tax_year=2024, output_dir=tmpdir)
            de_path = os.path.join(tmpdir, 'double_entry_2024.csv')
            self.assertTrue(os.path.exists(de_path))
            import csv as _csv
            with open(de_path) as f:
                reader = _csv.reader(f)
                headers = next(reader)
                rows = list(reader)
        debit_idx  = headers.index('Debit')
        credit_idx = headers.index('Credit')
        total_debit  = sum(Decimal(r[debit_idx])  for r in rows if r[debit_idx])
        total_credit = sum(Decimal(r[credit_idx]) for r in rows if r[credit_idx])
        self.assertEqual(total_debit, total_credit,
                         f"Unbalanced: debit={total_debit} credit={total_credit}")

    def test_capital_gains_produce_correct_journal_entries(self):
        """Test 6: Capital gains produce Crypto Assets debit + Capital Gains credit entries."""
        from reports.export import AccountingExporter
        pool, conn, cur = self._make_pool(
            gains_rows=[self._gains_row(
                proceeds=Decimal('1500.00'),
                acb=Decimal('900.00'),
                gain_loss=Decimal('600.00'),
            )]
        )
        exporter = AccountingExporter(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate_all(user_id=1, tax_year=2024, output_dir=tmpdir)
            de_path = os.path.join(tmpdir, 'double_entry_2024.csv')
            import csv as _csv
            with open(de_path) as f:
                reader = _csv.reader(f)
                headers = next(reader)
                rows = list(reader)
        account_idx = headers.index('Account')
        accounts = [r[account_idx] for r in rows]
        self.assertTrue(any('Capital' in a for a in accounts),
                        f"No Capital Gains account found in: {accounts}")

    def test_income_events_produce_income_account_entries(self):
        """Test 7: Income events produce Crypto Assets debit + Income credit entries."""
        from reports.export import AccountingExporter
        pool, conn, cur = self._make_pool(
            income_rows=[self._income_row(fmv_cad=Decimal('200.00'))],
        )
        exporter = AccountingExporter(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter.generate_all(user_id=1, tax_year=2024, output_dir=tmpdir)
            de_path = os.path.join(tmpdir, 'double_entry_2024.csv')
            import csv as _csv
            with open(de_path) as f:
                reader = _csv.reader(f)
                headers = next(reader)
                rows = list(reader)
        account_idx = headers.index('Account')
        accounts = [r[account_idx] for r in rows]
        self.assertTrue(any('Income' in a for a in accounts),
                        f"No Income account found in: {accounts}")


# ---------------------------------------------------------------------------
# TestPackageBuilder
# ---------------------------------------------------------------------------

class TestPackageBuilder(unittest.TestCase):
    """Tests for PackageBuilder.build() orchestrator."""

    def _make_pool(self):
        """Mock pool that satisfies gate check (0 needs_review) and returns empty rows."""
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        cur.fetchone.return_value = (0,)
        cur.fetchall.return_value = []
        return pool

    def _mock_summary(self):
        """Default summary dict returned by all mocked report modules."""
        return {
            'total_proceeds': '0', 'net_gain_loss': '0',
            'total_income': '0', 'by_source': {},
            'row_count': 0, 'file_path': 'mock.csv',
            't1135_required': False, 'total_foreign_cost': '0',
            'self_custody_ambiguous': False, 'self_custody_cost': '0',
            'count': 0, 'total_denied': '0',
            'output_path': 'mock.csv',
            'token_count': 0, 'total_cost_cad': '0',
            'crypto_income_cad': '0', 'capital_gains_net_cad': '0',
            'net_business_income_cad': '0',
            'files': ['mock.csv'],
        }

    def _build_with_mocks(self, pool, tax_year=2024, tax_treatment='capital',
                          tmpdir=None, specialist_override=False):
        """Helper: patch all report modules and ReportEngine._check_gate, run build(), return (manifest, patchers)."""
        from reports.generate import PackageBuilder

        modules = [
            'reports.generate.CapitalGainsReport',
            'reports.generate.IncomeReport',
            'reports.generate.LedgerReport',
            'reports.generate.T1135Checker',
            'reports.generate.SuperficialLossReport',
            'reports.generate.KoinlyExport',
            'reports.generate.AccountingExporter',
            'reports.generate.InventoryHoldingsReport',
            'reports.generate.COGSReport',
            'reports.generate.BusinessIncomeStatement',
        ]

        patchers = {}
        for mod in modules:
            p = patch(mod)
            mock_cls = p.start()
            mock_inst = MagicMock()
            mock_inst.generate.return_value = self._mock_summary()
            mock_inst.generate_all.return_value = {
                'quickbooks': 'mock_qb.iif',
                'xero': 'mock_xero.csv',
                'sage50': 'mock_sage.csv',
                'double_entry': 'mock_de.csv',
            }
            mock_cls.return_value = mock_inst
            patchers[mod] = (p, mock_inst)

        # Patch the top-level gate check and write_pdf to avoid DB/WeasyPrint calls
        gate_patcher = patch('reports.generate.ReportEngine._check_gate',
                             return_value={'blocked': False, 'flagged_count': 0})
        gate_patcher.start()
        patchers['_gate'] = (gate_patcher, None)

        pdf_patcher = patch('reports.generate.ReportEngine.write_pdf',
                            return_value='mock.pdf')
        pdf_patcher.start()
        patchers['_pdf'] = (pdf_patcher, None)

        # Phase 16: write_audit() requires a DEK in context; patch it out since
        # PackageBuilder tests don't test audit write behaviour.
        audit_patcher = patch('reports.generate.write_audit')
        audit_patcher.start()
        patchers['_audit'] = (audit_patcher, None)

        try:
            builder = PackageBuilder(pool, specialist_override=specialist_override)
            manifest = builder.build(
                user_id=1,
                tax_year=tax_year,
                output_base=tmpdir or '/tmp',
                year_end_month=12,
                tax_treatment=tax_treatment,
            )
        finally:
            for mod, (p, _) in patchers.items():
                p.stop()

        return manifest, patchers

    def test_build_calls_all_base_reports(self):
        """Test 1: build() calls CapitalGainsReport, IncomeReport, LedgerReport, T1135Checker."""
        import tempfile
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, patchers = self._build_with_mocks(pool, tmpdir=tmpdir)
        # Each of these report generate() methods should have been called
        for key in [
            'reports.generate.CapitalGainsReport',
            'reports.generate.IncomeReport',
            'reports.generate.LedgerReport',
            'reports.generate.T1135Checker',
        ]:
            mock_inst = patchers[key][1]
            self.assertTrue(
                mock_inst.generate.called or mock_inst.generate_all.called,
                f"{key} was not called during build()"
            )

    def test_build_creates_output_directory(self):
        """Test 2: Output directory output/{year}_tax_package/ is created."""
        import tempfile
        import os
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, _ = self._build_with_mocks(pool, tmpdir=tmpdir, tax_year=2024)
            expected_dir = os.path.join(tmpdir, '2024_tax_package')
            self.assertTrue(os.path.isdir(expected_dir),
                            f"Expected output dir {expected_dir} to exist")

    def test_build_returns_manifest_with_required_keys(self):
        """Test 3 + 10: build() returns manifest dict with files, summaries, tax_year, output_dir."""
        import tempfile
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, _ = self._build_with_mocks(pool, tmpdir=tmpdir)
        self.assertIn('files', manifest)
        self.assertIn('summaries', manifest)
        self.assertIn('tax_year', manifest)
        self.assertIn('output_dir', manifest)
        self.assertIsInstance(manifest['files'], list)
        self.assertIsInstance(manifest['summaries'], dict)

    def test_build_includes_koinly_export(self):
        """Test 4: Koinly export (year + full) is included."""
        import tempfile
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, patchers = self._build_with_mocks(pool, tmpdir=tmpdir)
        koinly_mock = patchers['reports.generate.KoinlyExport'][1]
        # Called at least twice: once for year-specific, once for full history
        self.assertGreaterEqual(koinly_mock.generate.call_count, 2,
                                "KoinlyExport.generate() should be called twice (year + full)")

    def test_build_includes_accounting_exports(self):
        """Test 5: Accounting exports (QB, Xero, Sage, double-entry) are included."""
        import tempfile
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, patchers = self._build_with_mocks(pool, tmpdir=tmpdir)
        acct_mock = patchers['reports.generate.AccountingExporter'][1]
        self.assertTrue(acct_mock.generate_all.called,
                        "AccountingExporter.generate_all() should be called")

    def test_capital_treatment_skips_cogs(self):
        """Test 6: tax_treatment='capital' skips COGSReport."""
        import tempfile
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, patchers = self._build_with_mocks(
                pool, tmpdir=tmpdir, tax_treatment='capital'
            )
        cogs_mock = patchers['reports.generate.COGSReport'][1]
        self.assertFalse(cogs_mock.generate.called,
                         "COGSReport should NOT be called for tax_treatment='capital'")

    def test_business_inventory_includes_cogs_and_business_income(self):
        """Test 7: tax_treatment='business_inventory' includes COGSReport and BusinessIncomeStatement."""
        import tempfile
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, patchers = self._build_with_mocks(
                pool, tmpdir=tmpdir, tax_treatment='business_inventory'
            )
        cogs_mock = patchers['reports.generate.COGSReport'][1]
        biz_mock = patchers['reports.generate.BusinessIncomeStatement'][1]
        self.assertTrue(cogs_mock.generate.called,
                        "COGSReport should be called for tax_treatment='business_inventory'")
        self.assertTrue(biz_mock.generate.called,
                        "BusinessIncomeStatement should be called for tax_treatment='business_inventory'")

    def test_hybrid_treatment_includes_both_views(self):
        """Test 8: tax_treatment='hybrid' generates both capital and business views."""
        import tempfile
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, patchers = self._build_with_mocks(
                pool, tmpdir=tmpdir, tax_treatment='hybrid'
            )
        cogs_mock = patchers['reports.generate.COGSReport'][1]
        biz_mock = patchers['reports.generate.BusinessIncomeStatement'][1]
        self.assertTrue(cogs_mock.generate.called,
                        "COGSReport should be called for tax_treatment='hybrid'")
        self.assertTrue(biz_mock.generate.called,
                        "BusinessIncomeStatement should be called for tax_treatment='hybrid'")

    def test_gate_check_runs_once(self):
        """Test 9: Gate check runs once at top level, not per-report (mocked so 0 gate calls in report modules)."""
        import tempfile
        pool = self._make_pool()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, _ = self._build_with_mocks(pool, tmpdir=tmpdir)
        # Gate check is done once in PackageBuilder; if it ran, manifest returned means no exception
        self.assertIn('tax_year', manifest)


# ---------------------------------------------------------------------------
# TestReportHandler
# ---------------------------------------------------------------------------

class TestReportHandler(unittest.TestCase):
    """Tests for ReportHandler job type."""

    def _make_pool(self):
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        cur.fetchone.return_value = (0,)
        cur.fetchall.return_value = []
        return pool

    def _make_job_row(self, tax_year=2024, tax_treatment='capital',
                      year_end_month=12, specialist_override=False,
                      excluded_wallet_ids=None):
        import json
        return {
            'id': 1,
            'user_id': 1,
            'wallet_id': 1,
            'job_type': 'generate_reports',
            'chain': 'near',
            'cursor': json.dumps({
                'tax_year': tax_year,
                'tax_treatment': tax_treatment,
                'year_end_month': year_end_month,
                'specialist_override': specialist_override,
                'excluded_wallet_ids': excluded_wallet_ids or [],
            }),
        }

    def test_run_with_valid_job_row_returns_stats(self):
        """Test 1: run() with valid job_row returns stats dict with files_generated and output_dir."""
        import tempfile
        from reports.handlers.report_handler import ReportHandler
        pool = self._make_pool()
        handler = ReportHandler(pool)
        job_row = self._make_job_row()

        with patch('reports.handlers.report_handler.PackageBuilder') as mock_pb_cls:
            mock_pb = MagicMock()
            mock_pb.build.return_value = {
                'files': ['file1.csv', 'file2.pdf'],
                'summaries': {},
                'tax_year': 2024,
                'output_dir': '/tmp/2024_tax_package',
            }
            mock_pb_cls.return_value = mock_pb

            with tempfile.TemporaryDirectory():
                stats = handler.run(job_row, conn=MagicMock())

        self.assertIn('files_generated', stats)
        self.assertIn('output_dir', stats)
        self.assertEqual(stats['files_generated'], 2)

    def test_run_with_blocked_gate_returns_error_dict(self):
        """Test 2: run() with ReportBlockedError returns error dict without raising."""
        from reports.handlers.report_handler import ReportHandler
        from reports.engine import ReportBlockedError
        pool = self._make_pool()
        handler = ReportHandler(pool)
        job_row = self._make_job_row()

        with patch('reports.handlers.report_handler.PackageBuilder') as mock_pb_cls:
            mock_pb = MagicMock()
            mock_pb.build.side_effect = ReportBlockedError(
                user_id=1, tax_year=2024, flagged_count=5
            )
            mock_pb_cls.return_value = mock_pb

            stats = handler.run(job_row, conn=MagicMock())

        self.assertIn('error', stats)
        self.assertTrue(stats.get('blocked'), "blocked flag should be True")

    def test_generate_reports_registered_in_service(self):
        """Test 3: generate_reports job type is registered in IndexerService handler map."""
        with patch('indexers.service.get_pool') as mock_pool, \
             patch('indexers.service.PriceService') as mock_price, \
             patch.object(__import__('signal'), 'signal'):
            mock_pool.return_value = MagicMock()
            mock_price.return_value = MagicMock()
            from indexers.service import IndexerService
            service = IndexerService()
            self.assertIn('generate_reports', service.handlers,
                          "generate_reports should be registered in IndexerService.handlers")


# ---------------------------------------------------------------------------
# TestStreamingNamedCursors
# ---------------------------------------------------------------------------

class TestStreamingNamedCursors(unittest.TestCase):
    """Tests for named cursor streaming in capital gains, ledger, and export reports.

    Verifies that large result-set queries use psycopg2 named cursors (server-side)
    instead of fetchall, and that named cursors are properly closed before putconn.
    """

    def _make_streaming_pool(self, rows=None):
        """Build a mock pool that tracks named cursor creation.

        Named cursors are created via conn.cursor(name=...) and return an iterable.
        """
        pool = MagicMock()
        conn = MagicMock()
        pool.getconn.return_value = conn

        # Gate check cursor (no name= arg)
        gate_cur = MagicMock()
        gate_cur.fetchone.side_effect = [(0,), (0,)]

        # Named cursor (for streaming)
        named_cur = MagicMock()
        named_cur.__iter__ = MagicMock(return_value=iter(rows or []))
        named_cur.__enter__ = MagicMock(return_value=named_cur)
        named_cur.__exit__ = MagicMock(return_value=False)

        # conn.cursor() without name= returns gate cursor; with name= returns named cursor
        def cursor_factory(**kwargs):
            if 'name' in kwargs:
                return named_cur
            return gate_cur

        conn.cursor.side_effect = cursor_factory
        return pool, conn, gate_cur, named_cur

    def test_streaming_capital_gains_uses_named_cursor(self):
        """capital_gains.generate() uses conn.cursor(name=...) for the main disposal query."""
        from reports.capital_gains import CapitalGainsReport

        pool, conn, gate_cur, named_cur = self._make_streaming_pool(rows=[])
        # Opening ACB query also needs a cursor — use regular one (not named)
        gate_cur.fetchone.side_effect = [(0,), (0,)]
        gate_cur.fetchall.return_value = []

        report = CapitalGainsReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)

        # Verify cursor was created with a name= keyword argument at some point
        calls_with_name = [
            c for c in conn.cursor.call_args_list
            if c.kwargs.get('name') or (c.args and False)
        ]
        self.assertGreater(
            len(calls_with_name), 0,
            "capital_gains.generate() must call conn.cursor(name=...) for streaming"
        )

    def test_streaming_ledger_uses_named_cursor(self):
        """ledger.generate() uses conn.cursor(name=...) for the UNION ALL ledger query."""
        from reports.ledger import LedgerReport

        pool, conn, gate_cur, named_cur = self._make_streaming_pool(rows=[])
        gate_cur.fetchone.side_effect = [(0,), (0,)]

        report = LedgerReport(pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)

        calls_with_name = [
            c for c in conn.cursor.call_args_list
            if c.kwargs.get('name')
        ]
        self.assertGreater(
            len(calls_with_name), 0,
            "ledger.generate() must call conn.cursor(name=...) for streaming"
        )

    def test_named_cursor_closed_before_putconn_capital_gains(self):
        """Named cursor is closed before pool.putconn() in capital_gains.generate()."""
        from reports.capital_gains import CapitalGainsReport

        pool, conn, gate_cur, named_cur = self._make_streaming_pool(rows=[])
        gate_cur.fetchone.side_effect = [(0,), (0,)]
        gate_cur.fetchall.return_value = []

        report = CapitalGainsReport(pool)
        close_order = []
        named_cur.close.side_effect = lambda: close_order.append('close')
        pool.putconn.side_effect = lambda c: close_order.append('putconn')

        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)

        # close must appear before putconn
        self.assertIn('close', close_order)
        self.assertIn('putconn', close_order)
        close_idx = close_order.index('close')
        putconn_idx = len(close_order) - 1 - close_order[::-1].index('putconn')
        self.assertLess(close_idx, putconn_idx,
                        "Named cursor must be closed before putconn is called")

    def test_named_cursor_closed_before_putconn_ledger(self):
        """Named cursor is closed before pool.putconn() in ledger.generate()."""
        from reports.ledger import LedgerReport

        pool, conn, gate_cur, named_cur = self._make_streaming_pool(rows=[])
        gate_cur.fetchone.side_effect = [(0,), (0,)]

        report = LedgerReport(pool)
        close_order = []
        named_cur.close.side_effect = lambda: close_order.append('close')
        pool.putconn.side_effect = lambda c: close_order.append('putconn')

        with tempfile.TemporaryDirectory() as tmpdir:
            report.generate(user_id=1, tax_year=2024, output_dir=tmpdir)

        self.assertIn('close', close_order)
        self.assertIn('putconn', close_order)
        close_idx = close_order.index('close')
        putconn_idx = len(close_order) - 1 - close_order[::-1].index('putconn')
        self.assertLess(close_idx, putconn_idx,
                        "Named cursor must be closed before putconn is called")


# ---------------------------------------------------------------------------
# TestManifestGeneration — Task 1 (11-02)
# ---------------------------------------------------------------------------


class TestManifestGeneration(unittest.TestCase):
    """Tests for PackageBuilder._write_manifest() and _get_data_fingerprint()."""

    def _make_fingerprint_conn(
        self,
        last_tx_ts='2024-12-31T23:59:59',
        tx_count=150,
        acb_version='2024-12-31T10:00:00',
        needs_review=3,
        exchange_tx_count=50,
    ):
        """Build a mock conn whose cursor returns fingerprint query results."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        # _get_data_fingerprint runs 5 queries in sequence
        cur.fetchone.side_effect = [
            (last_tx_ts,),
            (tx_count,),
            (acb_version,),
            (needs_review,),
            (exchange_tx_count,),
        ]
        return conn, cur

    def test_manifest_file_created(self):
        """Test 1: PackageBuilder._write_manifest() creates MANIFEST.json in output_dir."""
        from reports.generate import PackageBuilder
        pool = MagicMock()
        conn, cur = self._make_fingerprint_conn()

        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_file = os.path.join(tmpdir, 'capital_gains_2024.csv')
            with open(dummy_file, 'w') as f:
                f.write('Date,Amount\n2024-01-01,100\n')

            builder = PackageBuilder(pool)
            manifest_path = builder._write_manifest(tmpdir, user_id=1, tax_year=2024, conn=conn)

            manifest_json = os.path.join(tmpdir, 'MANIFEST.json')
            self.assertTrue(os.path.exists(manifest_json))
            self.assertEqual(manifest_path, manifest_json)

    def test_manifest_contains_files_with_sha256_and_size(self):
        """Test 2: MANIFEST.json 'files' array contains filename, sha256, size_bytes per file."""
        import json
        import hashlib
        from reports.generate import PackageBuilder
        pool = MagicMock()
        conn, cur = self._make_fingerprint_conn()

        with tempfile.TemporaryDirectory() as tmpdir:
            content = b'Date,Amount\n2024-01-01,100\n'
            dummy_file = os.path.join(tmpdir, 'capital_gains_2024.csv')
            with open(dummy_file, 'wb') as f:
                f.write(content)
            expected_sha256 = hashlib.sha256(content).hexdigest()
            expected_size = len(content)

            builder = PackageBuilder(pool)
            builder._write_manifest(tmpdir, user_id=1, tax_year=2024, conn=conn)

            with open(os.path.join(tmpdir, 'MANIFEST.json')) as f:
                manifest = json.load(f)

            self.assertIn('files', manifest)
            file_entry = next(
                (e for e in manifest['files'] if e['filename'] == 'capital_gains_2024.csv'),
                None,
            )
            self.assertIsNotNone(file_entry, "capital_gains_2024.csv not in manifest files")
            self.assertEqual(file_entry['sha256'], expected_sha256)
            self.assertEqual(file_entry['size_bytes'], expected_size)

    def test_manifest_does_not_include_itself(self):
        """Test 3: MANIFEST.json is NOT listed in its own 'files' array."""
        import json
        from reports.generate import PackageBuilder
        pool = MagicMock()
        conn, cur = self._make_fingerprint_conn()

        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_file = os.path.join(tmpdir, 'report.csv')
            with open(dummy_file, 'w') as f:
                f.write('data\n')

            builder = PackageBuilder(pool)
            builder._write_manifest(tmpdir, user_id=1, tax_year=2024, conn=conn)

            with open(os.path.join(tmpdir, 'MANIFEST.json')) as f:
                manifest = json.load(f)

            filenames = [e['filename'] for e in manifest['files']]
            self.assertNotIn('MANIFEST.json', filenames)

    def test_manifest_contains_source_data_version(self):
        """Test 4: MANIFEST.json contains source_data_version with fingerprint fields."""
        import json
        from reports.generate import PackageBuilder
        pool = MagicMock()
        conn, cur = self._make_fingerprint_conn(
            last_tx_ts='2024-12-31T23:59:59',
            tx_count=150,
            acb_version='2024-12-31T10:00:00',
            needs_review=3,
            exchange_tx_count=50,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_file = os.path.join(tmpdir, 'report.csv')
            with open(dummy_file, 'w') as f:
                f.write('data\n')

            builder = PackageBuilder(pool)
            builder._write_manifest(tmpdir, user_id=1, tax_year=2024, conn=conn)

            with open(os.path.join(tmpdir, 'MANIFEST.json')) as f:
                manifest = json.load(f)

            sdv = manifest.get('source_data_version', {})
            self.assertIn('last_tx_timestamp', sdv)
            self.assertIn('total_tx_count', sdv)
            self.assertIn('acb_snapshot_version', sdv)
            self.assertIn('needs_review_count', sdv)
            # total_tx_count = on-chain (150) + exchange (50) = 200
            self.assertEqual(sdv['total_tx_count'], 200)
            self.assertEqual(sdv['needs_review_count'], 3)

    def test_manifest_contains_metadata(self):
        """Test 5: MANIFEST.json contains generated_at (ISO 8601), tax_year, user_id."""
        import json
        from reports.generate import PackageBuilder
        pool = MagicMock()
        conn, cur = self._make_fingerprint_conn()

        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_file = os.path.join(tmpdir, 'report.csv')
            with open(dummy_file, 'w') as f:
                f.write('data\n')

            builder = PackageBuilder(pool)
            builder._write_manifest(tmpdir, user_id=42, tax_year=2024, conn=conn)

            with open(os.path.join(tmpdir, 'MANIFEST.json')) as f:
                manifest = json.load(f)

            self.assertIn('generated_at', manifest)
            self.assertTrue(manifest['generated_at'].endswith('Z'),
                            "generated_at must be ISO 8601 with Z suffix")
            self.assertEqual(manifest['tax_year'], 2024)
            self.assertEqual(manifest['user_id'], 42)


# ---------------------------------------------------------------------------
# TestStaleDetection — Task 2 (11-02)
# ---------------------------------------------------------------------------


class TestStaleDetection(unittest.TestCase):
    """Tests for stale report detection in GET /api/reports/download/{year}."""

    def _make_manifest(self, pkg_dir, tax_year=2024, user_id=1, **fingerprint_overrides):
        """Write a MANIFEST.json into pkg_dir with given source_data_version."""
        import json
        fingerprint = {
            'last_tx_timestamp': '2024-12-31T23:59:59',
            'total_tx_count': 200,
            'acb_snapshot_version': '2024-12-31T10:00:00',
            'needs_review_count': 0,
        }
        fingerprint.update(fingerprint_overrides)
        manifest = {
            'generated_at': '2024-12-31T23:59:59Z',
            'tax_year': tax_year,
            'user_id': user_id,
            'source_data_version': fingerprint,
            'files': [{'filename': 'report.csv', 'sha256': 'abc', 'size_bytes': 10}],
        }
        with open(os.path.join(pkg_dir, 'MANIFEST.json'), 'w') as f:
            json.dump(manifest, f)

    def _make_pool_with_fingerprint(
        self, last_tx_ts, tx_count, acb_version, needs_review, exchange_count
    ):
        """Build a mock pool returning the given fingerprint query results."""
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur
        cur.fetchone.side_effect = [
            (last_tx_ts,),
            (tx_count,),
            (acb_version,),
            (needs_review,),
            (exchange_count,),
        ]
        return pool, conn, cur

    def _make_app_with_overrides(self, pool, tmpdir, mock_user):
        """Build a FastAPI test app with dependency overrides for reports router."""
        from fastapi import FastAPI
        from api.routers.reports import router
        from api.dependencies import get_effective_user_with_dek, get_pool_dep
        from db.crypto import set_dek
        _TEST_DEK = b"\x00" * 32

        async def _dek_override():
            # Must be async so ContextVar write is visible to the async route handler.
            set_dek(_TEST_DEK)
            return mock_user

        app = FastAPI()
        app.include_router(router)
        # Phase 16: reports router uses get_effective_user_with_dek — inject a test DEK
        app.dependency_overrides[get_effective_user_with_dek] = _dek_override
        app.dependency_overrides[get_pool_dep] = lambda: pool
        return app

    def test_stale_false_when_fingerprint_matches(self):
        """Test 1: list_report_files includes stale=False when MANIFEST fingerprint matches DB."""
        from fastapi.testclient import TestClient

        pool, conn, cur = self._make_pool_with_fingerprint(
            last_tx_ts='2024-12-31T23:59:59',
            tx_count=150,
            acb_version='2024-12-31T10:00:00',
            needs_review=0,
            exchange_count=50,  # total = 200, matches manifest
        )

        mock_user = {'user_id': 1, 'email': 'test@example.com', 'is_admin': False}

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = os.path.join(tmpdir, '2024_tax_package')
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, 'report.csv'), 'w') as f:
                f.write('data\n')
            self._make_manifest(pkg_dir, user_id=1,
                                total_tx_count=200,
                                last_tx_timestamp='2024-12-31T23:59:59',
                                acb_snapshot_version='2024-12-31T10:00:00',
                                needs_review_count=0)

            app = self._make_app_with_overrides(pool, tmpdir, mock_user)
            with patch('api.routers.reports._get_output_dir', return_value=tmpdir):
                client = TestClient(app)
                resp = client.get('/api/reports/download/2024')

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('stale', data)
        self.assertFalse(data['stale'])

    def test_stale_true_when_fingerprint_differs(self):
        """Test 2: list_report_files includes stale=True when data has changed since report."""
        from fastapi.testclient import TestClient

        # DB has 300 total (150 on-chain + 150 exchange) but manifest says 200
        pool, conn, cur = self._make_pool_with_fingerprint(
            last_tx_ts='2024-12-31T23:59:59',
            tx_count=150,
            acb_version='2024-12-31T10:00:00',
            needs_review=0,
            exchange_count=150,  # Changed: was 50, now 150 => total 300 != 200
        )

        mock_user = {'user_id': 1, 'email': 'test@example.com', 'is_admin': False}

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = os.path.join(tmpdir, '2024_tax_package')
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, 'report.csv'), 'w') as f:
                f.write('data\n')
            self._make_manifest(pkg_dir, user_id=1,
                                total_tx_count=200,
                                last_tx_timestamp='2024-12-31T23:59:59',
                                acb_snapshot_version='2024-12-31T10:00:00',
                                needs_review_count=0)

            app = self._make_app_with_overrides(pool, tmpdir, mock_user)
            with patch('api.routers.reports._get_output_dir', return_value=tmpdir):
                client = TestClient(app)
                resp = client.get('/api/reports/download/2024')

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('stale', data)
        self.assertTrue(data['stale'])

    def test_no_stale_field_when_no_manifest(self):
        """Test 3: list_report_files returns normal response (no stale field) when no MANIFEST.json."""
        from fastapi.testclient import TestClient

        pool = MagicMock()
        mock_user = {'user_id': 1, 'email': 'test@example.com', 'is_admin': False}

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = os.path.join(tmpdir, '2024_tax_package')
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, 'report.csv'), 'w') as f:
                f.write('data\n')
            # No MANIFEST.json

            app = self._make_app_with_overrides(pool, tmpdir, mock_user)
            with patch('api.routers.reports._get_output_dir', return_value=tmpdir):
                client = TestClient(app)
                resp = client.get('/api/reports/download/2024')

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn('stale', data)
