"""Unit tests for EVMStreamFetcher — sync methods and URL construction."""

from unittest.mock import MagicMock, patch

import pytest

from indexers.evm_stream_fetcher import EVMStreamFetcher, ALCHEMY_WS_URLS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value = cursor
    return pool, conn, cursor


@pytest.fixture
def fetcher(mock_pool):
    pool, _, _ = mock_pool
    with patch("indexers.evm_stream_fetcher.EVMFetcher"):
        return EVMStreamFetcher(pool)


# ---------------------------------------------------------------------------
# get_ws_url tests
# ---------------------------------------------------------------------------

class TestGetWsUrl:
    def test_ethereum_url(self, fetcher):
        with patch.dict("os.environ", {"ALCHEMY_API_KEY": "test-key"}):
            url = fetcher.get_ws_url("ethereum", {"chain_id": 1})
        assert "eth-mainnet" in url
        assert "test-key" in url

    def test_polygon_url(self, fetcher):
        with patch.dict("os.environ", {"ALCHEMY_API_KEY": "test-key"}):
            url = fetcher.get_ws_url("polygon", {"chain_id": 137})
        assert "polygon-mainnet" in url

    def test_optimism_url(self, fetcher):
        with patch.dict("os.environ", {"ALCHEMY_API_KEY": "test-key"}):
            url = fetcher.get_ws_url("optimism", {"chain_id": 10})
        assert "opt-mainnet" in url

    def test_missing_api_key_returns_none(self, fetcher):
        with patch.dict("os.environ", {}, clear=True):
            url = fetcher.get_ws_url("ethereum", {"chain_id": 1})
        assert url is None

    def test_unknown_chain_returns_none(self, fetcher):
        with patch.dict("os.environ", {"ALCHEMY_API_KEY": "test-key"}):
            url = fetcher.get_ws_url("unknown_chain", {"chain_id": 999})
        assert url is None

    def test_all_supported_chains_have_urls(self, fetcher):
        """Every chain in ALCHEMY_WS_URLS produces a valid URL."""
        with patch.dict("os.environ", {"ALCHEMY_API_KEY": "key123"}):
            for chain in ALCHEMY_WS_URLS:
                url = fetcher.get_ws_url(chain, {})
                assert url is not None
                assert "key123" in url


# ---------------------------------------------------------------------------
# sync_wallet delegation tests
# ---------------------------------------------------------------------------

class TestSyncWallet:
    def test_delegates_to_evm_fetcher(self, fetcher):
        mock_evm = MagicMock()
        fetcher._evm_fetcher = mock_evm
        job = {"id": 1, "chain": "ethereum", "account_id": "0xabc"}

        fetcher.sync_wallet(job)

        mock_evm.sync_wallet.assert_called_once_with(job)


class TestGetBalance:
    def test_delegates_to_evm_fetcher(self, fetcher):
        mock_evm = MagicMock()
        mock_evm.get_balance.return_value = {"native_balance": "1000", "tokens": []}
        fetcher._evm_fetcher = mock_evm

        result = fetcher.get_balance("0xabc")

        assert result["native_balance"] == "1000"
        mock_evm.get_balance.assert_called_once_with("0xabc")


# ---------------------------------------------------------------------------
# Class attributes and configuration
# ---------------------------------------------------------------------------

class TestClassConfig:
    def test_chain_name(self, fetcher):
        assert fetcher.chain_name == "evm"

    def test_supported_job_types(self, fetcher):
        assert "evm_full_sync" in fetcher.supported_job_types
        assert "evm_incremental" in fetcher.supported_job_types

    def test_ping_interval_configured(self, fetcher):
        assert fetcher.PING_INTERVAL == 20

    def test_watchdog_timeout_configured(self, fetcher):
        assert fetcher.WATCHDOG_TIMEOUT == 60

    def test_max_backoff_configured(self, fetcher):
        assert fetcher.MAX_BACKOFF == 60

    def test_cost_tracker_optional(self, mock_pool):
        pool, _, _ = mock_pool
        with patch("indexers.evm_stream_fetcher.EVMFetcher"):
            f = EVMStreamFetcher(pool)
        assert f.cost_tracker is None

    def test_cost_tracker_stored(self, mock_pool):
        pool, _, _ = mock_pool
        tracker = MagicMock()
        with patch("indexers.evm_stream_fetcher.EVMFetcher"):
            f = EVMStreamFetcher(pool, cost_tracker=tracker)
        assert f.cost_tracker is tracker


# ---------------------------------------------------------------------------
# on_new_block tests
# ---------------------------------------------------------------------------

class TestOnNewBlock:
    def test_parses_hex_block_number(self, fetcher):
        """on_new_block should parse hex block numbers without error."""
        import asyncio
        header = {"number": "0xf4240", "hash": "0xabc"}

        # Run the async method synchronously
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                fetcher.on_new_block(header, "ethereum", {"0xabc"})
            )
        finally:
            loop.close()

    def test_handles_missing_number(self, fetcher):
        """on_new_block handles missing block number gracefully."""
        import asyncio
        header = {"hash": "0xabc"}

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                fetcher.on_new_block(header, "ethereum", set())
            )
        finally:
            loop.close()
