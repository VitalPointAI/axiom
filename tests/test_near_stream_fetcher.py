"""Unit tests for NearStreamFetcher — mocked HTTP, no live network calls."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from indexers.near_stream_fetcher import NearStreamFetcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BLOCK = {
    "block": {
        "header": {
            "height": 100_000_001,
            "timestamp": 1700000000_000_000_000,  # nanoseconds
            "hash": "abc123",
        }
    },
    "shards": [
        {
            "chunk": {
                "transactions": [
                    {
                        "transaction": {
                            "hash": "tx_hash_1",
                            "signer_id": "alice.near",
                            "receiver_id": "bob.near",
                            "actions": [{"Transfer": {"deposit": "1000000"}}],
                        },
                        "outcome": {"status": {"SuccessValue": ""}},
                    },
                    {
                        "transaction": {
                            "hash": "tx_hash_2",
                            "signer_id": "carol.near",
                            "receiver_id": "dave.near",
                            "actions": [{"Transfer": {"deposit": "500000"}}],
                        },
                        "outcome": {"status": {"SuccessValue": ""}},
                    },
                ],
            },
            "receipt_execution_outcomes": [
                {
                    "receipt": {
                        "predecessor_id": "alice.near",
                        "receiver_id": "contract.near",
                    },
                    "tx_hash": "tx_hash_3",
                    "execution_outcome": {"status": {"SuccessValue": ""}},
                },
            ],
        }
    ],
}

LAST_BLOCK_RESPONSE = {
    "block": {
        "header": {"height": 100_000_005}
    }
}


def _run(coro):
    """Run an async coroutine synchronously (no pytest-asyncio needed)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
    return NearStreamFetcher(pool)


# ---------------------------------------------------------------------------
# fetch_block tests
# ---------------------------------------------------------------------------

class TestFetchBlock:
    def test_fetch_block_valid(self, fetcher):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=json.dumps(SAMPLE_BLOCK))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)

        result = _run(fetcher.fetch_block(mock_session, 100_000_001))
        assert result is not None
        assert result["block"]["header"]["height"] == 100_000_001

    def test_fetch_block_null_response(self, fetcher):
        """neardata.xyz returns string 'null' for missing blocks."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="null")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)

        result = _run(fetcher.fetch_block(mock_session, 100_000_002))
        assert result is None

    def test_fetch_block_429_retries(self, fetcher):
        """Should retry on 429 and eventually succeed."""
        error_response = AsyncMock()
        error_response.status = 429
        error_response.text = AsyncMock(return_value="rate limited")
        error_response.__aenter__ = AsyncMock(return_value=error_response)
        error_response.__aexit__ = AsyncMock(return_value=False)

        ok_response = AsyncMock()
        ok_response.status = 200
        ok_response.text = AsyncMock(return_value=json.dumps(SAMPLE_BLOCK))
        ok_response.__aenter__ = AsyncMock(return_value=ok_response)
        ok_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=[error_response, ok_response])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = _run(fetcher.fetch_block(mock_session, 100_000_001))

        assert result is not None


# ---------------------------------------------------------------------------
# extract_wallet_txs tests
# ---------------------------------------------------------------------------

class TestExtractWalletTxs:
    def test_extract_matches_signer(self, fetcher):
        tracked = {"alice.near"}
        txs = fetcher.extract_wallet_txs(SAMPLE_BLOCK, tracked)
        hashes = {tx["tx_hash"] for tx in txs}
        assert "tx_hash_1" in hashes

    def test_extract_matches_receiver(self, fetcher):
        tracked = {"bob.near"}
        txs = fetcher.extract_wallet_txs(SAMPLE_BLOCK, tracked)
        hashes = {tx["tx_hash"] for tx in txs}
        assert "tx_hash_1" in hashes

    def test_extract_no_match(self, fetcher):
        tracked = {"nobody.near"}
        txs = fetcher.extract_wallet_txs(SAMPLE_BLOCK, tracked)
        assert txs == []

    def test_extract_receipt_match(self, fetcher):
        """Should match receipts where predecessor_id is a tracked wallet."""
        tracked = {"alice.near"}
        txs = fetcher.extract_wallet_txs(SAMPLE_BLOCK, tracked)
        hashes = {tx["tx_hash"] for tx in txs}
        assert "tx_hash_3" in hashes

    def test_extract_deduplicates_within_block(self, fetcher):
        """Same tx_hash should not appear twice even if matched in both tx and receipt."""
        tracked = {"alice.near"}
        txs = fetcher.extract_wallet_txs(SAMPLE_BLOCK, tracked)
        hashes = [tx["tx_hash"] for tx in txs]
        assert len(hashes) == len(set(hashes))

    def test_extract_returns_block_metadata(self, fetcher):
        tracked = {"alice.near"}
        txs = fetcher.extract_wallet_txs(SAMPLE_BLOCK, tracked)
        tx = txs[0]
        assert tx["block_height"] == 100_000_001
        assert tx["block_timestamp"] == 1700000000  # converted from ns

    def test_extract_handles_empty_block(self, fetcher):
        empty_block = {"block": {"header": {"height": 1}}, "shards": []}
        txs = fetcher.extract_wallet_txs(empty_block, {"alice.near"})
        assert txs == []

    def test_extract_handles_none_block(self, fetcher):
        txs = fetcher.extract_wallet_txs(None, {"alice.near"})
        assert txs == []


# ---------------------------------------------------------------------------
# get_last_final_block tests
# ---------------------------------------------------------------------------

class TestGetLastFinalBlock:
    def test_returns_height(self, fetcher):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=LAST_BLOCK_RESPONSE)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)

        height = _run(fetcher.get_last_final_block(mock_session))
        assert height == 100_000_005


# ---------------------------------------------------------------------------
# stream_blocks tests
# ---------------------------------------------------------------------------

class TestStreamBlocks:
    def test_stream_calls_callback_with_txs(self, fetcher):
        """stream_blocks should poll, fetch new blocks, and call callback with txs."""
        callback = AsyncMock()
        call_count = 0

        async def mock_get_last_final_block(session):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return 100_000_003
            raise asyncio.CancelledError()

        async def mock_fetch_block(session, height):
            return SAMPLE_BLOCK

        fetcher.get_last_final_block = mock_get_last_final_block
        fetcher.fetch_block = mock_fetch_block

        with patch("asyncio.sleep", new_callable=AsyncMock):
            try:
                _run(fetcher.stream_blocks(
                    100_000_001, {"alice.near"}, callback, session=MagicMock()
                ))
            except asyncio.CancelledError:
                pass

        assert callback.call_count >= 1
