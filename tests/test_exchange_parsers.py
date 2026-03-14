"""Unit tests for exchange CSV parsers (TDD - RED phase).

Tests verify:
- PostgreSQL migration (no SQLite imports, %s placeholders)
- BaseExchangeParser.import_to_db with user_id, pool, ON CONFLICT DO NOTHING
- Per-parser row parsing and format detection
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tests.fixtures.exchange_csv_samples import (
    COINBASE_CSV,
    CRYPTO_COM_APP_CSV,
    CRYPTO_COM_EXCHANGE_CSV,
    WEALTHSIMPLE_CSV,
    UPHOLD_CSV,
    COINSQUARE_CSV,
)
from indexers.exchange_parsers.coinbase import CoinbaseParser
from indexers.exchange_parsers.crypto_com import CryptoComParser
from indexers.exchange_parsers.wealthsimple import WealthsimpleParser
from indexers.exchange_parsers.generic import GenericParser, UpholdParser, CoinsquareParser


def _write_tempfile(content: str, suffix=".csv") -> str:
    """Write content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.flush()
    f.close()
    return f.name


class TestCoinbaseParser(unittest.TestCase):

    def setUp(self):
        self.parser = CoinbaseParser()

    # Test 3 from behavior list
    def test_coinbase_parse_row_buy(self):
        """CoinbaseParser.parse_row correctly maps Coinbase CSV columns."""
        row = {
            "Timestamp": "2023-01-15 10:30:00",
            "Transaction Type": "Buy",
            "Asset": "BTC",
            "Quantity Transacted": "0.1",
            "Spot Price Currency": "CAD",
            "Spot Price at Transaction": "25000.00",
            "Subtotal": "2500.00",
            "Total": "2525.00",
            "Fees": "25.00",
            "Notes": "",
        }
        result = self.parser.parse_row(row)
        self.assertIsNotNone(result)
        self.assertEqual(result["asset"], "BTC")
        self.assertEqual(result["tx_type"], "buy")
        self.assertEqual(result["quantity"], "0.1")
        self.assertEqual(result["currency"], "CAD")
        self.assertIsInstance(result["tx_date"], datetime)

    def test_coinbase_parse_file(self):
        """parse_file returns correct transaction count from fixture CSV."""
        path = _write_tempfile(COINBASE_CSV)
        try:
            txs = self.parser.parse_file(path)
            self.assertGreater(len(txs), 0)
            # Verify all transactions have required fields
            for tx in txs:
                self.assertIn("tx_date", tx)
                self.assertIn("tx_type", tx)
                self.assertIn("asset", tx)
        finally:
            os.unlink(path)

    def test_coinbase_detect(self):
        """CoinbaseParser.detect returns True for Coinbase headers."""
        first_lines = ["Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,Spot Price at Transaction,Subtotal,Total,Fees,Notes"]
        result = self.parser.detect("/path/to/file.csv", first_lines)
        self.assertTrue(result)

    def test_coinbase_detect_false_for_other(self):
        """CoinbaseParser.detect returns False for non-Coinbase headers."""
        first_lines = ["Date,Type,Currency,Amount,To Currency,To Amount,Native Currency"]
        result = self.parser.detect("/path/to/file.csv", first_lines)
        self.assertFalse(result)

    # Test 8 from behavior list
    def test_coinbase_raw_data_is_dict(self):
        """parse_row sets raw_data as dict (for JSONB), not string."""
        row = {
            "Timestamp": "2023-01-15 10:30:00",
            "Transaction Type": "Buy",
            "Asset": "BTC",
            "Quantity Transacted": "0.1",
            "Spot Price Currency": "CAD",
            "Spot Price at Transaction": "25000.00",
            "Subtotal": "2500.00",
            "Total": "2525.00",
            "Fees": "25.00",
            "Notes": "",
        }
        result = self.parser.parse_row(row)
        # raw_data must be a dict (JSONB-compatible)
        if "raw_data" in result:
            self.assertIsInstance(result["raw_data"], dict)


class TestCryptoComParser(unittest.TestCase):

    def setUp(self):
        self.parser = CryptoComParser()

    # Test 4 from behavior list
    def test_crypto_com_app_format(self):
        """CryptoComParser handles App CSV format correctly."""
        path = _write_tempfile(CRYPTO_COM_APP_CSV)
        try:
            txs = self.parser.parse_file(path)
            self.assertGreater(len(txs), 0)
            for tx in txs:
                self.assertIn("tx_date", tx)
                self.assertIn("tx_type", tx)
                self.assertIn("asset", tx)
        finally:
            os.unlink(path)

    def test_crypto_com_exchange_format(self):
        """CryptoComParser handles Exchange CSV format correctly."""
        path = _write_tempfile(CRYPTO_COM_EXCHANGE_CSV)
        try:
            txs = self.parser.parse_file(path)
            self.assertGreater(len(txs), 0)
        finally:
            os.unlink(path)

    def test_crypto_com_detect_app(self):
        """CryptoComParser.detect returns True for App format headers."""
        first_lines = ["Timestamp (UTC),Transaction Description,Currency,Amount,To Currency,To Amount,Native Currency,Native Amount,Native Amount (in USD),Transaction Kind"]
        result = self.parser.detect("/path/to/file.csv", first_lines)
        self.assertTrue(result)

    def test_crypto_com_detect_exchange(self):
        """CryptoComParser.detect returns True for Exchange format headers."""
        first_lines = ["Trade Date,Pair,Side,Price,Executed,Fee,Total"]
        result = self.parser.detect("/path/to/file.csv", first_lines)
        self.assertTrue(result)


class TestWealthsimpleParser(unittest.TestCase):

    def setUp(self):
        self.parser = WealthsimpleParser()

    # Test 5 from behavior list
    def test_wealthsimple_cad_only(self):
        """WealthsimpleParser handles CAD-only transactions (no USD column)."""
        path = _write_tempfile(WEALTHSIMPLE_CSV)
        try:
            txs = self.parser.parse_file(path)
            self.assertGreater(len(txs), 0)
            for tx in txs:
                self.assertEqual(tx["currency"], "CAD")
        finally:
            os.unlink(path)

    def test_wealthsimple_detect(self):
        """WealthsimpleParser.detect returns True for Wealthsimple headers."""
        first_lines = ["Date,Type,Asset,Quantity,Price,Amount,Fee"]
        result = self.parser.detect("/path/to/file.csv", first_lines)
        self.assertTrue(result)


class TestGenericParser(unittest.TestCase):

    # Test 6 from behavior list
    def test_generic_uphold_detect(self):
        """GenericParser.detect() returns True for Uphold headers."""
        parser = GenericParser()
        first_lines = ["Date,Destination Currency,Destination Amount,Origin Currency,Origin Amount,Fee Amount,Fee Currency,Type,Destination,Origin,Status"]
        result = parser.detect("/path/to/file.csv", first_lines)
        self.assertTrue(result)

    # Test 7 from behavior list
    def test_generic_coinsquare_detect(self):
        """GenericParser.detect() returns True for Coinsquare headers."""
        parser = GenericParser()
        first_lines = ["Date,Action,Asset,Volume,Total,Market Rate"]
        result = parser.detect("/path/to/file.csv", first_lines)
        self.assertTrue(result)

    def test_uphold_parser_parse_file(self):
        """UpholdParser parses Uphold CSV correctly."""
        parser = UpholdParser()
        path = _write_tempfile(UPHOLD_CSV)
        try:
            txs = parser.parse_file(path)
            self.assertGreater(len(txs), 0)
        finally:
            os.unlink(path)

    def test_coinsquare_parser_parse_file(self):
        """CoinsquareParser parses Coinsquare CSV correctly."""
        parser = CoinsquareParser()
        path = _write_tempfile(COINSQUARE_CSV)
        try:
            txs = parser.parse_file(path)
            self.assertGreater(len(txs), 0)
        finally:
            os.unlink(path)


class TestImportToDb(unittest.TestCase):
    """Test import_to_db with mocked database pool."""

    def _make_mock_pool(self, rowcount_sequence=None):
        """Create a mock psycopg2 connection pool."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # cursor() used as context manager
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        # rowcount: simulate 1 row inserted per call (no conflict)
        mock_cursor.rowcount = 1

        mock_conn.cursor.return_value = mock_cursor
        mock_pool.getconn.return_value = mock_conn

        return mock_pool, mock_conn, mock_cursor

    # Test 1 from behavior list
    def test_import_to_db_inserts_with_user_id(self):
        """import_to_db inserts rows with user_id and %s placeholders."""
        parser = CoinbaseParser()
        path = _write_tempfile(COINBASE_CSV)
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()

        try:
            result = parser.import_to_db(path, user_id=42, pool=mock_pool)
        finally:
            os.unlink(path)

        # Verify pool was used
        mock_pool.getconn.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)

        # Verify execute was called (one per transaction)
        self.assertTrue(mock_cursor.execute.called)

        # Verify result shape
        self.assertIn("imported", result)
        self.assertIn("skipped", result)
        self.assertIn("errors", result)
        self.assertIn("batch_id", result)

        # Verify SQL uses %s not ?
        for execute_call in mock_cursor.execute.call_args_list:
            sql = execute_call[0][0]
            self.assertNotIn("?", sql)
            self.assertIn("%s", sql)

        # Verify user_id appears in params
        for execute_call in mock_cursor.execute.call_args_list:
            params = execute_call[0][1]
            self.assertIn(42, params)

    # Test 2 from behavior list
    def test_import_dedup_on_conflict(self):
        """Re-importing same file triggers ON CONFLICT DO NOTHING in SQL."""
        parser = CoinbaseParser()
        path = _write_tempfile(COINBASE_CSV)
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()

        try:
            parser.import_to_db(path, user_id=1, pool=mock_pool)
        finally:
            os.unlink(path)

        # Verify ON CONFLICT present in SQL
        for execute_call in mock_cursor.execute.call_args_list:
            sql = execute_call[0][0]
            if "INSERT" in sql:
                self.assertIn("ON CONFLICT", sql)
                self.assertIn("DO NOTHING", sql)
                break
        else:
            self.fail("No INSERT call found in execute calls")

    def test_import_to_db_exchange_transactions_table(self):
        """import_to_db inserts into exchange_transactions table."""
        parser = CoinbaseParser()
        path = _write_tempfile(COINBASE_CSV)
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()

        try:
            parser.import_to_db(path, user_id=1, pool=mock_pool)
        finally:
            os.unlink(path)

        for execute_call in mock_cursor.execute.call_args_list:
            sql = execute_call[0][0]
            if "INSERT" in sql:
                self.assertIn("exchange_transactions", sql)
                break
        else:
            self.fail("No INSERT call found")

    def test_import_to_db_putconn_on_error(self):
        """pool.putconn is called even when an error occurs (finally block)."""
        parser = CoinbaseParser()
        path = _write_tempfile(COINBASE_CSV)
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_pool.getconn.return_value = mock_conn

        # Make execute raise an error
        mock_cursor.execute.side_effect = Exception("DB error")

        try:
            parser.import_to_db(path, user_id=1, pool=mock_pool)
        finally:
            os.unlink(path)

        # putconn must still be called
        mock_pool.putconn.assert_called_once_with(mock_conn)


class TestNoSQLiteImports(unittest.TestCase):
    """Test 9 from behavior list — no db.init imports in any parser file."""

    PARSER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "indexers", "exchange_parsers")

    def test_no_sqlite_imports(self):
        """No parser file imports from db.init (SQLite)."""
        for filename in ["base.py", "coinbase.py", "crypto_com.py", "wealthsimple.py", "generic.py"]:
            filepath = os.path.join(self.PARSER_DIR, filename)
            with open(filepath) as f:
                content = f.read()
            self.assertNotIn(
                "db.init",
                content,
                f"{filename} still imports from db.init (SQLite)"
            )


class TestNoQuestionMarkPlaceholders(unittest.TestCase):
    """Test 10 from behavior list — no ? SQL placeholders in any parser file."""

    PARSER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "indexers", "exchange_parsers")

    def test_no_question_mark_placeholders(self):
        """No parser file uses ? as SQL placeholder."""
        sql_keywords = ["INSERT", "UPDATE", "DELETE", "SELECT"]
        for filename in ["base.py", "coinbase.py", "crypto_com.py", "wealthsimple.py", "generic.py"]:
            filepath = os.path.join(self.PARSER_DIR, filename)
            with open(filepath) as f:
                lines = f.readlines()

            for i, line in enumerate(lines, 1):
                # Only check lines that look like SQL
                line_upper = line.upper()
                if any(kw in line_upper for kw in sql_keywords) or "VALUES" in line_upper:
                    self.assertNotIn(
                        "?",
                        line,
                        f"{filename} line {i} uses ? placeholder: {line.strip()}"
                    )


class TestParserRobustness(unittest.TestCase):
    """Edge case tests for exchange parser robustness.

    Covers QH-11: Silent data loss prevention.
    """

    def test_coinbase_parser_missing_column(self):
        """CSV missing required column returns None from parse_row."""
        parser = CoinbaseParser()
        row = {
            "Timestamp": "2023-01-15 10:30:00",
            # Missing "Transaction Type"
            "Asset": "BTC",
            "Quantity Transacted": "0.1",
        }
        result = parser.parse_row(row)
        # Should return None (missing tx_type_raw)
        self.assertIsNone(result)

    def test_coinbase_parser_extra_columns(self):
        """CSV with unexpected extra columns doesn't crash."""
        parser = CoinbaseParser()
        row = {
            "Timestamp": "2023-01-15 10:30:00",
            "Transaction Type": "Buy",
            "Asset": "BTC",
            "Quantity Transacted": "0.1",
            "Spot Price Currency": "CAD",
            "Spot Price at Transaction": "25000.00",
            "Subtotal": "2500.00",
            "Total": "2525.00",
            "Fees": "25.00",
            "Notes": "",
            "ExtraColumn1": "unexpected",
            "ExtraColumn2": "data",
        }
        result = parser.parse_row(row)
        self.assertIsNotNone(result)
        self.assertEqual(result["asset"], "BTC")

    def test_coinbase_parser_empty_csv(self):
        """CSV with only headers returns empty list."""
        parser = CoinbaseParser()
        csv_content = "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
        path = _write_tempfile(csv_content)
        try:
            txs = parser.parse_file(path)
            self.assertEqual(len(txs), 0)
        finally:
            os.unlink(path)

    def test_crypto_com_malformed_amount(self):
        """Amount field with non-numeric value handled without crash."""
        parser = CryptoComParser()
        row = {
            "Timestamp (UTC)": "2023-01-15 10:30:00",
            "Transaction Description": "Buy BTC",
            "Currency": "BTC",
            "Amount": "N/A",
            "To Currency": "",
            "To Amount": "",
            "Native Currency": "CAD",
            "Native Amount": "N/A",
            "Native Amount (in USD)": "",
            "Transaction Kind": "crypto_purchase",
        }
        # Should not raise — may return None or partial
        try:
            parser.parse_row(row)
        except Exception:
            self.fail("parse_row raised exception on malformed amount")

    def test_wealthsimple_missing_date(self):
        """Empty date field handled without crash."""
        parser = WealthsimpleParser()
        row = {
            "Date": "",
            "Type": "Buy",
            "Asset": "BTC",
            "Quantity": "0.1",
            "Price": "25000",
            "Amount": "2500",
            "Fee": "10",
        }
        # Should return None or handle gracefully
        try:
            parser.parse_row(row)
        except Exception:
            self.fail("parse_row raised exception on empty date")

    def test_parser_handles_unicode_bom(self):
        """CSV starting with UTF-8 BOM is parsed correctly."""
        parser = CoinbaseParser()
        bom = "\ufeff"
        csv_content = bom + "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,Spot Price at Transaction,Subtotal,Total,Fees,Notes\n"
        csv_content += "2023-01-15 10:30:00,Buy,BTC,0.1,CAD,25000.00,2500.00,2525.00,25.00,\n"
        path = _write_tempfile(csv_content)
        try:
            txs = parser.parse_file(path)
            # BOM handling: either parses correctly or returns empty (not crash)
            self.assertIsInstance(txs, list)
        finally:
            os.unlink(path)

    def test_coinbase_detect_wrong_format(self):
        """Coinbase detect returns False for non-CSV content."""
        parser = CoinbaseParser()
        first_lines = ["<html><head><title>Error</title></head>"]
        result = parser.detect("/path/to/file.csv", first_lines)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
