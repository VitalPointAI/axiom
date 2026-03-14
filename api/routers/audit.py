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

from api.dependencies import get_effective_user, get_pool_dep

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
    user: dict = Depends(get_effective_user),
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

    def _query(conn):
        cur = conn.cursor()
        try:
            if entity_id is not None:
                cur.execute(
                    """
                    SELECT id, user_id, entity_type, entity_id, action,
                           old_value, new_value, actor_type, notes,
                           created_at::text
                    FROM audit_log
                    WHERE user_id = %s
                      AND entity_type = %s
                      AND entity_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, entity_type, entity_id, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, user_id, entity_type, entity_id, action,
                           old_value, new_value, actor_type, notes,
                           created_at::text
                    FROM audit_log
                    WHERE user_id = %s
                      AND entity_type = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, entity_type, limit),
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
            row_id, row_user_id, row_entity_type, row_entity_id,
            row_action, row_old_value, row_new_value, row_actor_type,
            row_notes, row_created_at,
        ) = row
        result.append(
            {
                "id": row_id,
                "user_id": row_user_id,
                "entity_type": row_entity_type,
                "entity_id": row_entity_id,
                "action": row_action,
                "old_value": row_old_value,
                "new_value": row_new_value,
                "actor_type": row_actor_type,
                "notes": row_notes,
                "created_at": str(row_created_at) if row_created_at else None,
            }
        )
    return result
