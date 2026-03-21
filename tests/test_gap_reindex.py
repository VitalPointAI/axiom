"""Tests for gap detection re-index with loop protection."""

from unittest.mock import MagicMock

import pytest

from indexers.gap_reindex import (
    MAX_REINDEX_PER_DAY,
    get_reindex_count_today,
    queue_reindex_if_needed,
)


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value = cursor
    return pool, conn, cursor


class TestGetReindexCountToday:
    def test_returns_count(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchone.return_value = (2,)
        count = get_reindex_count_today(pool, user_id=10, wallet_id=1)
        assert count == 2

    def test_returns_zero_on_error(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.execute.side_effect = Exception("DB error")
        count = get_reindex_count_today(pool, user_id=10, wallet_id=1)
        assert count == 0

    def test_queries_correct_wallet(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchone.return_value = (0,)
        get_reindex_count_today(pool, user_id=10, wallet_id=42)
        args = cursor.execute.call_args[0][1]
        assert args == (10, 42)


class TestQueueReindexIfNeeded:
    def test_queues_when_under_cap(self, mock_pool):
        pool, conn, cursor = mock_pool
        # First call: get_reindex_count_today returns 1
        cursor.fetchone.return_value = (1,)

        result = queue_reindex_if_needed(
            pool, user_id=10, wallet_id=1, chain="near",
            mismatch_info={"difference": "0.5"},
        )
        assert result is True

    def test_blocked_when_at_cap(self, mock_pool):
        pool, conn, cursor = mock_pool
        # get_reindex_count_today returns MAX_REINDEX_PER_DAY
        cursor.fetchone.return_value = (MAX_REINDEX_PER_DAY,)

        result = queue_reindex_if_needed(
            pool, user_id=10, wallet_id=1, chain="near",
            mismatch_info={"difference": "0.5"},
        )
        assert result is False

    def test_sets_manual_review_when_capped(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchone.return_value = (MAX_REINDEX_PER_DAY,)

        queue_reindex_if_needed(
            pool, user_id=10, wallet_id=1, chain="near",
            mismatch_info={},
        )

        # Should have called UPDATE verification_results
        update_calls = [
            c for c in cursor.execute.call_args_list
            if "manual_review_required" in str(c)
        ]
        assert len(update_calls) >= 1

    def test_inserts_reindex_job_with_chain_prefix(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchone.return_value = (0,)

        queue_reindex_if_needed(
            pool, user_id=10, wallet_id=1, chain="ethereum",
            mismatch_info={"difference": "0.01"},
        )

        insert_calls = [
            c for c in cursor.execute.call_args_list
            if "INSERT INTO indexing_jobs" in str(c)
        ]
        assert len(insert_calls) >= 1
        # Check job_type contains chain name
        insert_args = insert_calls[0][0][1]
        assert "ethereum_reindex" in insert_args

    def test_returns_false_on_insert_error(self, mock_pool):
        pool, conn, cursor = mock_pool
        # First call for count succeeds
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return  # count query
            raise Exception("insert failed")

        cursor.execute.side_effect = side_effect
        cursor.fetchone.return_value = (0,)

        result = queue_reindex_if_needed(
            pool, user_id=10, wallet_id=1, chain="near",
            mismatch_info={},
        )
        assert result is False

    def test_max_reindex_per_day_is_three(self):
        assert MAX_REINDEX_PER_DAY == 3
