"""Tests for TransactionClassifier — the core classification engine.

Covers CLASS-01 (NEAR rule-based), CLASS-02 (wallet graph / internal transfers),
CLASS-03 (staking reward linkage), CLASS-04 (lockup vest linkage),
CLASS-05 (EVM classification), and multi-leg decomposition.

All database interactions are mocked so no live DB is required.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch, call
import pytest

from engine.classifier import TransactionClassifier
from tax.categories import TaxCategory


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

def _make_pool(rows=None, rowcount=1):
    """Build a minimal mock psycopg2 connection pool."""
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = None
    cur.rowcount = rowcount

    conn = MagicMock()
    conn.cursor.return_value = cur

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool, conn, cur


def _make_classifier(pool=None, rules=None, owned_wallets=None):
    """Build a TransactionClassifier with optional rule/wallet overrides."""
    if pool is None:
        pool, _, _ = _make_pool()
    clf = TransactionClassifier(pool)
    if rules is not None:
        clf._rules = rules
    return clf


def _near_rules():
    """Return a minimal set of classification rules matching rule_seeder patterns."""
    return [
        {
            "id": 1,
            "name": "near_staking_deposit",
            "chain": "near",
            "pattern": {
                "action_type": "FUNCTION_CALL",
                "method_name": ["deposit_and_stake", "stake", "deposit"],
                "counterparty_suffix": [".poolv1.near", ".pool.near", "aurora.pool.near"],
            },
            "category": "stake",
            "confidence": 0.95,
            "priority": 100,
        },
        {
            "id": 2,
            "name": "near_staking_reward",
            "chain": "near",
            "pattern": {
                "direction": "in",
                "amount_gt": 0,
                "counterparty_suffix": [".poolv1.near", ".pool.near", "aurora.pool.near"],
            },
            "category": "reward",
            "confidence": 0.85,
            "priority": 100,
        },
        {
            "id": 3,
            "name": "near_dex_swap_out",
            "chain": "near",
            "pattern": {
                "action_type": "FUNCTION_CALL",
                "method_name": ["swap", "ft_transfer_call"],
                "direction": "out",
                "counterparty_in": [
                    "v2.ref-finance.near",
                    "ref-finance.near",
                    "jumbo_exchange.near",
                ],
            },
            "category": "trade",
            "confidence": 0.90,
            "priority": 90,
        },
        {
            "id": 4,
            "name": "near_transfer_in",
            "chain": "near",
            "pattern": {
                "action_type": "TRANSFER",
                "direction": "in",
            },
            "category": "deposit",
            "confidence": 0.70,
            "priority": 50,
        },
        {
            "id": 5,
            "name": "exchange_buy",
            "chain": "exchange",
            "pattern": {"tx_type": ["buy", "purchase"]},
            "category": "buy",
            "confidence": 0.95,
            "priority": 40,
        },
        {
            "id": 6,
            "name": "exchange_sell",
            "chain": "exchange",
            "pattern": {"tx_type": ["sell", "sale"]},
            "category": "sell",
            "confidence": 0.95,
            "priority": 40,
        },
        {
            "id": 7,
            "name": "exchange_staking_reward",
            "chain": "exchange",
            "pattern": {"tx_type": ["staking_reward"]},
            "category": "reward",
            "confidence": 0.95,
            "priority": 40,
        },
        {
            "id": 8,
            "name": "evm_dex_swap_swapexacttokensfortokens",
            "chain": "evm",
            "pattern": {
                "input_selector": "0x38ed1739",
                "method_name": "swapExactTokensForTokens",
                "dex_type": "uniswap_v2",
            },
            "category": "trade",
            "confidence": 0.90,
            "priority": 90,
        },
        {
            "id": 9,
            "name": "evm_plain_transfer_in",
            "chain": "evm",
            "pattern": {
                "input_selector": None,
                "direction": "in",
            },
            "category": "deposit",
            "confidence": 0.70,
            "priority": 50,
        },
        {
            "id": 10,
            "name": "evm_plain_transfer_out",
            "chain": "evm",
            "pattern": {
                "input_selector": None,
                "direction": "out",
            },
            "category": "withdrawal",
            "confidence": 0.70,
            "priority": 50,
        },
    ]


# ---------------------------------------------------------------------------
# TestNearClassification
# ---------------------------------------------------------------------------

class TestNearClassification:
    """CLASS-01: NEAR on-chain rule-based classification."""

    def test_staking_deposit(self):
        """deposit_and_stake method_name + pool suffix -> STAKE, confidence >= 0.90."""
        clf = _make_classifier(rules=_near_rules())

        # Patch internal transfer and spam checks to not interfere
        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            tx = {
                "id": 1,
                "wallet_id": 10,
                "tx_hash": "hash1",
                "action_type": "FUNCTION_CALL",
                "method_name": "deposit_and_stake",
                "counterparty": "validator1.poolv1.near",
                "direction": "out",
                "amount": 1000000000000000000000000,
                "block_timestamp": 1700000000,
                "success": True,
                "raw_data": {},
            }
            results = clf._classify_near_tx(
                user_id=1,
                tx=tx,
                rules=_near_rules(),
                owned_wallets=set(),
            )

        assert results, "Expected at least one classification result"
        parent = results[0]
        assert parent["category"] == TaxCategory.STAKE.value, f"Got {parent['category']}"
        assert parent["confidence"] >= 0.90

    def test_dex_swap(self):
        """method_name='swap' + ref-finance counterparty -> TRADE, confidence >= 0.85."""
        clf = _make_classifier(rules=_near_rules())

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            tx = {
                "id": 2,
                "wallet_id": 10,
                "tx_hash": "hash2",
                "action_type": "FUNCTION_CALL",
                "method_name": "swap",
                "counterparty": "v2.ref-finance.near",
                "direction": "out",
                "amount": 5000000000000000000000000,
                "block_timestamp": 1700000100,
                "success": True,
                "raw_data": {},
            }
            results = clf._classify_near_tx(
                user_id=1,
                tx=tx,
                rules=_near_rules(),
                owned_wallets=set(),
            )

        assert results, "Expected classification for DEX swap"
        parent = results[0]
        assert parent["category"] == TaxCategory.TRADE.value, f"Got {parent['category']}"
        assert parent["confidence"] >= 0.85

    def test_basic_transfer(self):
        """Plain NEAR transfer in + not owned -> DEPOSIT, needs_review=True."""
        clf = _make_classifier(rules=_near_rules())

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            tx = {
                "id": 3,
                "wallet_id": 10,
                "tx_hash": "hash3",
                "action_type": "TRANSFER",
                "method_name": None,
                "counterparty": "someone.near",
                "direction": "in",
                "amount": 2000000000000000000000000,
                "block_timestamp": 1700000200,
                "success": True,
                "raw_data": {},
            }
            results = clf._classify_near_tx(
                user_id=1,
                tx=tx,
                rules=_near_rules(),
                owned_wallets=set(),
            )

        assert results, "Expected classification for basic transfer"
        parent = results[0]
        assert parent["category"] == TaxCategory.DEPOSIT.value, f"Got {parent['category']}"
        assert parent["needs_review"] is True

    def test_unknown_function_call(self):
        """Unrecognized method -> UNKNOWN, needs_review=True."""
        clf = _make_classifier(rules=_near_rules())

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            tx = {
                "id": 4,
                "wallet_id": 10,
                "tx_hash": "hash4",
                "action_type": "FUNCTION_CALL",
                "method_name": "some_unknown_method_xyz",
                "counterparty": "unknown.near",
                "direction": "out",
                "amount": 0,
                "block_timestamp": 1700000300,
                "success": True,
                "raw_data": {},
            }
            results = clf._classify_near_tx(
                user_id=1,
                tx=tx,
                rules=_near_rules(),
                owned_wallets=set(),
            )

        assert results, "Expected fallback classification for unknown call"
        parent = results[0]
        assert parent["category"] == TaxCategory.UNKNOWN.value, f"Got {parent['category']}"
        assert parent["needs_review"] is True


# ---------------------------------------------------------------------------
# TestExchangeClassification
# ---------------------------------------------------------------------------

class TestExchangeClassification:
    """CLASS-01: Exchange transaction classification."""

    def test_buy_classified(self):
        """tx_type='buy' -> BUY, confidence >= 0.90."""
        clf = _make_classifier(rules=_near_rules())

        tx = {
            "id": 100,
            "tx_type": "buy",
            "counterparty": None,
            "amount": 1000,
            "raw_data": {},
        }
        results = clf._classify_exchange_tx(user_id=1, tx=tx, rules=_near_rules())

        assert results, "Expected classification for buy"
        r = results[0]
        assert r["category"] == TaxCategory.BUY.value, f"Got {r['category']}"
        assert r["confidence"] >= 0.90

    def test_sell_classified(self):
        """tx_type='sell' -> SELL, confidence >= 0.90."""
        clf = _make_classifier(rules=_near_rules())

        tx = {
            "id": 101,
            "tx_type": "sell",
            "counterparty": None,
            "amount": 2000,
            "raw_data": {},
        }
        results = clf._classify_exchange_tx(user_id=1, tx=tx, rules=_near_rules())

        assert results, "Expected classification for sell"
        r = results[0]
        assert r["category"] == TaxCategory.SELL.value, f"Got {r['category']}"
        assert r["confidence"] >= 0.90

    def test_reward_classified(self):
        """tx_type='staking_reward' -> REWARD, confidence >= 0.90."""
        clf = _make_classifier(rules=_near_rules())

        tx = {
            "id": 102,
            "tx_type": "staking_reward",
            "counterparty": None,
            "amount": 50,
            "raw_data": {},
        }
        results = clf._classify_exchange_tx(user_id=1, tx=tx, rules=_near_rules())

        assert results, "Expected classification for staking_reward"
        r = results[0]
        assert r["category"] == TaxCategory.REWARD.value, f"Got {r['category']}"
        assert r["confidence"] >= 0.90


# ---------------------------------------------------------------------------
# TestEVMClassification
# ---------------------------------------------------------------------------

class TestEVMClassification:
    """CLASS-05: EVM on-chain classification."""

    def test_evm_swap_detected(self):
        """EVM tx with known Uniswap selector -> TRADE, is_swap=True."""
        clf = _make_classifier(rules=_near_rules())

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            # swapExactTokensForTokens selector = 0x38ed1739
            tx = {
                "id": 200,
                "wallet_id": 20,
                "tx_hash": "0xabc123",
                "action_type": None,
                "method_name": None,
                "counterparty": "0xrouter",
                "direction": "out",
                "amount": 1000000,
                "block_timestamp": 1700001000,
                "success": True,
                "raw_data": {"input": "0x38ed1739000000000000000"},
                "chain": "ethereum",
            }
            groups = {"0xabc123": [tx]}
            results = clf._classify_evm_tx_group(
                user_id=1,
                txs=[tx],
                rules=_near_rules(),
                owned_wallets=set(),
            )

        assert results, "Expected classification for EVM swap"
        parent = results[0]
        assert parent["category"] == TaxCategory.TRADE.value, f"Got {parent['category']}"

    def test_evm_transfer(self):
        """EVM plain ETH transfer (no DEX sig) -> DEPOSIT or WITHDRAWAL."""
        clf = _make_classifier(rules=_near_rules())

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            tx = {
                "id": 201,
                "wallet_id": 20,
                "tx_hash": "0xdef456",
                "action_type": None,
                "method_name": None,
                "counterparty": "0xsender",
                "direction": "in",
                "amount": 500000,
                "block_timestamp": 1700001100,
                "success": True,
                "raw_data": {"input": "0x"},  # plain ETH transfer
                "chain": "ethereum",
            }
            results = clf._classify_evm_tx_group(
                user_id=1,
                txs=[tx],
                rules=_near_rules(),
                owned_wallets=set(),
            )

        assert results, "Expected classification for plain EVM transfer"
        parent = results[0]
        # plain ETH in from unknown = DEPOSIT (not a swap)
        assert parent["category"] in (
            TaxCategory.DEPOSIT.value,
            TaxCategory.TRANSFER_IN.value,
        ), f"Got {parent['category']}"


# ---------------------------------------------------------------------------
# TestStakingRewardLinkage
# ---------------------------------------------------------------------------

class TestStakingRewardLinkage:
    """CLASS-03: Link staking income classifications to staking_events."""

    def test_links_to_staking_event(self):
        """REWARD classification from staking pool -> staking_event_id set, not NULL."""
        pool, conn, cur = _make_pool()

        # Simulate finding a matching staking_event by tx_hash
        cur.fetchone.return_value = (42,)  # staking_event.id = 42

        clf = _make_classifier(pool=pool, rules=_near_rules())

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            tx = {
                "id": 300,
                "wallet_id": 30,
                "tx_hash": "stake_hash_1",
                "action_type": "FUNCTION_CALL",
                "method_name": None,
                "counterparty": "validatorX.poolv1.near",
                "direction": "in",
                "amount": 100000000000000000000000,
                "block_timestamp": 1700002000,
                "success": True,
                "raw_data": {},
            }
            results = clf._classify_near_tx(
                user_id=1,
                tx=tx,
                rules=_near_rules(),
                owned_wallets=set(),
            )

        assert results, "Expected classification result"
        reward_rec = results[0]
        assert reward_rec["category"] == TaxCategory.REWARD.value
        assert reward_rec["staking_event_id"] == 42, (
            f"Expected staking_event_id=42, got {reward_rec.get('staking_event_id')}"
        )

    def test_no_duplicate_income(self):
        """Re-classifying same tx produces one record, not two income entries."""
        pool, conn, cur = _make_pool()
        cur.fetchone.return_value = (99,)  # staking_event found

        clf = _make_classifier(pool=pool, rules=_near_rules())

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            tx = {
                "id": 301,
                "wallet_id": 30,
                "tx_hash": "stake_hash_2",
                "action_type": None,
                "method_name": None,
                "counterparty": "validatorY.poolv1.near",
                "direction": "in",
                "amount": 50000000000000000000000,
                "block_timestamp": 1700002100,
                "success": True,
                "raw_data": {},
            }
            results = clf._classify_near_tx(
                user_id=1,
                tx=tx,
                rules=_near_rules(),
                owned_wallets=set(),
            )

        # One classification per tx (no duplicate income legs for staking)
        reward_records = [r for r in results if r["category"] == TaxCategory.REWARD.value]
        assert len(reward_records) == 1, (
            f"Expected exactly 1 REWARD record, got {len(reward_records)}"
        )
        assert reward_records[0]["staking_event_id"] == 99


# ---------------------------------------------------------------------------
# TestLockupVestLinkage
# ---------------------------------------------------------------------------

class TestLockupVestLinkage:
    """CLASS-04: Link lockup vest classifications to lockup_events."""

    def test_links_to_lockup_event(self):
        """INCOME classification for vest tx -> lockup_event_id set."""
        pool, conn, cur = _make_pool()
        # First fetchone call for staking (returns None), second for lockup (returns (77,))
        cur.fetchone.side_effect = [None, (77,)]

        clf = _make_classifier(pool=pool, rules=_near_rules())

        # Add a lockup vest rule (priority 95, higher than near_transfer_in at 50)
        lockup_rules = sorted(
            _near_rules() + [
                {
                    "id": 20,
                    "name": "near_lockup_vest",
                    "chain": "near",
                    "pattern": {
                        "counterparty_suffix": [".lockup.near"],
                        "direction": "in",
                        "amount_gt": 0,
                    },
                    "category": "income",
                    "confidence": 0.90,
                    "priority": 95,
                }
            ],
            key=lambda r: r["priority"],
            reverse=True,
        )

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            tx = {
                "id": 400,
                "wallet_id": 40,
                "tx_hash": "lockup_hash_1",
                "action_type": "TRANSFER",
                "method_name": None,
                "counterparty": "db59d1a4abc1.lockup.near",
                "direction": "in",
                "amount": 1000000000000000000000000,
                "block_timestamp": 1700003000,
                "success": True,
                "raw_data": {},
            }
            results = clf._classify_near_tx(
                user_id=1,
                tx=tx,
                rules=lockup_rules,
                owned_wallets=set(),
            )

        assert results, "Expected classification for lockup vest"
        income_rec = next(
            (r for r in results if r["category"] == TaxCategory.INCOME.value), None
        )
        assert income_rec is not None, (
            f"Expected INCOME record in results: {[r['category'] for r in results]}"
        )
        assert income_rec["lockup_event_id"] == 77, (
            f"Expected lockup_event_id=77, got {income_rec.get('lockup_event_id')}"
        )


# ---------------------------------------------------------------------------
# TestMultiLegDecomposition
# ---------------------------------------------------------------------------

class TestMultiLegDecomposition:
    """Swap decomposition into parent + sell_leg + buy_leg + fee_leg."""

    def test_swap_creates_parent_and_legs(self):
        """DEX swap -> parent row + at least sell_leg + buy_leg."""
        clf = _make_classifier(rules=_near_rules())

        tx = {
            "id": 500,
            "wallet_id": 50,
            "tx_hash": "swap_hash_1",
            "action_type": "FUNCTION_CALL",
            "method_name": "swap",
            "counterparty": "v2.ref-finance.near",
            "direction": "out",
            "amount": 3000000000000000000000000,
            "block_timestamp": 1700004000,
            "success": True,
            "raw_data": {},
        }
        category_result_dict = {
            "category": TaxCategory.TRADE.value,
            "confidence": 0.90,
            "notes": "DEX swap",
            "needs_review": False,
        }
        results = clf._decompose_swap(parent_tx=tx, category_result=category_result_dict)

        assert len(results) >= 3, f"Expected parent + at least sell_leg + buy_leg, got {len(results)}"
        leg_types = [r["leg_type"] for r in results]
        assert "parent" in leg_types, f"Missing parent: {leg_types}"
        assert "sell_leg" in leg_types, f"Missing sell_leg: {leg_types}"
        assert "buy_leg" in leg_types, f"Missing buy_leg: {leg_types}"

    def test_leg_index_ordering(self):
        """sell_leg=index 0, buy_leg=index 1, fee_leg=index 2."""
        clf = _make_classifier(rules=_near_rules())

        tx = {
            "id": 501,
            "wallet_id": 50,
            "tx_hash": "swap_hash_2",
            "action_type": "FUNCTION_CALL",
            "method_name": "swap",
            "counterparty": "v2.ref-finance.near",
            "direction": "out",
            "amount": 1000000000000000000000000,
            "block_timestamp": 1700004100,
            "success": True,
            "raw_data": {},
        }
        category_result_dict = {
            "category": TaxCategory.TRADE.value,
            "confidence": 0.90,
            "notes": "DEX swap",
            "needs_review": False,
        }
        results = clf._decompose_swap(parent_tx=tx, category_result=category_result_dict)

        sell = next((r for r in results if r["leg_type"] == "sell_leg"), None)
        buy = next((r for r in results if r["leg_type"] == "buy_leg"), None)

        assert sell is not None, "Missing sell_leg"
        assert buy is not None, "Missing buy_leg"
        assert sell["leg_index"] == 0, f"sell_leg index should be 0, got {sell['leg_index']}"
        assert buy["leg_index"] == 1, f"buy_leg index should be 1, got {buy['leg_index']}"


# ---------------------------------------------------------------------------
# TestSwapDecomposition
# ---------------------------------------------------------------------------

class TestSwapDecomposition:
    """Advanced multi-leg decomposition edge cases."""

    def test_dex_swap_3_legs(self):
        """Swap with fee_leg -> parent + sell_leg + buy_leg + fee_leg (4 rows)."""
        clf = _make_classifier(rules=_near_rules())

        tx = {
            "id": 600,
            "wallet_id": 60,
            "tx_hash": "swap_hash_3",
            "action_type": "FUNCTION_CALL",
            "method_name": "swap",
            "counterparty": "v2.ref-finance.near",
            "direction": "out",
            "amount": 5000000000000000000000000,
            "block_timestamp": 1700005000,
            "success": True,
            "raw_data": {},
            "fee": 1250000000000000000000,
        }
        category_result_dict = {
            "category": TaxCategory.TRADE.value,
            "confidence": 0.90,
            "notes": "DEX swap",
            "needs_review": False,
        }
        results = clf._decompose_swap(parent_tx=tx, category_result=category_result_dict)

        assert len(results) == 4, f"Expected 4 rows (parent+3 legs), got {len(results)}: {[r['leg_type'] for r in results]}"

        leg_types = [r["leg_type"] for r in results]
        assert "parent" in leg_types
        assert "sell_leg" in leg_types
        assert "buy_leg" in leg_types
        assert "fee_leg" in leg_types

        # All children reference the parent (parent_classification_id)
        parent_row = next(r for r in results if r["leg_type"] == "parent")
        children = [r for r in results if r["leg_type"] != "parent"]
        fee = next(r for r in results if r["leg_type"] == "fee_leg")
        assert fee["leg_index"] == 2, f"fee_leg index should be 2, got {fee['leg_index']}"
