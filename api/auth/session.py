"""Session management for the Axiom FastAPI auth system.

Creates and destroys HTTP-only session cookies backed by the sessions
PostgreSQL table. Token is a secrets.token_hex(32) random string stored
as the cookie value and sessions.id primary key.

Session lifetime: 7 days.
Cookie attributes: httponly=True, samesite=lax, secure from SESSION_SECURE env var.
"""

import os
import secrets
from datetime import datetime, timezone, timedelta

import psycopg2.extensions
from fastapi import Response


SESSION_MAX_AGE = 7 * 24 * 60 * 60  # 604800 seconds = 7 days
_SESSION_SECURE = os.environ.get("SESSION_SECURE", "false").lower() == "true"


def create_session(
    user_id: int,
    response: Response,
    conn: psycopg2.extensions.connection,
) -> str:
    """Create a new session for user_id, set the cookie, return the session token.

    Inserts a row into the sessions table with a 7-day expiry, then sets the
    ``neartax_session`` cookie on the FastAPI Response object.

    Args:
        user_id: The authenticated user's DB row ID.
        response: FastAPI Response (or TestClient mock) to set the cookie on.
        conn: psycopg2 connection — caller owns the transaction boundary.

    Returns:
        The session token string (also set as the cookie value).
    """
    session_token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE)

    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO sessions (id, user_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (session_token, user_id, expires_at),
        )
    finally:
        cur.close()

    conn.commit()

    response.set_cookie(
        key="neartax_session",
        value=session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=_SESSION_SECURE,
        samesite="lax",
    )

    return session_token


def destroy_session(
    session_id: str,
    response: Response,
    conn: psycopg2.extensions.connection,
) -> None:
    """Delete the session from the DB and clear the cookie.

    Args:
        session_id: The session token value from the cookie.
        response: FastAPI Response to delete the cookie on.
        conn: psycopg2 connection — caller owns the transaction boundary.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM sessions WHERE id = %s",
            (session_id,),
        )
    finally:
        cur.close()

    conn.commit()

    response.delete_cookie(key="neartax_session")
