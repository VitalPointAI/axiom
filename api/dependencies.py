"""FastAPI shared dependency injection for database and authentication.

All dependencies follow the Depends() injection pattern. Database connections
are obtained from the shared psycopg2 pool and returned in a finally block
to prevent connection leaks.

psycopg2 pool operations are synchronous. They are wrapped with
fastapi.concurrency.run_in_threadpool() where needed so they don't block
the async event loop in production.
"""

from typing import Generator, Optional

import psycopg2.extensions
from fastapi import Cookie, Depends, HTTPException, status

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


# ---------------------------------------------------------------------------
# Phase 16: DEK-aware dependencies (plan 16-02)
# ---------------------------------------------------------------------------
# NOTE: get_session_dek reads from the session_dek_cache table which is
# created by migration 022 in plan 16-04. Until that migration is applied,
# any call to get_session_dek will return 401 (table does not exist).
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402 — local import to avoid polluting auth deps

from db import crypto as _crypto  # noqa: E402 — imported here to keep Phase 16 additions together


def get_session_dek(
    neartax_session: Optional[str] = Cookie(default=None),
    pool=Depends(get_pool_dep),
):
    """Resolve the per-session DEK from session_dek_cache and inject into ContextVar.

    Reads the session_dek_cache row for the current session cookie, decrypts the
    encrypted_dek column using SESSION_DEK_WRAP_KEY (via db.crypto.unwrap_session_dek),
    sets the DEK in the request-scoped ContextVar via db.crypto.set_dek, yields, then
    zeroes the DEK in the finally block (D-15, T-16-15).

    Fails closed (HTTPException 401) when:
      - No neartax_session cookie is present.
      - No session_dek_cache row exists for the session (plan 16-04 migration 022
        creates this table; missing → 401 until auth-service populates a row at login).
      - The cached row has expired (auth-service sets expires_at to match session TTL).

    Depends on: plan 16-04 migration 022 creating the session_dek_cache table.

    Yields:
        dek (bytes): the plaintext DEK, available inside the endpoint as
                     db.crypto.get_dek(). Zeroed unconditionally in finally.
    """
    if not neartax_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie — authentication required",
        )

    conn = pool.getconn()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT encrypted_dek, expires_at FROM session_dek_cache WHERE session_id = %s",
                (neartax_session,),
            )
            row = cur.fetchone()
        finally:
            cur.close()
    finally:
        pool.putconn(conn)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session DEK unavailable — re-authentication required",
        )

    encrypted_dek, expires_at = row

    # Normalise expires_at to UTC-aware for comparison.
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is not None and expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session DEK expired — re-authentication required",
        )

    dek = _crypto.unwrap_session_dek(bytes(encrypted_dek))
    _crypto.set_dek(dek)
    try:
        yield dek
    finally:
        _crypto.zero_dek()


def get_effective_user_with_dek(
    user: dict = Depends(get_effective_user),
    _dek: bytes = Depends(get_session_dek),
) -> dict:
    """Combines effective-user resolution with DEK injection.

    Use this dependency (instead of get_effective_user alone) on any route that
    reads or writes encrypted columns.  The DEK is available via db.crypto.get_dek()
    inside the endpoint body; it will be zeroed when the request completes.

    Accountant viewing mode:
        TODO(16-06): When viewing_as_user_id is set (accountant is viewing a client),
        plan 16-06 will replace get_session_dek with a path that resolves the client's
        DEK from accountant_access.rewrapped_client_dek.  Until then, any accountant
        viewing attempt raises HTTP 501 so no route silently operates under the wrong DEK.

    Returns:
        The effective user dict (same shape as get_effective_user).

    Raises:
        HTTP 401 if no valid session DEK is available.
        HTTP 501 if viewing_as_user_id is set (accountant mode not yet wired, plan 16-06).
    """
    if user.get("viewing_as_user_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Accountant DEK resolution is not yet wired — "
                "this will be implemented in plan 16-06."
            ),
        )
    return user
