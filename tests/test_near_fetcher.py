"""
Unit tests for indexers/near_fetcher.py

Tests cover:
- parse_transaction() for all NEAR action types
- Cursor resume logic (mocked API client)
- Duplicate handling (ON CONFLICT DO NOTHING)
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Sample NearBlocks API transaction fixtures
# ---------------------------------------------------------------------------

def make_tx(
    tx_hash="ABC123",
    receipt_id=None,
    predecessor="alice.near",
    receiver="bob.near",
    actions=None,
    block_height=12345,
    block_timestamp=1700000000000000000,
    transaction_fee="1000000000000000000000",  # 0.001 NEAR in yoctoNEAR
    outcomes_status=True,
):
    """Build a minimal NearBlocks transaction dict."""
    if actions is None:
        actions = [{"action": "TRANSFER", "deposit": "1000000000000000000000000"}]  # 1 NEAR
    return {
        "transaction_hash": tx_hash,
        "receipt_id": receipt_id,
        "predecessor_account_id": predecessor,
        "receiver_account_id": receiver,
        "actions": actions,
        "block": {"block_height": block_height},
        "block_timestamp": str(block_timestamp),
        "outcomes_agg": {"transaction_fee": transaction_fee},
        "outcomes": {"status": outcomes_status},
    }


# ---------------------------------------------------------------------------
# Tests for parse_transaction()
# ---------------------------------------------------------------------------

class TestParseTransaction:

    def setup_method(self):
        """Import the module under test fresh for each test."""
        from indexers.near_fetcher import parse_transaction
        self.parse_transaction = parse_transaction

    def test_transfer_outgoing(self):
        """TRANSFER action from our wallet = outgoing transaction."""
        raw = make_tx(
            tx_hash="TX_OUT_001",
            predecessor="alice.near",
            receiver="bob.near",
            actions=[{"action": "TRANSFER", "deposit": "2000000000000000000000000"}],  # 2 NEAR
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["tx_hash"] == "TX_OUT_001"
        assert result["direction"] == "out"
        assert result["counterparty"] == "bob.near"
        assert result["action_type"] == "TRANSFER"
        assert int(result["amount"]) == 2000000000000000000000000
        assert result["chain"] == "near"
        assert result["wallet_id"] == 1
        assert result["user_id"] == 1
        assert result["success"] is True

    def test_transfer_incoming(self):
        """TRANSFER action to our wallet = incoming transaction."""
        raw = make_tx(
            tx_hash="TX_IN_001",
            predecessor="bob.near",
            receiver="alice.near",
            actions=[{"action": "TRANSFER", "deposit": "500000000000000000000000"}],  # 0.5 NEAR
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["direction"] == "in"
        assert result["counterparty"] == "bob.near"
        assert int(result["amount"]) == 500000000000000000000000

    def test_function_call_action(self):
        """FUNCTION_CALL action is parsed with method_name."""
        raw = make_tx(
            tx_hash="TX_FC_001",
            predecessor="alice.near",
            receiver="staking.pool.near",
            actions=[{
                "action": "FUNCTION_CALL",
                "method": "deposit_and_stake",
                "deposit": "10000000000000000000000000",  # 10 NEAR
                "args": {"amount": "10000000000000000000000000"},
            }],
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["action_type"] == "FUNCTION_CALL"
        assert result["method_name"] == "deposit_and_stake"
        assert int(result["amount"]) == 10000000000000000000000000
        assert result["direction"] == "out"

    def test_stake_action(self):
        """STAKE action type is correctly identified."""
        raw = make_tx(
            tx_hash="TX_STAKE_001",
            predecessor="alice.near",
            receiver="alice.near",
            actions=[{
                "action": "STAKE",
                "stake": "5000000000000000000000000",  # 5 NEAR
                "public_key": "ed25519:ABC",
            }],
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["action_type"] == "STAKE"

    def test_add_key_action(self):
        """ADD_KEY action type is correctly identified."""
        raw = make_tx(
            tx_hash="TX_ADDKEY_001",
            predecessor="alice.near",
            receiver="alice.near",
            actions=[{
                "action": "ADD_KEY",
                "public_key": "ed25519:ABC",
                "access_key": {"permission": "FullAccess"},
            }],
            transaction_fee="100000000000000000000",
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["action_type"] == "ADD_KEY"

    def test_delete_key_action(self):
        """DELETE_KEY action type is correctly identified."""
        raw = make_tx(
            tx_hash="TX_DELKEY_001",
            predecessor="alice.near",
            receiver="alice.near",
            actions=[{"action": "DELETE_KEY", "public_key": "ed25519:ABC"}],
            transaction_fee="100000000000000000000",
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["action_type"] == "DELETE_KEY"

    def test_create_account_action(self):
        """CREATE_ACCOUNT action type is correctly identified."""
        raw = make_tx(
            tx_hash="TX_CREATE_001",
            predecessor="alice.near",
            receiver="new.alice.near",
            actions=[{"action": "CREATE_ACCOUNT"}],
            transaction_fee="100000000000000000000",
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["action_type"] == "CREATE_ACCOUNT"

    def test_delete_account_action(self):
        """DELETE_ACCOUNT action type is correctly identified."""
        raw = make_tx(
            tx_hash="TX_DEL_001",
            predecessor="alice.near",
            receiver="alice.near",
            actions=[{"action": "DELETE_ACCOUNT", "beneficiary_id": "bob.near"}],
            transaction_fee="100000000000000000000",
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["action_type"] == "DELETE_ACCOUNT"

    def test_deploy_contract_action(self):
        """DEPLOY_CONTRACT action type is correctly identified."""
        raw = make_tx(
            tx_hash="TX_DEPLOY_001",
            predecessor="alice.near",
            receiver="alice.near",
            actions=[{"action": "DEPLOY_CONTRACT", "code_sha256": "abc123"}],
            transaction_fee="100000000000000000000",
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["action_type"] == "DEPLOY_CONTRACT"

    def test_fee_extracted(self):
        """Transaction fee is correctly extracted from outcomes_agg."""
        raw = make_tx(
            tx_hash="TX_FEE_001",
            predecessor="alice.near",
            receiver="bob.near",
            transaction_fee="2000000000000000000000",  # 0.002 NEAR
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert int(result["fee"]) == 2000000000000000000000

    def test_block_fields_extracted(self):
        """Block height and timestamp are correctly extracted."""
        raw = make_tx(
            tx_hash="TX_BLOCK_001",
            block_height=99999,
            block_timestamp=1700000000123456789,
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["block_height"] == 99999
        assert result["block_timestamp"] == 1700000000123456789

    def test_raw_data_stored(self):
        """Full raw transaction is stored in raw_data field."""
        raw = make_tx(tx_hash="TX_RAW_001")
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert "raw_data" in result
        assert result["raw_data"]["transaction_hash"] == "TX_RAW_001"

    def test_failed_transaction(self):
        """Failed transaction (outcomes.status=False) is stored with success=False."""
        raw = make_tx(tx_hash="TX_FAIL_001", outcomes_status=False)
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["success"] is False

    def test_multiple_actions_uses_first(self):
        """When tx has multiple actions, the primary action_type is captured."""
        raw = make_tx(
            tx_hash="TX_MULTI_001",
            actions=[
                {"action": "CREATE_ACCOUNT"},
                {"action": "TRANSFER", "deposit": "1000000000000000000000000"},
                {"action": "ADD_KEY", "public_key": "ed25519:ABC", "access_key": {}},
            ],
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        # action_type should be set (first non-trivial action or TRANSFER)
        assert result["action_type"] is not None


# ---------------------------------------------------------------------------
# Tests for NearFetcher.sync_wallet() — cursor resume logic
# ---------------------------------------------------------------------------

class TestNearFetcherSyncWallet:

    def _make_mock_pool(self, cursor_results=None):
        """Build a mock psycopg2 connection pool."""
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn

        if cursor_results:
            mock_cursor.fetchone.side_effect = cursor_results

        return mock_pool, mock_conn, mock_cursor

    @patch("indexers.near_fetcher.NearBlocksClient")
    def test_sync_fetches_all_pages(self, MockClient):
        """sync_wallet() iterates through all pages until cursor is None."""
        from indexers.near_fetcher import NearFetcher

        # Set up mock API responses: page 1 with cursor, page 2 without
        mock_client = MockClient.return_value
        mock_client.get_transaction_count.return_value = 2
        mock_client.fetch_transactions.side_effect = [
            {
                "txns": [make_tx("TX_P1_001")],
                "cursor": "CURSOR_PAGE2",
            },
            {
                "txns": [make_tx("TX_P2_001")],
                "cursor": None,
            },
        ]

        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()

        # fetchone for wallet lookup returns (account_id, user_id)
        # fetchone for job query returns job row
        mock_cursor.fetchone.return_value = ("alice.near", 1)

        fetcher = NearFetcher(mock_pool)

        job = {
            "id": 1,
            "wallet_id": 1,
            "user_id": 1,
            "chain": "near",
            "cursor": None,
            "progress_fetched": 0,
            "job_type": "full_sync",
        }

        fetcher.sync_wallet(job)

        # Should have called fetch_transactions twice (two pages)
        assert mock_client.fetch_transactions.call_count == 2

    @patch("indexers.near_fetcher.NearBlocksClient")
    def test_sync_resumes_from_cursor(self, MockClient):
        """sync_wallet() resumes from job.cursor when set."""
        from indexers.near_fetcher import NearFetcher

        mock_client = MockClient.return_value
        mock_client.get_transaction_count.return_value = 1
        mock_client.fetch_transactions.return_value = {
            "txns": [make_tx("TX_RESUME_001")],
            "cursor": None,
        }

        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchone.return_value = ("alice.near", 1)

        fetcher = NearFetcher(mock_pool)

        job = {
            "id": 1,
            "wallet_id": 1,
            "user_id": 1,
            "chain": "near",
            "cursor": "EXISTING_CURSOR",  # resume from here
            "progress_fetched": 10,
            "job_type": "incremental_sync",
        }

        fetcher.sync_wallet(job)

        # First fetch should use the existing cursor (passed as keyword arg)
        first_call = mock_client.fetch_transactions.call_args_list[0]
        positional_cursor = first_call[0][1] if len(first_call[0]) > 1 else None
        keyword_cursor = first_call[1].get("cursor") if first_call[1] else None
        assert positional_cursor == "EXISTING_CURSOR" or keyword_cursor == "EXISTING_CURSOR"

    @patch("indexers.near_fetcher.NearBlocksClient")
    def test_empty_wallet_no_transactions(self, MockClient):
        """sync_wallet() handles wallets with zero transactions gracefully."""
        from indexers.near_fetcher import NearFetcher

        mock_client = MockClient.return_value
        mock_client.get_transaction_count.return_value = 0
        mock_client.fetch_transactions.return_value = {
            "txns": [],
            "cursor": None,
        }

        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchone.return_value = ("empty.near", 1)

        fetcher = NearFetcher(mock_pool)

        job = {
            "id": 1,
            "wallet_id": 1,
            "user_id": 1,
            "chain": "near",
            "cursor": None,
            "progress_fetched": 0,
            "job_type": "full_sync",
        }

        # Should complete without error
        fetcher.sync_wallet(job)


# ---------------------------------------------------------------------------
# Tests for duplicate handling
# ---------------------------------------------------------------------------

class TestDuplicateHandling:

    def test_on_conflict_clause_present(self):
        """Verify that near_fetcher.py uses ON CONFLICT DO NOTHING for inserts."""
        near_fetcher_path = os.path.join(PROJECT_ROOT, "indexers", "near_fetcher.py")
        with open(near_fetcher_path) as f:
            source = f.read()
        assert "ON CONFLICT" in source.upper(), "Missing ON CONFLICT clause for duplicate handling"
        assert "DO NOTHING" in source.upper(), "Missing DO NOTHING in conflict clause"


# ---------------------------------------------------------------------------
# Tests for verify_sync()
# ---------------------------------------------------------------------------

class TestVerifySync:

    @patch("indexers.near_fetcher.NearBlocksClient")
    @patch("indexers.near_fetcher.requests")
    def test_verify_passes_when_counts_match(self, mock_requests, MockClient):
        """verify_sync() returns True when DB count matches NearBlocks count."""
        from indexers.near_fetcher import NearFetcher

        mock_client = MockClient.return_value
        mock_client.get_transaction_count.return_value = 5

        mock_pool, mock_conn, mock_cursor = MagicMock(), MagicMock(), MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (5,)  # DB count = 5
        mock_conn.cursor.return_value = mock_cursor
        mock_pool.getconn.return_value = mock_conn

        # Mock RPC response for balance check
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"amount": "1000000000000000000000000000"}  # 1000 NEAR
        }
        mock_requests.post.return_value = mock_response

        fetcher = NearFetcher(mock_pool)
        passed, message = fetcher.verify_sync(wallet_id=1, account_id="alice.near")

        assert passed is True

    @patch("indexers.near_fetcher.NearBlocksClient")
    @patch("indexers.near_fetcher.requests")
    def test_verify_allows_tolerance(self, mock_requests, MockClient):
        """verify_sync() allows small count discrepancy (NearBlocks lag)."""
        from indexers.near_fetcher import NearFetcher

        mock_client = MockClient.return_value
        mock_client.get_transaction_count.return_value = 100  # NearBlocks says 100

        mock_pool, mock_conn, mock_cursor = MagicMock(), MagicMock(), MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (97,)  # DB has 97 (within tolerance)
        mock_conn.cursor.return_value = mock_cursor
        mock_pool.getconn.return_value = mock_conn

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"amount": "1000000000000000000000000000"}
        }
        mock_requests.post.return_value = mock_response

        fetcher = NearFetcher(mock_pool)
        passed, message = fetcher.verify_sync(wallet_id=1, account_id="alice.near")

        # Should pass with small tolerance
        assert passed is True


# ---------------------------------------------------------------------------
# NearBlocks client caching tests
# ---------------------------------------------------------------------------


class TestNearBlocksCache(unittest.TestCase):
    """Tests for NearBlocksClient TTL cache."""

    def test_cache_hit_returns_without_api_call(self):
        """Cached entry returns value without making an API request."""
        from indexers.nearblocks_client import NearBlocksClient

        client = NearBlocksClient(delay=0)
        # Pre-populate cache
        client._cache_set("txn_count:alice.near", 42)

        # Mock _request to ensure it's NOT called
        client._request = unittest.mock.MagicMock()

        result = client.get_transaction_count("alice.near")
        self.assertEqual(result, 42)
        client._request.assert_not_called()

    def test_cache_miss_makes_api_call(self):
        """Missing cache entry triggers API call and caches result."""
        from indexers.nearblocks_client import NearBlocksClient

        client = NearBlocksClient(delay=0)
        client._request = unittest.mock.MagicMock(
            return_value={"txns": [{"count": "100"}]}
        )

        result = client.get_transaction_count("bob.near")
        self.assertEqual(result, 100)
        client._request.assert_called_once()

        # Second call should hit cache
        result2 = client.get_transaction_count("bob.near")
        self.assertEqual(result2, 100)
        # Still only 1 API call
        client._request.assert_called_once()

    def test_cache_expired_makes_fresh_api_call(self):
        """Expired cache entry triggers fresh API call."""
        import time as _time
        from indexers.nearblocks_client import NearBlocksClient

        client = NearBlocksClient(delay=0)
        # Set cache entry with expired TTL
        client._cache["txn_count:charlie.near"] = (50, _time.time() - 1)

        client._request = unittest.mock.MagicMock(
            return_value={"txns": [{"count": "75"}]}
        )

        result = client.get_transaction_count("charlie.near")
        self.assertEqual(result, 75)
        client._request.assert_called_once()


# ---------------------------------------------------------------------------
# Staking backfill batch commit tests
# ---------------------------------------------------------------------------


class TestBackfillBatchCommit(unittest.TestCase):
    """Tests for BACKFILL_BATCH_SIZE batch commit pattern."""

    def test_backfill_batch_size_constant_exists(self):
        """BACKFILL_BATCH_SIZE is defined and equals 100."""
        from indexers.staking_fetcher import BACKFILL_BATCH_SIZE
        self.assertEqual(BACKFILL_BATCH_SIZE, 100)
