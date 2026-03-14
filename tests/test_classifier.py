"""Tests for TransactionClassifier — the core classification engine.

Covers CLASS-01 (NEAR rule-based), CLASS-02 (wallet graph / internal transfers),
CLASS-03 (staking reward linkage), CLASS-04 (lockup vest linkage),
CLASS-05 (EVM classification), and multi-leg decomposition.

All database interactions are mocked so no live DB is required.
"""

from unittest.mock import MagicMock, patch

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
        next(r for r in results if r["leg_type"] == "parent")
        [r for r in results if r["leg_type"] != "parent"]
        fee = next(r for r in results if r["leg_type"] == "fee_leg")
        assert fee["leg_index"] == 2, f"fee_leg index should be 2, got {fee['leg_index']}"


# ---------------------------------------------------------------------------
# TestRulePriorityAndChainFilter (RC-10)
# ---------------------------------------------------------------------------


class TestRulePriorityAndChainFilter:
    """Rule priority resolution, conflict handling, chain filtering, and unknown fallthrough.

    Covers RC-10: classification rule interactions.
    """

    def _make_two_matching_rules(self, high_priority_category="staking_reward", low_priority_category="transfer"):
        """Return two rules that both match a NEAR FUNCTION_CALL with method_name='deposit_and_stake'.

        high_priority_rule has priority=100, low_priority_rule has priority=50.
        Rules are pre-sorted by priority DESC (as load_rules() guarantees).
        """
        high_priority_rule = {
            "id": 101,
            "name": "near_staking_high",
            "chain": "near",
            "pattern": {
                "action_type": "FUNCTION_CALL",
                "method_name": ["deposit_and_stake", "stake"],
            },
            "category": high_priority_category,
            "confidence": 0.95,
            "priority": 100,
        }
        low_priority_rule = {
            "id": 102,
            "name": "near_transfer_low",
            "chain": "near",
            "pattern": {
                "action_type": "FUNCTION_CALL",
                "method_name": ["deposit_and_stake", "transfer"],
            },
            "category": low_priority_category,
            "confidence": 0.70,
            "priority": 50,
        }
        # sorted by priority DESC — high comes first, first match wins
        return [high_priority_rule, low_priority_rule]

    def test_higher_priority_rule_wins_over_lower(self):
        """Higher-priority rule (100) wins when two rules match the same tx pattern.

        _match_rules() iterates rules in priority DESC order; the first match wins.
        """
        clf = _make_classifier()
        rules = self._make_two_matching_rules(
            high_priority_category="reward",
            low_priority_category="deposit",
        )

        tx = {
            "id": 700,
            "action_type": "FUNCTION_CALL",
            "method_name": "deposit_and_stake",
            "counterparty": "validator.poolv1.near",
            "direction": "out",
            "amount": 1000000000000000000000000,
            "raw_data": {},
        }
        result = clf._match_rules(tx, rules, chain="near")

        assert result is not None, "Expected a rule match"
        assert result["category"] == "reward", (
            f"Higher-priority rule (reward) should win, got {result['category']}"
        )

    def test_equal_priority_first_rule_wins(self):
        """When two rules share the same priority, the first in sorted order wins.

        Stable sort: if priority is equal, the rule added first to the list wins.
        This mirrors the DB ORDER BY priority DESC, id ASC stable ordering.
        """
        clf = _make_classifier()

        rule_a = {
            "id": 201,
            "name": "rule_a",
            "chain": "near",
            "pattern": {"action_type": "FUNCTION_CALL", "method_name": ["some_method"]},
            "category": "income",
            "confidence": 0.90,
            "priority": 75,
        }
        rule_b = {
            "id": 202,
            "name": "rule_b",
            "chain": "near",
            "pattern": {"action_type": "FUNCTION_CALL", "method_name": ["some_method"]},
            "category": "reward",
            "confidence": 0.85,
            "priority": 75,
        }
        # rule_a appears first in the list (lower id, DB stable sort)
        rules = [rule_a, rule_b]

        tx = {
            "id": 701,
            "action_type": "FUNCTION_CALL",
            "method_name": "some_method",
            "counterparty": "anyone.near",
            "direction": "out",
            "amount": 500,
            "raw_data": {},
        }
        result = clf._match_rules(tx, rules, chain="near")

        assert result is not None, "Expected a rule match"
        assert result["category"] == "income", (
            f"First rule in equal-priority list should win, got {result['category']}"
        )

    def test_conflicting_categories_resolved_by_priority(self):
        """Staking rule at priority 100 vs transfer rule at priority 50; staking wins."""
        clf = _make_classifier()

        staking_rule = {
            "id": 301,
            "name": "staking_high",
            "chain": "near",
            "pattern": {
                "action_type": "FUNCTION_CALL",
                "method_name": ["deposit_and_stake"],
                "counterparty_suffix": [".poolv1.near", ".pool.near"],
            },
            "category": "stake",
            "confidence": 0.95,
            "priority": 100,
        }
        transfer_rule = {
            "id": 302,
            "name": "transfer_low",
            "chain": "near",
            "pattern": {
                "action_type": "FUNCTION_CALL",
                "method_name": ["deposit_and_stake"],
            },
            "category": "deposit",
            "confidence": 0.60,
            "priority": 50,
        }
        rules = [staking_rule, transfer_rule]  # priority DESC order

        tx = {
            "id": 702,
            "action_type": "FUNCTION_CALL",
            "method_name": "deposit_and_stake",
            "counterparty": "myvalidator.poolv1.near",
            "direction": "out",
            "amount": 2000000000000000000000000,
            "raw_data": {},
        }
        result = clf._match_rules(tx, rules, chain="near")

        assert result is not None, "Expected a rule match"
        assert result["category"] == "stake", (
            f"Staking rule (priority=100) should beat transfer (priority=50); got {result['category']}"
        )

    def test_chain_filter_prevents_wrong_chain_rule(self):
        """A NEAR-specific rule (chain='near') does NOT match an EVM tx.

        Even if the method_name matches, the chain filter prevents cross-chain application.
        """
        clf = _make_classifier()

        # NEAR-only rule: matches deposit_and_stake on NEAR chain
        near_only_rule = {
            "id": 401,
            "name": "near_staking_rule",
            "chain": "near",  # NEAR-specific
            "pattern": {
                "method_name": ["deposit_and_stake"],
            },
            "category": "stake",
            "confidence": 0.95,
            "priority": 100,
        }

        # EVM tx with same method_name — should NOT match NEAR rule
        evm_tx = {
            "id": 703,
            "action_type": None,
            "method_name": "deposit_and_stake",
            "counterparty": "0xsomecontract",
            "direction": "out",
            "amount": 1000000,
            "raw_data": {"input": "0x"},
            "chain": "ethereum",
        }
        result = clf._match_rules(evm_tx, [near_only_rule], chain="evm")

        assert result is None, (
            f"NEAR-only rule should NOT match EVM tx; got {result}"
        )

    def test_no_match_falls_through_to_unknown(self):
        """A transaction that matches zero rules gets 'unknown' with needs_review=True.

        When _match_rules returns None (no rule matched), the AI fallback is invoked.
        We mock the AI to return 'unknown' (simulating no confidence) and assert the
        final classification is 'unknown' with needs_review=True.
        """
        clf = _make_classifier(rules=_near_rules())

        _ai_unknown = {
            "category": TaxCategory.UNKNOWN.value,
            "confidence": 0.30,
            "notes": "AI: no confident classification",
            "needs_review": True,
            "rule_id": None,
            "classification_source": "ai",
        }

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}), \
             patch.object(clf, "_classify_with_ai", return_value=_ai_unknown):

            # tx that won't match any rule in _near_rules():
            # - not a NEAR pool counterparty
            # - not a DEX method
            # - not a plain TRANSFER action_type
            tx = {
                "id": 704,
                "wallet_id": 10,
                "tx_hash": "unknown_hash_1",
                "action_type": "FUNCTION_CALL",
                "method_name": "totally_unknown_method_xyz",
                "counterparty": "random.contract.near",
                "direction": "in",
                "amount": 100,
                "block_timestamp": 1700000500,
                "success": True,
                "raw_data": {},
            }
            results = clf._classify_near_tx(
                user_id=1,
                tx=tx,
                rules=_near_rules(),
                owned_wallets=set(),
            )

        assert results, "Expected fallback classification result"
        parent = results[0]
        assert parent["category"] == TaxCategory.UNKNOWN.value, (
            f"Unmatched tx should fall through to 'unknown'; got {parent['category']}"
        )
        assert parent["needs_review"] is True, "Unknown category should always have needs_review=True"

    def test_concurrent_upsert_preserves_specialist_confirmed(self):
        """Upsert on a specialist_confirmed=True row does NOT overwrite the category.

        The SQL uses WHERE specialist_confirmed = FALSE; if the row has specialist_confirmed=True,
        fetchone() returns None (no RETURNING row), and the classification is left unchanged.
        """
        pool, conn, cur = _make_pool()

        # Simulate: INSERT ... ON CONFLICT ... WHERE specialist_confirmed = FALSE
        # If the existing row has specialist_confirmed=True, the DO UPDATE is skipped.
        # fetchone() returns None (no RETURNING row).
        cur.fetchone.return_value = None  # specialist_confirmed=True row -> no return

        clf = _make_classifier(pool=pool)

        # Build a record to upsert
        record = {
            "user_id": 1,
            "transaction_id": 999,
            "exchange_transaction_id": None,
            "leg_type": "parent",
            "leg_index": 0,
            "category": "deposit",  # trying to overwrite with a different category
            "confidence": 0.70,
            "classification_source": "rule",
            "rule_id": None,
            "staking_event_id": None,
            "lockup_event_id": None,
            "fmv_usd": None,
            "fmv_cad": None,
            "needs_review": True,
        }

        classification_id = clf._upsert_classification(conn, record)

        # Verify the SQL was called with WHERE specialist_confirmed = FALSE
        assert cur.execute.called, "cursor.execute should have been called"
        sql_called = cur.execute.call_args[0][0]
        assert "specialist_confirmed" in sql_called, (
            "Upsert SQL must contain specialist_confirmed guard"
        )
        # Since fetchone returned None (no row updated), classification_id should be 0 or falsy
        assert classification_id == 0, (
            f"specialist_confirmed=True row should not return an id; got {classification_id}"
        )

    def test_duplicate_classify_call_idempotent(self):
        """Calling _classify_near_tx twice on the same tx produces the same category.

        Idempotency: repeated classification produces identical results.
        """
        clf = _make_classifier(rules=_near_rules())

        tx = {
            "id": 705,
            "wallet_id": 10,
            "tx_hash": "idempotent_hash_1",
            "action_type": "FUNCTION_CALL",
            "method_name": "deposit_and_stake",
            "counterparty": "validator.poolv1.near",
            "direction": "out",
            "amount": 1000000000000000000000000,
            "block_timestamp": 1700000600,
            "success": True,
            "raw_data": {},
        }

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            results_first = clf._classify_near_tx(
                user_id=1, tx=tx, rules=_near_rules(), owned_wallets=set()
            )

        with patch.object(clf.wallet_graph, "is_internal_transfer", return_value=False), \
             patch.object(clf.spam_detector, "check_spam", return_value={"is_spam": False, "confidence": 0.0, "signals": []}):

            results_second = clf._classify_near_tx(
                user_id=1, tx=tx, rules=_near_rules(), owned_wallets=set()
            )

        assert results_first, "First classify call should produce results"
        assert results_second, "Second classify call should produce results"
        assert results_first[0]["category"] == results_second[0]["category"], (
            f"Idempotent: first={results_first[0]['category']}, second={results_second[0]['category']}"
        )
        assert results_first[0]["confidence"] == results_second[0]["confidence"], (
            "Repeated classification should produce same confidence"
        )


# ---------------------------------------------------------------------------
# TestMultiHopSwapDecomposition
# ---------------------------------------------------------------------------

class TestMultiHopSwapDecomposition:
    """Multi-hop swap leg decomposition via _decompose_swap with token_path."""

    TOKEN_A = "0x" + "aa" * 20
    TOKEN_B = "0x" + "bb" * 20
    TOKEN_C = "0x" + "cc" * 20
    TOKEN_D = "0x" + "dd" * 20

    def _make_clf(self):
        pool, conn, cur = _make_pool()
        cur.fetchone.return_value = (42,)  # upsert returns an id
        clf = _make_classifier(pool)
        return clf

    def _swap_category_result(self, hop_count=1, token_path=None):
        return {
            "category": "trade",
            "confidence": 0.90,
            "notes": "EVM DEX swap: exactInput (uniswap_v3)",
            "needs_review": False,
            "rule_id": None,
            "hop_count": hop_count,
            "token_path": token_path or [],
        }

    def _parent_tx(self, tx_id=99, fee=None):
        return {
            "id": tx_id,
            "raw_data": {},
            "fee": fee,
        }

    def test_multi_hop_3_hop_swap_produces_4_legs(self):
        """3-hop swap (A->B->C) produces parent + sell_leg + intermediate_leg_1 + buy_leg = 4 records."""
        clf = self._make_clf()
        parent_tx = self._parent_tx()
        category_result = self._swap_category_result(
            hop_count=2,
            token_path=[self.TOKEN_A, self.TOKEN_B, self.TOKEN_C],
        )
        records = clf._decompose_swap(parent_tx, category_result)

        assert len(records) == 4, f"Expected 4 records, got {len(records)}"
        leg_types = [r["leg_type"] for r in records]
        assert "parent" in leg_types
        assert "sell_leg" in leg_types
        assert "intermediate_leg_1" in leg_types
        assert "buy_leg" in leg_types

    def test_multi_hop_4_hop_swap_produces_5_legs(self):
        """4-hop swap (A->B->C->D) produces parent + sell + 2 intermediate + buy = 5 records."""
        clf = self._make_clf()
        parent_tx = self._parent_tx()
        category_result = self._swap_category_result(
            hop_count=3,
            token_path=[self.TOKEN_A, self.TOKEN_B, self.TOKEN_C, self.TOKEN_D],
        )
        records = clf._decompose_swap(parent_tx, category_result)

        assert len(records) == 5, f"Expected 5 records, got {len(records)}"
        leg_types = [r["leg_type"] for r in records]
        assert "parent" in leg_types
        assert "sell_leg" in leg_types
        assert "intermediate_leg_1" in leg_types
        assert "intermediate_leg_2" in leg_types
        assert "buy_leg" in leg_types

    def test_multi_hop_intermediate_has_needs_review(self):
        """Multi-hop swap sets needs_review=True on parent and intermediate legs."""
        clf = self._make_clf()
        parent_tx = self._parent_tx()
        category_result = self._swap_category_result(
            hop_count=2,
            token_path=[self.TOKEN_A, self.TOKEN_B, self.TOKEN_C],
        )
        records = clf._decompose_swap(parent_tx, category_result)

        # Parent must be flagged needs_review due to missing intermediate FMV
        parent_rec = next(r for r in records if r["leg_type"] == "parent")
        assert parent_rec["needs_review"] is True, "Parent must have needs_review=True for multi-hop"

        # Intermediate must be flagged
        intermediate = next(r for r in records if r["leg_type"] == "intermediate_leg_1")
        assert intermediate["needs_review"] is True

    def test_standard_2_hop_swap_unchanged(self):
        """Standard 2-hop swap (no token_path > 2) still produces 3 records: parent, sell, buy."""
        clf = self._make_clf()
        parent_tx = self._parent_tx()
        category_result = self._swap_category_result(hop_count=1, token_path=[])
        records = clf._decompose_swap(parent_tx, category_result)

        assert len(records) == 3, f"Expected 3 records for standard swap, got {len(records)}"
        leg_types = [r["leg_type"] for r in records]
        assert "parent" in leg_types
        assert "sell_leg" in leg_types
        assert "buy_leg" in leg_types
        assert not any("intermediate" in lt for lt in leg_types)


# ---------------------------------------------------------------------------
# Classifier Invariant Batch Checks
# ---------------------------------------------------------------------------


class TestClassifierInvariants:
    """Tests for check_classifier_invariants_batch — detect structural issues."""

    def test_invariant_missing_parent(self):
        """Transaction with 0 parent classifications is detected."""
        from engine.classifier.writer import check_classifier_invariants_batch

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # First query (parent count): tx_id=42 with 0 parents
        # Second query (swap leg balance): no results
        mock_cursor.fetchall.side_effect = [[(42, 0)], []]
        mock_conn.cursor.return_value = mock_cursor

        violations = check_classifier_invariants_batch(mock_conn, user_id=1)
        assert len(violations) >= 1
        assert violations[0]["transaction_id"] == 42
        assert violations[0]["parent_count"] == 0

    def test_invariant_duplicate_parent(self):
        """Transaction with 2 parent classifications is detected."""
        from engine.classifier.writer import check_classifier_invariants_batch

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [[(99, 2)], []]
        mock_conn.cursor.return_value = mock_cursor

        violations = check_classifier_invariants_batch(mock_conn, user_id=1)
        assert len(violations) >= 1
        assert violations[0]["parent_count"] == 2

    def test_invariant_clean_state(self):
        """No violations returns empty list."""
        from engine.classifier.writer import check_classifier_invariants_batch

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [[], []]
        mock_conn.cursor.return_value = mock_cursor

        violations = check_classifier_invariants_batch(mock_conn, user_id=1)
        assert violations == []

    def test_invariant_swap_leg_imbalance(self):
        """Swap with missing buy_leg is detected."""
        from engine.classifier.writer import check_classifier_invariants_batch

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # First query (parent count): clean
        # Second query (swap legs): cls_id=50, tx_id=10, 1 sell, 0 buy, 0 fee
        mock_cursor.fetchall.side_effect = [[], [(50, 10, 1, 0, 0)]]
        mock_conn.cursor.return_value = mock_cursor

        violations = check_classifier_invariants_batch(mock_conn, user_id=1)
        assert len(violations) >= 1
        assert violations[0]["buy_legs"] == 0
