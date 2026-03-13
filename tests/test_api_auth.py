"""Tests for FastAPI app foundation and auth endpoints.

Tests:
  Foundation (from 07-01):
  - test_health_endpoint: GET /health returns 200 {"status": "ok"}
  - test_unauthenticated_returns_401: protected routes return 401 without session
  - test_multi_user_isolation: verify user_id filtering expectation (stub)
  - test_accountant_viewing_as: verify client context switching (stub)

  Session management (07-02 Task 1):
  - test_session_create: create_session inserts row, sets httponly cookie
  - test_session_destroy: destroy_session deletes row, clears cookie

  WebAuthn passkey register (07-02 Task 1):
  - test_register_start: POST /auth/register/start returns options + challenge_id
  - test_register_finish: POST /auth/register/finish creates user+passkey, returns session
  - test_login_start: POST /auth/login/start returns authentication options
  - test_login_finish: POST /auth/login/finish verifies assertion, returns session

  Session endpoints:
  - test_get_session: GET /auth/session returns current user from valid session cookie
  - test_logout: POST /auth/logout destroys session

  OAuth + Magic link (07-02 Task 2):
  - test_oauth_start: GET /auth/oauth/start returns Google auth URL
  - test_oauth_callback: POST /auth/oauth/callback exchanges code for token, creates session
  - test_magic_link_request: POST /auth/magic-link/request sends email (mocked), stores token
  - test_magic_link_verify: GET /auth/magic-link/verify validates token, creates session
  - test_magic_link_expired: expired token returns 401
  - test_magic_link_reuse: already-used token returns 401
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
import json

import pytest
from fastapi import Response as FastAPIResponse
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_pool_dep
from api.main import create_app


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


def test_health_endpoint(api_client):
    """GET /health must return 200 with status ok — no auth required."""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


def test_unauthenticated_wallets_returns_401(api_client, mock_pool, mock_conn, mock_cursor):
    """GET /api/wallets without a session cookie must return 401.

    The mock DB is configured to return no session row so get_current_user
    raises HTTPException 401.
    """
    # Simulate no matching session in DB
    mock_cursor.fetchone.return_value = None
    response = api_client.get("/api/wallets")
    assert response.status_code == 401


def test_unauthenticated_transactions_returns_401(api_client):
    """GET /api/transactions without a session cookie must return 401."""
    response = api_client.get("/api/transactions")
    assert response.status_code == 401


def test_unauthenticated_portfolio_returns_401(api_client):
    """GET /api/portfolio without a session cookie must return 401."""
    response = api_client.get("/api/portfolio")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Multi-user isolation (stub — full tests in 07-04)
# ---------------------------------------------------------------------------


def test_multi_user_isolation_stub(mock_user):
    """Verify that the user context carries user_id for query filtering."""
    assert mock_user["user_id"] == 1
    assert mock_user["is_admin"] is False


# ---------------------------------------------------------------------------
# Accountant viewing mode (stub — full tests in 07-04)
# ---------------------------------------------------------------------------


def test_accountant_viewing_as_stub(mock_user):
    """Verify the mock_user fixture has viewing_as_user_id=None for normal mode."""
    assert mock_user["viewing_as_user_id"] is None
    assert mock_user["permission_level"] is None


def test_accountant_context_switches_user_id(mock_pool, mock_conn, mock_cursor):
    """When neartax_viewing_as cookie is set, get_effective_user returns client context."""
    from api.dependencies import get_effective_user, get_current_user

    accountant = {
        "user_id": 10,
        "near_account_id": "accountant.near",
        "is_admin": False,
        "email": "accountant@firm.com",
        "username": "accountant",
        "codename": None,
    }

    mock_cursor.fetchone.return_value = (
        "read", 20, "client.near", False, "client@example.com", "client", None
    )

    result = get_effective_user(
        user=accountant,
        neartax_viewing_as="20",
        pool=mock_pool,
    )

    assert result["user_id"] == 20
    assert result["viewing_as_user_id"] == 10
    assert result["permission_level"] == "read"


def test_accountant_no_access_raises_403(mock_pool, mock_conn, mock_cursor):
    """get_effective_user raises 403 when accountant_access row does not exist."""
    from fastapi import HTTPException
    from api.dependencies import get_effective_user

    accountant = {
        "user_id": 10,
        "near_account_id": "accountant.near",
        "is_admin": False,
        "email": "accountant@firm.com",
        "username": "accountant",
        "codename": None,
    }

    mock_cursor.fetchone.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_effective_user(
            user=accountant,
            neartax_viewing_as="99",
            pool=mock_pool,
        )

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Task 1: Session management tests
# ---------------------------------------------------------------------------


def test_session_create(mock_pool, mock_conn, mock_cursor):
    """create_session inserts a row in sessions table and sets httponly cookie."""
    from api.auth.session import create_session

    response = MagicMock()
    create_session(user_id=1, response=response, conn=mock_conn)

    # Verify DB INSERT was called
    assert mock_cursor.execute.called
    call_args = mock_cursor.execute.call_args[0][0]
    assert "INSERT" in call_args.upper()
    assert "sessions" in call_args.lower()

    # Verify cookie was set with correct attributes
    assert response.set_cookie.called
    cookie_kwargs = response.set_cookie.call_args[1]
    assert cookie_kwargs.get("key") == "neartax_session"
    assert cookie_kwargs.get("httponly") is True
    assert cookie_kwargs.get("samesite") == "lax"

    # Commit should be called
    assert mock_conn.commit.called


def test_session_create_max_age(mock_pool, mock_conn, mock_cursor):
    """create_session sets cookie max_age to 7 days (604800 seconds)."""
    from api.auth.session import create_session

    response = MagicMock()
    create_session(user_id=1, response=response, conn=mock_conn)

    cookie_kwargs = response.set_cookie.call_args[1]
    # 7 days = 604800 seconds
    assert cookie_kwargs.get("max_age") == 604800


def test_session_destroy(mock_pool, mock_conn, mock_cursor):
    """destroy_session deletes session row and clears cookie."""
    from api.auth.session import destroy_session

    response = MagicMock()
    destroy_session(session_id="test-session-id", response=response, conn=mock_conn)

    # Verify DELETE was called
    assert mock_cursor.execute.called
    call_args = mock_cursor.execute.call_args[0][0]
    assert "DELETE" in call_args.upper()
    assert "sessions" in call_args.lower()

    # Verify cookie was deleted
    assert response.delete_cookie.called
    delete_kwargs = response.delete_cookie.call_args
    # Key is either positional or keyword
    if delete_kwargs[0]:
        assert delete_kwargs[0][0] == "neartax_session"
    else:
        assert delete_kwargs[1].get("key") == "neartax_session"


# ---------------------------------------------------------------------------
# Task 1: WebAuthn passkey tests
# ---------------------------------------------------------------------------


def test_register_start(mock_conn, mock_cursor):
    """start_registration returns WebAuthn options with challenge stored in DB."""
    from api.auth.passkey import start_registration

    # Mock the webauthn library
    mock_options = MagicMock()
    mock_options.challenge = b"test_challenge_bytes"

    with patch("api.auth.passkey.webauthn.generate_registration_options", return_value=mock_options) as mock_gen, \
         patch("api.auth.passkey.webauthn.options_to_json", return_value='{"publicKey": {}}') as mock_json:

        result = start_registration(username="alice", conn=mock_conn)

    # Should have stored challenge in DB
    assert mock_cursor.execute.called

    # Should return challenge_id and options
    assert "challenge_id" in result
    assert "options" in result
    assert result["challenge_id"] is not None


def test_register_finish(mock_conn, mock_cursor):
    """finish_registration verifies credential, creates user+passkey, returns user_id."""
    from api.auth.passkey import finish_registration

    challenge_id = "test-challenge-id"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)

    # Mock DB: returns challenge row first, then None for user lookup, then user insert
    challenge_row = (b"test_challenge_bytes", expires_at)
    mock_cursor.fetchone.side_effect = [
        challenge_row,    # SELECT challenge FROM challenges
        None,             # SELECT id FROM users (user not found)
        (42,),            # INSERT INTO users RETURNING id
    ]

    mock_verified = MagicMock()
    mock_verified.credential_id = b"cred_id_bytes"
    mock_verified.credential_public_key = b"pub_key_bytes"
    mock_verified.sign_count = 0
    mock_verified.credential_backed_up = False
    mock_verified.credential_device_type = MagicMock()
    mock_verified.credential_device_type.value = "singleDevice"

    credential = {
        "id": "base64url_cred_id",
        "rawId": "base64url_cred_id",
        "response": {
            "clientDataJSON": "eyJ0eXBlIjoibm9uZSJ9",
            "attestationObject": "o2NmbXRkbm9uZQ==",
        },
        "type": "public-key",
    }

    with patch("api.auth.passkey.webauthn.verify_registration_response", return_value=mock_verified):
        user_id = finish_registration(
            challenge_id=challenge_id,
            credential=credential,
            conn=mock_conn,
        )

    assert user_id == 42


def test_login_start(mock_conn, mock_cursor):
    """start_authentication returns authentication options with challenge stored in DB."""
    from api.auth.passkey import start_authentication

    mock_options = MagicMock()
    mock_options.challenge = b"auth_challenge_bytes"

    with patch("api.auth.passkey.webauthn.generate_authentication_options", return_value=mock_options), \
         patch("api.auth.passkey.webauthn.options_to_json", return_value='{"publicKey": {}}'):

        result = start_authentication(conn=mock_conn)

    assert "challenge_id" in result
    assert "options" in result
    # Challenge should be stored in DB
    assert mock_cursor.execute.called


def test_login_finish(mock_conn, mock_cursor):
    """finish_authentication verifies assertion, updates counter, returns user_id."""
    from api.auth.passkey import finish_authentication

    challenge_id = "test-auth-challenge-id"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)

    # Mock DB: challenge row, passkey row
    challenge_row = (b"auth_challenge_bytes", expires_at)
    passkey_row = (
        "passkey-uuid",     # id
        5,                  # user_id
        b"pub_key_bytes",   # public_key
        10,                 # counter
    )
    mock_cursor.fetchone.side_effect = [
        challenge_row,  # SELECT FROM challenges
        passkey_row,    # SELECT FROM passkeys
    ]

    mock_verified = MagicMock()
    mock_verified.new_sign_count = 11

    credential = {
        "id": "base64url_cred_id",
        "rawId": "base64url_cred_id",
        "response": {
            "clientDataJSON": "eyJ0eXBlIjoibm9uZSJ9",
            "authenticatorData": "SZYN5YgOjGh0NBcPZHZgW4_krrmihjLHmVzzuoMdl2MBAAAACw==",
            "signature": "MEYCIQC...",
        },
        "type": "public-key",
    }

    with patch("api.auth.passkey.webauthn.verify_authentication_response", return_value=mock_verified):
        user_id = finish_authentication(
            challenge_id=challenge_id,
            credential=credential,
            conn=mock_conn,
        )

    assert user_id == 5
    # Counter update should be called
    assert mock_cursor.execute.called


# ---------------------------------------------------------------------------
# Task 1: Auth router endpoints tests
# ---------------------------------------------------------------------------


def test_post_register_start_endpoint(api_client, mock_pool, mock_conn, mock_cursor):
    """POST /auth/register/start returns 200 with challenge_id and options."""
    mock_options = MagicMock()
    mock_options.challenge = b"reg_challenge"

    with patch("api.auth.passkey.webauthn.generate_registration_options", return_value=mock_options), \
         patch("api.auth.passkey.webauthn.options_to_json", return_value='{"publicKey": {"challenge": "abc"}}'):
        response = api_client.post("/auth/register/start", json={"username": "alice"})

    assert response.status_code == 200
    data = response.json()
    assert "challenge_id" in data
    assert "options" in data


def test_post_register_finish_endpoint(api_client, mock_pool, mock_conn, mock_cursor):
    """POST /auth/register/finish creates user and returns session."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    challenge_row = (b"reg_challenge_bytes", expires_at)

    mock_cursor.fetchone.side_effect = [
        challenge_row,  # Challenge lookup
        None,           # User not found
        (1,),           # User INSERT RETURNING id
        # Session and passkey INSERT calls will also go through cursor
    ]

    mock_verified = MagicMock()
    mock_verified.credential_id = b"cred_id"
    mock_verified.credential_public_key = b"pub_key"
    mock_verified.sign_count = 0
    mock_verified.credential_backed_up = False
    mock_verified.credential_device_type = MagicMock()
    mock_verified.credential_device_type.value = "singleDevice"

    with patch("api.auth.passkey.webauthn.verify_registration_response", return_value=mock_verified):
        response = api_client.post(
            "/auth/register/finish",
            json={
                "challenge_id": "test-challenge-id",
                "credential": {"id": "cred_id", "type": "public-key", "response": {}},
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert "expires_at" in data


def test_get_session_endpoint(auth_client, mock_user):
    """GET /auth/session returns the current user info when session is valid."""
    response = auth_client.get("/auth/session")
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert data["user"]["user_id"] == mock_user["user_id"]


def test_post_logout_endpoint(auth_client, mock_conn, mock_cursor):
    """POST /auth/logout destroys session and clears cookie."""
    response = auth_client.post("/auth/logout", cookies={"neartax_session": "some-session-id"})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Task 2: Google OAuth tests
# ---------------------------------------------------------------------------


def test_oauth_start(api_client):
    """GET /auth/oauth/start returns Google auth URL with state in challenges table."""
    with patch("api.auth.oauth.start_google_oauth") as mock_start:
        mock_start.return_value = {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=test&state=abc123",
            "state": "abc123",
        }
        response = api_client.get("/auth/oauth/start")

    assert response.status_code == 200
    data = response.json()
    assert "auth_url" in data
    assert "google.com" in data["auth_url"]


def test_oauth_callback(api_client, mock_pool, mock_conn, mock_cursor):
    """POST /auth/oauth/callback exchanges code for token, upserts user, creates session."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    # Mock DB: state challenge row, then user insert/upsert row
    mock_cursor.fetchone.side_effect = [
        (b"state_bytes", expires_at),  # state challenge lookup
        (99,),                          # user upsert RETURNING id
    ]

    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "goog_token", "token_type": "Bearer"}
    mock_token_response.raise_for_status = MagicMock()

    mock_userinfo_response = MagicMock()
    mock_userinfo_response.json.return_value = {
        "email": "user@gmail.com",
        "name": "Test User",
        "sub": "google_user_123",
    }
    mock_userinfo_response.raise_for_status = MagicMock()

    with patch("api.auth.oauth.httpx") as mock_httpx:
        mock_client = MagicMock()
        mock_httpx.Client.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_token_response
        mock_client.get.return_value = mock_userinfo_response

        response = api_client.post(
            "/auth/oauth/callback",
            json={"code": "auth_code_123", "state": "state_abc"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert "expires_at" in data


def test_magic_link_request(api_client, mock_pool, mock_conn, mock_cursor):
    """POST /auth/magic-link/request sends email (mocked SES) and stores token."""
    with patch("api.auth.magic_link.boto3") as mock_boto3:
        mock_ses = MagicMock()
        mock_boto3.client.return_value = mock_ses
        mock_ses.send_email.return_value = {"MessageId": "test-msg-id"}

        response = api_client.post(
            "/auth/magic-link/request",
            json={"email": "user@example.com"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("sent") is True


def test_magic_link_verify(api_client, mock_pool, mock_conn, mock_cursor):
    """GET /auth/magic-link/verify validates token, creates session, returns session."""
    import itsdangerous

    secret_key = "test-secret-key"
    email = "user@example.com"
    s = itsdangerous.URLSafeTimedSerializer(secret_key)
    token = s.dumps(email)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    # Mock: token row (valid, unused), then user upsert
    mock_cursor.fetchone.side_effect = [
        ("ml-token-id", email, None),  # magic_link_tokens row (id, email, used_at=None)
        (77,),                          # user upsert RETURNING id
    ]

    with patch("api.auth.magic_link.SECRET_KEY", secret_key):
        response = api_client.get(f"/auth/magic-link/verify?token={token}")

    assert response.status_code == 200
    data = response.json()
    assert "user" in data


def test_magic_link_expired(api_client, mock_pool, mock_conn, mock_cursor):
    """Expired magic link token returns 401."""
    import itsdangerous

    secret_key = "test-secret-key"
    email = "user@example.com"
    s = itsdangerous.URLSafeTimedSerializer(secret_key)
    token = s.dumps(email)

    # Simulate signature expired by making max_age=0
    with patch("api.auth.magic_link.SECRET_KEY", secret_key), \
         patch("api.auth.magic_link.TOKEN_MAX_AGE", 0):  # expired immediately
        import time
        time.sleep(0.01)  # ensure some time passes
        response = api_client.get(f"/auth/magic-link/verify?token={token}")

    assert response.status_code == 401


def test_magic_link_reuse(api_client, mock_pool, mock_conn, mock_cursor):
    """Already-used magic link token returns 401."""
    import itsdangerous

    secret_key = "test-secret-key"
    email = "user@example.com"
    s = itsdangerous.URLSafeTimedSerializer(secret_key)
    token = s.dumps(email)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    # Token row has used_at set (already used)
    mock_cursor.fetchone.return_value = (
        "ml-token-id", email, datetime.now(timezone.utc)  # used_at is not None
    )

    with patch("api.auth.magic_link.SECRET_KEY", secret_key):
        response = api_client.get(f"/auth/magic-link/verify?token={token}")

    assert response.status_code == 401
