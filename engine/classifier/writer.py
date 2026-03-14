"""
DB persistence helpers for transaction classification.

Contains:
  - make_record(): build a classification record dict
  - write_records(): write classification records to DB
  - upsert_classification(): INSERT ... ON CONFLICT for transaction_classifications
  - write_audit_log(): insert into classification_audit_log
"""

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def make_record(
    classifier,
    transaction_id,
    category: str,
    confidence: float,
    notes: str = "",
    needs_review: bool = False,
    classification_source: str = "rule",
    rule_id=None,
    leg_type: str = "parent",
    leg_index: int = 0,
    staking_event_id=None,
    lockup_event_id=None,
    fmv_usd=None,
    fmv_cad=None,
) -> dict:
    """Build a classification record dict."""
    if confidence < classifier.REVIEW_THRESHOLD:
        needs_review = True
    return {
        "transaction_id": transaction_id,
        "category": category,
        "confidence": confidence,
        "notes": notes,
        "needs_review": needs_review,
        "classification_source": classification_source,
        "rule_id": rule_id,
        "leg_type": leg_type,
        "leg_index": leg_index,
        "staking_event_id": staking_event_id,
        "lockup_event_id": lockup_event_id,
        "fmv_usd": fmv_usd,
        "fmv_cad": fmv_cad,
    }


def write_records(
    classifier,
    user_id: int,
    records: list,
    stats: dict,
    is_exchange: bool = False,
    exchange_tx_id=None,
) -> None:
    """Write classification records to DB, updating stats."""
    if not records:
        return
    conn = classifier.pool.getconn()
    try:
        for rec in records:
            tx_id = None if is_exchange else rec.get("transaction_id")
            exc_tx_id = exchange_tx_id if is_exchange else None
            classification_id = upsert_classification(
                classifier,
                conn,
                {**rec, "transaction_id": tx_id, "exchange_transaction_id": exc_tx_id}
            )
            write_audit_log(classifier, conn, classification_id, rec)
            stats["classified"] += 1
            if rec.get("needs_review"):
                stats["needs_review"] += 1
        conn.commit()
    finally:
        classifier.pool.putconn(conn)


def upsert_classification(classifier, conn, record: dict) -> int:
    """Upsert a classification record. Preserves specialist-confirmed records.

    Uses INSERT ... ON CONFLICT DO UPDATE WHERE specialist_confirmed = FALSE.
    Returns classification id.
    """
    cur = conn.cursor()

    tx_id = record.get("transaction_id")
    exc_tx_id = record.get("exchange_transaction_id")
    leg_type = record.get("leg_type", "parent")
    leg_index = record.get("leg_index", 0)

    cur.execute(
        """
        INSERT INTO transaction_classifications
            (user_id, transaction_id, exchange_transaction_id,
             leg_type, leg_index, category, confidence,
             classification_source, rule_id,
             staking_event_id, lockup_event_id,
             fmv_usd, fmv_cad, needs_review,
             specialist_confirmed, created_at, updated_at)
        VALUES
            (%(user_id)s, %(transaction_id)s, %(exchange_transaction_id)s,
             %(leg_type)s, %(leg_index)s, %(category)s, %(confidence)s,
             %(classification_source)s, %(rule_id)s,
             %(staking_event_id)s, %(lockup_event_id)s,
             %(fmv_usd)s, %(fmv_cad)s, %(needs_review)s,
             FALSE, NOW(), NOW())
        ON CONFLICT ON CONSTRAINT uq_tc_tx_leg
        DO UPDATE SET
            category = EXCLUDED.category,
            confidence = EXCLUDED.confidence,
            classification_source = EXCLUDED.classification_source,
            rule_id = EXCLUDED.rule_id,
            staking_event_id = EXCLUDED.staking_event_id,
            lockup_event_id = EXCLUDED.lockup_event_id,
            fmv_usd = EXCLUDED.fmv_usd,
            fmv_cad = EXCLUDED.fmv_cad,
            needs_review = EXCLUDED.needs_review,
            updated_at = NOW()
        WHERE transaction_classifications.specialist_confirmed = FALSE
        RETURNING id
        """,
        {
            "user_id": record.get("user_id", 0),
            "transaction_id": tx_id,
            "exchange_transaction_id": exc_tx_id,
            "leg_type": leg_type,
            "leg_index": leg_index,
            "category": record["category"],
            "confidence": record["confidence"],
            "classification_source": record.get("classification_source", "rule"),
            "rule_id": record.get("rule_id"),
            "staking_event_id": record.get("staking_event_id"),
            "lockup_event_id": record.get("lockup_event_id"),
            "fmv_usd": record.get("fmv_usd"),
            "fmv_cad": record.get("fmv_cad"),
            "needs_review": record.get("needs_review", True),
        },
    )
    row = cur.fetchone()
    return row[0] if row else 0


def write_audit_log(
    classifier,
    conn,
    classification_id: int,
    record: dict,
    old_record: dict | None = None,
) -> None:
    """Write audit log entry for a classification change.

    change_reason: 'initial' for new, 'rule_update' for re-classification.
    """
    if not classification_id:
        return

    cur = conn.cursor()
    old_category = old_record["category"] if old_record else None
    old_confidence = old_record["confidence"] if old_record else None
    change_reason = "rule_update" if old_record else "initial"

    cur.execute(
        """
        INSERT INTO classification_audit_log
            (classification_id, changed_by_user_id, changed_by_type,
             old_category, new_category, old_confidence, new_confidence,
             change_reason, rule_id, notes, created_at)
        VALUES
            (%s, NULL, 'system', %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            classification_id,
            old_category,
            record["category"],
            old_confidence,
            record["confidence"],
            change_reason,
            record.get("rule_id"),
            record.get("notes", ""),
        ),
    )
