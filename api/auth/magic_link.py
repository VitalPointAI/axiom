"""Email magic link generation and verification for the Axiom auth system.

Implements:
  request_magic_link — generate signed token, store in DB, send via SES
  verify_magic_link  — decode and validate token, mark used, upsert user, return user_id

Token format: itsdangerous.URLSafeTimedSerializer signed with SECRET_KEY.
  - dumps(email) → signed token string
  - loads(token, max_age=TOKEN_MAX_AGE) → email (raises SignatureExpired on expiry)

Token row: magic_link_tokens(id=token, email=email, expires_at, used_at=NULL)

Configuration via environment variables:
  SECRET_KEY           — Token signing secret (REQUIRED in production)
  SES_FROM_EMAIL       — Sender address for magic link emails
  SES_REGION           — AWS region for SES (default: us-east-1)
  FRONTEND_URL         — Base URL for the magic link (default: http://localhost:3003)
"""

import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
import itsdangerous
import psycopg2.extensions

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "noreply@axiom.tax")
SES_REGION = os.environ.get("SES_REGION", "us-east-1")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3003")

TOKEN_MAX_AGE = int(os.environ.get("TOKEN_MAX_AGE", "900"))  # 15 minutes = 900 seconds


def _get_serializer() -> itsdangerous.URLSafeTimedSerializer:
    return itsdangerous.URLSafeTimedSerializer(SECRET_KEY)


def request_magic_link(
    email: str,
    conn: psycopg2.extensions.connection,
) -> None:
    """Generate a signed magic link token, store it in DB, and send via SES.

    Args:
        email: Recipient email address.
        conn: psycopg2 connection.
    """
    s = _get_serializer()
    token = s.dumps(email)

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_MAX_AGE)
    token_id = secrets.token_urlsafe(16)  # short ID for the DB row

    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO magic_link_tokens (id, email, expires_at)
            VALUES (%s, %s, %s)
            """,
            (token_id, email, expires_at),
        )
    finally:
        cur.close()

    conn.commit()

    magic_url = f"{FRONTEND_URL}/auth/magic-link/verify?token={token}"

    # Send via SES
    ses_client = boto3.client("ses", region_name=SES_REGION)
    ses_client.send_email(
        Source=SES_FROM_EMAIL,
        Destination={"ToAddresses": [email]},
        Message={
            "Subject": {"Data": "Your Axiom login link"},
            "Body": {
                "Text": {
                    "Data": f"Click to log in: {magic_url}\n\nThis link expires in 15 minutes."
                },
                "Html": {
                    "Data": (
                        f'<p>Click to log in: <a href="{magic_url}">{magic_url}</a></p>'
                        "<p>This link expires in 15 minutes.</p>"
                    )
                },
            },
        },
    )


def verify_magic_link(
    token: str,
    conn: psycopg2.extensions.connection,
) -> int:
    """Decode and validate a magic link token, mark it used, upsert user, return user_id.

    Args:
        token: Signed token string from the magic link URL.
        conn: psycopg2 connection.

    Returns:
        user_id (int) of the authenticated user.

    Raises:
        ValueError if token expired, already used, or invalid.
    """
    s = _get_serializer()

    # Decode token — raises SignatureExpired or BadSignature on failure
    try:
        email = s.loads(token, max_age=TOKEN_MAX_AGE)
    except itsdangerous.SignatureExpired:
        raise ValueError("Magic link token has expired")
    except (itsdangerous.BadSignature, itsdangerous.BadData):
        raise ValueError("Invalid magic link token")

    # Look up unused token in DB
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, email, used_at
            FROM magic_link_tokens
            WHERE email = %s
              AND used_at IS NULL
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (email,),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if row is None:
        raise ValueError("Magic link token not found, already used, or expired")

    token_id, token_email, used_at = row

    if used_at is not None:
        raise ValueError("Magic link token has already been used")

    # Mark token as used
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE magic_link_tokens SET used_at = NOW() WHERE id = %s",
            (token_id,),
        )
    finally:
        cur.close()

    # Upsert user by email
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (email)
            VALUES (%s)
            ON CONFLICT (email) DO UPDATE
              SET email = excluded.email
            RETURNING id
            """,
            (email,),
        )
        user_row = cur.fetchone()
    finally:
        cur.close()

    conn.commit()

    return user_row[0]
