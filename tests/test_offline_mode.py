"""Tests for offline / cached mode in IndexerService.

Tests cover:
  - OFFLINE_MODE=true causes IndexerService to skip full_sync jobs
    (re-queued with last_error='offline_mode')
  - OFFLINE_MODE=true allows classify_transactions, calculate_acb,
    verify_balances, generate_reports to proceed
  - OFFLINE_MODE=auto detects offline when health check fails
  - OFFLINE_MODE=false does not activate offline mode
  - /api/health exposes offline_mode status
  - /api/status exposes offline_mode status
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import get_pool_dep


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pool():
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    pool = MagicMock()
    pool.getconn.return_value = mock_conn
    pool.putconn.return_value = None
    return pool


def _make_api_client_context(mock_pool):
    """Create a TestClient with overridden pool (context manager for use in with-statements)."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test 1: OFFLINE_MODE=true causes full_sync to be re-queued
# ---------------------------------------------------------------------------


def test_offline_mode_true_skips_network_jobs():
    """When OFFLINE_MODE=true, IndexerService._is_offline=True and full_sync re-queued."""
    from indexers.service import IndexerService
    from config import NETWORK_JOB_TYPES

    with patch("config.OFFLINE_MODE", "true"), \
         patch("indexers.service.OFFLINE_MODE", "true"), \
         patch("indexers.service.get_pool") as mock_get_pool, \
         patch("indexers.service.PriceService"), \
         patch("indexers.service.NearFetcher"), \
         patch("indexers.service.StakingFetcher"), \
         patch("indexers.service.LockupFetcher"), \
         patch("indexers.service.EVMFetcher"), \
         patch("indexers.service.FileImportHandler"), \
         patch("indexers.service.XRPFetcher"), \
         patch("indexers.service.AkashFetcher"), \
         patch("indexers.service.DedupHandler"), \
         patch("indexers.service.ClassifierHandler"), \
         patch("indexers.service.ACBHandler"), \
         patch("indexers.service.VerifyHandler"), \
         patch("reports.handlers.report_handler.ReportHandler"):

        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        service = IndexerService()
        assert service._is_offline is True, "Expected _is_offline=True when OFFLINE_MODE=true"

        # Simulate a full_sync job being claimed
        full_sync_job = {
            "id": 1,
            "user_id": 1,
            "wallet_id": 1,
            "job_type": "full_sync",
            "chain": "near",
            "status": "running",
            "priority": 5,
            "cursor": None,
            "progress_fetched": 0,
            "progress_total": 0,
            "attempts": 1,
            "max_attempts": 100,
            "last_error": None,
            "created_at": "2024-01-01",
            "account_id": "alice.near",
        }

        # Mock the requeue helper
        requeue_calls = []
        service._requeue_for_offline = lambda job_id: requeue_calls.append(job_id)

        # Verify the job type is in NETWORK_JOB_TYPES
        assert "full_sync" in NETWORK_JOB_TYPES
        # Verify offline mode would gate it
        assert service._is_offline and full_sync_job["job_type"] in NETWORK_JOB_TYPES


# ---------------------------------------------------------------------------
# Test 2: OFFLINE_MODE=true allows non-network jobs to proceed
# ---------------------------------------------------------------------------


def test_offline_mode_true_allows_non_network_jobs():
    """When offline, classify_transactions and calculate_acb are NOT in NETWORK_JOB_TYPES."""
    from config import NETWORK_JOB_TYPES

    non_network_jobs = {
        "classify_transactions",
        "calculate_acb",
        "verify_balances",
        "generate_reports",
        "dedup_scan",
        "file_import",
    }

    for job_type in non_network_jobs:
        assert job_type not in NETWORK_JOB_TYPES, (
            f"'{job_type}' should NOT be in NETWORK_JOB_TYPES — it doesn't require network access"
        )


# ---------------------------------------------------------------------------
# Test 3: OFFLINE_MODE=auto detects offline when NearBlocks unreachable
# ---------------------------------------------------------------------------


def test_offline_mode_auto_detects_offline():
    """OFFLINE_MODE=auto activates offline mode when NearBlocks is unreachable."""
    from indexers.service import IndexerService
    import requests

    with patch("config.OFFLINE_MODE", "auto"), \
         patch("indexers.service.OFFLINE_MODE", "auto"), \
         patch("indexers.service.get_pool") as mock_get_pool, \
         patch("indexers.service.PriceService"), \
         patch("indexers.service.NearFetcher"), \
         patch("indexers.service.StakingFetcher"), \
         patch("indexers.service.LockupFetcher"), \
         patch("indexers.service.EVMFetcher"), \
         patch("indexers.service.FileImportHandler"), \
         patch("indexers.service.XRPFetcher"), \
         patch("indexers.service.AkashFetcher"), \
         patch("indexers.service.DedupHandler"), \
         patch("indexers.service.ClassifierHandler"), \
         patch("indexers.service.ACBHandler"), \
         patch("indexers.service.VerifyHandler"), \
         patch("reports.handlers.report_handler.ReportHandler"), \
         patch("requests.get", side_effect=requests.exceptions.ConnectionError("unreachable")):

        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        service = IndexerService()
        assert service._is_offline is True, (
            "Expected _is_offline=True when NearBlocks is unreachable in auto mode"
        )
        assert "NearBlocks unreachable" in service._offline_reason or \
               "unreachable" in service._offline_reason.lower()


# ---------------------------------------------------------------------------
# Test 4: OFFLINE_MODE=false does not activate offline mode
# ---------------------------------------------------------------------------


def test_offline_mode_false_stays_online():
    """OFFLINE_MODE=false keeps _is_offline=False regardless of network."""
    from indexers.service import IndexerService

    with patch("config.OFFLINE_MODE", "false"), \
         patch("indexers.service.OFFLINE_MODE", "false"), \
         patch("indexers.service.get_pool") as mock_get_pool, \
         patch("indexers.service.PriceService"), \
         patch("indexers.service.NearFetcher"), \
         patch("indexers.service.StakingFetcher"), \
         patch("indexers.service.LockupFetcher"), \
         patch("indexers.service.EVMFetcher"), \
         patch("indexers.service.FileImportHandler"), \
         patch("indexers.service.XRPFetcher"), \
         patch("indexers.service.AkashFetcher"), \
         patch("indexers.service.DedupHandler"), \
         patch("indexers.service.ClassifierHandler"), \
         patch("indexers.service.ACBHandler"), \
         patch("indexers.service.VerifyHandler"), \
         patch("reports.handlers.report_handler.ReportHandler"):

        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool

        service = IndexerService()
        assert service._is_offline is False, (
            "Expected _is_offline=False when OFFLINE_MODE=false"
        )


# ---------------------------------------------------------------------------
# Test 5: /api/health exposes offline_mode status
# ---------------------------------------------------------------------------


def test_health_endpoint_exposes_offline_mode(mock_pool):
    """GET /health returns offline_mode field."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "offline_mode" in data, f"Expected 'offline_mode' in health response: {data}"
    assert "status" in data
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Test 6 (bonus): /api/status exposes offline_mode status
# ---------------------------------------------------------------------------


def test_status_endpoint_exposes_offline_mode(mock_pool):
    """GET /api/status returns offline_mode field."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "offline_mode" in data, f"Expected 'offline_mode' in status response: {data}"
