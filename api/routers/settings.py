"""Settings endpoints for Phase 16 user-controllable features, plus /api/users/me.

Endpoints:
  GET    /api/users/me           — user info including mlkem_ek_provisioned flag (D-21)
  POST   /api/settings/worker-key — enable background processing (D-17)
  DELETE /api/settings/worker-key — revoke background processing (D-17)
  GET    /api/settings/worker-key — get background processing status (D-17, D-19)

All worker-key endpoints gate on get_effective_user_with_dek to ensure the caller
has an active session with a resolved DEK before they can modify worker-key state.

The worker-key enable/revoke endpoints forward to auth-service via HTTP because
the sealing operation requires auth-service to call /internal/crypto/seal-worker-dek
(FastAPI) with the current session's encrypted DEK blob — a loop only possible if
auth-service initiates it.
"""

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_effective_user_with_dek, get_pool_dep

router = APIRouter(tags=["settings"])

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:3100")
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")


# ---------------------------------------------------------------------------
# GET /api/users/me — user info including Phase 16 key provisioning flag (D-21)
# ---------------------------------------------------------------------------


@router.get("/api/users/me")
async def get_users_me(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return information about the current user needed by the onboarding wizard.

    Includes mlkem_ek_provisioned so the wizard can detect returning-from-pre-encryption
    users who have ML-KEM keys provisioned but no wallets yet (D-21).

    Response shape:
        user_id: int
        mlkem_ek_provisioned: bool — true if users.mlkem_ek IS NOT NULL
        wallet_count: int — number of wallet rows in the wallets table for this user
        onboarding_completed_at: string | null — ISO 8601 timestamp or null
    """
    user_id = user["user_id"]

    def _fetch(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT
                       CASE WHEN mlkem_ek IS NOT NULL THEN TRUE ELSE FALSE END AS mlkem_ek_provisioned,
                       onboarding_completed_at
                   FROM users WHERE id = %s""",
                (user_id,),
            )
            user_row = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*) FROM wallets WHERE user_id = %s",
                (user_id,),
            )
            count_row = cur.fetchone()
            return user_row, count_row
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        user_row, count_row = await run_in_threadpool(_fetch, conn)
    finally:
        pool.putconn(conn)

    mlkem_provisioned = bool(user_row[0]) if user_row else False
    onboarding_at = user_row[1] if user_row else None
    wallet_count = int(count_row[0]) if count_row else 0

    return {
        "user_id": user_id,
        "mlkem_ek_provisioned": mlkem_provisioned,
        "wallet_count": wallet_count,
        "onboarding_completed_at": onboarding_at.isoformat() if onboarding_at else None,
    }


# ---------------------------------------------------------------------------
# POST /api/settings/worker-key — enable background processing
# ---------------------------------------------------------------------------


@router.post("/api/settings/worker-key")
async def enable_worker_key(
    request: Request,
    user: dict = Depends(get_effective_user_with_dek),
):
    """Enable opt-in background processing for the current user (D-17, D-19).

    Forwards the request to auth-service /auth/worker-key/enable with the user's
    session cookie.  auth-service reads the session_dek_cache row and calls
    /internal/crypto/seal-worker-dek to produce the WORKER_KEY_WRAP_KEY-sealed blob,
    then stores it in users.worker_sealed_dek and writes an audit_log row (T-16-41).

    Requires an active session with a valid DEK (get_effective_user_with_dek gating).
    """
    cookie_value = request.cookies.get("neartax_session", "")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{AUTH_SERVICE_URL}/auth/worker-key/enable",
            cookies={"session": cookie_value},
            headers={"X-Internal-Service-Token": INTERNAL_SERVICE_TOKEN},
        )
    if not r.is_success:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


# ---------------------------------------------------------------------------
# DELETE /api/settings/worker-key — revoke background processing
# ---------------------------------------------------------------------------


@router.delete("/api/settings/worker-key")
async def revoke_worker_key(
    request: Request,
    user: dict = Depends(get_effective_user_with_dek),
):
    """Revoke opt-in background processing for the current user (D-17).

    Forwards to auth-service /auth/worker-key DELETE, which sets
    users.worker_sealed_dek = NULL, worker_key_enabled = FALSE, and writes
    an audit_log row.  The worker process will skip this user on its next
    iteration (within 60 seconds) because worker_sealed_dek IS NULL (T-16-44).
    """
    cookie_value = request.cookies.get("neartax_session", "")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.delete(
            f"{AUTH_SERVICE_URL}/auth/worker-key",
            cookies={"session": cookie_value},
            headers={"X-Internal-Service-Token": INTERNAL_SERVICE_TOKEN},
        )
    if not r.is_success:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


# ---------------------------------------------------------------------------
# GET /api/settings/worker-key — read background processing status
# ---------------------------------------------------------------------------


@router.get("/api/settings/worker-key")
async def get_worker_key_status(
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Return the user's background processing status.

    Response shape:
        enabled: bool — whether worker_key_enabled is TRUE
        last_run_at: string | null — ISO 8601 timestamp of last worker pipeline run,
                     or null if the worker has never run for this user.

    The last_run_at field reads from the users table's worker_last_run_at column
    (added in migration 022). If the column does not exist yet, returns null.
    """
    user_id = user["user_id"]

    def _fetch(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT worker_key_enabled,
                          CASE WHEN column_name IS NOT NULL THEN worker_last_run_at
                               ELSE NULL END AS last_run_at
                   FROM users
                   LEFT JOIN information_schema.columns
                     ON table_name = 'users'
                     AND column_name = 'worker_last_run_at'
                     AND table_schema = 'public'
                   WHERE users.id = %s""",
                (user_id,),
            )
            return cur.fetchone()
        except Exception:
            # Fallback: query without worker_last_run_at if column not present
            try:
                cur.execute(
                    "SELECT worker_key_enabled FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
                return (row[0] if row else False, None)
            finally:
                pass
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        row = await run_in_threadpool(_fetch, conn)
    finally:
        pool.putconn(conn)

    if row is None:
        return {"enabled": False, "last_run_at": None}

    enabled, last_run_at = row[0], row[1] if len(row) > 1 else None
    return {
        "enabled": bool(enabled),
        "last_run_at": last_run_at.isoformat() if last_run_at else None,
    }
