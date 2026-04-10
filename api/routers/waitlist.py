"""Waitlist email capture endpoint.

Public POST /api/waitlist endpoint that validates email addresses,
deduplicates via PostgreSQL UNIQUE constraint (ON CONFLICT DO NOTHING),
and rate-limits at 10 requests/minute per IP.

No authentication required -- this is a public marketing endpoint.
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr

from api.dependencies import get_pool_dep
from api.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/waitlist", tags=["waitlist"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class WaitlistRequest(BaseModel):
    email: EmailStr


class WaitlistResponse(BaseModel):
    message: str
    already_registered: bool = False


# ---------------------------------------------------------------------------
# POST /api/waitlist
# ---------------------------------------------------------------------------


@router.post("", response_model=WaitlistResponse)
@limiter.limit("10/minute")
async def join_waitlist(
    request: Request,
    body: WaitlistRequest,
    pool=Depends(get_pool_dep),
):
    """Add an email to the waitlist.

    - Normalises the email to lowercase.
    - Uses INSERT ... ON CONFLICT DO NOTHING to deduplicate.
    - Returns 201 for new signups, 200 for already-registered.
    - Rate limited to 10 requests/minute per IP address.
    """
    email = body.email.lower().strip()

    def _insert(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO waitlist_signups (email, source)
                VALUES (%s, %s)
                ON CONFLICT (email) DO NOTHING
                RETURNING id
                """,
                (email, "website"),
            )
            row = cur.fetchone()
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    try:
        conn = pool.getconn()
        try:
            row = await run_in_threadpool(_insert, conn)
        finally:
            pool.putconn(conn)

        if row:
            return WaitlistResponse(
                message="You're on the list. We'll email you when Axiom opens.",
                already_registered=False,
            )
        return WaitlistResponse(
            message="You're already on the list. We'll be in touch.",
            already_registered=True,
        )
    except Exception:
        logger.exception("Waitlist signup failed for %s", email)
        raise
