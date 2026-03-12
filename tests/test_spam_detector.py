"""Unit tests for SpamDetector — multi-signal spam detection with adaptive learning.

Covers:
- Dust amount detection
- Known spam contract matching
- Multi-signal threshold (2+ signals required for auto-spam >= 0.90)
- Legitimate transaction not flagged
- User tag creates spam_rules DB record
- Global propagation queries without user_id filter

All tests use mocked DB connections — no live database required.
"""

from unittest.mock import MagicMock, call

import pytest

from engine.spam_detector import SpamDetector


def make_pool(fetchall_return=None, fetchone_return=None):
    """Create a mock psycopg2 pool returning a mock cursor."""
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_return or []
    cursor.fetchone.return_value = fetchone_return

    conn = MagicMock()
    conn.cursor.return_value = cursor

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool, conn, cursor


class TestSpamDetection:
    """Core spam detection: dust amounts and known contract addresses."""

    def test_dust_amount_flagged(self):
        """Dust token transfer (< DUST_THRESHOLD) + direction='in' (unsolicited) -> spam >= 0.90."""
        # No spam rules in DB (rules check returns empty)
        pool, conn, cursor = make_pool(fetchall_return=[])
        sd = SpamDetector(pool)

        tx = {
            "id": 1,
            "direction": "in",
            "amount": 0.00001,         # well below 0.001 threshold
            "amount_usd": 0.000001,    # negligible USD value
            "counterparty": "unknown.contract",
            "action_type": "TRANSFER",
            "token_id": None,
        }
        result = sd.check_spam(user_id=1, tx=tx)

        # Dust + unsolicited (direction='in') = 2 signals => should hit >= 0.90
        assert result["confidence"] >= 0.90, f"Expected >= 0.90, got {result['confidence']}"
        assert result["is_spam"] is True
        assert len(result["signals"]) >= 2

    def test_known_spam_contract(self):
        """Transaction from address matching spam_rules.contract_address -> confidence 0.99."""
        # Return a contract_address spam rule matching the counterparty
        rules = [
            (1, None, "contract_address", "spammy.contract", True),
        ]
        pool, conn, cursor = make_pool(fetchall_return=rules)
        sd = SpamDetector(pool)

        tx = {
            "id": 2,
            "direction": "in",
            "amount": 100.0,
            "amount_usd": 50.0,
            "counterparty": "spammy.contract",
            "action_type": "TRANSFER",
            "token_id": None,
        }
        result = sd.check_spam(user_id=1, tx=tx)

        assert result["confidence"] >= 0.99
        assert result["is_spam"] is True
        assert "known_spam_contract" in result["signals"]

    def test_legitimate_not_flagged(self):
        """Normal-value user-initiated transaction -> not flagged as spam."""
        pool, conn, cursor = make_pool(fetchall_return=[])
        sd = SpamDetector(pool)

        tx = {
            "id": 3,
            "direction": "out",        # user-initiated
            "amount": 5000000,
            "amount_usd": 25.00,       # real market value
            "counterparty": "exchange.near",
            "action_type": "TRANSFER",
            "token_id": None,
        }
        result = sd.check_spam(user_id=1, tx=tx)

        assert result["is_spam"] is False
        assert result["confidence"] < 0.70

    def test_multi_signal_required(self):
        """Single dust signal alone should NOT exceed 0.90 (prevents false positives)."""
        pool, conn, cursor = make_pool(fetchall_return=[])
        sd = SpamDetector(pool)

        # Dust amount but user-initiated (direction='out') — only 1 signal
        tx = {
            "id": 4,
            "direction": "out",        # user sent it, so NOT unsolicited
            "amount": 0.00001,
            "amount_usd": 0.000001,
            "counterparty": "some.near",
            "action_type": "TRANSFER",
            "token_id": None,
        }
        result = sd.check_spam(user_id=1, tx=tx)

        assert result["confidence"] < 0.90, (
            f"Single signal should not exceed 0.90, got {result['confidence']}"
        )


class TestSpamLearning:
    """User-driven spam learning and global propagation."""

    def test_user_tag_creates_rule(self):
        """User marking tx as spam -> inserts row in spam_rules with user_id."""
        pool, conn, cursor = make_pool(
            # tx lookup returns a row with counterparty
            fetchone_return=(42, "spammer.near", None),
        )
        sd = SpamDetector(pool)

        sd.tag_as_spam(user_id=1, tx_id=42, source_type="contract_address")

        # Verify an INSERT into spam_rules was executed
        insert_calls = [
            c for c in cursor.execute.call_args_list
            if "INSERT" in str(c) and "spam_rules" in str(c)
        ]
        assert len(insert_calls) >= 1, "Expected INSERT INTO spam_rules"

        # Verify user_id was included in the INSERT parameters
        found_user_id = False
        for c in insert_calls:
            args = c[0]
            if len(args) > 1:
                params = args[1]
                if 1 in params or (hasattr(params, '__iter__') and 1 in list(params)):
                    found_user_id = True
        assert found_user_id, "user_id=1 must be in INSERT parameters"

    def test_global_propagation(self):
        """find_similar_spam() returns matching txs across ALL users (no user_id filter)."""
        # Rule lookup returns a contract_address rule
        rule_row = (10, None, "contract_address", "evil.contract", True)
        # Matching txs (across all users)
        matching_txs = [(100, 1), (200, 2), (300, 3)]

        pool = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        pool.getconn.return_value = conn
        cursor.fetchone.return_value = rule_row
        cursor.fetchall.return_value = matching_txs

        sd = SpamDetector(pool)
        results = sd.find_similar_spam(rule_id=10)

        assert len(results) == 3

        # Verify the query does NOT filter by user_id in WHERE clause
        # (global propagation searches across all users)
        # The SELECT may return user_id as a column, but must not filter on it.
        search_calls = [
            c for c in cursor.execute.call_args_list
            if "SELECT" in str(c) and "transactions" in str(c)
        ]
        assert len(search_calls) >= 1, "Expected a SELECT on transactions"
        for c in search_calls:
            sql = str(c[0][0]) if c[0] else ""
            # Check that the WHERE clause does not contain "user_id ="
            # (selecting user_id as a column is fine)
            sql_upper = sql.upper()
            where_idx = sql_upper.find("WHERE")
            if where_idx >= 0:
                where_clause = sql_upper[where_idx:]
                assert "USER_ID =" not in where_clause and "USER_ID=" not in where_clause, (
                    "Global propagation must not filter by user_id in WHERE clause"
                )
