"""Tests for DedupHandler — cross-source deduplication between on-chain and exchange data.

Tests use Mock objects to simulate database interactions without a real DB connection.
All tests verify the matching algorithm (asset+amount+timestamp+direction) and flagging behavior.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone


class TestDedupHandlerInit:
    """Test DedupHandler initialization."""

    def test_init_stores_pool(self):
        """DedupHandler stores the connection pool."""
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        handler = DedupHandler(mock_pool)
        assert handler.pool is mock_pool


class TestDedupMatchingLogic:
    """Test the core matching algorithm: asset+amount+timestamp+direction."""

    def test_matching_transactions_are_flagged(self):
        """Test 1: Matching transactions (same asset, similar amount, within 10 min) are linked.

        Exchange: received 1.0 ETH at 2024-01-15T12:00:00Z
        On-chain:  'in'    1000000000000000000 (wei) at 2024-01-15T12:03:00Z
        Expected: exchange tx flagged with needs_review=True, note referencing on-chain tx_hash.
        """
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Exchange tx: received 1.0 ETH, timestamp within 10 min of on-chain tx
        {
            "id": 101,
            "exchange": "coinbase",
            "tx_id": "CB-001",
            "tx_type": "receive",
            "asset": "ETH",
            "quantity": "1.0",
            "tx_date": datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        }

        # On-chain tx: 'in' direction, 1 ETH = 1e18 wei, timestamp 3 min later
        {
            "tx_hash": "0xabc123",
            "chain": "ethereum",
            "action_type": "in",
            "token_id": "ETH",
            "amount": "1000000000000000000",  # 1 ETH in wei (NUMERIC 40,0)
            "block_timestamp": datetime(2024, 1, 15, 12, 3, 0, tzinfo=timezone.utc),
        }

        # Step 1: fetchall returns one exchange tx not yet reviewed
        # Step 2: fetchall returns one on-chain tx that matches
        mock_cur.fetchall.side_effect = [
            [(101, "coinbase", "CB-001", "receive", "ETH", "1.0",
              datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc))],  # exchange txs
            [("0xabc123", "ethereum", "in", "ETH",
              "1000000000000000000",
              datetime(2024, 1, 15, 12, 3, 0, tzinfo=timezone.utc))],  # on-chain matches
        ]

        handler = DedupHandler(mock_pool)
        job = {"user_id": 1, "id": 999}
        handler.run_scan(job)

        # Verify: UPDATE was called to flag the exchange tx
        update_calls = [c for c in mock_cur.execute.call_args_list
                        if "UPDATE" in str(c) and "needs_review" in str(c)]
        assert len(update_calls) >= 1, "Expected UPDATE with needs_review=True for matched tx"

        # Verify: the update includes the on-chain tx_hash in the note
        update_args = str(update_calls[0])
        assert "0xabc123" in update_args, "Update note should reference on-chain tx_hash"

    def test_non_matching_different_asset_not_flagged(self):
        """Test 2a: Non-matching transactions (different asset) are NOT flagged.

        Exchange: received 1.0 BTC
        On-chain:  'in' 1.0 ETH
        Expected: no flag — asset mismatch.
        """
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Exchange tx: received 1.0 BTC
        mock_cur.fetchall.side_effect = [
            [(201, "coinbase", "CB-002", "receive", "BTC", "1.0",
              datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc))],  # exchange txs
            [],  # no on-chain matches (query filters by asset)
        ]

        handler = DedupHandler(mock_pool)
        job = {"user_id": 1, "id": 999}
        handler.run_scan(job)

        # Verify: no UPDATE with needs_review=True
        update_calls = [c for c in mock_cur.execute.call_args_list
                        if "UPDATE" in str(c) and "needs_review" in str(c)]
        assert len(update_calls) == 0, "Should not flag non-matching (different asset) tx"

    def test_non_matching_outside_time_window_not_flagged(self):
        """Test 2b: Non-matching transactions (outside 10-min window) are NOT flagged.

        Exchange: received 1.0 ETH at 12:00
        On-chain:  'in' 1 ETH at 12:15 (15 minutes later — outside window)
        Expected: no flag.
        """
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Exchange tx: received 1.0 ETH
        mock_cur.fetchall.side_effect = [
            [(301, "coinbase", "CB-003", "receive", "ETH", "1.0",
              datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc))],  # exchange txs
            [],  # no on-chain matches (query uses WHERE timestamp window)
        ]

        handler = DedupHandler(mock_pool)
        job = {"user_id": 1, "id": 999}
        handler.run_scan(job)

        # Verify: no UPDATE with needs_review=True
        update_calls = [c for c in mock_cur.execute.call_args_list
                        if "UPDATE" in str(c) and "needs_review" in str(c)]
        assert len(update_calls) == 0, "Should not flag tx outside 10-min timestamp window"

    def test_already_flagged_not_reprocessed(self):
        """Test 3: Already-flagged (needs_review=True) transactions are not re-processed.

        The query for exchange txs should filter out ones already flagged as duplicates.
        """
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # No exchange txs to process (all already reviewed)
        mock_cur.fetchall.return_value = []

        handler = DedupHandler(mock_pool)
        job = {"user_id": 1, "id": 999}
        handler.run_scan(job)

        # Verify the SELECT query filters out already-flagged txs
        select_calls = [c for c in mock_cur.execute.call_args_list
                        if "SELECT" in str(c)]
        assert len(select_calls) >= 1, "Should execute a SELECT query"

        # The first SELECT should filter out already-flagged duplicates
        first_select = str(select_calls[0])
        # Query should look for txs that haven't been checked yet (not already duplicate-flagged)
        assert "needs_review" in first_select or "dedup" in first_select.lower() or \
               "notes" in first_select.lower(), \
               "Query should filter out already-processed duplicate txs"

    def test_dedup_flags_with_needs_review_and_note(self):
        """Test 4: Dedup sets needs_review=True and adds explanatory note referencing on-chain tx.

        Verifies the flagging behavior: needs_review=True, notes contain 'Potential duplicate'
        and the on-chain tx_hash.
        """
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        on_chain_hash = "0xdeadbeef1234567890"

        mock_cur.fetchall.side_effect = [
            [(401, "crypto_com", "CC-001", "receive", "ETH", "0.5",
              datetime(2024, 2, 10, 9, 0, 0, tzinfo=timezone.utc))],  # exchange txs
            [(on_chain_hash, "ethereum", "in", "ETH",
              "500000000000000000",  # 0.5 ETH in wei
              datetime(2024, 2, 10, 9, 1, 30, tzinfo=timezone.utc))],  # on-chain match
        ]

        handler = DedupHandler(mock_pool)
        job = {"user_id": 1, "id": 999}
        handler.run_scan(job)

        # Find the UPDATE call that flags the exchange tx
        update_calls = [c for c in mock_cur.execute.call_args_list
                        if "UPDATE" in str(c) and "needs_review" in str(c)]
        assert len(update_calls) >= 1, "Should flag matched exchange tx"

        # The update args should contain: True (needs_review), the hash, exchange tx id
        all_update_str = str(update_calls)
        assert on_chain_hash in all_update_str, f"Note should contain on-chain hash {on_chain_hash}"

    def test_direction_alignment_send_matches_out(self):
        """Test direction alignment: exchange 'send'/'withdrawal' matches on-chain 'out'."""
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        mock_cur.fetchall.side_effect = [
            [(501, "coinbase", "CB-SEND-001", "send", "ETH", "2.0",
              datetime(2024, 3, 1, 10, 0, 0, tzinfo=timezone.utc))],  # exchange txs (send)
            [("0xsend123", "ethereum", "out", "ETH",
              "2000000000000000000",  # 2 ETH in wei
              datetime(2024, 3, 1, 10, 0, 45, tzinfo=timezone.utc))],  # on-chain out match
        ]

        handler = DedupHandler(mock_pool)
        job = {"user_id": 1, "id": 999}
        handler.run_scan(job)

        update_calls = [c for c in mock_cur.execute.call_args_list
                        if "UPDATE" in str(c) and "needs_review" in str(c)]
        assert len(update_calls) >= 1, "send/out direction should produce a match"

    def test_direction_mismatch_not_flagged(self):
        """Test direction mismatch: exchange 'receive' should NOT match on-chain 'out'."""
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        mock_cur.fetchall.side_effect = [
            [(601, "coinbase", "CB-DIR-001", "receive", "ETH", "1.0",
              datetime(2024, 3, 1, 10, 0, 0, tzinfo=timezone.utc))],  # exchange txs (receive)
            [],  # no on-chain matches (direction mismatch filtered by query)
        ]

        handler = DedupHandler(mock_pool)
        job = {"user_id": 1, "id": 999}
        handler.run_scan(job)

        update_calls = [c for c in mock_cur.execute.call_args_list
                        if "UPDATE" in str(c) and "needs_review" in str(c)]
        assert len(update_calls) == 0, "Mismatched direction should not produce a flag"

    def test_connection_returned_to_pool(self):
        """Test that connection is always returned to pool even if scan raises."""
        from indexers.dedup_handler import DedupHandler

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.side_effect = Exception("DB failure")

        handler = DedupHandler(mock_pool)
        job = {"user_id": 1, "id": 999}

        with pytest.raises(Exception, match="DB failure"):
            handler.run_scan(job)

        # Pool must always return conn even on exception
        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_amount_tolerance_one_percent(self):
        """Test 1% amount tolerance: 0.995 ETH exchange vs 1.0 ETH on-chain is a match."""
        from indexers.dedup_handler import DedupHandler

        # Test the tolerance calculation directly
        handler = DedupHandler(MagicMock())

        # 0.995 vs 1.0: difference is 0.5% — within tolerance
        assert handler._amounts_match("0.995", "1000000000000000000", "ETH") is True

        # 2.0 vs 1.0: difference is 100% — way outside tolerance
        assert handler._amounts_match("2.0", "1000000000000000000", "ETH") is False

        # 1.009 vs 1.0: difference is 0.9% — within 1% tolerance
        assert handler._amounts_match("1.009", "1000000000000000000", "ETH") is True

        # 1.02 vs 1.0: difference is 2% — outside 1% tolerance
        assert handler._amounts_match("1.02", "1000000000000000000", "ETH") is False
