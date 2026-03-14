"""
EVM-specific transaction classification logic.

Contains:
  - classify_evm_tx_group(): classify a group of EVM transactions sharing base tx_hash
"""

import logging

from tax.categories import TaxCategory

logger = logging.getLogger(__name__)


def classify_evm_tx_group(
    classifier,
    user_id: int,
    txs: list,
    rules: list,
    owned_wallets: set,
) -> list:
    """Classify a group of EVM transactions sharing base tx_hash.

    Uses EVMDecoder to detect swap/defi type.
    If swap detected: create parent + legs from the group.
    If not swap: classify each individually.
    """
    from engine.classifier import AI_CONFIDENCE_THRESHOLD

    if not txs:
        return []

    # Check if any tx in group is a swap
    primary_tx = txs[0]
    swap_result = classifier.evm_decoder.detect_swap(primary_tx)

    if swap_result["is_swap"]:
        # Decompose into parent + sell_leg + buy_leg + fee_leg
        category_result = {
            "category": TaxCategory.TRADE.value,
            "confidence": 0.90,
            "notes": f"EVM DEX swap: {swap_result['method_name']} ({swap_result['dex_type']})",
            "needs_review": False,
            "rule_id": None,
        }
        return classifier._decompose_swap(primary_tx, category_result)

    # Not a swap — classify each tx individually
    results = []
    for tx in txs:
        # Spam check
        spam_result = classifier.spam_detector.check_spam(user_id, tx)
        if spam_result["is_spam"]:
            results.append(classifier._make_record(
                transaction_id=tx.get("id"),
                category=TaxCategory.SPAM.value,
                confidence=spam_result["confidence"],
                notes=f"Spam: {', '.join(spam_result['signals'])}",
                needs_review=False,
                classification_source="rule",
            ))
            continue

        # Internal transfer check
        direction = tx.get("direction", "")
        counterparty = tx.get("counterparty") or ""
        is_internal = False
        if counterparty:
            try:
                is_internal = classifier.wallet_graph.is_internal_transfer(
                    user_id, counterparty, counterparty
                )
            except Exception:
                is_internal = False

        if is_internal:
            cat = TaxCategory.TRANSFER_IN.value if direction == "in" else TaxCategory.TRANSFER_OUT.value
            results.append(classifier._make_record(
                transaction_id=tx.get("id"),
                category=cat,
                confidence=0.95,
                notes="Internal EVM transfer between owned wallets",
                needs_review=False,
                classification_source="rule",
            ))
            continue

        # Rule matching using EVM chain
        category_result = classifier._match_rules(tx, rules, chain="evm")

        if category_result is None or category_result["confidence"] < AI_CONFIDENCE_THRESHOLD:
            # AI fallback for unmatched or low-confidence EVM transactions
            ai_context = classifier._build_ai_context(tx, chain="evm")
            ai_result = classifier._classify_with_ai(ai_context)
            if category_result is None or ai_result["confidence"] > category_result["confidence"]:
                category_result = ai_result

        if category_result is None:
            category_result = {
                "category": TaxCategory.UNKNOWN.value,
                "confidence": 0.30,
                "notes": "No EVM rule matched",
                "needs_review": True,
                "rule_id": None,
            }

        confidence = category_result["confidence"]
        needs_review = confidence < classifier.REVIEW_THRESHOLD or category_result.get("needs_review", False)
        source = category_result.get("classification_source", "rule")

        results.append(classifier._make_record(
            transaction_id=tx.get("id"),
            category=category_result["category"],
            confidence=confidence,
            notes=category_result.get("notes", ""),
            needs_review=needs_review,
            classification_source=source,
            rule_id=category_result.get("rule_id"),
        ))

    return results
