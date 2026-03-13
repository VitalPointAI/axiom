# Testing Patterns

**Analysis Date:** 2026-03-13

## Test Framework

**Runner:**
- pytest - all test files use pytest conventions
- Config: No explicit `pytest.ini` detected; pytest discovers tests automatically via `test_*.py` naming

**Assertion Library:**
- pytest built-in assertions (`assert`, `assert x == y`)
- unittest assertions in some test classes (`.assertEqual()`, `.assertRaises()`)
- No external assertion library (requests, hypothesis, etc.)

**Run Commands:**
```bash
pytest                    # Run all tests
pytest tests/test_*.py   # Run all tests in tests/ directory
pytest -v                # Verbose output with individual test names
pytest --tb=short        # Show short traceback format
```

No `conftest.py` fixture discovery or custom pytest plugins configured beyond shared fixtures.

## Test File Organization

**Location:**
- All tests in `/home/vitalpointai/projects/Axiom/tests/` directory
- Tests are **co-located with codebase** (not in separate test directory structure matching src/)
- Fixture data in `tests/fixtures/` subdirectory
- Test database data mocked, not requiring live PostgreSQL

**Naming:**
- Test files: `test_*.py` (e.g., `test_acb.py`, `test_classifier.py`, `test_api_auth.py`)
- Test functions: `test_*()` (e.g., `test_acquire()`, `test_multi_acquire()`)
- Test classes: `Test*` (e.g., `TestACBPool`, `TestACBEngine`, `TestClassifierRules`)
- Helper functions: `_*()` (e.g., `_make_pool()`, `_make_classifier()`)

**Structure:**
```
tests/
├── conftest.py                         # Shared pytest fixtures
├── fixtures/                           # Fixture data
├── test_acb.py                        # ACB engine tests
├── test_api_auth.py                   # FastAPI auth endpoint tests
├── test_api_wallets.py                # Wallets endpoint tests
├── test_api_portfolio.py               # Portfolio endpoint tests
├── test_api_transactions.py            # Transactions endpoint tests
├── test_api_reports.py                 # Reports endpoint tests
├── test_api_verification.py            # Verification endpoint tests
├── test_classifier.py                  # Transaction classifier tests
├── test_evm_decoder.py                 # EVM method signature decoding tests
├── test_evm_fetcher.py                 # EVM indexer tests
├── test_fifo.py                        # FIFO tracker tests
├── test_near_fetcher.py                # NEAR fetcher tests
├── test_price_service.py               # Price service tests
├── test_reports.py                     # Report generation tests
└── test_superficial.py                 # Superficial loss detection tests
```

## Test Structure

**Suite Organization:**

From `tests/test_acb.py`:
```python
"""
Tests for ACB (Adjusted Cost Base) engine.

Coverage:
  - TestACBPool: unit tests for the per-token pool state machine
  - TestACBEngine: integration tests for cross-wallet replay and income handling
  - TestGainsCalculator: tests for capital gains and income ledger population
"""

class TestACBPool:
    """Unit tests for the ACBPool (per-token running total / ACB calculator)."""

    def test_acquire(self):
        """Acquiring 1000 units at $5000 CAD -> acb_per_unit = 5.00000000"""
        from engine.acb import ACBPool
        pool = ACBPool("NEAR")
        result = pool.acquire(Decimal("1000"), Decimal("5000"))
        assert pool.total_units == Decimal("1000")
        assert pool.total_cost_cad == Decimal("5000")
```

From `tests/test_classifier.py`:
```python
"""Tests for TransactionClassifier — the core classification engine.

Covers CLASS-01 (NEAR rule-based), CLASS-02 (wallet graph / internal transfers),
CLASS-03 (staking reward linkage), CLASS-04 (lockup vest linkage),
CLASS-05 (EVM classification), and multi-leg decomposition.

All database interactions are mocked so no live DB is required.
"""

def _make_pool(rows=None, rowcount=1):
    """Build a minimal mock psycopg2 connection pool."""
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = None
    cur.rowcount = rowcount

    conn = MagicMock()
    conn.cursor.return_value = cur

    pool = MagicMock()
    pool.getconn.return_value = conn
    return pool, conn, cur
```

**Patterns:**

1. **Module docstring with coverage summary:**
   ```python
   """Tests for ReportEngine — report generation and validation.

   Tests:
     - TestReportGate: gate check logic (needs_review blocking)
     - TestCapitalGainsReport: CSV generation with summaries
   """
   ```

2. **Test class organization by component:**
   - One class per logical component (e.g., `TestACBPool`, `TestWalletGraph`)
   - Class docstring explains what is being tested

3. **Helper functions at module level:**
   ```python
   def _make_pool(rows=None):
       """Build a minimal mock psycopg2 connection pool."""

   def _make_classifier(pool=None, rules=None):
       """Build a TransactionClassifier with optional overrides."""
   ```

4. **Test method docstrings describe the scenario and assertion:**
   ```python
   def test_oversell_clamps(self):
       """If pool has 100 units and dispose(150), clamp to 100 and flag needs_review"""
   ```

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**

From `tests/conftest.py`:
```python
@pytest.fixture
def mock_pool(mock_conn):
    """MagicMock psycopg2 SimpleConnectionPool.

    getconn() returns mock_conn, putconn() is a no-op.
    """
    pool = MagicMock()
    pool.getconn.return_value = mock_conn
    pool.putconn.return_value = None
    return pool


@pytest.fixture
def api_client(mock_pool):
    """FastAPI TestClient with the DB pool dependency overridden.

    The get_pool_dep dependency is replaced with a mock so tests don't
    need a real PostgreSQL connection.
    """
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()
```

**Mocking helpers:**
```python
from unittest.mock import MagicMock, patch, call

# Create mock objects
pool = MagicMock()
pool.getconn.return_value = mock_conn

# Configure return values
cur.fetchall.return_value = [row1, row2]
cur.fetchone.return_value = None

# Setup side effects (multiple calls)
cur.fetchone.side_effect = [(row1,), (row2,), None]

# Verify calls made
pool.getconn.assert_called_once_with()
pool.putconn.assert_called_with(conn)

# Use patch for imports
with patch("module.function_name", return_value=value):
    test_function()
```

**What to Mock:**
- Database connections and cursors (psycopg2 operations)
- External API calls (e.g., price fetcher, blockchain indexers)
- Authentication/session dependencies in FastAPI tests
- Time-based functions when testing temporal logic

**What NOT to Mock:**
- Business logic being tested (ACBPool, TransactionClassifier, etc.)
- Pydantic model validation
- Core tax calculation engines
- Internal helper functions

## Fixtures and Factories

**Test Data:**

From `tests/conftest.py` — shared fixtures for all tests:
```python
@pytest.fixture
def mock_user():
    """Standard authenticated user context dict (non-admin)."""
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
def auth_client(mock_pool, mock_user):
    """FastAPI TestClient with both DB pool and authentication mocked."""
    app = create_app()
    app.dependency_overrides[get_pool_dep] = lambda: mock_pool
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch("indexers.db.get_pool", return_value=mock_pool), \
         patch("indexers.db.close_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    app.dependency_overrides.clear()
```

From `tests/test_superficial.py` — test-specific factories:
```python
def _make_ledger_row(**kwargs):
    """Create a mock capital_gains_ledger-style row."""
    defaults = {
        "id": 1,
        "user_id": 1,
        "token_symbol": "NEAR",
        "gain_loss_cad": Decimal("-200.00"),
        "units_disposed": Decimal("100"),
        "block_timestamp": 1680000000,
        "acb_snapshot_id": 10,
    }
    defaults.update(kwargs)
    row = MagicMock()
    for k, v in defaults.items():
        setattr(row, k, v)
    return row
```

**Location:**
- Shared fixtures: `tests/conftest.py` — available to all tests
- Test-specific factories: defined at module level in test file (e.g., `_make_pool()`)
- Fixture data: `tests/fixtures/` (if using file-based data)

## Coverage

**Requirements:** No explicit coverage enforcement detected

**View Coverage:**
```bash
pytest --cov=api --cov=engine --cov=indexers tests/
pytest --cov-report=html  # Generate HTML coverage report
```

Current test files cover:
- API endpoints (auth, wallets, transactions, portfolio, reports, verification)
- Core engines (ACB, FIFO, gains calculation, classification)
- Utility modules (EVM decoder, wallet graph, spam detector, price service)
- Exchange parsers (Coinbase, Crypto.com, Wealthsimple)

## Test Types

**Unit Tests:**
- Scope: Single function or small class (e.g., ACBPool.acquire, ACBPool.dispose)
- Approach: Test with specific inputs, verify output and state changes
- Example from `test_acb.py`:
  ```python
  def test_acquire(self):
      """Acquiring 1000 units at $5000 CAD -> acb_per_unit = 5.00000000"""
      from engine.acb import ACBPool
      pool = ACBPool("NEAR")
      result = pool.acquire(Decimal("1000"), Decimal("5000"))
      assert pool.total_units == Decimal("1000")
      assert pool.acb_per_unit == Decimal("5.00000000")
  ```

**Integration Tests:**
- Scope: Multiple components interacting (e.g., ACBEngine with classifier output)
- Approach: Set up mocked DB with test data, replay through engine, verify ledger results
- Example from `test_acb.py` — `TestACBEngine` class testing full replay flow
- Example from `test_classifier.py` — classifier rules against transactions with DB mocks

**E2E Tests:**
- Status: Not observed in current test suite
- FastAPI tests use TestClient (simulated requests, not real HTTP)
- No browser/Selenium tests for UI

## Common Patterns

**Async Testing:**
FastAPI TestClient handles async routes automatically:
```python
def test_health_endpoint(api_client):
    """GET /health must return 200 with status ok — no auth required."""
    response = api_client.get("/health")
    assert response.status_code == 200
```

**Error Testing:**

From `tests/test_reports.py`:
```python
def test_raises_when_cgl_has_needs_review(self):
    """Test: ReportBlockedError raised when capital_gains_ledger has needs_review=TRUE rows."""
    from reports.engine import ReportEngine, ReportBlockedError
    pool, conn, cur = self._make_pool(cgl_count=3, acb_count=0)
    engine = ReportEngine(pool)
    with self.assertRaises(ReportBlockedError):
        engine._check_gate(user_id=1, tax_year=2024)
```

**Testing with side_effect for sequential calls:**
```python
cur.fetchone.side_effect = [(cgl_count,), (acb_count,)]  # Two sequential calls return different values
```

**Testing HTTP responses:**
```python
def test_unauthenticated_wallets_returns_401(api_client, mock_cursor):
    """GET /api/wallets without a session cookie must return 401."""
    mock_cursor.fetchone.return_value = None  # No session row in DB
    response = api_client.get("/api/wallets")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
```

**Testing database operations:**
```python
def test_session_create(auth_client, mock_conn, mock_cursor):
    """POST /auth/session/create inserts row and returns session ID."""
    mock_cursor.fetchone.return_value = (1, "abc123def456")  # (id, token)
    response = auth_client.post("/auth/session/create", json={"...": "..."})
    assert response.status_code == 201
    # Verify SQL was executed
    mock_cursor.execute.assert_called()
```

---

*Testing analysis: 2026-03-13*
