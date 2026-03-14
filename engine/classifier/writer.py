"""
DB persistence helpers for transaction classification.

Contains:
  - make_record(): build a classification record dict
  - write_records(): write classification records to DB
  - upsert_classification(): INSERT ... ON CONFLICT for transaction_classifications
  - write_audit_log(): insert into audit_log (via unified write_audit())
"""

import logging
from decimal import Decimal

from db.audit import write_audit

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

    Delegates to the unified write_audit() helper (db/audit.py).
    Keeps function name for backward compatibility.
    """
    if not classification_id:
        return

    old_category = old_record["category"] if old_record else None
    old_confidence = old_record["confidence"] if old_record else None

    write_audit(
        conn,
        user_id=record.get("user_id", 0),
        entity_type="transaction_classification",
        entity_id=classification_id,
        action="initial_classify" if not old_record else "reclassify",
        old_value=(
            {"category": old_category, "confidence": float(old_confidence)}
            if old_record else None
        ),
        new_value={
            "category": record["category"],
            "confidence": float(record["confidence"]),
        },
        actor_type="system",
        notes=record.get("notes", ""),
    )


def check_classifier_invariants_batch(conn, user_id: int) -> list:
    """Detect transactions with missing or duplicate parent classifications.

    Runs a single GROUP BY query — call once at end of a classify job.
    Returns list of violation dicts. Never raises.
    """
    violations = []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.id, COUNT(tc.id) as parent_count
            FROM transactions t
            LEFT JOIN transaction_classifications tc
                ON tc.transaction_id = t.id AND tc.user_id = %s AND tc.leg_type = 'parent'
            WHERE t.user_id = %s
            GROUP BY t.id
            HAVING COUNT(tc.id) != 1
            LIMIT 100
            """,
            (user_id, user_id),
        )
        for row in cur.fetchall():
            tx_id, parent_count = row[0], row[1]
            violation = {"transaction_id": tx_id, "parent_count": parent_count}
            violations.append(violation)
            logger.warning(
                "Classifier invariant: tx_id=%s has %d parent classifications (expected 1)",
                tx_id, parent_count,
            )
            write_audit(
                conn,
                user_id=user_id,
                entity_type="transaction_classification",
                entity_id=tx_id,
                action="invariant_violation",
                new_value={"issue": "parent_count_mismatch", "parent_count": parent_count},
                actor_type="system",
            )
        cur.close()

        # Swap leg balance check
        cur = conn.cursor()
        cur.execute(
            """
            SELECT tc_parent.id, tc_parent.transaction_id,
                   COUNT(CASE WHEN tc_child.leg_type = 'sell_leg' THEN 1 END) as sell_count,
                   COUNT(CASE WHEN tc_child.leg_type = 'buy_leg' THEN 1 END) as buy_count,
                   COUNT(CASE WHEN tc_child.leg_type = 'fee_leg' THEN 1 END) as fee_count
            FROM transaction_classifications tc_parent
            LEFT JOIN transaction_classifications tc_child
                ON tc_child.parent_classification_id = tc_parent.id
            WHERE tc_parent.user_id = %s
              AND tc_parent.leg_type = 'parent'
              AND tc_parent.category IN ('capital_gain', 'capital_loss')
            GROUP BY tc_parent.id, tc_parent.transaction_id
            HAVING COUNT(CASE WHEN tc_child.leg_type = 'sell_leg' THEN 1 END) != 1
                OR COUNT(CASE WHEN tc_child.leg_type = 'buy_leg' THEN 1 END) != 1
            LIMIT 100
            """,
            (user_id,),
        )
        for row in cur.fetchall():
            cls_id, tx_id, sell_count, buy_count, fee_count = row
            violation = {
                "classification_id": cls_id,
                "transaction_id": tx_id,
                "sell_legs": sell_count,
                "buy_legs": buy_count,
                "fee_legs": fee_count,
            }
            violations.append(violation)
            logger.warning(
                "Classifier invariant: swap cls_id=%s has %d sell, %d buy legs",
                cls_id, sell_count, buy_count,
            )
            write_audit(
                conn,
                user_id=user_id,
                entity_type="transaction_classification",
                entity_id=cls_id,
                action="invariant_violation",
                new_value={"issue": "swap_leg_imbalance", **violation},
                actor_type="system",
            )
        cur.close()
    except Exception:
        logger.warning("Failed to run classifier invariant batch check", exc_info=True)

    return violations
