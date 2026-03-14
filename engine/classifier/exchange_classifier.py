"""
Exchange transaction classification logic.

Contains:
  - classify_exchange_tx(): classify a single exchange transaction
"""

import logging

from tax.categories import TaxCategory

logger = logging.getLogger(__name__)


def classify_exchange_tx(
    classifier,
    user_id: int,
    tx: dict,
    rules: list,
) -> list:
    """Classify a single exchange transaction.

    Returns list of classification record dicts.
    """
    from engine.classifier import AI_CONFIDENCE_THRESHOLD

    tx_id = tx.get("id")
    category_result = classifier._match_rules(tx, rules, chain="exchange")

    if category_result is None or category_result["confidence"] < AI_CONFIDENCE_THRESHOLD:
        # AI fallback for unmatched or low-confidence exchange transactions
        ai_context = classifier._build_ai_context(tx, chain="exchange")
        ai_result = classifier._classify_with_ai(ai_context)
        if category_result is None or ai_result["confidence"] > category_result["confidence"]:
            category_result = ai_result

    if category_result is None:
        category_result = {
            "category": TaxCategory.UNKNOWN.value,
            "confidence": 0.30,
            "notes": f"Unknown exchange tx_type: {tx.get('tx_type')}",
            "needs_review": True,
            "rule_id": None,
        }

    confidence = category_result["confidence"]
    needs_review = confidence < classifier.REVIEW_THRESHOLD or category_result.get("needs_review", False)
    source = category_result.get("classification_source", "rule")

    return [classifier._make_record(
        transaction_id=tx_id,
        category=category_result["category"],
        confidence=confidence,
        notes=category_result.get("notes", ""),
        needs_review=needs_review,
        classification_source=source,
        rule_id=category_result.get("rule_id"),
    )]
