"""Internal pipeline dispatch endpoint for the background worker process (D-17).

This endpoint is called by the worker process (auth-service/src/worker-process.ts)
to trigger the per-user pipeline with a worker-unsealed DEK.

Security:
  - Token-guarded via X-Internal-Service-Token (same guard as internal_crypto.py)
  - Not exposed in OpenAPI docs (include_in_schema=False)
  - Only called from auth-service/worker-process.ts over the Docker internal network

The endpoint:
  1. Validates the internal service token
  2. Reads the session_dek_wrapped_hex from the request body
  3. Unwraps the DEK and injects it into the ContextVar via set_dek()
  4. Triggers resync for all wallets owned by user_id
  5. Zeroes the DEK in the finally block (D-15)

Threat mitigations:
  T-16-39: Documented trade-off — users opt in knowing the server holds the key.
  T-16-44: Worker dispatches users sequentially; this endpoint processes one user at a time.
"""

import hmac as _hmac
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import indexers.db as _db
from db import crypto as _c

router = APIRouter(
    prefix="/api/internal",
    tags=["internal-pipeline"],
    include_in_schema=False,
)


# ---------------------------------------------------------------------------
# Token guard (mirrors internal_crypto.py pattern)
# ---------------------------------------------------------------------------


def _require_internal_token(
    x_internal_service_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503, detail="INTERNAL_SERVICE_TOKEN not configured"
        )
    if not x_internal_service_token or not _hmac.compare_digest(
        x_internal_service_token.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=401, detail="Invalid or missing internal service token"
        )


_AUTH_DEPS = [Depends(_require_internal_token)]


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class RunPipelineRequest(BaseModel):
    """POST /api/internal/run-pipeline request body."""

    user_id: int
    session_dek_wrapped_hex: str


# ---------------------------------------------------------------------------
# POST /api/internal/run-pipeline
# ---------------------------------------------------------------------------


@router.post("/run-pipeline", dependencies=_AUTH_DEPS)
async def run_pipeline(req: RunPipelineRequest):
    """Trigger the per-user pipeline for a background worker user (D-17).

    Called by the worker process with the worker-unsealed session-wrapped DEK.
    Injects the DEK into the ContextVar, triggers wallet resync for all of the
    user's wallets, then zeroes the DEK in the finally block.

    The pipeline runs the same path as a user-initiated resync:
      wallet_ids → indexer → classify → ACB → verify → reports

    Returns:
        {dispatched: N, user_id: int} where N is the number of wallets queued.
    """
    session_dek_wrapped = bytes.fromhex(req.session_dek_wrapped_hex)
    dek = b""
    pool = _db.get_pool()

    try:
        # Unwrap the session DEK and inject into ContextVar
        dek = _c.unwrap_session_dek(session_dek_wrapped)
        _c.set_dek(dek)

        # Fetch the user's wallet IDs (account_id is encrypted; we only need IDs)
        def _get_wallet_ids(conn):
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT id FROM wallets WHERE user_id = %s",
                    (req.user_id,),
                )
                return [r[0] for r in cur.fetchall()]
            finally:
                cur.close()

        conn = pool.getconn()
        try:
            wallet_ids = await run_in_threadpool(_get_wallet_ids, conn)
        finally:
            pool.putconn(conn)

        # Queue indexing jobs for each wallet
        # (Same pattern as POST /api/wallets/{id}/resync in wallets.py)
        def _queue_jobs(conn):
            cur = conn.cursor()
            try:
                for wallet_id in wallet_ids:
                    cur.execute(
                        """INSERT INTO indexing_jobs
                               (user_id, wallet_id, job_type, status, created_at)
                           VALUES (%s, %s, 'sync', 'pending', NOW())
                           ON CONFLICT DO NOTHING""",
                        (req.user_id, wallet_id),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

        conn = pool.getconn()
        try:
            await run_in_threadpool(_queue_jobs, conn)
        finally:
            pool.putconn(conn)

        return {"dispatched": len(wallet_ids), "user_id": req.user_id}

    finally:
        _c.zero_dek()
        if dek:
            _c._zero_bytes(dek)
