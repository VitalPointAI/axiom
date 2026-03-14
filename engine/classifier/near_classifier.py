"""
NEAR-specific transaction classification logic.

Contains:
  - classify_near_tx(): classify a single NEAR transaction
  - load_staking_event_index(): batch-load staking events per wallet
  - load_lockup_event_index(): batch-load lockup events per wallet
  - find_staking_event(): staking reward linkage (CLASS-03)
  - find_lockup_event(): lockup vest linkage (CLASS-04)

All functions accept the TransactionClassifier instance as first arg to
access self.spam_detector, self.wallet_graph, self.REVIEW_THRESHOLD, etc.
"""

import logging
from decimal import Decimal

from tax.categories import TaxCategory

logger = logging.getLogger(__name__)


def load_staking_event_index(classifier, conn, user_id: int, wallet_id: int) -> dict:
    """Load all staking reward events for a wallet into an in-memory index.

    Returns a dict with two lookup structures:
        {
            'by_hash': {tx_hash: event_id, ...},
            'by_timestamp': [(block_timestamp, event_id), ...],  # sorted ascending
        }

    Loaded once per wallet (not per-transaction) to eliminate N+1 queries.
    Per-wallet scope keeps memory bounded (research pitfall #5).
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT id, tx_hash, block_timestamp FROM staking_events "
        "WHERE user_id = %s AND wallet_id = %s AND event_type = 'reward'",
        (user_id, wallet_id),
    )
    rows = cur.fetchall()
    cur.close()

    by_hash = {}
    by_timestamp = []
    for event_id, tx_hash, block_ts in rows:
        if tx_hash:
            by_hash[tx_hash] = event_id
        if block_ts is not None:
            by_timestamp.append((int(block_ts), event_id))

    by_timestamp.sort(key=lambda x: x[0])
    return {"by_hash": by_hash, "by_timestamp": by_timestamp}


def load_lockup_event_index(classifier, conn, user_id: int, wallet_id: int) -> dict:
    """Load all lockup events for a wallet into an in-memory index.

    Returns a dict with two lookup structures:
        {
            'by_hash': {tx_hash: event_id, ...},
            'by_timestamp': [(block_timestamp, event_id), ...],  # sorted ascending
        }

    Loaded once per wallet (not per-transaction) to eliminate N+1 queries.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT id, tx_hash, block_timestamp FROM lockup_events "
        "WHERE user_id = %s AND wallet_id = %s",
        (user_id, wallet_id),
    )
    rows = cur.fetchall()
    cur.close()

    by_hash = {}
    by_timestamp = []
    for event_id, tx_hash, block_ts in rows:
        if tx_hash:
            by_hash[tx_hash] = event_id
        if block_ts is not None:
            by_timestamp.append((int(block_ts), event_id))

    by_timestamp.sort(key=lambda x: x[0])
    return {"by_hash": by_hash, "by_timestamp": by_timestamp}


def find_staking_event(
    classifier,
    user_id: int,
    wallet_id: int,
    tx_hash: str,
    block_timestamp: int,
    index: dict | None = None,
) -> int | None:
    """Find staking_event matching this tx for reward linkage (CLASS-03).

    If `index` is provided (loaded via load_staking_event_index), performs
    O(1) hash lookup then O(n) timestamp scan in memory — no DB query.
    Falls back to direct DB query only when index is None (backward compat).

    Prevents Pitfall 1: double-counting staking rewards.
    """
    if index is not None:
        # Fast path: hash lookup
        if tx_hash and tx_hash in index["by_hash"]:
            return index["by_hash"][tx_hash]
        # Fallback: timestamp range scan in the index (no DB query)
        if block_timestamp:
            ts = int(block_timestamp)
            for event_ts, event_id in index["by_timestamp"]:
                if event_ts > ts + 60:
                    break
                if ts - 60 <= event_ts <= ts + 60:
                    return event_id
        return None

    # Legacy path (no index): direct DB query (backward compat)
    conn = classifier.pool.getconn()
    try:
        cur = conn.cursor()
        # Try exact tx_hash match first
        cur.execute(
            "SELECT id FROM staking_events "
            "WHERE user_id = %s AND wallet_id = %s "
            "  AND tx_hash = %s AND event_type = 'reward' "
            "LIMIT 1",
            (user_id, wallet_id, tx_hash),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        # Fallback: 60-second timestamp window
        if block_timestamp:
            ts = int(block_timestamp)
            cur.execute(
                "SELECT id FROM staking_events "
                "WHERE user_id = %s AND wallet_id = %s "
                "  AND event_type = 'reward' "
                "  AND block_timestamp BETWEEN %s AND %s "
                "LIMIT 1",
                (user_id, wallet_id, ts - 60, ts + 60),
            )
            row = cur.fetchone()
            if row:
                return row[0]
    finally:
        classifier.pool.putconn(conn)

    return None


def find_lockup_event(
    classifier,
    user_id: int,
    wallet_id: int,
    tx_hash: str,
    block_timestamp: int,
    index: dict | None = None,
) -> int | None:
    """Find lockup_event matching this tx for vest linkage (CLASS-04).

    If `index` is provided (loaded via load_lockup_event_index), performs
    O(1) hash lookup then O(n) timestamp scan in memory — no DB query.
    Falls back to direct DB query only when index is None (backward compat).
    """
    if index is not None:
        # Fast path: hash lookup
        if tx_hash and tx_hash in index["by_hash"]:
            return index["by_hash"][tx_hash]
        # Fallback: timestamp range scan in the index (no DB query)
        if block_timestamp:
            ts = int(block_timestamp)
            for event_ts, event_id in index["by_timestamp"]:
                if event_ts > ts + 60:
                    break
                if ts - 60 <= event_ts <= ts + 60:
                    return event_id
        return None

    # Legacy path (no index): direct DB query (backward compat)
    conn = classifier.pool.getconn()
    try:
        cur = conn.cursor()
        # Try exact tx_hash match first
        cur.execute(
            "SELECT id FROM lockup_events "
            "WHERE user_id = %s AND wallet_id = %s "
            "  AND tx_hash = %s "
            "LIMIT 1",
            (user_id, wallet_id, tx_hash),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        # Fallback: 60-second timestamp window
        if block_timestamp:
            ts = int(block_timestamp)
            cur.execute(
                "SELECT id FROM lockup_events "
                "WHERE user_id = %s AND wallet_id = %s "
                "  AND block_timestamp BETWEEN %s AND %s "
                "LIMIT 1",
                (user_id, wallet_id, ts - 60, ts + 60),
            )
            row = cur.fetchone()
            if row:
                return row[0]
    finally:
        classifier.pool.putconn(conn)

    return None


def classify_near_tx(
    classifier,
    user_id: int,
    tx: dict,
    rules: list,
    owned_wallets: set,
    staking_index: dict | None = None,
    lockup_index: dict | None = None,
) -> list:
    """Classify a single NEAR transaction.

    Args:
        classifier: TransactionClassifier instance
        staking_index: Pre-loaded staking event index from load_staking_event_index.
                       If provided, O(1) hash lookups replace per-tx DB queries.
        lockup_index: Pre-loaded lockup event index from load_lockup_event_index.

    Returns list of classification record dicts (1 for simple, N for multi-leg).
    """
    from engine.classifier import AI_CONFIDENCE_THRESHOLD

    tx_id = tx.get("id")
    wallet_id = tx.get("wallet_id")
    counterparty = (tx.get("counterparty") or "").lower()
    direction = tx.get("direction", "")

    # Step 1: Spam check
    spam_result = classifier.spam_detector.check_spam(user_id, tx)
    if spam_result["is_spam"]:
        return [classifier._make_record(
            transaction_id=tx_id,
            category=TaxCategory.SPAM.value,
            confidence=spam_result["confidence"],
            notes=f"Spam: {', '.join(spam_result['signals'])}",
            needs_review=False,
            classification_source="rule",
        )]

    # Step 2: Internal transfer check
    from_addr = tx.get("counterparty") or ""
    to_addr = tx.get("counterparty") or ""
    # Use direction to determine who is from/to relative to owned wallet
    # If direction=in, counterparty is sender; if out, counterparty is receiver
    if direction == "in":
        from_addr = tx.get("counterparty") or ""
    else:
        from_addr = ""  # sender is the owned wallet

    is_internal = False
    if counterparty:
        try:
            is_internal = classifier.wallet_graph.is_internal_transfer(
                user_id, from_addr or counterparty, counterparty
            )
        except Exception:
            is_internal = False

    if is_internal:
        cat = TaxCategory.TRANSFER_IN.value if direction == "in" else TaxCategory.TRANSFER_OUT.value
        return [classifier._make_record(
            transaction_id=tx_id,
            category=cat,
            confidence=0.95,
            notes="Internal transfer between owned wallets",
            needs_review=False,
            classification_source="rule",
        )]

    # Step 3: Rule matching
    category_result = classifier._match_rules(tx, rules, chain="near")

    if category_result is None or category_result["confidence"] < AI_CONFIDENCE_THRESHOLD:
        # AI fallback for unmatched or low-confidence transactions
        ai_context = classifier._build_ai_context(tx, chain="near")
        ai_result = classifier._classify_with_ai(ai_context)
        # Use AI result if no rule matched, or if AI is more confident
        if category_result is None or ai_result["confidence"] > category_result["confidence"]:
            category_result = ai_result

    if category_result is None:
        # Safety net: should never reach here after AI fallback
        category_result = {
            "category": TaxCategory.UNKNOWN.value,
            "confidence": 0.30,
            "notes": f"No rule matched: {tx.get('action_type')}/{tx.get('method_name')}",
            "needs_review": True,
            "rule_id": None,
        }

    # Ensure needs_review if confidence below threshold
    confidence = category_result["confidence"]
    needs_review = confidence < classifier.REVIEW_THRESHOLD or category_result.get("needs_review", False)
    source = category_result.get("classification_source", "rule")

    record = classifier._make_record(
        transaction_id=tx_id,
        category=category_result["category"],
        confidence=confidence,
        notes=category_result.get("notes", ""),
        needs_review=needs_review,
        classification_source=source,
        rule_id=category_result.get("rule_id"),
    )

    # Step 4: Staking reward linkage (CLASS-03)
    # Only link if category is reward; use pre-loaded index if available
    if category_result["category"] == TaxCategory.REWARD.value:
        staking_event_id = find_staking_event(
            classifier, user_id, wallet_id, tx.get("tx_hash", ""), tx.get("block_timestamp", 0),
            index=staking_index,
        )
        if staking_event_id is not None:
            record["staking_event_id"] = staking_event_id

    # Step 5: Lockup vest linkage (CLASS-04)
    # Link if counterparty ends in .lockup.near and category involves income
    if counterparty.endswith(".lockup.near") and category_result["category"] in (
        TaxCategory.INCOME.value,
        TaxCategory.REWARD.value,
        TaxCategory.DEPOSIT.value,
    ):
        lockup_event_id = find_lockup_event(
            classifier, user_id, wallet_id, tx.get("tx_hash", ""), tx.get("block_timestamp", 0),
            index=lockup_index,
        )
        if lockup_event_id is not None:
            record["lockup_event_id"] = lockup_event_id

    # Step 6: DEX swap decomposition (CLASS-05)
    if category_result["category"] == TaxCategory.TRADE.value:
        return classifier._decompose_swap(tx, record)

    return [record]
