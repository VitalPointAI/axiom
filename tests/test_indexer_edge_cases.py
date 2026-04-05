"""Tests for indexer edge cases — retries, malformed responses, timeouts.

Covers QH-10: Production resilience when APIs misbehave.
"""

from unittest.mock import MagicMock, patch

import requests

from indexers.neardata_client import NeardataClient
from indexers.near_fetcher import parse_transaction


# ---------------------------------------------------------------------------
# NeardataClient edge cases
# ---------------------------------------------------------------------------


class TestNeardataClientEdgeCases:
    """Edge case handling for neardata.xyz client."""

    def _make_client(self):
        return NeardataClient()

    def test_handles_null_block_response(self):
        """Block returning 'null' text is treated as missing."""
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "null"

        with patch.object(client, "session") as mock_session:
            mock_session.get.return_value = mock_resp
            result = client.fetch_block(100)
            assert result is None

    def test_handles_server_error_with_retry(self):
        """500 errors trigger retries, return None on exhaustion."""
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch.object(client, "session") as mock_session:
            mock_session.get.return_value = mock_resp
            with patch("indexers.neardata_client.time.sleep"):
                result = client.fetch_block(100)
        assert result is None

    def test_handles_timeout(self):
        """Timeout exception triggers retry, returns None on exhaustion."""
        client = self._make_client()

        with patch.object(client, "session") as mock_session:
            mock_session.get.side_effect = requests.exceptions.Timeout("timed out")
            with patch("indexers.neardata_client.time.sleep"):
                result = client.fetch_block(100)
        assert result is None

    def test_extract_deduplicates_by_hash(self):
        """Same tx_hash appearing in multiple shards is only returned once."""
        client = self._make_client()
        block = {
            "block": {"header": {"height": 100, "timestamp": 1700000000000000000}},
            "shards": [
                {"chunk": {
                    "transactions": [{
                        "transaction": {
                            "hash": "TX_DUP", "signer_id": "alice.near",
                            "receiver_id": "bob.near", "actions": [],
                        },
                        "outcome": {},
                    }],
                    "receipt_execution_outcomes": [],
                }},
                {"chunk": {
                    "transactions": [{
                        "transaction": {
                            "hash": "TX_DUP", "signer_id": "alice.near",
                            "receiver_id": "charlie.near", "actions": [],
                        },
                        "outcome": {},
                    }],
                    "receipt_execution_outcomes": [],
                }},
            ],
        }
        results = client.extract_wallet_txs(block, "alice.near")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# parse_transaction edge cases
# ---------------------------------------------------------------------------


class TestParseTransactionEdgeCases:
    """Edge cases in NEAR transaction parsing."""

    def test_handles_missing_fields(self):
        """Transaction missing expected fields returns None (skip, no crash)."""
        raw_tx = {}  # completely empty
        result = parse_transaction(raw_tx, wallet_id=1, user_id=1, account_id="test.near")
        # Should return None or a dict — must not raise
        assert result is None or isinstance(result, dict)

    def test_handles_missing_block_timestamp(self):
        """Transaction with hash but no block_timestamp is handled gracefully."""
        raw_tx = {
            "transaction_hash": "abc123",
            "receipt_id": "r1",
            "predecessor_account_id": "alice.near",
            "receiver_account_id": "bob.near",
            # no block_timestamp
        }
        result = parse_transaction(raw_tx, wallet_id=1, user_id=1, account_id="alice.near")
        assert result is None or isinstance(result, dict)

    def test_handles_none_amount(self):
        """Transaction with None amount fields doesn't crash."""
        raw_tx = {
            "transaction_hash": "abc123",
            "receipt_id": "r1",
            "predecessor_account_id": "alice.near",
            "receiver_account_id": "bob.near",
            "block_timestamp": "1700000000000000000",
            "actions_agg": None,
            "outcomes_agg": None,
        }
        result = parse_transaction(raw_tx, wallet_id=1, user_id=1, account_id="alice.near")
        assert result is None or isinstance(result, dict)
