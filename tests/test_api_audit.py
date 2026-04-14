"""Tests for the audit history API endpoint.

Tests cover:
  - GET /api/audit/history with entity_type filter
  - 422 when entity_type is missing
  - Results ordered by created_at DESC
  - Response includes all required fields
  - User isolation (user A cannot see user B's rows)
"""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import get_current_user, get_effective_user_with_dek, get_pool_dep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_audit_row(
    id=1,
    user_id=1,
    entity_type="transaction_classification",
    entity_id=42,
    action="reclassify",
    old_value=None,
    new_value=None,
    actor_type="user",
    notes=None,
    created_at="2024-06-01T10:00:00",
):
    """Build a mock audit_log row tuple in DB column order."""
    return (
        id,
        user_id,
        entity_type,
        entity_id,
        action,
        old_value,
        new_value,
        actor_type,
        notes,
        created_at,
    )


_TEST_DEK = b"\x00" * 32


def _make_dek_override(user_dict):
    """Return a dep override for get_effective_user_with_dek that injects a test DEK.

    Must be async so ContextVar writes are visible to the async route handler.
    """
    from db.crypto import set_dek

    async def _override():
        set_dek(_TEST_DEK)
        return user_dict

    return _override


def _make_client(rows, user_dict):
    """Return (TestClient, mock_cursor) for the given rows and user."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn.return_value = None

    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: user_dict
    # Phase 16: audit router uses get_effective_user_with_dek — inject a test DEK
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(user_dict)

    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        client = TestClient(app, raise_server_exceptions=True)
        return client, mock_cursor


_USER_1 = {
    "user_id": 1,
    "near_account_id": "alice.near",
    "is_admin": False,
    "email": "alice@example.com",
    "username": "alice",
    "codename": None,
    "viewing_as_user_id": None,
    "permission_level": None,
}

_USER_2 = {
    "user_id": 2,
    "near_account_id": "bob.near",
    "is_admin": False,
    "email": "bob@example.com",
    "username": "bob",
    "codename": None,
    "viewing_as_user_id": None,
    "permission_level": None,
}


# ---------------------------------------------------------------------------
# Test 1: GET /api/audit/history returns rows for entity_type filter
# ---------------------------------------------------------------------------


def test_audit_history_returns_rows_for_entity_type():
    """GET /api/audit/history?entity_type=transaction_classification returns rows."""
    rows = [
        _make_audit_row(id=1, entity_type="transaction_classification", entity_id=10),
        _make_audit_row(id=2, entity_type="transaction_classification", entity_id=11),
    ]
    client, _ = _make_client(rows, _USER_1)

    resp = client.get("/api/audit/history?entity_type=transaction_classification")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["entity_type"] == "transaction_classification"


# ---------------------------------------------------------------------------
# Test 2: Missing entity_type returns 422
# ---------------------------------------------------------------------------


def test_audit_history_missing_entity_type_returns_422():
    """GET /api/audit/history without entity_type returns HTTP 422."""
    client, _ = _make_client([], _USER_1)

    resp = client.get("/api/audit/history")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 3: Rows ordered newest first (created_at DESC enforced in SQL)
# ---------------------------------------------------------------------------


def test_audit_history_ordered_newest_first():
    """Audit rows come back in the order returned by the DB (newest first from ORDER BY)."""
    rows = [
        _make_audit_row(id=5, created_at="2024-06-05T12:00:00"),
        _make_audit_row(id=3, created_at="2024-06-03T08:00:00"),
        _make_audit_row(id=1, created_at="2024-06-01T00:00:00"),
    ]
    client, mock_cursor = _make_client(rows, _USER_1)

    resp = client.get("/api/audit/history?entity_type=transaction_classification")
    assert resp.status_code == 200
    data = resp.json()
    # Verify that the SQL ORDER BY clause mentions DESC
    sql_call = str(mock_cursor.execute.call_args[0][0]).upper()
    assert "ORDER BY" in sql_call
    assert "DESC" in sql_call
    # And the returned order reflects the DB ordering
    ids = [r["id"] for r in data]
    assert ids == [5, 3, 1], f"Expected newest first, got: {ids}"


# ---------------------------------------------------------------------------
# Test 4: Response includes all required fields
# ---------------------------------------------------------------------------


def test_audit_history_response_fields():
    """Each audit row contains all required fields."""
    rows = [
        _make_audit_row(
            id=1,
            user_id=1,
            entity_type="transaction_classification",
            entity_id=42,
            action="reclassify",
            old_value='{"category": "income"}',
            new_value='{"category": "capital_gain"}',
            actor_type="user",
            notes="Manual fix",
            created_at="2024-06-01T10:00:00",
        )
    ]
    client, _ = _make_client(rows, _USER_1)

    resp = client.get("/api/audit/history?entity_type=transaction_classification")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    row = data[0]
    required_fields = {
        "id", "user_id", "entity_type", "entity_id",
        "action", "old_value", "new_value", "actor_type",
        "notes", "created_at",
    }
    missing = required_fields - set(row.keys())
    assert not missing, f"Missing fields: {missing}"


# ---------------------------------------------------------------------------
# Test 5: User isolation — each user's query scopes to their user_id
# ---------------------------------------------------------------------------


def test_audit_history_user_isolation():
    """User A's audit query uses user_id=1; User B's query uses user_id=2."""
    user_a_rows = [_make_audit_row(id=10, user_id=1)]
    user_b_rows = [_make_audit_row(id=20, user_id=2)]

    client_a, cursor_a = _make_client(user_a_rows, _USER_1)
    client_b, cursor_b = _make_client(user_b_rows, _USER_2)

    resp_a = client_a.get("/api/audit/history?entity_type=transaction_classification")
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert all(r["user_id"] == 1 for r in data_a), "User A should only see own rows"

    # Verify user_id=1 was passed in the SQL params for user A
    params_a = cursor_a.execute.call_args[0][1]
    assert params_a[0] == 1, f"Expected user_id=1 in query params, got: {params_a}"

    resp_b = client_b.get("/api/audit/history?entity_type=transaction_classification")
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert all(r["user_id"] == 2 for r in data_b), "User B should only see own rows"

    # Verify user_id=2 was passed in the SQL params for user B
    params_b = cursor_b.execute.call_args[0][1]
    assert params_b[0] == 2, f"Expected user_id=2 in query params, got: {params_b}"


# ---------------------------------------------------------------------------
# Test 6: entity_id filter narrows results
# ---------------------------------------------------------------------------


def test_audit_history_entity_id_filter():
    """When entity_id is provided, it is passed to the DB query."""
    rows = [_make_audit_row(id=1, entity_id=99)]
    client, mock_cursor = _make_client(rows, _USER_1)

    resp = client.get(
        "/api/audit/history?entity_type=transaction_classification&entity_id=99"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["entity_id"] == 99

    # Verify entity_id=99 is in query params
    params = mock_cursor.execute.call_args[0][1]
    assert 99 in params, f"entity_id=99 should be in DB query params: {params}"
