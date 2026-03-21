"""Tests for StreamingWorker lifecycle and event handling."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from indexers.streaming_worker import StreamingWorker


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value = cursor
    return pool, conn, cursor


@pytest.fixture
def worker(mock_pool):
    pool, conn, cursor = mock_pool
    # Mock chain_sync_config query to raise (fallback path)
    cursor.execute.side_effect = Exception("table does not exist")
    with patch("indexers.streaming_worker.NearStreamFetcher"):
        with patch("indexers.streaming_worker.EVMStreamFetcher") as mock_evm:
            mock_evm_instance = MagicMock()
            mock_evm_instance.get_ws_url.return_value = None
            mock_evm.return_value = mock_evm_instance
            w = StreamingWorker(pool)
    # Reset cursor side effects for subsequent calls
    cursor.execute.side_effect = None
    cursor.execute.reset_mock()
    return w


class TestStreamingWorkerInit:
    def test_init_stores_pool(self, mock_pool):
        pool, _, _ = mock_pool
        with patch("indexers.streaming_worker.NearStreamFetcher"):
            with patch("indexers.streaming_worker.EVMStreamFetcher"):
                w = StreamingWorker(pool)
        assert w.pool is pool

    def test_init_cost_tracker_optional(self, mock_pool):
        pool, _, _ = mock_pool
        with patch("indexers.streaming_worker.NearStreamFetcher"):
            with patch("indexers.streaming_worker.EVMStreamFetcher"):
                w = StreamingWorker(pool)
        assert w.cost_tracker is None

    def test_init_cost_tracker_stored(self, mock_pool):
        pool, _, _ = mock_pool
        tracker = MagicMock()
        with patch("indexers.streaming_worker.NearStreamFetcher"):
            with patch("indexers.streaming_worker.EVMStreamFetcher"):
                w = StreamingWorker(pool, cost_tracker=tracker)
        assert w.cost_tracker is tracker


class TestLoadStreamingChains:
    def test_fallback_when_table_missing(self, worker, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.execute.side_effect = Exception("table does not exist")
        chains = worker._load_streaming_chains()
        # Should return at least NEAR in fallback
        assert "near" in chains

    def test_fallback_includes_evm_with_api_key(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.execute.side_effect = Exception("missing table")
        with patch("indexers.streaming_worker.NearStreamFetcher"):
            with patch("indexers.streaming_worker.EVMStreamFetcher") as mock_evm:
                instance = MagicMock()
                instance.get_ws_url.return_value = "wss://test/ws"
                mock_evm.return_value = instance
                w = StreamingWorker(pool)

        cursor.execute.side_effect = Exception("missing table")
        chains = w._load_streaming_chains()
        # Should include EVM chains since ws_url is available
        assert any(c in chains for c in ("ethereum", "polygon", "optimism"))


class TestRefreshWallets:
    def test_loads_wallets_grouped_by_chain(self, worker, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = [
            (1, 10, "alice.near", "near"),
            (2, 10, "0xabc", "ethereum"),
            (3, 20, "bob.near", "near"),
        ]

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(worker._refresh_wallets())
        finally:
            loop.close()

        assert "near" in worker._tracked_wallets
        assert "ethereum" in worker._tracked_wallets
        assert len(worker._tracked_wallets["near"]) == 2
        assert len(worker._tracked_wallets["ethereum"]) == 1

    def test_builds_wallet_id_lookup(self, worker, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = [
            (1, 10, "alice.near", "near"),
        ]

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(worker._refresh_wallets())
        finally:
            loop.close()

        assert ("near", "alice.near") in worker._wallet_to_ids
        assert worker._wallet_to_ids[("near", "alice.near")] == (10, 1)


class TestOnNearTxsFound:
    def test_upserts_transactions_and_notifies(self, worker, mock_pool):
        pool, conn, cursor = mock_pool
        worker._wallet_to_ids = {
            ("near", "alice.near"): (10, 1),
        }
        worker._tracked_wallets = {"near": {"alice.near"}}

        # Simulate successful insert (RETURNING id)
        cursor.fetchone.return_value = (42,)

        txs = [{
            "tx_hash": "abc123",
            "signer_id": "alice.near",
            "receiver_id": "bob.near",
            "block_height": 100000,
            "block_timestamp": 1700000000,
            "actions": [],
        }]

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(worker._on_near_txs_found(txs))
        finally:
            loop.close()

        # Should have called execute for INSERT and pg_notify
        calls = cursor.execute.call_args_list
        insert_calls = [c for c in calls if "INSERT INTO transactions" in str(c)]
        notify_calls = [c for c in calls if "pg_notify" in str(c)]
        assert len(insert_calls) >= 1
        assert len(notify_calls) >= 1


class TestOnEvmNewBlock:
    def test_queues_incremental_sync(self, worker, mock_pool):
        pool, conn, cursor = mock_pool
        worker._tracked_wallets = {"ethereum": {"0xabc"}}
        worker._wallet_to_ids = {("ethereum", "0xabc"): (10, 1)}

        block_header = {"number": "0xf4240", "hash": "0x123"}

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                worker._on_evm_new_block(block_header, "ethereum")
            )
        finally:
            loop.close()

        calls = cursor.execute.call_args_list
        insert_calls = [c for c in calls if "INSERT INTO indexing_jobs" in str(c)]
        assert len(insert_calls) >= 1

    def test_skips_when_no_wallets(self, worker, mock_pool):
        pool, conn, cursor = mock_pool
        worker._tracked_wallets = {}

        block_header = {"number": "0x1"}

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                worker._on_evm_new_block(block_header, "ethereum")
            )
        finally:
            loop.close()

        # Should not attempt any DB operations
        pool.getconn.assert_not_called()


class TestStopLifecycle:
    def test_stop_cancels_tasks(self, worker):
        loop = asyncio.new_event_loop()
        try:
            # Create a real asyncio task that sleeps forever
            async def forever():
                await asyncio.sleep(9999)

            real_task = loop.create_task(forever())
            worker._tasks = [real_task]

            loop.run_until_complete(worker.stop())
        finally:
            loop.close()

        assert real_task.cancelled()
        assert len(worker._tasks) == 0
