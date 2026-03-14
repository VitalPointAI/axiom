"""
AI fallback classification using Claude API.

Contains:
  - classify_with_ai(): classify ambiguous transactions via Claude
  - parse_json_response(): parse AI JSON with markdown fallback
  - build_ai_context(): build minimal context dict for AI classification
"""

import json
import logging
import re
from decimal import Decimal

from tax.categories import TaxCategory

logger = logging.getLogger(__name__)


def classify_with_ai(classifier, tx_context: dict) -> dict:
    """Classify an ambiguous transaction using Claude API.

    Args:
        classifier: TransactionClassifier instance (for ai_client property).
        tx_context: dict with tx details (chain, action_type, method_name,
                   counterparty, direction, amount, token_id, raw_data summary)

    Returns:
        Classification result dict with category, confidence, notes, needs_review.
    """
    from engine.classifier import AI_CONFIDENCE_THRESHOLD, CLASSIFICATION_SYSTEM_PROMPT

    if classifier.ai_client is None:
        return {
            "category": TaxCategory.UNKNOWN.value,
            "confidence": 0.30,
            "notes": "AI fallback unavailable (anthropic SDK not installed)",
            "needs_review": True,
            "rule_id": None,
            "classification_source": "ai",
        }

    try:
        response = classifier.ai_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=CLASSIFICATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(tx_context, default=str)}],
        )

        result = parse_json_response(response.content[0].text)

        category_str = result.get("category", "unknown").lower()
        confidence = float(result.get("confidence", 0.30))
        reasoning = result.get("reasoning", "")
        needs_review = result.get("needs_review", True)

        # Validate category against known values
        try:
            TaxCategory(category_str)
        except ValueError:
            logger.warning("AI returned unknown category '%s'; falling back to unknown", category_str)
            category_str = TaxCategory.UNKNOWN.value
            confidence = min(confidence, 0.50)
            needs_review = True

        # Always flag low-confidence AI results for review
        if confidence < AI_CONFIDENCE_THRESHOLD:
            needs_review = True

        return {
            "category": category_str,
            "confidence": confidence,
            "notes": f"AI: {reasoning}" if reasoning else "AI classification",
            "needs_review": needs_review,
            "rule_id": None,
            "classification_source": "ai",
        }

    except Exception as exc:
        logger.warning("AI classification failed: %s", exc)
        return {
            "category": TaxCategory.UNKNOWN.value,
            "confidence": 0.30,
            "notes": f"AI classification error: {exc}",
            "needs_review": True,
            "rule_id": None,
            "classification_source": "ai",
        }


def parse_json_response(text: str) -> dict:
    """Parse AI JSON response with regex fallback for markdown code blocks.

    Reuses exact pattern from indexers/ai_file_agent.py.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise


def build_ai_context(tx: dict, chain: str) -> dict:
    """Build context dict for AI classification.

    Includes relevant tx fields but excludes raw_data bulk to keep
    token count low.
    """
    raw_data = tx.get("raw_data") or {}
    raw_summary = {}
    if isinstance(raw_data, dict):
        for key in ("input", "logs", "events", "token_id", "memo"):
            if key in raw_data:
                val = raw_data[key]
                if isinstance(val, str) and len(val) > 200:
                    val = val[:200] + "..."
                raw_summary[key] = val

    return {
        "chain": chain,
        "action_type": tx.get("action_type", ""),
        "method_name": tx.get("method_name", ""),
        "counterparty": tx.get("counterparty", ""),
        "direction": tx.get("direction", ""),
        "amount": str(tx.get("amount") or 0),
        "tx_type": tx.get("tx_type", ""),
        "raw_data_summary": raw_summary,
    }


def get_fmv(classifier, coin_id: str, timestamp: int, currency: str = "usd") -> Decimal | None:
    """Get FMV for income events using PriceService.

    Returns None if PriceService not configured or price unavailable.
    """
    if classifier.price_service is None:
        return None
    try:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(timestamp / 1e9, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        return classifier.price_service.get_price(coin_id, date_str, currency)
    except Exception:
        return None
