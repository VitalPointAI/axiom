# Coding Conventions

**Analysis Date:** 2026-03-13

## Naming Patterns

**Files:**
- Modules: `snake_case.py` (e.g., `classifier.py`, `acb.py`, `wallet_graph.py`)
- API routers: `snake_case.py` in `api/routers/` (e.g., `wallets.py`, `transactions.py`)
- Schemas: `snake_case.py` in `api/schemas/` (e.g., `auth.py`, `wallets.py`)
- Indexers: `snake_case.py` with descriptive names (e.g., `near_fetcher.py`, `evm_indexer.py`)
- Test files: `test_*.py` (e.g., `test_acb.py`, `test_classifier.py`)
- Exchange parsers: `snake_case.py` in `indexers/exchange_parsers/` (e.g., `coinbase.py`, `crypto_com.py`)

**Functions:**
- Public functions: `snake_case()` (e.g., `get_connection()`, `create_app()`, `resolve_token_symbol()`)
- Private functions: `_snake_case()` with leading underscore (e.g., `_make_pool()`, `_is_near_chain()`, `_compute_stage()`)
- Helper functions in tests: `_make_*()` pattern (e.g., `_make_pool()`, `_make_classifier()`, `_make_ledger_row()`)
- Route handlers: `snake_case()` (e.g., `test_health_endpoint()`, `test_acquire()`)

**Variables:**
- Constants: `UPPER_SNAKE_CASE` (e.g., `NEAR_TIMESTAMP_DIVISOR`, `AI_CONFIDENCE_THRESHOLD`, `REVIEW_THRESHOLD`)
- Class attributes: `snake_case` (e.g., `pool`, `price_service`, `wallet_graph`)
- Loop/iteration variables: `snake_case` (e.g., `row`, `conn`, `cur`, `rule`)
- Database results: descriptive names (e.g., `mock_user`, `mock_pool`, `mock_cursor`)

**Types/Classes:**
- Classes: `PascalCase` (e.g., `TransactionClassifier`, `ACBPool`, `ACBEngine`, `WalletGraph`, `SpamDetector`)
- Pydantic models: `PascalCase` (e.g., `WalletCreate`, `WalletResponse`, `SyncStatusResponse`, `RegisterStartRequest`)
- Enums/constants: `UPPER_SNAKE_CASE`
- Exception classes: `PascalCase` ending in `Error` or `Exception` (e.g., `ReportBlockedError`)

## Code Style

**Formatting:**
- Python style follows PEP 8 conventions
- No explicit formatter config detected; code appears manually formatted
- Indentation: 4 spaces
- Line length: appears to favor readability over strict limits; some lines exceed 100 chars

**Linting:**
- No `.eslintrc`, `.pylintrc`, or `tox.ini` detected
- No enforced linting configuration; style is maintained through convention

**Docstring Format:**
- Module-level docstrings: triple-quoted at top, describing module purpose and key classes/functions
- Function docstrings: triple-quoted, describe purpose, arguments, return value, and exceptions
- Class docstrings: triple-quoted, describe the class purpose and key attributes
- Example from `api/main.py`:
  ```python
  """Axiom FastAPI application factory.

  Creates and configures the FastAPI app with:
    - CORS middleware (origins from ALLOWED_ORIGINS env var)
    - Startup/shutdown lifespan events for DB pool management
  """
  ```

## Import Organization

**Order (as observed):**
1. Standard library imports (e.g., `json`, `sys`, `os`, `csv`, `tempfile`, `logging`)
2. Third-party imports (e.g., `psycopg2`, `fastapi`, `pydantic`, `pytest`)
3. Local application imports (e.g., `from api.main import`, `from engine.classifier import`)

**Path Aliases:**
- Absolute imports used throughout: `from api.dependencies import get_current_user`
- No `@` path alias prefixes observed; imports use relative project paths
- Some indexers use `sys.path.insert(0, ...)` for adding parent directory when needed

**Example from `tests/test_acb.py`:**
```python
import sys
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

## Error Handling

**Patterns:**
- Try/except blocks with specific exception catching (not bare except)
- Logging on exception: `logger.warning()`, `logger.error()` with context
- HTTPException for API responses (FastAPI conventions)
- Custom exceptions: `ReportBlockedError` raised in reports engine
- Database operations wrapped in try/finally for connection cleanup

**Example from `api/dependencies.py`:**
```python
conn = pool.getconn()
try:
    cur = conn.cursor()
    cur.execute(...)
    row = cur.fetchone()
    cur.close()
finally:
    pool.putconn(conn)
```

**Example from `engine/classifier.py`:**
```python
except Exception as exc:
    logger.warning("FMV lookup failed for %s at %s: %s", symbol, unix_ts, exc)

except json.JSONDecodeError:
    logger.warning("AI returned invalid JSON; falling back to unknown")
```

## Logging

**Framework:** Standard `logging` module

**Patterns:**
- Module-level logger: `logger = logging.getLogger(__name__)`
- Log levels used:
  - `logger.debug()` — low-level state/iteration details (e.g., "Skipping category=X")
  - `logger.info()` — key lifecycle events (e.g., "Replay started")
  - `logger.warning()` — recoverable errors and fallbacks
  - `logger.error()` — critical failures with context
- Always include context in log messages (use % formatting or f-strings)

**Example from `engine/acb.py`:**
```python
logger = logging.getLogger(__name__)

logger.info("Replay started for user_id=%s, token=%s, chain=%s", user_id, token, chain)
logger.warning("FMV lookup failed for %s at %s: %s", symbol, unix_ts, exc)
logger.error("ACB calculation failed: %s", exc, exc_info=True)
logger.debug("Skipping category=%s classification_id=%s", category, row.id)
```

## Comments

**When to Comment:**
- Section headers with dashes: `# ---------------------------------------------------------------------------`
- Complex business logic needing explanation (tax rules, algorithm steps)
- Non-obvious intent or workarounds
- Algorithm constraints (e.g., "NEAR nanoseconds; divide by 1e9")

**JSDoc/TSDoc:**
- Not used in Python codebase; use docstrings instead
- Function docstrings follow pattern: "Brief description.\n\nLonger explanation.\n\nArgs:\n...\nReturns:\n...\nRaises:\n..."

**Example from `engine/acb.py`:**
```python
def resolve_token_symbol(
    token_id: Optional[str],
    chain: str,
    asset: Optional[str] = None,
) -> str:
    """Resolve a token identifier to a canonical uppercase symbol.

    Priority:
      1. If asset is not None (exchange transaction): return asset.upper()
      2. If token_id in TOKEN_SYMBOL_MAP: return mapped symbol
      3. If token_id is None and chain == 'near': return 'NEAR'
      4. Otherwise: return token_id or 'UNKNOWN'
    """
```

## Function Design

**Size:** Generally 20-50 lines; larger functions (100+ lines) appear only in core engines with clear sections

**Parameters:**
- Positional parameters for required arguments
- Type hints used throughout (e.g., `pool: pg_pool.SimpleConnectionPool`, `amount: Decimal`)
- Optional parameters use `Optional[T]` from `typing`
- Dependency injection in FastAPI routes: `param=Depends(get_db_conn)`

**Return Values:**
- Explicit return types (e.g., `-> FastAPI`, `-> dict`, `-> Decimal`)
- Functions return dict for flexible JSON responses in API routes
- Database operations return tuples or dicts (e.g., `(status, count)` or `{"blocked": False}`)

**Example from `api/routers/wallets.py`:**
```python
def _jobs_for_chain(chain: str) -> List[tuple]:
    """Return list of (job_type, priority) tuples to queue for the given chain."""
    if _is_near_chain(chain):
        return _NEAR_JOBS
    return _EVM_JOBS
```

## Module Design

**Exports:**
- All public functions/classes available at module level
- No `__all__` declarations observed; imports are explicit
- Internal helpers prefixed with `_` to indicate private

**Barrel Files:**
- `api/__init__.py` — minimal, no re-exports
- `api/routers/__init__.py` — imports and re-exports all router modules:
  ```python
  from api.routers.wallets import router as wallets_router
  from api.routers.transactions import router as transactions_router
  ```
- `api/schemas/__init__.py` — minimal

## Database Code

**Pattern:**
- psycopg2 connections managed via `indexers/db.py`
- Connection pool usage: `pool.getconn()` and `pool.putconn(conn)` in finally blocks
- Cursors created with `conn.cursor()`, closed with `cur.close()`
- SQL passed as strings with `%s` parameterization for safety
- No ORM; raw SQL used throughout

**Example:**
```python
conn = pool.getconn()
try:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name FROM rules WHERE active = %s",
        (True,)
    )
    rows = cur.fetchall()
finally:
    cur.close()
    pool.putconn(conn)
```

## Decimal Precision

**Pattern:**
- `from decimal import Decimal` for all financial calculations
- Amounts stored as `Decimal("123.45")` not float
- Quantization: `Decimal("5.33333333")` for 8 decimal place precision
- Comparisons: `amount_gt: 0` for numeric threshold checks

---

*Convention analysis: 2026-03-13*
