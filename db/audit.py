"""Unified audit log writer.

All mutation points import write_audit() to insert audit_log rows.
Must be called within the caller's transaction boundary (same conn).

Phase 16: write_audit() now requires a DEK to be set in context before writing.
This is a deliberate fail-closed invariant: audit_log columns (entity_type, action,
old_value, new_value, notes) are all EncryptedBytes per migration 022. Writing
without a DEK would either raise at the DB level or silently store corrupted data.
The preflight get_dek() call surfaces this as a clear RuntimeError early.
"""

import json
import logging

import db.crypto as _c

logger = logging.getLogger(__name__)


def write_audit(
    conn,
    *,
    user_id,
    entity_type,
    entity_id=None,
    action,
    old_value=None,
    new_value,
    actor_type="system",
    notes=None,
):
    """Insert one audit_log row.

    Silently returns if conn is None (test compatibility — callers that pass
    conn=None skip audit writes without raising).

    The try/except ensures audit log failures never crash the pipeline
    (consistent with the "flag + continue" pattern used throughout the codebase).

    Args:
        conn: psycopg2 connection (must be within caller's transaction boundary).
              Pass None to skip — used in tests that do not provision a DB.
        user_id: The user who initiated the action, or None for system actions.
        entity_type: Type of entity being mutated (e.g. 'transaction_classification').
        entity_id: PK of the entity being mutated, or None for actions with no
                   single entity (e.g. report generation).
        action: The mutation action (e.g. 'initial_classify', 'reclassify').
        old_value: Dict representing state before the mutation. None for
                   initial-creation actions.
        new_value: Dict representing state after the mutation.
        actor_type: Who initiated the action: 'system', 'user', 'specialist', 'ai'.
        notes: Optional free-text notes for specialist review context.
    """
    # Preflight DEK check — fail closed (T-16-30).
    # The audit_log columns (entity_type, action, old_value, new_value, notes)
    # are all EncryptedBytes after migration 022. A missing DEK means the INSERT
    # would fail anyway; raise here with a clear message rather than a cryptic
    # DB error.
    try:
        _c.get_dek()
    except RuntimeError:
        raise RuntimeError(
            "audit_log write attempted without a DEK in context. "
            "Audit writes must happen inside a request that resolved "
            "get_effective_user_with_dek."
        )

    if conn is None:
        return
    try:
        cur = conn.cursor()
        # Use savepoint so audit failures don't poison the parent transaction
        cur.execute("SAVEPOINT audit_sp")
        cur.execute(
            """INSERT INTO audit_log
               (user_id, entity_type, entity_id, action, old_value, new_value, actor_type, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                user_id,
                entity_type,
                entity_id,
                action,
                json.dumps(old_value) if old_value is not None else None,
                json.dumps(new_value) if not isinstance(new_value, str) else new_value,
                actor_type,
                notes,
            ),
        )
        cur.execute("RELEASE SAVEPOINT audit_sp")
    except Exception:
        try:
            conn.cursor().execute("ROLLBACK TO SAVEPOINT audit_sp")
        except Exception:
            pass
        logger.warning("Failed to write audit log entry", exc_info=True)
