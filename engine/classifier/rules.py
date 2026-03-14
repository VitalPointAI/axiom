"""
Rule matching and swap decomposition logic for TransactionClassifier.

Contains:
  - match_rules(): apply classification rules against a transaction
  - decompose_swap(): decompose a swap into parent + child legs (CLASS-05)
"""

import json
import logging
from decimal import Decimal

from tax.categories import TaxCategory

logger = logging.getLogger(__name__)


def match_rules(classifier, tx: dict, rules: list, chain: str) -> dict | None:
    """Match transaction against rules. First match wins (rules sorted by priority DESC).

    Pattern fields supported:
        method_name          - str or list[str]: exact match
        action_type          - str or list[str]: exact match
        counterparty_suffix  - str or list[str]: endswith check
        counterparty_in      - list[str]: exact counterparty match
        counterparty_contains - str: contains check
        tx_type              - str or list[str]: exact match (exchange rules)
        input_selector       - str or None: EVM 4-byte selector startswith
        direction            - str: exact match
        amount_gt            - numeric: amount must be > this value
        is_own_wallet        - bool: skipped (handled before rule matching)
    """
    tx_action = (tx.get("action_type") or "").upper()
    tx_method = (tx.get("method_name") or "").lower()
    tx_direction = tx.get("direction", "")
    tx_counterparty = (tx.get("counterparty") or "").lower()
    tx_type = (tx.get("tx_type") or "").lower()
    tx_amount = tx.get("amount", 0) or 0

    # Extract EVM input selector
    raw_data = tx.get("raw_data") or {}
    input_hex = raw_data.get("input", "") if isinstance(raw_data, dict) else ""
    tx_input_selector = classifier.evm_decoder._extract_selector(input_hex)

    for rule in rules:
        # Chain filter: rule chain must match or be 'all'
        rule_chain = rule.get("chain", "")
        if rule_chain != "all" and rule_chain != chain:
            continue

        pattern = rule.get("pattern", {})
        if isinstance(pattern, str):
            pattern = json.loads(pattern)

        matched = True

        # action_type match
        if "action_type" in pattern:
            expected = pattern["action_type"]
            if isinstance(expected, list):
                if tx_action not in [e.upper() for e in expected]:
                    matched = False
            else:
                if tx_action != expected.upper():
                    matched = False
        if not matched:
            continue

        # method_name match
        if "method_name" in pattern:
            expected = pattern["method_name"]
            if isinstance(expected, list):
                if tx_method not in [e.lower() for e in expected]:
                    matched = False
            else:
                if tx_method != expected.lower():
                    matched = False
        if not matched:
            continue

        # tx_type match (exchange)
        if "tx_type" in pattern:
            expected = pattern["tx_type"]
            if isinstance(expected, list):
                if tx_type not in [e.lower() for e in expected]:
                    matched = False
            else:
                if tx_type != expected.lower():
                    matched = False
        if not matched:
            continue

        # direction match
        if "direction" in pattern:
            if tx_direction != pattern["direction"]:
                matched = False
        if not matched:
            continue

        # counterparty_suffix: counterparty must end with one of the suffixes
        if "counterparty_suffix" in pattern:
            suffixes = pattern["counterparty_suffix"]
            if isinstance(suffixes, str):
                suffixes = [suffixes]
            if not any(tx_counterparty.endswith(s.lower()) for s in suffixes):
                matched = False
        if not matched:
            continue

        # counterparty_in: exact match against a list of known contracts
        if "counterparty_in" in pattern:
            contracts = [c.lower() for c in pattern["counterparty_in"]]
            if tx_counterparty not in contracts:
                matched = False
        if not matched:
            continue

        # counterparty_contains
        if "counterparty_contains" in pattern:
            needle = pattern["counterparty_contains"].lower()
            if needle not in tx_counterparty:
                matched = False
        if not matched:
            continue

        # amount_gt
        if "amount_gt" in pattern:
            threshold = Decimal(str(pattern["amount_gt"]))
            try:
                amt = Decimal(str(tx_amount))
            except Exception:
                amt = Decimal("0")
            if amt <= threshold:
                matched = False
        if not matched:
            continue

        # input_selector (EVM method selector)
        if "input_selector" in pattern:
            expected_selector = pattern["input_selector"]
            if expected_selector is None:
                # Rule expects no selector (plain transfer)
                if tx_input_selector is not None:
                    matched = False
            else:
                if tx_input_selector != expected_selector.lower():
                    matched = False
        if not matched:
            continue

        # Rule matched!
        confidence = float(rule.get("confidence", 0.0))
        needs_review = confidence < classifier.REVIEW_THRESHOLD
        return {
            "category": rule["category"],
            "confidence": confidence,
            "notes": f"Rule: {rule['name']}",
            "needs_review": needs_review,
            "rule_id": rule.get("id"),
        }

    return None  # No rule matched


def decompose_swap(classifier, parent_tx: dict, category_result: dict) -> list:
    """Decompose a swap into parent + child legs.

    For standard 2-hop swaps (token_path empty or 2 tokens) returns:
    - parent: leg_type='parent', category=TRADE
    - sell_leg: leg_type='sell_leg', leg_index=0, category=SELL
    - buy_leg: leg_type='buy_leg', leg_index=1, category=BUY
    - fee_leg: leg_type='fee_leg', leg_index=N, category=FEE  (only if fee present)

    For multi-hop swaps (token_path has >2 tokens) additionally creates
    intermediate legs for each token between the first and last:
    - intermediate_leg_N: leg_type='intermediate_leg_1', 'intermediate_leg_2', ...
      Distinct leg_type strings avoid conflict with the partial unique index
      uq_tc_tx_leg on (user_id, transaction_id, leg_type).
    """
    tx_id = parent_tx.get("id")
    has_fee = bool(parent_tx.get("fee"))

    # Resolve category/confidence from dict or CategoryResult
    if isinstance(category_result, dict):
        cat = category_result.get("category", TaxCategory.TRADE.value)
        confidence = category_result.get("confidence", 0.90)
        notes = category_result.get("notes", "DEX swap")
        needs_review = category_result.get("needs_review", False)
        rule_id = category_result.get("rule_id")
        token_path: list = category_result.get("token_path") or []
    else:
        cat = getattr(category_result, "category", TaxCategory.TRADE).value
        confidence = getattr(category_result, "confidence", 0.90)
        notes = getattr(category_result, "notes", "DEX swap")
        needs_review = getattr(category_result, "needs_review", False)
        rule_id = None
        token_path = []

    # Intermediate tokens are all tokens between the first (sold) and last (bought)
    intermediate_tokens = token_path[1:-1] if len(token_path) > 2 else []
    is_multi_hop = bool(intermediate_tokens)

    # Multi-hop swaps always require review (missing intermediate FMV)
    parent_needs_review = needs_review or is_multi_hop

    parent = classifier._make_record(
        transaction_id=tx_id,
        category=cat,
        confidence=confidence,
        notes=notes,
        needs_review=parent_needs_review,
        classification_source="rule",
        rule_id=rule_id,
        leg_type="parent",
        leg_index=0,
    )

    sell_leg = classifier._make_record(
        transaction_id=tx_id,
        category=TaxCategory.SELL.value,
        confidence=confidence,
        notes=f"{notes} (sell leg)",
        needs_review=needs_review,
        classification_source="rule",
        rule_id=rule_id,
        leg_type="sell_leg",
        leg_index=0,
    )

    legs = [parent, sell_leg]

    # Intermediate legs for multi-hop swaps
    # Use 'intermediate_leg_N' as leg_type to avoid the partial unique index conflict
    # on (user_id, transaction_id, leg_type) in the transaction_classifications table.
    for i, _token in enumerate(intermediate_tokens, start=1):
        intermediate_leg = classifier._make_record(
            transaction_id=tx_id,
            category=TaxCategory.TRADE.value,
            confidence=0.50,
            notes="Multi-hop intermediate: acquired and disposed in same transaction",
            needs_review=True,
            classification_source="rule",
            rule_id=rule_id,
            leg_type=f"intermediate_leg_{i}",
            leg_index=i,
            fmv_usd=None,
            fmv_cad=None,
        )
        legs.append(intermediate_leg)

    # buy_leg index is after all intermediate legs
    buy_leg_index = len(intermediate_tokens) + 1
    buy_leg = classifier._make_record(
        transaction_id=tx_id,
        category=TaxCategory.BUY.value,
        confidence=confidence,
        notes=f"{notes} (buy leg)",
        needs_review=needs_review,
        classification_source="rule",
        rule_id=rule_id,
        leg_type="buy_leg",
        leg_index=buy_leg_index,
    )
    legs.append(buy_leg)

    if has_fee:
        fee_leg = classifier._make_record(
            transaction_id=tx_id,
            category=TaxCategory.FEE.value,
            confidence=confidence,
            notes=f"{notes} (fee leg)",
            needs_review=needs_review,
            classification_source="rule",
            rule_id=rule_id,
            leg_type="fee_leg",
            leg_index=buy_leg_index + 1,
        )
        legs.append(fee_leg)

    return legs
