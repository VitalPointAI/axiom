"""Shared helpers for auth handlers — user loading and session expiry calculation."""

from datetime import datetime, timezone, timedelta

import psycopg2.extensions

SESSION_MAX_AGE = 7 * 24 * 60 * 60  # 604800 seconds


def load_user_by_id(
    user_id: int,
    conn: psycopg2.extensions.connection,
) -> dict:
    """Load a user row from the DB by primary key.

    Returns:
        dict with user_id, near_account_id, username, email, codename, is_admin.

    Raises:
        ValueError if user not found.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, near_account_id, username, email, codename, is_admin
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if row is None:
        raise ValueError(f"User not found: {user_id}")

    user_id_db, near_account_id, username, email, codename, is_admin = row
    return {
        "user_id": user_id_db,
        "near_account_id": near_account_id,
        "username": username,
        "email": email,
        "codename": codename,
        "is_admin": bool(is_admin) if is_admin is not None else False,
    }


def get_session_expires_at() -> str:
    """Return ISO 8601 string for session expiry (now + 7 days)."""
    expires = datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE)
    return expires.isoformat()
