"""Tests for report generation, preview, download, and exchange import endpoints.

Covers:
  - POST /api/reports/generate — job queue creation
  - GET /api/reports/preview/{report_type} — inline previews
  - GET /api/reports/download/{year} — list report files
  - GET /api/reports/download/{year}/{filename} — serve file
  - GET /api/reports/status — check if reports exist for year
  - POST /api/exchanges/import — CSV upload + file_import job
  - GET /api/exchanges — list supported exchanges
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import get_current_user, get_effective_user_with_dek, get_pool_dep

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
def mock_conn(mock_cursor):
    conn = MagicMock()
    conn.cursor.return_value = mock_cursor
    return conn


@pytest.fixture
def mock_pool(mock_conn):
    pool = MagicMock()
    pool.getconn.return_value = mock_conn
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
def mock_admin():
    return {
        "user_id": 2,
        "near_account_id": "admin.near",
        "is_admin": True,
        "email": "admin@example.com",
        "username": "admin",
        "codename": None,
        "viewing_as_user_id": None,
        "permission_level": None,
    }


@pytest.fixture
def auth_client(mock_pool, mock_user):
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_user
    # Phase 16: reports router uses get_effective_user_with_dek — inject a test DEK
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(mock_user)
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(mock_pool, mock_admin):
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    # Phase 16: reports router uses get_effective_user_with_dek — inject a test DEK
    app.dependency_overrides[get_effective_user_with_dek] = _make_dek_override(mock_admin)
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture
def api_client(mock_pool):
    """Unauthenticated client — no user override."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Task 1: Report generation via job queue
# ---------------------------------------------------------------------------


def test_generate_report(auth_client, mock_cursor):
    """POST /api/reports/generate creates a generate_reports job and returns job_id."""
    mock_cursor.fetchone.return_value = (42,)

    resp = auth_client.post("/api/reports/generate", json={"year": 2024, "tax_treatment": "capital"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == 42
    assert data["status"] == "queued"


def test_generate_requires_auth(api_client):
    """POST /api/reports/generate returns 401 for unauthenticated requests."""
    resp = api_client.post("/api/reports/generate", json={"year": 2024, "tax_treatment": "capital"})
    assert resp.status_code == 401


def test_specialist_override_admin_only(auth_client, admin_client, mock_cursor):
    """specialist_override=True requires admin; non-admin gets 403."""
    # Non-admin requesting specialist_override should be 403
    resp = auth_client.post(
        "/api/reports/generate",
        json={"year": 2024, "tax_treatment": "capital", "specialist_override": True},
    )
    assert resp.status_code == 403

    # Admin can use specialist_override
    mock_cursor.fetchone.return_value = (99,)
    resp = admin_client.post(
        "/api/reports/generate",
        json={"year": 2024, "tax_treatment": "capital", "specialist_override": True},
    )
    assert resp.status_code == 200
    assert resp.json()["job_id"] == 99


def test_report_preview_capital_gains(auth_client, mock_cursor):
    """GET /api/reports/preview/capital-gains returns rows and total."""
    mock_cursor.fetchall.return_value = [
        ("2024-01-15", "NEAR", "100.00", "500.00", "400.00", "50.00"),
    ]
    mock_cursor.rowcount = 1

    resp = auth_client.get("/api/reports/preview/capital-gains")
    assert resp.status_code == 200
    data = resp.json()
    assert "rows" in data
    assert data["report_type"] == "capital-gains"
    assert isinstance(data["rows"], list)


def test_report_preview_income(auth_client, mock_cursor):
    """GET /api/reports/preview/income returns monthly summary rows."""
    mock_cursor.fetchall.return_value = [
        ("NEAR", "2024-01-01", "200.00", "1000.00"),
    ]

    resp = auth_client.get("/api/reports/preview/income")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "income"
    assert isinstance(data["rows"], list)


def test_report_preview_invalid_type(auth_client):
    """GET /api/reports/preview/unknown-type returns 400."""
    resp = auth_client.get("/api/reports/preview/unknown-type")
    assert resp.status_code == 400


def test_download_report_list(auth_client, tmp_path):
    """GET /api/reports/download/{year} lists all files in the tax package directory."""
    pkg_dir = tmp_path / "2024_tax_package"
    pkg_dir.mkdir()
    (pkg_dir / "capital_gains.csv").write_text("data")
    (pkg_dir / "income.csv").write_text("data2")

    with patch("api.routers.reports._get_output_dir", return_value=str(tmp_path)):
        resp = auth_client.get("/api/reports/download/2024")

    assert resp.status_code == 200
    data = resp.json()
    assert data["year"] == 2024
    assert len(data["files"]) == 2
    filenames = [f["name"] for f in data["files"]]
    assert "capital_gains.csv" in filenames


def test_download_report_list_not_found(auth_client, tmp_path):
    """GET /api/reports/download/{year} returns 404 if directory does not exist."""
    with patch("api.routers.reports._get_output_dir", return_value=str(tmp_path)):
        resp = auth_client.get("/api/reports/download/1999")

    assert resp.status_code == 404


def test_download_report_file(auth_client, tmp_path):
    """GET /api/reports/download/{year}/{filename} serves the file via FileResponse."""
    pkg_dir = tmp_path / "2024_tax_package"
    pkg_dir.mkdir()
    (pkg_dir / "capital_gains.csv").write_text("col1,col2\nval1,val2")

    with patch("api.routers.reports._get_output_dir", return_value=str(tmp_path)):
        resp = auth_client.get("/api/reports/download/2024/capital_gains.csv")

    assert resp.status_code == 200


def test_download_not_found(auth_client, tmp_path):
    """GET /api/reports/download/{year}/{filename} returns 404 for missing file."""
    pkg_dir = tmp_path / "2024_tax_package"
    pkg_dir.mkdir()

    with patch("api.routers.reports._get_output_dir", return_value=str(tmp_path)):
        resp = auth_client.get("/api/reports/download/2024/nonexistent.csv")

    assert resp.status_code == 404


def test_download_path_traversal(auth_client, tmp_path):
    """GET /api/reports/download/{year}/{filename} rejects path traversal attempts."""
    with patch("api.routers.reports._get_output_dir", return_value=str(tmp_path)):
        resp = auth_client.get("/api/reports/download/2024/..%2F..%2Fetc%2Fpasswd")

    assert resp.status_code in (400, 404)


def test_report_status(auth_client, tmp_path):
    """GET /api/reports/status?year=2024 returns exists=True when files present."""
    pkg_dir = tmp_path / "2024_tax_package"
    pkg_dir.mkdir()
    (pkg_dir / "capital_gains.csv").write_text("data")

    with patch("api.routers.reports._get_output_dir", return_value=str(tmp_path)):
        resp = auth_client.get("/api/reports/status?year=2024")

    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["year"] == 2024


def test_report_status_not_found(auth_client, tmp_path):
    """GET /api/reports/status?year=1999 returns exists=False when dir absent."""
    with patch("api.routers.reports._get_output_dir", return_value=str(tmp_path)):
        resp = auth_client.get("/api/reports/status?year=1999")

    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is False


# ---------------------------------------------------------------------------
# Task 1: Exchange import endpoint
# ---------------------------------------------------------------------------


def test_exchange_import(auth_client, mock_cursor):
    """POST /api/exchanges/import accepts CSV upload and queues file_import job."""
    mock_cursor.fetchone.side_effect = [
        (99,),   # wallets INSERT RETURNING id (exchange wallet)
        (10,),   # file_imports INSERT RETURNING id
        (20,),   # indexing_jobs INSERT RETURNING id
    ]

    csv_content = b"date,asset,amount,type\n2024-01-01,BTC,0.5,buy"
    resp = auth_client.post(
        "/api/exchanges/import",
        files={"file": ("coinbase.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == 20
    assert data["file_import_id"] == 10


def test_exchange_import_requires_auth(api_client):
    """POST /api/exchanges/import returns 401 for unauthenticated requests."""
    csv_content = b"date,asset,amount,type\n2024-01-01,BTC,0.5,buy"
    resp = api_client.post(
        "/api/exchanges/import",
        files={"file": ("coinbase.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 401


def test_list_exchanges(auth_client, mock_cursor):
    """GET /api/exchanges returns list of supported exchanges."""
    mock_cursor.fetchall.return_value = [
        ("coinbase", "Coinbase", True),
        ("wealthsimple", "Wealthsimple", True),
    ]

    resp = auth_client.get("/api/exchanges")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["slug"] == "coinbase"
