"""
Unit tests for indexers/evm_fetcher.py

Tests cover:
- sync_wallet() inserts normal transactions into transactions table
- ERC20 transfers get tx_hash = "{hash}-{logIndex}"
- Pagination loops until result count < page_size
- Job cursor updated to max blockNumber after sync
- Direction detection (in vs out)
- Fee calculation: gas_used * gas_price
- Cronos uses custom_api URL
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tests.fixtures.etherscan_responses import (
    NORMAL_TX,
    ERC20_TX,
    INTERNAL_TX,
    NFT_TX,
    EMPTY_RESPONSE,
    make_page,
)
from indexers.evm_fetcher import EVMFetcher, CHAIN_CONFIG


@pytest.fixture(autouse=True)
def _evm_test_dek():
    # _batch_upsert -> insert_transaction_with_dedup encrypts columns
    # and requires a DEK in the ContextVar. Provide a stub for every test.
    from db.crypto import set_dek, zero_dek

    set_dek(b"\x00" * 32)
    try:
        yield
    finally:
        zero_dek()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WALLET_ADDRESS = "0xWALLET000000000000000000000000000000000"


def make_job(chain="ethereum", cursor=None, job_type="evm_full_sync"):
    return {
        "id": 1,
        "user_id": 10,
        "wallet_id": 42,
        "chain": chain,
        "account_id": WALLET_ADDRESS,
        "cursor": cursor,
        "job_type": job_type,
        "attempts": 0,
    }


def make_mock_pool():
    """Return a minimal mock connection pool."""
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    return mock_pool, mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# Test 1: sync_wallet() inserts normal transactions
# ---------------------------------------------------------------------------

class TestSyncWalletNormalTx:
    """sync_wallet() with mocked Etherscan API inserts normal transactions."""

    def test_sync_wallet_calls_insert_helper(self):
        """Verify that sync_wallet writes transactions via insert_transaction_with_dedup."""
        mock_pool, mock_conn, mock_cursor = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        # Mock _fetch_paginated to return one normal tx and empty for others
        with patch.object(fetcher, "_fetch_paginated") as mock_fetch, \
             patch("indexers.evm_fetcher.insert_transaction_with_dedup") as mock_insert:

            # normal, internal, erc20, nft -> one normal tx, rest empty
            mock_fetch.side_effect = [[NORMAL_TX], [], [], []]

            fetcher.sync_wallet(make_job())

            # insert helper should have been called at least once
            assert mock_insert.called

    def test_sync_wallet_passes_correct_columns(self):
        """Verify that insert_transaction_with_dedup is called with transactions-shape kwargs."""
        mock_pool, mock_conn, mock_cursor = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        with patch.object(fetcher, "_fetch_paginated") as mock_fetch, \
             patch("indexers.evm_fetcher.insert_transaction_with_dedup") as mock_insert:

            mock_fetch.side_effect = [[NORMAL_TX], [], [], []]
            fetcher.sync_wallet(make_job())

        # One normal tx → one helper call
        assert mock_insert.call_count == 1
        call_kwargs = mock_insert.call_args.kwargs
        # Every required transactions column is forwarded as a keyword arg
        expected_keys = {
            "user_id", "wallet_id", "tx_hash", "receipt_id", "chain", "direction",
            "counterparty", "action_type", "method_name", "amount", "fee",
            "token_id", "block_height", "block_timestamp", "success", "raw_data",
        }
        missing = expected_keys - set(call_kwargs.keys())
        assert not missing, f"Missing expected kwargs: {missing}"


# ---------------------------------------------------------------------------
# Test 2: ERC20 tx_hash includes logIndex suffix
# ---------------------------------------------------------------------------

class TestERC20TxHash:
    """ERC20 transfers get tx_hash = '{hash}-{logIndex}'."""

    def test_erc20_tx_hash_has_log_index_suffix(self):
        """_transform_tx for ERC20 produces tx_hash with logIndex appended."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)
        chain_conf = CHAIN_CONFIG["ETH"]

        row = fetcher._transform_tx(ERC20_TX, WALLET_ADDRESS, "ethereum", "erc20", chain_conf)

        expected_hash = f"{ERC20_TX['hash']}-{ERC20_TX['logIndex']}"
        assert row["tx_hash"] == expected_hash

    def test_normal_tx_hash_has_no_suffix(self):
        """_transform_tx for normal tx produces tx_hash without suffix."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)
        chain_conf = CHAIN_CONFIG["ETH"]

        row = fetcher._transform_tx(NORMAL_TX, WALLET_ADDRESS, "ethereum", "transfer", chain_conf)

        assert row["tx_hash"] == NORMAL_TX["hash"]

    def test_nft_tx_hash_has_log_index_suffix(self):
        """_transform_tx for NFT produces tx_hash with logIndex appended."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)
        chain_conf = CHAIN_CONFIG["ETH"]

        row = fetcher._transform_tx(NFT_TX, WALLET_ADDRESS, "ethereum", "nft", chain_conf)

        expected_hash = f"{NFT_TX['hash']}-{NFT_TX['logIndex']}"
        assert row["tx_hash"] == expected_hash


# ---------------------------------------------------------------------------
# Test 3: Pagination loops until result count < page_size
# ---------------------------------------------------------------------------

class TestPagination:
    """_fetch_paginated loops until result count < page_size."""

    def test_pagination_fetches_all_pages(self):
        """When first response has 10000 items, fetches page 2 as well."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        page1 = make_page(10000, start_block=17000000)
        page2 = make_page(500, start_block=17010000)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        call_count = [0]

        def mock_get(url, params=None, timeout=None):
            call_count[0] += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            if call_count[0] == 1:
                mock_resp.json.return_value = page1
            else:
                mock_resp.json.return_value = page2
            return mock_resp

        with patch("requests.get", side_effect=mock_get):
            params = {
                "module": "account",
                "action": "txlist",
                "address": WALLET_ADDRESS,
                "startblock": "0",
                "endblock": "99999999",
                "sort": "asc",
            }
            chain_conf = CHAIN_CONFIG["ETH"]
            results = fetcher._fetch_paginated(params, chain_conf)

        assert len(results) == 10500
        assert call_count[0] == 2

    def test_pagination_single_page(self):
        """When response has fewer items than page_size, only one request is made."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        page = make_page(50)

        def mock_get(url, params=None, timeout=None):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = page
            return mock_resp

        with patch("requests.get", side_effect=mock_get) as mock_requests:
            params = {"module": "account", "action": "txlist", "address": WALLET_ADDRESS,
                      "startblock": "0", "endblock": "99999999", "sort": "asc"}
            results = fetcher._fetch_paginated(params, CHAIN_CONFIG["ETH"])

        assert len(results) == 50
        assert mock_requests.call_count == 1


# ---------------------------------------------------------------------------
# Test 4: Job cursor updated to max blockNumber
# ---------------------------------------------------------------------------

class TestCursorUpdate:
    """Job cursor is updated to max blockNumber after sync."""

    def test_cursor_updated_to_max_block(self):
        """After sync_wallet, job cursor = highest blockNumber seen."""
        mock_pool, mock_conn, mock_cursor = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        tx_low_block = dict(NORMAL_TX, blockNumber="17499000")
        tx_high_block = dict(NORMAL_TX, blockNumber="17500000",
                             hash="0x" + "b" * 64)

        with patch.object(fetcher, "_fetch_paginated") as mock_fetch, \
             patch("indexers.evm_fetcher.insert_transaction_with_dedup"):

            mock_fetch.side_effect = [[tx_low_block, tx_high_block], [], [], []]
            fetcher.sync_wallet(make_job())

        # cursor update is done via pool.getconn / cursor.execute
        # Verify that UPDATE indexing_jobs ... cursor = '17500000' was called
        update_calls = [
            c for c in mock_cursor.execute.call_args_list
            if "UPDATE indexing_jobs" in str(c)
        ]
        assert len(update_calls) >= 1
        # The cursor value should be '17500000'
        last_update = update_calls[-1]
        args = last_update[0]  # positional args to execute
        assert "17500000" in str(args)


# ---------------------------------------------------------------------------
# Test 5: Direction detection
# ---------------------------------------------------------------------------

class TestDirectionDetection:
    """Direction: to_address == wallet => 'in', from_address == wallet => 'out'."""

    def test_incoming_tx_direction(self):
        """Transaction TO wallet address is direction='in'."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        # NORMAL_TX has 'to' == WALLET_ADDRESS
        row = fetcher._transform_tx(NORMAL_TX, WALLET_ADDRESS, "ethereum", "transfer", CHAIN_CONFIG["ETH"])
        # from = COUNTERPARTY, to = WALLET => direction in
        assert row["direction"] == "in"

    def test_outgoing_tx_direction(self):
        """Transaction FROM wallet address is direction='out'."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        # Swap from/to: wallet is the sender
        outgoing_tx = dict(NORMAL_TX,
                           **{"from": WALLET_ADDRESS,
                              "to": "0xCOUNTERPARTY0000000000000000000000000000"})
        row = fetcher._transform_tx(outgoing_tx, WALLET_ADDRESS, "ethereum", "transfer", CHAIN_CONFIG["ETH"])
        assert row["direction"] == "out"

    def test_direction_is_case_insensitive(self):
        """Direction comparison is case-insensitive for addresses."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        # Mix case in 'to' field
        mixed_case_tx = dict(NORMAL_TX, **{"to": WALLET_ADDRESS.upper()})
        row = fetcher._transform_tx(mixed_case_tx, WALLET_ADDRESS, "ethereum", "transfer", CHAIN_CONFIG["ETH"])
        assert row["direction"] == "in"


# ---------------------------------------------------------------------------
# Test 6: Fee calculation
# ---------------------------------------------------------------------------

class TestFeeCalculation:
    """Fee = gas_used * gas_price stored as int (NUMERIC 40,0)."""

    def test_fee_calculated_correctly(self):
        """Normal tx fee = gasUsed * gasPrice."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        row = fetcher._transform_tx(NORMAL_TX, WALLET_ADDRESS, "ethereum", "transfer", CHAIN_CONFIG["ETH"])

        expected_fee = int(NORMAL_TX["gasUsed"]) * int(NORMAL_TX["gasPrice"])
        assert row["fee"] == expected_fee

    def test_internal_tx_has_no_fee(self):
        """Internal transactions don't have separate gas fees."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        row = fetcher._transform_tx(INTERNAL_TX, WALLET_ADDRESS, "ethereum", "internal", CHAIN_CONFIG["ETH"])
        assert row["fee"] is None or row["fee"] == 0

    def test_erc20_tx_has_no_fee(self):
        """ERC20 transfers don't have separate fee (gas counted in parent tx)."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        row = fetcher._transform_tx(ERC20_TX, WALLET_ADDRESS, "ethereum", "erc20", CHAIN_CONFIG["ETH"])
        assert row["fee"] is None or row["fee"] == 0


# ---------------------------------------------------------------------------
# Test 7: Cronos uses custom_api URL
# ---------------------------------------------------------------------------

class TestCronosCustomAPI:
    """Cronos fetcher uses cronos.org/explorer/api instead of Etherscan V2."""

    def test_cronos_uses_custom_api_url(self):
        """_fetch_paginated sends request to custom_api for Cronos."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        used_urls = []

        def mock_get(url, params=None, timeout=None):
            used_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = EMPTY_RESPONSE
            return mock_resp

        with patch("requests.get", side_effect=mock_get):
            params = {"module": "account", "action": "txlist", "address": WALLET_ADDRESS,
                      "startblock": "0", "endblock": "99999999", "sort": "asc"}
            fetcher._fetch_paginated(params, CHAIN_CONFIG["Cronos"])

        assert len(used_urls) >= 1
        assert "cronos.org" in used_urls[0]

    def test_eth_uses_etherscan_v2_url(self):
        """_fetch_paginated sends request to Etherscan V2 for ETH."""
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)

        used_urls = []

        def mock_get(url, params=None, timeout=None):
            used_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = EMPTY_RESPONSE
            return mock_resp

        with patch("requests.get", side_effect=mock_get):
            params = {"module": "account", "action": "txlist", "address": WALLET_ADDRESS,
                      "startblock": "0", "endblock": "99999999", "sort": "asc"}
            fetcher._fetch_paginated(params, CHAIN_CONFIG["ETH"])

        assert len(used_urls) >= 1
        assert "etherscan.io" in used_urls[0]


# ---------------------------------------------------------------------------
# Test: CHAIN_CONFIG completeness
# ---------------------------------------------------------------------------

class TestChainConfig:
    """CHAIN_CONFIG should include all 4 required chains with correct IDs."""

    def test_all_chains_present(self):
        assert "ETH" in CHAIN_CONFIG
        assert "Polygon" in CHAIN_CONFIG
        assert "Cronos" in CHAIN_CONFIG
        assert "Optimism" in CHAIN_CONFIG

    def test_chain_ids(self):
        assert CHAIN_CONFIG["ETH"]["chainid"] == 1
        assert CHAIN_CONFIG["Polygon"]["chainid"] == 137
        assert CHAIN_CONFIG["Cronos"]["chainid"] == 25
        assert CHAIN_CONFIG["Optimism"]["chainid"] == 10

    def test_cronos_has_custom_api(self):
        assert "custom_api" in CHAIN_CONFIG["Cronos"]
        assert "cronos.org" in CHAIN_CONFIG["Cronos"]["custom_api"]

    def test_chain_name_mapping(self):
        """chain_name_map produces lowercase names for transactions table."""
        from indexers.evm_fetcher import CHAIN_NAME_MAP
        assert CHAIN_NAME_MAP["ETH"] == "ethereum"
        assert CHAIN_NAME_MAP["Polygon"] == "polygon"
        assert CHAIN_NAME_MAP["Cronos"] == "cronos"
        assert CHAIN_NAME_MAP["Optimism"] == "optimism"


# ---------------------------------------------------------------------------
# Test: EVMFetcher inherits from ChainFetcher
# ---------------------------------------------------------------------------

class TestInheritance:
    """EVMFetcher should implement ChainFetcher ABC."""

    def test_inherits_chain_fetcher(self):
        from indexers.chain_plugin import ChainFetcher
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)
        assert isinstance(fetcher, ChainFetcher)

    def test_supported_job_types(self):
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)
        assert "evm_full_sync" in fetcher.supported_job_types
        assert "evm_incremental" in fetcher.supported_job_types

    def test_chain_name(self):
        mock_pool, _, _ = make_mock_pool()
        fetcher = EVMFetcher(pool=mock_pool)
        assert fetcher.chain_name == "evm"
