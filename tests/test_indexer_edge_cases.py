"""Tests for indexer edge cases — rate limits, malformed responses, timeouts.

Covers QH-10: Production resilience when APIs misbehave.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from indexers.nearblocks_client import NearBlocksClient
from indexers.near_fetcher import parse_transaction


# ---------------------------------------------------------------------------
# NearBlocksClient edge cases
# ---------------------------------------------------------------------------


class TestNearBlocksClientEdgeCases:
    """Edge case handling for NearBlocks API client."""

    def _make_client(self):
        return NearBlocksClient(delay=0, max_retries=2)

    def test_handles_429_response(self):
        """429 rate limit triggers retry logic, eventually raises on exhaustion."""
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too Many Requests"
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)

        with patch.object(client, "session") as mock_session:
            mock_session.get.return_value = mock_resp
            with pytest.raises((RuntimeError, requests.exceptions.HTTPError)):
                client._nearblocks_request("/test")

    def test_handles_empty_response(self):
        """Empty JSON array response returns empty list without crash."""
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None

        with patch.object(client, "session") as mock_session:
            mock_session.get.return_value = mock_resp
            result = client._nearblocks_request("/test")
            assert result == []

    def test_handles_timeout(self):
        """Timeout exception triggers retry or raises."""
        client = self._make_client()

        with patch.object(client, "session") as mock_session:
            mock_session.get.side_effect = requests.exceptions.Timeout("Connection timed out")
            with pytest.raises((RuntimeError, requests.exceptions.Timeout)):
                client._nearblocks_request("/test")

    def test_handles_connection_error(self):
        """ConnectionError triggers retry or raises."""
        client = self._make_client()

        with patch.object(client, "session") as mock_session:
            mock_session.get.side_effect = requests.exceptions.ConnectionError("Connection refused")
            with pytest.raises((RuntimeError, requests.exceptions.ConnectionError)):
                client._nearblocks_request("/test")


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
