"""Tests for SSE streaming endpoint /api/stream/wallet/{wallet_id}.

Tests focus on:
1. Unit tests of the helper functions (_build_sse_event, _matches_wallet, KEEPALIVE_COMMENT)
2. Auth enforcement (401 for unauthenticated requests)
3. Content-type header returned as text/event-stream

Note: pytest-asyncio 1.3.0 is very old. We avoid complex async streaming tests
that may hang. The HTTP layer tests use standard TestClient (non-streaming) where
possible, and the SSE generator logic is tested as pure Python functions.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import get_current_user, get_pool_dep


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cursor():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    return cursor


@pytest.fixture
def mock_pool_conn(mock_cursor):
    conn = MagicMock()
    conn.cursor.return_value = mock_cursor
    return conn


@pytest.fixture
def mock_pool(mock_pool_conn):
    pool = MagicMock()
    pool.getconn.return_value = mock_pool_conn
    pool.putconn.return_value = None
    return pool


@pytest.fixture
def mock_user():
    return {
        "user_id": 1,
        "near_account_id": "alice.near",
        "is_admin": False,
        "email": "alice@example.com",
        "username": "alice",
        "codename": None,
        "viewing_as_user_id": None,
        "permission_level": None,
    }


@pytest.fixture
def unauth_client(mock_pool):
    """TestClient with no auth override."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    with patch("api.main.validate_env"), \
         patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# SSE streaming endpoint auth tests
# ---------------------------------------------------------------------------


class TestStreamingEndpointRequiresAuth:
    def test_streaming_requires_auth(self, unauth_client):
        """Unauthenticated request gets 401 from streaming endpoint."""
        resp = unauth_client.get("/api/stream/wallet/1")
        assert resp.status_code == 401


class TestStreamingEndpointRegistered:
    def test_streaming_endpoint_exists(self, mock_pool, mock_user):
        """Streaming endpoint is registered and accessible with auth."""
        app = create_app()
        app.dependency_overrides[get_pool_dep] = lambda: mock_pool
        app.dependency_overrides[get_current_user] = lambda: mock_user

        # Set DATABASE_URL so streaming connection setup doesn't skip
        mock_cursor = mock_pool.getconn.return_value.cursor.return_value
        # Wallet ownership check returns None (wallet not found) → yields error event
        mock_cursor.fetchone.return_value = None

        with patch("indexers.db.get_pool", return_value=mock_pool), \
             patch("indexers.db.close_pool"):
            with TestClient(app, raise_server_exceptions=True) as client:
                # Non-streaming GET — the generator yields the "wallet not found" error event
                # and then returns, so the response body is finite
                resp = client.get("/api/stream/wallet/1")

        app.dependency_overrides.clear()
        # Should succeed (200) with SSE content-type, yielding an error event body
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_streaming_wallet_not_found_yields_error_event(self, mock_pool, mock_user):
        """When wallet ownership check fails, SSE yields error event and closes."""
        app = create_app()
        app.dependency_overrides[get_pool_dep] = lambda: mock_pool
        app.dependency_overrides[get_current_user] = lambda: mock_user

        # Wallet ownership check returns None
        mock_cursor = mock_pool.getconn.return_value.cursor.return_value
        mock_cursor.fetchone.return_value = None

        with patch("indexers.db.get_pool", return_value=mock_pool), \
             patch("indexers.db.close_pool"):
            with TestClient(app, raise_server_exceptions=True) as client:
                resp = client.get("/api/stream/wallet/999")

        app.dependency_overrides.clear()
        assert resp.status_code == 200
        body = resp.text
        # Should contain an error event
        assert "data:" in body
        assert "error" in body


# ---------------------------------------------------------------------------
# Unit tests for SSE helper functions (pure Python, no HTTP layer)
# ---------------------------------------------------------------------------


class TestSSEHelperFunctions:
    def test_build_sse_event_format(self):
        """_build_sse_event returns properly formatted SSE data event."""
        from api.routers.streaming import _build_sse_event

        payload = {"wallet_id": 42, "tx_hash": "abc123", "amount": "100", "chain": "near"}
        event = _build_sse_event(payload)

        assert event.startswith("data: ")
        assert "abc123" in event
        assert event.endswith("\n\n")

    def test_build_sse_event_valid_json(self):
        """_build_sse_event contains valid JSON after 'data: ' prefix."""
        from api.routers.streaming import _build_sse_event

        payload = {"wallet_id": 42, "tx_hash": "abc123"}
        event = _build_sse_event(payload)

        # Strip "data: " prefix and trailing "\n\n"
        json_part = event[len("data: "):].rstrip("\n")
        parsed = json.loads(json_part)
        assert parsed["wallet_id"] == 42
        assert parsed["tx_hash"] == "abc123"

    def test_keepalive_format(self):
        """KEEPALIVE_COMMENT has correct SSE comment format."""
        from api.routers.streaming import KEEPALIVE_COMMENT

        assert KEEPALIVE_COMMENT.startswith(": ")
        assert KEEPALIVE_COMMENT.endswith("\n\n")
        assert "keepalive" in KEEPALIVE_COMMENT

    def test_matches_wallet_with_matching_id(self):
        """_matches_wallet returns True for matching wallet_id."""
        from api.routers.streaming import _matches_wallet

        payload = {"wallet_id": 42, "tx_hash": "abc"}
        assert _matches_wallet(payload, 42) is True

    def test_matches_wallet_with_non_matching_id(self):
        """_matches_wallet returns False for different wallet_id."""
        from api.routers.streaming import _matches_wallet

        payload = {"wallet_id": 99, "tx_hash": "abc"}
        assert _matches_wallet(payload, 42) is False

    def test_matches_wallet_with_string_id_in_payload(self):
        """_matches_wallet handles string wallet_id in payload (JSON coercion)."""
        from api.routers.streaming import _matches_wallet

        payload_str = {"wallet_id": "42", "tx_hash": "abc"}
        assert _matches_wallet(payload_str, 42) is True

    def test_matches_wallet_with_missing_wallet_id(self):
        """_matches_wallet returns False when wallet_id key is missing."""
        from api.routers.streaming import _matches_wallet

        payload = {"tx_hash": "abc"}
        assert _matches_wallet(payload, 42) is False

    def test_matches_wallet_with_invalid_wallet_id(self):
        """_matches_wallet returns False when wallet_id is non-numeric string."""
        from api.routers.streaming import _matches_wallet

        payload = {"wallet_id": "not-a-number", "tx_hash": "abc"}
        assert _matches_wallet(payload, 42) is False
