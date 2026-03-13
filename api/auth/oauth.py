"""Google OAuth PKCE flow for the Axiom auth system.

Implements the two-step OAuth dance:
  1. start_google_oauth — generate state, store in challenges table, return auth URL
  2. finish_google_oauth — verify state, exchange code for tokens, upsert user by email

Configuration via environment variables:
  GOOGLE_CLIENT_ID      — Google OAuth 2.0 client ID
  GOOGLE_CLIENT_SECRET  — Google OAuth 2.0 client secret
  OAUTH_REDIRECT_URI    — Registered redirect URI (e.g. https://app.com/auth/oauth/callback)

Uses httpx for synchronous HTTP calls (called from run_in_threadpool in router).
"""

import json
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

import httpx
import psycopg2.extensions

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:3003/auth/oauth/callback")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

_STATE_TTL_SECONDS = 600  # 10 minutes


def start_google_oauth(
    conn: psycopg2.extensions.connection,
) -> Dict[str, Any]:
    """Generate Google OAuth redirect URL and store PKCE state in DB.

    Args:
        conn: psycopg2 connection.

    Returns:
        dict with ``auth_url`` (str) and ``state`` (str).
    """
    state = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_STATE_TTL_SECONDS)

    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO challenges (id, challenge, challenge_type, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (state, state.encode(), "oauth_state", expires_at),
        )
    finally:
        cur.close()

    conn.commit()

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"{GOOGLE_AUTH_URL}?{query_string}"

    return {"auth_url": auth_url, "state": state}


def finish_google_oauth(
    code: str,
    state: str,
    conn: psycopg2.extensions.connection,
) -> int:
    """Exchange OAuth code for token, fetch user info, upsert user by email.

    Args:
        code: Authorization code from Google redirect.
        state: State parameter for CSRF validation.
        conn: psycopg2 connection.

    Returns:
        user_id (int) of the upserted user.

    Raises:
        ValueError if state invalid/expired or token exchange fails.
    """
    # Verify state from challenges table
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT challenge, expires_at
            FROM challenges
            WHERE id = %s AND challenge_type = 'oauth_state'
            """,
            (state,),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if row is None:
        raise ValueError("Invalid OAuth state — possible CSRF")

    _, expires_at = row
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise ValueError("OAuth state expired")

    # Consume the state
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM challenges WHERE id = %s", (state,))
    finally:
        cur.close()
    conn.commit()

    # Exchange code for tokens
    with httpx.Client() as client:
        token_response = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        token_data = token_response.json()

        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("No access_token in Google token response")

        # Fetch user info
        userinfo_response = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    email = userinfo.get("email")
    if not email:
        raise ValueError("No email in Google user info")

    username = userinfo.get("name", email.split("@")[0])

    # Upsert user by email
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (email, username)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE
              SET username = COALESCE(users.username, excluded.username)
            RETURNING id
            """,
            (email, username),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    conn.commit()

    return row[0]
