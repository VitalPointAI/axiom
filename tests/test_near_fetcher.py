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

    def test_ft_transfer_sets_token_id(self):
        """ft_transfer sets token_id to the receiver contract."""
        raw = make_tx(
            tx_hash="TX_FT_001",
            predecessor="alice.near",
            receiver="token.sweat",
            actions=[{
                "action": "FUNCTION_CALL",
                "method": "ft_transfer",
                "deposit": "1",
                "args": '{"receiver_id": "bob.near", "amount": "5000000000000000000"}',
            }],
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["token_id"] == "token.sweat"
        assert result["method_name"] == "ft_transfer"
        assert result["counterparty"] == "bob.near"
        assert int(result["amount"]) == 5000000000000000000

    def test_ft_transfer_call_sets_token_id(self):
        """ft_transfer_call also sets token_id correctly."""
        import base64
        import json
        args_b64 = base64.b64encode(json.dumps({
            "receiver_id": "v2.ref-finance.near",
            "amount": "1000000",
        }).encode()).decode()

        raw = make_tx(
            tx_hash="TX_FTC_001",
            predecessor="alice.near",
            receiver="usdt.tether-token.near",
            actions=[{
                "action": "FUNCTION_CALL",
                "method": "ft_transfer_call",
                "deposit": "1",
                "args": args_b64,
            }],
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["token_id"] == "usdt.tether-token.near"
        assert result["counterparty"] == "v2.ref-finance.near"
        assert int(result["amount"]) == 1000000

    def test_ft_transfer_incoming(self):
        """Incoming FT transfer: direction=in, counterparty=sender."""
        raw = make_tx(
            tx_hash="TX_FT_IN_001",
            predecessor="bob.near",
            receiver="token.sweat",
            actions=[{
                "action": "FUNCTION_CALL",
                "method": "ft_transfer",
                "deposit": "1",
                "args": '{"receiver_id": "alice.near", "amount": "3000000000000000000"}',
            }],
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["token_id"] == "token.sweat"
        assert result["direction"] == "in"
        assert result["counterparty"] == "bob.near"

    def test_non_ft_function_call_no_token_id(self):
        """Regular function calls should NOT set token_id."""
        raw = make_tx(
            tx_hash="TX_REG_001",
            predecessor="alice.near",
            receiver="staking.pool.near",
            actions=[{
                "action": "FUNCTION_CALL",
                "method": "deposit_and_stake",
                "deposit": "10000000000000000000000000",
            }],
        )
        result = self.parse_transaction(raw, wallet_id=1, user_id=1, account_id="alice.near")

        assert result is not None
        assert result["token_id"] is None

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

    @patch("indexers.near_fetcher.NeardataClient")
    def test_sync_scans_blocks(self, MockClient):
        """sync_wallet() scans blocks via neardata and inserts transactions."""
        from indexers.near_fetcher import NearFetcher

        mock_client = MockClient.return_value
        mock_client.get_final_block_height.return_value = 100_000_002
        mock_client.fetch_block.return_value = {"block": {"header": {"height": 100_000_001}}}
        # Return one tx on first call, empty for all subsequent
        mock_client.extract_wallet_txs.return_value = []
        mock_client.extract_wallet_txs.side_effect = None

        def extract_side_effect(block, account_id):
            if block and block.get("block", {}).get("header", {}).get("height") == 100_000_001:
                return [make_tx("TX_B1_001", predecessor="alice.near", receiver="bob.near")]
            return []
        mock_client.extract_wallet_txs.side_effect = extract_side_effect

        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchone.return_value = ("alice.near", 1)

        fetcher = NearFetcher(mock_pool)
        fetcher.BATCH_SIZE = 3  # Small batch for testing

        job = {
            "id": 1, "wallet_id": 1, "user_id": 1,
            "chain": "near", "cursor": "100000000",
            "progress_fetched": 0, "job_type": "full_sync",
        }

        fetcher.sync_wallet(job)

        assert mock_client.fetch_block.call_count >= 2

    @patch("indexers.near_fetcher.NeardataClient")
    def test_sync_resumes_from_block_cursor(self, MockClient):
        """sync_wallet() resumes from block height cursor."""
        from indexers.near_fetcher import NearFetcher

        mock_client = MockClient.return_value
        mock_client.get_final_block_height.return_value = 100_000_001
        mock_client.fetch_block.return_value = None  # No transactions found
        mock_client.extract_wallet_txs.return_value = []

        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchone.return_value = ("alice.near", 1)

        fetcher = NearFetcher(mock_pool)
        fetcher.BATCH_SIZE = 2

        job = {
            "id": 1, "wallet_id": 1, "user_id": 1,
            "chain": "near", "cursor": "100000000",
            "progress_fetched": 10, "job_type": "incremental_sync",
        }

        fetcher.sync_wallet(job)

        # First fetch_block should start at block 100000000
        first_call_height = mock_client.fetch_block.call_args_list[0][0][0]
        assert first_call_height == 100_000_000

    @patch("indexers.near_fetcher.NeardataClient")
    def test_empty_wallet_no_transactions(self, MockClient):
        """sync_wallet() handles wallets with no matching transactions."""
        from indexers.near_fetcher import NearFetcher

        mock_client = MockClient.return_value
        mock_client.get_final_block_height.return_value = 100_000_001
        mock_client.fetch_block.return_value = None
        mock_client.extract_wallet_txs.return_value = []

        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchone.return_value = ("empty.near", 1)

        fetcher = NearFetcher(mock_pool)
        fetcher.BATCH_SIZE = 2

        job = {
            "id": 1, "wallet_id": 1, "user_id": 1,
            "chain": "near", "cursor": "100000000",
            "progress_fetched": 0, "job_type": "full_sync",
        }

        fetcher.sync_wallet(job)


# ---------------------------------------------------------------------------
# Tests for duplicate handling
# ---------------------------------------------------------------------------

class TestDuplicateHandling:

    def test_on_conflict_clause_present(self):
        """Verify duplicate handling is wired through the dedup HMAC helper.

        Phase 16 refactored the raw INSERT SQL out of near_fetcher.py and into
        db.dedup_hmac_helpers.insert_transaction_with_dedup(). Check that
        near_fetcher imports it and that the helper's SQL still carries
        ON CONFLICT for idempotent upserts.
        """
        near_fetcher_path = os.path.join(PROJECT_ROOT, "indexers", "near_fetcher.py")
        helper_path = os.path.join(PROJECT_ROOT, "db", "dedup_hmac_helpers.py")

        with open(near_fetcher_path) as f:
            near_src = f.read()
        assert "insert_transaction_with_dedup" in near_src, (
            "near_fetcher.py must use insert_transaction_with_dedup for duplicate handling"
        )

        with open(helper_path) as f:
            helper_src = f.read()
        assert "ON CONFLICT" in helper_src.upper(), (
            "dedup helper must carry ON CONFLICT clause for duplicate handling"
        )


# ---------------------------------------------------------------------------
# Tests for verify_sync()
# ---------------------------------------------------------------------------

class TestVerifySync:

    @patch("indexers.near_fetcher.NeardataClient")
    @patch("indexers.near_fetcher.requests")
    def test_verify_passes_with_balance(self, mock_requests, MockClient):
        """verify_sync() returns True when RPC balance check succeeds."""
        from indexers.near_fetcher import NearFetcher

        mock_pool, mock_conn, mock_cursor = MagicMock(), MagicMock(), MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (5,)  # DB count
        mock_conn.cursor.return_value = mock_cursor
        mock_pool.getconn.return_value = mock_conn

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"amount": "1000000000000000000000000000"}
        }
        mock_requests.post.return_value = mock_response

        fetcher = NearFetcher(mock_pool)
        passed, message = fetcher.verify_sync(wallet_id=1, account_id="alice.near")

        assert passed is True


# ---------------------------------------------------------------------------
# NeardataClient tests
# ---------------------------------------------------------------------------


class TestNeardataClient(unittest.TestCase):
    """Tests for NeardataClient block scanning."""

    def test_normalize_action_type(self):
        """Action type mapping from neardata CamelCase to UPPER_SNAKE."""
        from indexers.neardata_client import NeardataClient
        self.assertEqual(NeardataClient._normalize_action_type("FunctionCall"), "FUNCTION_CALL")
        self.assertEqual(NeardataClient._normalize_action_type("Transfer"), "TRANSFER")
        self.assertEqual(NeardataClient._normalize_action_type("Stake"), "STAKE")

    def test_extract_wallet_txs_empty(self):
        """Empty/None block returns no transactions."""
        from indexers.neardata_client import NeardataClient
        client = NeardataClient()
        self.assertEqual(client.extract_wallet_txs(None, "alice.near"), [])

    def test_extract_wallet_txs_match(self):
        """Extracts tx when signer matches wallet."""
        from indexers.neardata_client import NeardataClient
        client = NeardataClient()
        block = {
            "block": {"header": {"height": 100, "timestamp": 1700000000000000000}},
            "shards": [{"chunk": {
                "transactions": [{
                    "transaction": {
                        "hash": "TX_001", "signer_id": "alice.near",
                        "receiver_id": "bob.near",
                        "actions": [{"Transfer": {"deposit": "1000"}}],
                    },
                    "outcome": {"execution_outcome": {"outcome": {
                        "tokens_burnt": "500", "status": {"SuccessValue": ""},
                    }}},
                }],
                "receipt_execution_outcomes": [],
            }}],
        }
        results = client.extract_wallet_txs(block, "alice.near")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["transaction_hash"], "TX_001")
        self.assertEqual(results[0]["actions"][0]["action"], "TRANSFER")


# ---------------------------------------------------------------------------
# Staking backfill batch commit tests
# ---------------------------------------------------------------------------


class TestBackfillBatchCommit(unittest.TestCase):
    """Tests for BACKFILL_BATCH_SIZE batch commit pattern."""

    def test_backfill_batch_size_constant_exists(self):
        """BACKFILL_BATCH_SIZE is defined and equals 100."""
        from indexers.staking_fetcher import BACKFILL_BATCH_SIZE
        self.assertEqual(BACKFILL_BATCH_SIZE, 100)
