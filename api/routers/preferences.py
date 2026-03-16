"""User preferences endpoints: onboarding state and banner dismissals.

Endpoints:
  GET   /api/preferences                   — return onboarding_completed_at + dismissed_banners
  POST  /api/preferences/complete-onboarding — idempotently set onboarding_completed_at
  PATCH /api/preferences/dismiss-banner    — merge a banner key into dismissed_banners JSONB

All endpoints use get_effective_user so accountants can act on behalf of clients.
All DB calls are synchronous psycopg2 wrapped with run_in_threadpool().
"""

import json

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from api.dependencies import get_effective_user, get_pool_dep

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class DismissBannerRequest(BaseModel):
    banner_key: str


# ---------------------------------------------------------------------------
# GET /api/preferences
# ---------------------------------------------------------------------------


@router.get("")
async def get_preferences(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return the current user's onboarding state and dismissed banners.

    Returns:
        onboarding_completed_at: ISO 8601 string or null
        dismissed_banners: dict (defaults to empty dict when NULL in DB)
    """
    user_id = user["user_id"]

    def _get(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT onboarding_completed_at, dismissed_banners FROM users WHERE id = %s",
                (user_id,),
            )
            return cur.fetchone()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        row = await run_in_threadpool(_get, conn)
    finally:
        pool.putconn(conn)

    if row is None:
        return {"onboarding_completed_at": None, "dismissed_banners": {}}

    completed_at, dismissed = row
    return {
        "onboarding_completed_at": completed_at.isoformat() if completed_at else None,
        "dismissed_banners": dismissed if dismissed is not None else {},
    }


# ---------------------------------------------------------------------------
# POST /api/preferences/complete-onboarding
# ---------------------------------------------------------------------------


@router.post("/complete-onboarding")
async def complete_onboarding(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Idempotently mark onboarding as completed.

    Uses COALESCE so the timestamp is only set on the first call.
    Subsequent calls return the existing timestamp unchanged.
    """
    user_id = user["user_id"]

    def _complete(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE users
                SET onboarding_completed_at = COALESCE(onboarding_completed_at, NOW())
                WHERE id = %s
                RETURNING onboarding_completed_at
                """,
                (user_id,),
            )
            row = cur.fetchone()
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        row = await run_in_threadpool(_complete, conn)
    finally:
        pool.putconn(conn)

    completed_at = row[0] if row else None
    return {
        "onboarding_completed_at": completed_at.isoformat() if completed_at else None,
    }


# ---------------------------------------------------------------------------
# PATCH /api/preferences/dismiss-banner
# ---------------------------------------------------------------------------


@router.patch("/dismiss-banner")
async def dismiss_banner(
    body: DismissBannerRequest,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Merge a banner key into the user's dismissed_banners JSONB column.

    Uses the || operator for atomic JSONB merge. COALESCE on the existing
    column ensures NULL is treated as an empty object before the merge.

    Returns the updated dismissed_banners dict.
    """
    user_id = user["user_id"]
    banner_patch = json.dumps({body.banner_key: True})

    def _dismiss(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE users
                SET dismissed_banners = COALESCE(dismissed_banners, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                RETURNING dismissed_banners
                """,
                (banner_patch, user_id),
            )
            row = cur.fetchone()
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        row = await run_in_threadpool(_dismiss, conn)
    finally:
        pool.putconn(conn)

    dismissed = row[0] if row else {}
    return {"dismissed_banners": dismissed if dismissed is not None else {}}
