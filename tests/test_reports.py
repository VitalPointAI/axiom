"""
Unit tests for reports package — ReportEngine, CapitalGainsReport, IncomeReport.

Test classes:
  - TestReportGate: gate check logic (needs_review blocking, specialist override)
  - TestHelpers: fiscal_year_range, fmt_cad, fmt_units
  - TestCapitalGainsReport: chronological CSV, grouped CSV, summary dict
  - TestIncomeReport: detail CSV, monthly CSV, summary dict
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
        Subsequent fetchall() returns the disposal rows.
        """
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        pool.getconn.return_value = conn
        conn.cursor.return_value = cur

        # Gate fetchone side_effect: (cgl_count,), (acb_count,)
        # Then fetchall for the disposal query
        cur.fetchone.side_effect = [(gate_cgl,), (gate_acb,)]
        cur.fetchall.return_value = rows or []
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


if __name__ == '__main__':
    unittest.main()
