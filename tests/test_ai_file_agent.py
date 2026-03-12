"""Unit tests for AI file ingestion agent.

Tests verify:
- Claude API response parsing and transaction extraction
- Confidence threshold flagging (needs_review)
- File reading for CSV, XLSX formats
- tx_id generation when absent from AI response
- source='ai_agent' for all AI-extracted transactions
- Graceful handling of invalid/malformed JSON from Claude

All tests use unittest.mock — NO real API calls or DB connections are made.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from indexers.ai_file_agent import AIFileAgent, CONFIDENCE_THRESHOLD


def _make_mock_pool():
    """Return a mock psycopg2 connection pool with cursor support."""
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1  # Default: row was inserted (not skipped)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    return mock_pool, mock_conn, mock_cursor


def _make_agent(pool=None):
    """Create an AIFileAgent with a mock pool."""
    if pool is None:
        pool, _, _ = _make_mock_pool()
    return AIFileAgent(pool)


def _make_claude_response(content_text: str):
    """Create a mock Anthropic messages.create() response object."""
    mock_content = MagicMock()
    mock_content.text = content_text
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


SAMPLE_TRANSACTIONS = [
    {
        "tx_id": "TXN-001",
        "tx_date": "2024-01-15T10:30:00",
        "tx_type": "buy",
        "asset": "BTC",
        "quantity": "0.5",
        "price_per_unit": "45000.00",
        "total_value": "22500.00",
        "fee": "5.00",
        "fee_asset": "USD",
        "currency": "USD",
        "notes": "Market order",
        "confidence": 0.95,
    },
    {
        "tx_id": "TXN-002",
        "tx_date": "2024-01-16T14:00:00",
        "tx_type": "sell",
        "asset": "ETH",
        "quantity": "2.0",
        "price_per_unit": "3000.00",
        "total_value": "6000.00",
        "fee": None,
        "fee_asset": None,
        "currency": "USD",
        "notes": None,
        "confidence": 0.90,
    },
    {
        "tx_id": "TXN-003",
        "tx_date": "2024-01-17T09:00:00",
        "tx_type": "deposit",
        "asset": "USDC",
        "quantity": "1000.00",
        "price_per_unit": None,
        "total_value": None,
        "fee": None,
        "fee_asset": None,
        "currency": "USD",
        "notes": "Bank deposit",
        "confidence": 0.88,
    },
]


class TestExtractTransactionsParsesResponse(unittest.TestCase):
    """test_extract_transactions_parses_response: Mock Claude returning valid JSON with 3 txs."""

    def test_extracts_all_transactions(self):
        """Agent correctly parses a 3-transaction Claude response."""
        agent = _make_agent()

        claude_json = json.dumps({
            "exchange": "TestExchange",
            "transactions": SAMPLE_TRANSACTIONS,
        })
        mock_response = _make_claude_response(claude_json)

        with patch.object(type(agent), "client", new_callable=PropertyMock) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_prop.return_value = mock_client

            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                transactions, exchange = agent._extract_transactions("file content", "test.csv")

        self.assertEqual(len(transactions), 3)
        self.assertEqual(exchange, "TestExchange")
        self.assertEqual(transactions[0]["tx_id"], "TXN-001")
        self.assertEqual(transactions[1]["asset"], "ETH")
        self.assertEqual(transactions[2]["tx_type"], "deposit")

    def test_uses_correct_model(self):
        """Agent calls Claude with the expected model identifier."""
        agent = _make_agent()

        claude_json = json.dumps({"exchange": "X", "transactions": []})
        mock_response = _make_claude_response(claude_json)

        with patch.object(type(agent), "client", new_callable=PropertyMock) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_prop.return_value = mock_client

            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                agent._extract_transactions("content", "file.csv")

            call_kwargs = mock_client.messages.create.call_args
            self.assertEqual(call_kwargs.kwargs["model"], "claude-sonnet-4-20250514")


class TestConfidenceThresholdFlagging(unittest.TestCase):
    """test_confidence_threshold_flagging: Verify needs_review is set correctly."""

    def test_threshold_is_0_8(self):
        """CONFIDENCE_THRESHOLD is 0.8."""
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.8)

    def test_flagging_logic(self):
        """Transactions at 0.95 pass; 0.75 and 0.50 get needs_review=True."""
        transactions = [
            {"tx_id": "A", "tx_date": "2024-01-01T00:00:00", "tx_type": "buy",
             "asset": "BTC", "quantity": "1", "confidence": 0.95,
             "currency": "USD", "price_per_unit": None, "total_value": None,
             "fee": None, "fee_asset": None, "notes": None},
            {"tx_id": "B", "tx_date": "2024-01-01T00:00:00", "tx_type": "sell",
             "asset": "ETH", "quantity": "1", "confidence": 0.75,
             "currency": "USD", "price_per_unit": None, "total_value": None,
             "fee": None, "fee_asset": None, "notes": None},
            {"tx_id": "C", "tx_date": "2024-01-01T00:00:00", "tx_type": "deposit",
             "asset": "USDC", "quantity": "100", "confidence": 0.50,
             "currency": "USD", "price_per_unit": None, "total_value": None,
             "fee": None, "fee_asset": None, "notes": None},
        ]

        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        agent = _make_agent(mock_pool)

        agent._insert_transactions(transactions, user_id=1, exchange="TestEx", file_import_id=99)

        # Collect all calls to cur.execute
        execute_calls = mock_cursor.execute.call_args_list
        # Filter to INSERT calls only
        insert_calls = [c for c in execute_calls if "INSERT INTO exchange_transactions" in str(c)]

        self.assertEqual(len(insert_calls), 3)

        # Extract needs_review from each INSERT call's params (index 17 in VALUES tuple)
        insert_params_list = [c.args[1] for c in insert_calls]

        # confidence_score is at index 16 (0-based), needs_review at index 17
        confidence_scores = [p[16] for p in insert_params_list]
        needs_review_flags = [p[17] for p in insert_params_list]

        self.assertEqual(confidence_scores[0], 0.95)
        self.assertFalse(needs_review_flags[0], "0.95 >= threshold, should NOT be flagged")

        self.assertEqual(confidence_scores[1], 0.75)
        self.assertTrue(needs_review_flags[1], "0.75 < threshold, should be flagged")

        self.assertEqual(confidence_scores[2], 0.50)
        self.assertTrue(needs_review_flags[2], "0.50 < threshold, should be flagged")

    def test_flagged_count_in_result(self):
        """_insert_transactions returns correct flagged count."""
        transactions = [
            {"tx_id": "A", "confidence": 0.95, "tx_type": "buy", "asset": "BTC",
             "quantity": "1", "tx_date": "2024-01-01T00:00:00", "currency": "USD",
             "price_per_unit": None, "total_value": None, "fee": None, "fee_asset": None, "notes": None},
            {"tx_id": "B", "confidence": 0.70, "tx_type": "sell", "asset": "ETH",
             "quantity": "1", "tx_date": "2024-01-01T00:00:00", "currency": "USD",
             "price_per_unit": None, "total_value": None, "fee": None, "fee_asset": None, "notes": None},
            {"tx_id": "C", "confidence": 0.60, "tx_type": "deposit", "asset": "USDC",
             "quantity": "100", "tx_date": "2024-01-01T00:00:00", "currency": "USD",
             "price_per_unit": None, "total_value": None, "fee": None, "fee_asset": None, "notes": None},
        ]

        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        agent = _make_agent(mock_pool)

        result = agent._insert_transactions(transactions, user_id=1, exchange="X", file_import_id=1)
        self.assertEqual(result["flagged"], 2)


class TestReadCsvContent(unittest.TestCase):
    """test_read_csv_content: Verify CSV file reading works correctly."""

    def test_reads_csv_text(self):
        """_read_file_content returns correct text from a CSV file."""
        csv_content = "Date,Type,Asset,Amount\n2024-01-01,buy,BTC,0.5\n2024-01-02,sell,ETH,1.0\n"
        agent = _make_agent()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            tmppath = f.name

        try:
            content = agent._read_file_content(tmppath)
            self.assertEqual(content, csv_content)
        finally:
            os.unlink(tmppath)

    def test_handles_bom_encoding(self):
        """_read_file_content handles UTF-8 BOM (common in Excel CSV exports)."""
        csv_content = "Date,Type\n2024-01-01,buy\n"
        agent = _make_agent()

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            # Write with BOM
            f.write(b"\xef\xbb\xbf" + csv_content.encode("utf-8"))
            tmppath = f.name

        try:
            content = agent._read_file_content(tmppath)
            # BOM should be stripped (utf-8-sig encoding)
            self.assertFalse(content.startswith("\ufeff"), "BOM should be stripped")
            self.assertIn("Date,Type", content)
        finally:
            os.unlink(tmppath)

    def test_truncates_large_files(self):
        """_read_file_content truncates files larger than 50,000 characters."""
        agent = _make_agent()
        large_content = "a" * 100_000

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(large_content)
            tmppath = f.name

        try:
            content = agent._read_file_content(tmppath)
            self.assertEqual(len(content), 50_000)
        finally:
            os.unlink(tmppath)


class TestReadXlsxContent(unittest.TestCase):
    """test_read_xlsx_content: Verify XLSX file reading using openpyxl."""

    def test_reads_xlsx_to_csv_text(self):
        """_read_file_content converts XLSX first sheet to CSV-like text."""
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl not installed")

        agent = _make_agent()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Date", "Type", "Asset", "Amount"])
        ws.append(["2024-01-01", "buy", "BTC", "0.5"])
        ws.append(["2024-01-02", "sell", "ETH", "1.0"])

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            tmppath = f.name

        wb.save(tmppath)

        try:
            content = agent._read_file_content(tmppath)
            self.assertIn("Date", content)
            self.assertIn("BTC", content)
            self.assertIn("ETH", content)
            # Should have newlines separating rows
            lines = content.strip().split("\n")
            self.assertEqual(len(lines), 3)
        finally:
            os.unlink(tmppath)

    def test_xlsx_import_error_raises(self):
        """_read_file_content raises ImportError with helpful message if openpyxl missing."""
        agent = _make_agent()

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            tmppath = f.name

        try:
            with patch.dict("sys.modules", {"openpyxl": None}):
                with self.assertRaises((ImportError, TypeError)):
                    agent._read_file_content(tmppath)
        finally:
            os.unlink(tmppath)


class TestTxIdGeneration(unittest.TestCase):
    """test_tx_id_generation: Verify AI-generated tx_id when absent from Claude response."""

    def test_generates_tx_id_when_absent(self):
        """Transactions with no tx_id get ai_{file_import_id}_{index} as tx_id."""
        transactions = [
            {"tx_date": "2024-01-01T00:00:00", "tx_type": "buy", "asset": "BTC",
             "quantity": "1", "confidence": 0.95, "currency": "USD",
             "price_per_unit": None, "total_value": None, "fee": None, "fee_asset": None, "notes": None},
            {"tx_date": "2024-01-02T00:00:00", "tx_type": "sell", "asset": "ETH",
             "quantity": "2", "confidence": 0.90, "currency": "USD",
             "price_per_unit": None, "total_value": None, "fee": None, "fee_asset": None, "notes": None},
        ]
        # Note: no "tx_id" key in any transaction above

        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        agent = _make_agent(mock_pool)
        file_import_id = 42

        agent._insert_transactions(transactions, user_id=1, exchange="X", file_import_id=file_import_id)

        execute_calls = mock_cursor.execute.call_args_list
        insert_calls = [c for c in execute_calls if "INSERT INTO exchange_transactions" in str(c)]

        tx_ids = [c.args[1][2] for c in insert_calls]  # tx_id is 3rd param (index 2)

        self.assertEqual(tx_ids[0], f"ai_{file_import_id}_0")
        self.assertEqual(tx_ids[1], f"ai_{file_import_id}_1")

    def test_preserves_existing_tx_id(self):
        """Transactions with an existing tx_id keep it."""
        transactions = [
            {"tx_id": "EXISTING-ID-123", "tx_date": "2024-01-01T00:00:00",
             "tx_type": "buy", "asset": "BTC", "quantity": "1", "confidence": 0.95,
             "currency": "USD", "price_per_unit": None, "total_value": None,
             "fee": None, "fee_asset": None, "notes": None},
        ]

        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        agent = _make_agent(mock_pool)

        agent._insert_transactions(transactions, user_id=1, exchange="X", file_import_id=1)

        execute_calls = mock_cursor.execute.call_args_list
        insert_calls = [c for c in execute_calls if "INSERT INTO exchange_transactions" in str(c)]

        tx_id = insert_calls[0].args[1][2]
        self.assertEqual(tx_id, "EXISTING-ID-123")


class TestSourceField(unittest.TestCase):
    """test_source_field: Verify all inserted transactions have source='ai_agent'."""

    def test_source_is_ai_agent(self):
        """Every transaction inserted by AIFileAgent has source='ai_agent'."""
        transactions = [
            {"tx_id": f"TX-{i}", "tx_date": "2024-01-01T00:00:00", "tx_type": "buy",
             "asset": "BTC", "quantity": "1", "confidence": 0.95, "currency": "USD",
             "price_per_unit": None, "total_value": None, "fee": None, "fee_asset": None, "notes": None}
            for i in range(5)
        ]

        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        agent = _make_agent(mock_pool)

        agent._insert_transactions(transactions, user_id=1, exchange="TestEx", file_import_id=7)

        execute_calls = mock_cursor.execute.call_args_list
        insert_calls = [c for c in execute_calls if "INSERT INTO exchange_transactions" in str(c)]

        self.assertEqual(len(insert_calls), 5)

        # source is at index 15 in the VALUES tuple (0-based)
        sources = [c.args[1][15] for c in insert_calls]
        for source in sources:
            self.assertEqual(source, "ai_agent", f"Expected 'ai_agent', got '{source}'")


class TestInvalidJsonHandling(unittest.TestCase):
    """test_invalid_json_handling: Verify graceful handling of malformed Claude responses."""

    def test_returns_empty_on_pure_garbage(self):
        """_parse_json_response returns empty result for completely invalid input."""
        agent = _make_agent()
        result = agent._parse_json_response("This is not JSON at all!!!")
        self.assertEqual(result["transactions"], [])
        self.assertEqual(result["exchange"], "unknown")

    def test_extracts_json_from_markdown_block(self):
        """_parse_json_response can extract JSON from a markdown code block."""
        agent = _make_agent()
        raw_text = (
            'Here is the extracted data:\n'
            '```json\n'
            '{"exchange": "Binance", "transactions": [{"tx_id": "X1"}]}\n'
            '```\n'
            'Hope this helps!'
        )
        result = agent._parse_json_response(raw_text)
        self.assertEqual(result["exchange"], "Binance")
        self.assertEqual(len(result["transactions"]), 1)

    def test_extract_transactions_handles_invalid_response_gracefully(self):
        """_extract_transactions does not crash on invalid JSON from Claude."""
        agent = _make_agent()
        mock_response = _make_claude_response("INVALID JSON GARBAGE !!!@#$")

        with patch.object(type(agent), "client", new_callable=PropertyMock) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_prop.return_value = mock_client

            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                # Should not raise
                transactions, exchange = agent._extract_transactions("content", "bad.csv")

        self.assertEqual(transactions, [])
        self.assertEqual(exchange, "unknown")

    def test_missing_api_key_raises_environment_error(self):
        """_extract_transactions raises EnvironmentError if ANTHROPIC_API_KEY not set."""
        agent = _make_agent()

        env_without_key = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            with self.assertRaises(EnvironmentError):
                agent._extract_transactions("content", "file.csv")


if __name__ == "__main__":
    unittest.main()
