"""Audit history API endpoint.

Endpoints:
  GET /api/audit/history — query audit_log rows filtered by entity_type (required)
                            and optional entity_id; ordered by created_at DESC.

All rows are user-scoped: only audit rows belonging to the authenticated user
are returned. The entity_type query parameter is required (returns 422 if
omitted — FastAPI validates this automatically for Query params with no default).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

import db.crypto as _crypto
from api.dependencies import get_effective_user_with_dek, get_pool_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# GET /api/audit/history
# ---------------------------------------------------------------------------


@router.get("/history")
async def audit_history(
    entity_type: str = Query(..., description="Entity type to filter by (required)"),
    entity_id: Optional[int] = Query(default=None, description="Filter by specific entity PK"),
    limit: int = Query(default=50, ge=1, le=200, description="Max rows to return"),
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
) -> List[dict]:
    """Return audit log rows for the authenticated user.

    Query parameters:
      entity_type (required): Type of entity to filter by
                               (e.g. 'transaction_classification', 'acb_snapshot').
      entity_id (optional):   Filter to a specific entity PK.
      limit (optional):       Max rows returned (1–200, default 50).

    Results are ordered by created_at DESC (most recent first).
    Only rows belonging to the authenticated user are returned.
    """
    user_id = user["user_id"]

    def _dec(raw) -> Optional[str]:
        if raw is None:
            return None
        if isinstance(raw, str):
            return raw  # already plaintext (e.g. mock in tests)
        v = _crypto.EncryptedBytes().process_result_value(bytes(raw), None)
        return str(v) if v is not None else None

    def _query(conn):
        cur = conn.cursor()
        try:
            # D-07: entity_type is encrypted (EncryptedBytes). SQL filter removed.
            # Filter in Python after decryption. SQL only filters on cleartext columns
            # (user_id, entity_id). We fetch up to limit*10 to allow for entity_type filtering,
            # then trim to limit after in-memory filtering.
            fetch_limit = min(limit * 10, 2000)
            if entity_id is not None:
                cur.execute(
                    """
                    SELECT id, user_id, entity_type, entity_id, action,
                           old_value, new_value, actor_type, notes,
                           created_at::text
                    FROM audit_log
                    WHERE user_id = %s
                      AND entity_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, entity_id, fetch_limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, user_id, entity_type, entity_id, action,
                           old_value, new_value, actor_type, notes,
                           created_at::text
                    FROM audit_log
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, fetch_limit),
                )
            return cur.fetchall()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    result = []
    for row in rows:
        (
            row_id, row_user_id, row_entity_type_raw, row_entity_id,
            row_action_raw, row_old_value_raw, row_new_value_raw, row_actor_type,
            row_notes_raw, row_created_at,
        ) = row

        # Decrypt encrypted columns
        dec_entity_type = _dec(row_entity_type_raw) if isinstance(row_entity_type_raw, (bytes, memoryview)) else str(row_entity_type_raw) if row_entity_type_raw else None
        dec_action = _dec(row_action_raw) if isinstance(row_action_raw, (bytes, memoryview)) else str(row_action_raw) if row_action_raw else None
        dec_old_value = _dec(row_old_value_raw) if isinstance(row_old_value_raw, (bytes, memoryview)) else row_old_value_raw
        dec_new_value = _dec(row_new_value_raw) if isinstance(row_new_value_raw, (bytes, memoryview)) else row_new_value_raw
        dec_notes = _dec(row_notes_raw) if isinstance(row_notes_raw, (bytes, memoryview)) else row_notes_raw

        # In-memory entity_type filter (D-07)
        if entity_type and (dec_entity_type or "").lower() != entity_type.lower():
            continue

        result.append(
            {
                "id": row_id,
                "user_id": row_user_id,
                "entity_type": dec_entity_type,
                "entity_id": row_entity_id,
                "action": dec_action,
                "old_value": dec_old_value,
                "new_value": dec_new_value,
                "actor_type": row_actor_type,
                "notes": dec_notes,
                "created_at": str(row_created_at) if row_created_at else None,
            }
        )
        if len(result) >= limit:
            break
    return result
