"""WebAuthn passkey registration and authentication using the webauthn library.

Implements the four-step WebAuthn flow:
  1. start_registration  — generate challenge + options (register start)
  2. finish_registration — verify credential, create user + passkey row (register finish)
  3. start_authentication — generate challenge + options (login start)
  4. finish_authentication — verify assertion, update counter (login finish)

Challenges are stored in the PostgreSQL ``challenges`` table (not in-memory)
so they survive server restarts and work in multi-process deployments.

Configuration via environment variables:
  RP_ID    — Relying Party domain (default: "localhost")
  RP_NAME  — Human-readable RP name (default: "Axiom")
  ORIGIN   — Expected browser origin (default: "http://localhost:3003")
"""

import json
import os
import secrets
from base64 import b64encode
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import psycopg2.extensions
import webauthn
from webauthn.helpers.base64url_to_bytes import base64url_to_bytes

RP_ID = os.environ.get("RP_ID", "localhost")
RP_NAME = os.environ.get("RP_NAME", "Axiom")
ORIGIN = os.environ.get("ORIGIN", "http://localhost:3003")

_CHALLENGE_TTL_SECONDS = 60  # 1 minute for WebAuthn challenges


def _store_challenge(
    challenge_bytes: bytes,
    challenge_type: str,
    conn: psycopg2.extensions.connection,
    metadata: Optional[dict] = None,
    ttl: int = _CHALLENGE_TTL_SECONDS,
) -> str:
    """Insert challenge into the challenges table, return challenge_id."""
    challenge_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO challenges (id, challenge, challenge_type, expires_at, metadata)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (challenge_id, challenge_bytes, challenge_type, expires_at, json.dumps(metadata) if metadata else None),
        )
    finally:
        cur.close()

    conn.commit()
    return challenge_id


def _get_challenge(
    challenge_id: str,
    conn: psycopg2.extensions.connection,
) -> bytes:
    """Retrieve and validate (not expired) challenge bytes from DB.

    Raises:
        ValueError if challenge not found or expired.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT challenge, expires_at
            FROM challenges
            WHERE id = %s
            """,
            (challenge_id,),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if row is None:
        raise ValueError(f"Challenge not found: {challenge_id}")

    challenge_bytes, expires_at = row
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise ValueError(f"Challenge expired: {challenge_id}")

    # psycopg2 returns bytea as memoryview; convert to bytes for WebAuthn comparison
    return bytes(challenge_bytes) if not isinstance(challenge_bytes, bytes) else challenge_bytes


def _delete_challenge(challenge_id: str, conn: psycopg2.extensions.connection) -> None:
    """Remove a consumed challenge from the DB."""
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM challenges WHERE id = %s", (challenge_id,))
    finally:
        cur.close()
    conn.commit()


def start_registration(
    username: str,
    conn: psycopg2.extensions.connection,
) -> Dict[str, Any]:
    """Generate WebAuthn registration options and store the challenge in PostgreSQL.

    Args:
        username: The user's display name for the authenticator.
        conn: psycopg2 connection — must be within a valid transaction context.

    Returns:
        dict with ``challenge_id`` (str) and ``options`` (JSON-serializable dict).
    """
    options = webauthn.generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_name=username,
    )

    challenge_id = _store_challenge(
        challenge_bytes=options.challenge,
        challenge_type="registration",
        conn=conn,
    )

    return {
        "challenge_id": challenge_id,
        "options": json.loads(webauthn.options_to_json(options)),
    }


def finish_registration(
    challenge_id: str,
    credential: Dict[str, Any],
    conn: psycopg2.extensions.connection,
) -> int:
    """Verify a registration credential and persist user + passkey to DB.

    Args:
        challenge_id: The challenge_id returned by start_registration.
        credential: Raw WebAuthn credential JSON from the browser.
        conn: psycopg2 connection.

    Returns:
        user_id (int) of the created or found user.

    Raises:
        ValueError if challenge expired/not found.
        webauthn.helpers.exceptions.InvalidRegistrationResponse on bad credential.
    """
    expected_challenge = _get_challenge(challenge_id, conn)

    verified = webauthn.verify_registration_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )

    # Consume the challenge
    _delete_challenge(challenge_id, conn)

    credential_id_b64 = b64encode(verified.credential_id).decode("ascii")

    # Find or create user by credential (username stored in challenge metadata)
    cur = conn.cursor()
    try:
        # Use credential_id to look for existing user (passkey may already exist)
        cur.execute(
            "SELECT user_id FROM passkeys WHERE credential_id = %s",
            (credential_id_b64,),
        )
        existing = cur.fetchone()
        if existing:
            return existing[0]

        # Create a new user (username optional — can be updated later)
        cur.execute(
            """
            INSERT INTO users (near_account_id)
            VALUES (NULL)
            RETURNING id
            """,
        )
        row = cur.fetchone()
        user_id = row[0]

        # Store the passkey
        device_type = (
            verified.credential_device_type.value
            if hasattr(verified.credential_device_type, "value")
            else str(verified.credential_device_type)
        )
        cur.execute(
            """
            INSERT INTO passkeys (user_id, credential_id, public_key, counter, device_type, backed_up)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                credential_id_b64,
                verified.credential_public_key,
                verified.sign_count,
                device_type,
                verified.credential_backed_up,
            ),
        )
    finally:
        cur.close()

    conn.commit()
    return user_id


def start_authentication(
    conn: psycopg2.extensions.connection,
) -> Dict[str, Any]:
    """Generate WebAuthn authentication options (discoverable credentials).

    No allowCredentials list — lets the browser use any registered passkey.

    Args:
        conn: psycopg2 connection.

    Returns:
        dict with ``challenge_id`` and ``options``.
    """
    options = webauthn.generate_authentication_options(
        rp_id=RP_ID,
        # No allow_credentials — discoverable credentials / resident keys
    )

    challenge_id = _store_challenge(
        challenge_bytes=options.challenge,
        challenge_type="authentication",
        conn=conn,
    )

    return {
        "challenge_id": challenge_id,
        "options": json.loads(webauthn.options_to_json(options)),
    }


def finish_authentication(
    challenge_id: str,
    credential: Dict[str, Any],
    conn: psycopg2.extensions.connection,
) -> int:
    """Verify an authentication assertion and update the passkey counter.

    Args:
        challenge_id: The challenge_id returned by start_authentication.
        credential: Raw WebAuthn assertion JSON from the browser.
        conn: psycopg2 connection.

    Returns:
        user_id (int) of the authenticated user.

    Raises:
        ValueError if challenge expired, passkey not found, or counter regression.
        webauthn.helpers.exceptions.InvalidAuthenticationResponse on bad assertion.
    """
    expected_challenge = _get_challenge(challenge_id, conn)

    # Extract credential_id from the incoming credential
    raw_id = credential.get("id") or credential.get("rawId", "")
    try:
        cred_id_bytes = base64url_to_bytes(raw_id)
    except Exception:
        cred_id_bytes = raw_id.encode() if isinstance(raw_id, str) else raw_id

    cred_id_b64 = b64encode(cred_id_bytes).decode("ascii")

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, user_id, public_key, counter
            FROM passkeys
            WHERE credential_id = %s
            """,
            (cred_id_b64,),
        )
        passkey_row = cur.fetchone()
    finally:
        cur.close()

    if passkey_row is None:
        raise ValueError(f"Passkey not found for credential: {cred_id_b64}")

    passkey_id, user_id, public_key, current_counter = passkey_row

    verified = webauthn.verify_authentication_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
        credential_public_key=public_key,
        credential_current_sign_count=current_counter,
    )

    # Consume challenge and update counter
    _delete_challenge(challenge_id, conn)

    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE passkeys
            SET counter = %s, last_used_at = NOW()
            WHERE id = %s
            """,
            (verified.new_sign_count, passkey_id),
        )
    finally:
        cur.close()

    conn.commit()
    return user_id
