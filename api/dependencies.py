"""FastAPI shared dependency injection for database and authentication.

All dependencies follow the Depends() injection pattern. Database connections
are obtained from the shared psycopg2 pool and returned in a finally block
to prevent connection leaks.

psycopg2 pool operations are synchronous. They are wrapped with
fastapi.concurrency.run_in_threadpool() where needed so they don't block
the async event loop in production.
"""

from datetime import datetime, timezone
from typing import Generator, Optional

import psycopg2.extensions
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

import indexers.db as _db


# ---------------------------------------------------------------------------
# Database pool dependency
# ---------------------------------------------------------------------------


def get_pool_dep():
    """Return the shared psycopg2 SimpleConnectionPool.

    Initialized on FastAPI startup via the lifespan event in api/main.py.
    All route handlers that need DB access receive this via Depends().
    """
    return _db.get_pool()


def get_db_conn(
    pool=Depends(get_pool_dep),
) -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield a psycopg2 connection from the pool, returning it in finally.

    Usage in routes::

        @router.get("/example")
        def my_route(conn=Depends(get_db_conn)):
            cur = conn.cursor()
            ...
    """
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


# ---------------------------------------------------------------------------
# Authentication dependencies
# ---------------------------------------------------------------------------


def get_current_user(
    neartax_session: Optional[str] = Cookie(default=None),
    pool=Depends(get_pool_dep),
) -> dict:
    """Validate the session cookie and return the authenticated user context.

    Queries the sessions table for a non-expired matching session token,
    then joins to users to return the full user profile.

    Returns dict with keys: user_id, near_account_id, is_admin, email, username, codename.

    Raises:
        HTTPException 401 if session cookie is missing or expired.
    """
    if not neartax_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                u.id,
                u.near_account_id,
                u.is_admin,
                u.email,
                u.username,
                u.codename
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = %s
              AND s.expires_at > NOW()
            """,
            (neartax_session,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        pool.putconn(conn)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )

    user_id, near_account_id, is_admin, email, username, codename = row
    return {
        "user_id": user_id,
        "near_account_id": near_account_id,
        "is_admin": bool(is_admin),
        "email": email,
        "username": username,
        "codename": codename,
    }


def get_effective_user(
    user: dict = Depends(get_current_user),
    neartax_viewing_as: Optional[str] = Cookie(default=None),
    pool=Depends(get_pool_dep),
) -> dict:
    """Resolve the effective user context, supporting accountant viewing mode.

    If the `neartax_viewing_as` cookie is set, the authenticated user is
    assumed to be an accountant. This dependency:
      1. Checks accountant_access for a valid grant (accountant → client).
      2. Returns the *client's* user context enriched with viewing_as metadata.
      3. Raises 403 if the authenticated user lacks access to the requested client.

    All data routers use get_effective_user (not get_current_user) so that
    accountants transparently query client data.

    Returns the same dict shape as get_current_user, plus:
      - viewing_as_user_id: int | None — the original accountant user_id
      - permission_level: str | None — 'read' or 'readwrite'
    """
    if not neartax_viewing_as:
        # Normal mode — no delegation
        return {
            **user,
            "viewing_as_user_id": None,
            "permission_level": None,
        }

    # Accountant viewing mode — resolve client user_id
    try:
        client_user_id = int(neartax_viewing_as)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid neartax_viewing_as value",
        )

    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                aa.permission_level,
                u.id,
                u.near_account_id,
                u.is_admin,
                u.email,
                u.username,
                u.codename
            FROM accountant_access aa
            JOIN users u ON u.id = aa.client_user_id
            WHERE aa.accountant_user_id = %s
              AND aa.client_user_id = %s
            """,
            (user["user_id"], client_user_id),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        pool.putconn(conn)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No accountant access to the requested client",
        )

    permission_level, uid, near_id, is_admin, email, username, codename = row
    return {
        "user_id": uid,
        "near_account_id": near_id,
        "is_admin": bool(is_admin),
        "email": email,
        "username": username,
        "codename": codename,
        "viewing_as_user_id": user["user_id"],
        "permission_level": permission_level,
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Raise 403 if the authenticated user is not an admin.

    Usage::

        @router.post("/admin/seed-rules")
        def seed_rules(user=Depends(require_admin)):
            ...
    """
    if not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
