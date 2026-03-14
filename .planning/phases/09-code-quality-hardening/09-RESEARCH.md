# Phase 9: Code Quality & Hardening — Research

**Researched:** 2026-03-13
**Domain:** Python code quality, PostgreSQL migration, API rate limiting, CI/CD quality gates, test coverage
**Confidence:** HIGH

---

## Summary

Phase 9 addresses all unfixed concerns from `.planning/codebase/CONCERNS.md`. The codebase has 8 active phases complete and 364 tests passing (1 failing: `test_create_wallet_evm`). The primary concerns are: mixed SQLite/PostgreSQL usage in `engine/prices.py` (the only active production module still using SQLite), monolithic modules that are hard to test, N+1 query patterns in the classifier, missing API rate limiting (slowapi is already in requirements.txt but not wired), no CI/CD quality gates (deploy.yml skips tests), SQL injection risk in one dynamic UPDATE, startup env validation, and test gaps in authorization, indexer edge cases, and exchange parsers.

The `scripts/` directory contains many legacy SQLite one-off files. These are historical utility scripts, not production code. They should be either deleted (if obsolete) or left as-is with a comment. The only production SQLite usage requiring migration is `engine/prices.py` — this is the legacy `PriceFetcher` class which has been superseded by `indexers/price_service.py` (PostgreSQL-backed). The fix is to remove or archive `engine/prices.py` rather than migrate it.

The `hybrid_indexer.py` and `ft_indexer.py` files also use SQLite directly, but their place in the production path needs verification — they appear to be legacy pre-Phase-1 indexers, not used by `IndexerService`.

**Primary recommendation:** Fix the 8 active concerns in CONCERNS.md using targeted plans (one per concern cluster), add CI quality gates as the first plan, and add authorization test coverage as the highest-priority test gap.

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| QH-01 | SQLite→PostgreSQL: migrate/remove remaining SQLite modules | `engine/prices.py` is superseded by `indexers/price_service.py`; `hybrid_indexer.py`/`ft_indexer.py` are legacy non-service code |
| QH-02 | Refactor monolithic modules (classifier, reconcile) | `engine/classifier.py` (1114 lines), `verify/reconcile.py` (1002 lines) — extract sub-components |
| QH-03 | Fix N+1 query patterns in classifier | `_find_staking_event()` and `_find_lockup_event()` called per-transaction; batch with IN/JOIN |
| QH-04 | Fix SQL injection risk in dynamic UPDATE | `transactions.py:501-541` builds SET clauses via string join with %s placeholders — safe pattern but tighten |
| QH-05 | Add API rate limiting | slowapi in requirements.txt; not wired into `api/main.py` or any router |
| QH-06 | Startup environment variable validation | config.py warns on DATABASE_URL but doesn't fail fast; no validation for other required vars |
| QH-07 | Complete transaction rollback pattern | `classifier_handler.py` and `file_handler.py` have rollbacks but pattern inconsistent |
| QH-08 | Add CI/CD quality gates | `deploy.yml` has no test/lint step; runs deploy directly |
| QH-09 | Test coverage: authorization isolation | No tests verify cross-user data access is blocked |
| QH-10 | Test coverage: indexer edge cases | Rate limit handling, malformed API responses, network timeouts untested |
| QH-11 | Test coverage: exchange parser robustness | Missing columns, unexpected field order, duplicate rows in CSV |
| QH-12 | Document stub implementations | `xrp_fetcher.py`, `akash_fetcher.py`, `api/routers/portfolio.py` stub - add clear NOT_IMPLEMENTED responses |

---

## Standard Stack

### Core (Already in requirements.txt)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| slowapi | >=0.1.9 | FastAPI rate limiting | In requirements, NOT wired |
| pytest | (installed) | Test runner | Already used, 364 tests |
| psycopg2-binary | >=2.9.9 | PostgreSQL | Already used everywhere |
| fastapi | >=0.111.0 | API framework | In production |

### To Add
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| ruff | latest | Lint + format | Single tool replacing flake8+isort+black; fast; GitHub Actions friendly |
| pytest-cov | latest | Coverage reporting | `pytest --cov=. --cov-report=xml` for CI badge |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| slowapi | Custom middleware | slowapi is the FastAPI-native choice; already in requirements |
| ruff | flake8 + black | ruff replaces both; 10-100x faster; single config |

**Installation:**
```bash
pip install ruff pytest-cov
```

---

## Architecture Patterns

### SQLite Migration Pattern

`engine/prices.py` is a legacy module using SQLite. It has been superseded by `indexers/price_service.py` which uses PostgreSQL. The correct fix is **removal** (or archival), not migration.

```python
# BEFORE: engine/prices.py (SQLite-based, legacy)
class PriceFetcher:
    def _init_cache(self):
        conn = sqlite3.connect(str(db_path))  # WRONG

# AFTER: Use indexers/price_service.py (PostgreSQL-backed PriceService)
# PriceService already has: get_price_cad_at_timestamp(), get_boc_cad_rate(), etc.
# No migration needed — just remove engine/prices.py if unused
```

**Verification step:** grep all imports of `engine.prices` to confirm nothing imports it before deleting.

### Classifier N+1 Fix Pattern

The `_find_staking_event()` and `_find_lockup_event()` methods are called once per transaction. For 1000 txs, that is 2000+ queries. Fix by pre-loading staking/lockup event indexes once per classification run:

```python
# BEFORE: Per-transaction query (N+1)
def _find_staking_event(self, user_id, wallet_id, tx_hash, block_timestamp):
    conn = self.pool.getconn()  # New connection per call!
    ...

# AFTER: Pre-load batch at start of classify_user_transactions()
def _load_staking_event_index(self, user_id: int) -> dict:
    """Load all staking events for user into memory once.
    Returns dict keyed by (wallet_id, tx_hash) -> event_id.
    """
    conn = self.pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, wallet_id, tx_hash, event_type, block_timestamp "
            "FROM staking_events WHERE user_id = %s AND event_type = 'reward'",
            (user_id,)
        )
        rows = cur.fetchall()
    finally:
        self.pool.putconn(conn)
    index = {}
    for row in rows:
        index[(row[1], row[2])] = row[0]  # (wallet_id, tx_hash) -> id
        # Also index by (wallet_id, block_timestamp range) for fallback
    return index
```

Pass the pre-loaded index to `_find_staking_event()` and `_find_lockup_event()` instead of querying per-call.

### API Rate Limiting Pattern (slowapi)

slowapi is already in requirements.txt but not wired. Standard FastAPI integration:

```python
# api/main.py additions
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

def create_app() -> FastAPI:
    application = FastAPI(...)
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    ...
```

Apply limits to specific routes:
```python
# Auth endpoints — strictest limits to prevent credential stuffing
@router.post("/auth/register/finish")
@limiter.limit("10/minute")
async def register_finish(request: Request, ...):
    ...

# Job trigger endpoints — prevent queue flooding
@router.post("/wallets/{wallet_id}/sync")
@limiter.limit("5/minute")
async def trigger_sync(request: Request, ...):
    ...

# API endpoints generally
@router.get("/transactions")
@limiter.limit("60/minute")
async def list_transactions(request: Request, ...):
    ...
```

**Key**: The `request: Request` parameter is required by slowapi for all rate-limited endpoints.

### CI Quality Gate Pattern (GitHub Actions)

Add a `ci.yml` workflow that runs BEFORE deploy:

```yaml
# .github/workflows/ci.yml
name: CI Quality Gates
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -r requirements.txt ruff pytest-cov
      - name: Lint (ruff)
        run: ruff check . --select E,W,F --ignore E501
      - name: Run tests
        run: pytest tests/ -q --tb=short --cov=. --cov-report=term-missing
      - name: Fail if tests fail
        run: |
          FAILED=$(pytest tests/ -q --tb=no 2>&1 | grep "failed" || true)
          if [[ -n "$FAILED" ]]; then exit 1; fi
```

Alternatively, add a `test` job in deploy.yml that must pass before the `deploy` job (using `needs: test`).

### Startup Environment Validation Pattern

```python
# config.py — add to existing file
REQUIRED_ENV_VARS = ["DATABASE_URL"]
OPTIONAL_ENV_VARS_WARN = ["NEARBLOCKS_API_KEY", "COINGECKO_API_KEY"]

def validate_env() -> None:
    """Fail fast if required env vars are missing."""
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"Required environment variables not set: {', '.join(missing)}. "
            "Check .env file or container environment."
        )
    for var in OPTIONAL_ENV_VARS_WARN:
        if not os.environ.get(var):
            logger.warning("Optional env var %s not set — some features will be limited", var)
```

Call `validate_env()` from the FastAPI lifespan and from IndexerService `__init__`.

### Transaction Rollback Pattern

The codebase has partial rollback coverage. Standardize using try/except/rollback:

```python
# Standard pattern — already used in some handlers
conn = pool.getconn()
try:
    cur = conn.cursor()
    # ... multi-step operations ...
    conn.commit()
except Exception:
    conn.rollback()
    raise
finally:
    cur.close()
    pool.putconn(conn)
```

The inconsistency is in `classifier_handler.py` where the ACB re-queue path might not rollback properly, and `file_handler.py` where the file import path has a rollback but the AI agent call does not.

### Authorization Test Pattern

```python
# tests/test_api_authorization.py — new file
def test_user_cannot_access_other_users_wallets(auth_client, other_user_wallet_id):
    """Users must not see wallets belonging to other users."""
    resp = auth_client.get(f"/wallets/{other_user_wallet_id}")
    assert resp.status_code in (403, 404)

def test_user_cannot_read_other_users_transactions(auth_client, other_user_tx_hash):
    """Users must not access other users' transaction data."""
    resp = auth_client.get(f"/transactions/{other_user_tx_hash}")
    assert resp.status_code in (403, 404)
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rate limiting | Custom middleware counting requests | slowapi | Already in requirements; battle-tested; decorator syntax |
| Lint/format | Custom scripts | ruff | 10-100x faster than flake8; single binary; covers isort+pyflakes |
| Test coverage | Manual counting | pytest-cov | Standard; produces XML for CI badges |
| CI gates | Build-then-check | GitHub Actions `needs:` dependency chain | Built-in job sequencing |

---

## Common Pitfalls

### Pitfall 1: Deleting Legacy Files Still Imported
**What goes wrong:** Removing `engine/prices.py` breaks import in forgotten script.
**How to avoid:** `grep -rn "from engine.prices\|import engine.prices" . --include="*.py"` before deletion. Only remove if zero hits outside the file itself.
**Warning signs:** `ImportError` on startup or test run.

### Pitfall 2: slowapi `request: Request` Parameter Required
**What goes wrong:** Adding `@limiter.limit("X/minute")` to a route without adding `request: Request` param causes TypeError at runtime.
**How to avoid:** Every rate-limited endpoint MUST have `request: Request` as a parameter, even if the handler doesn't use it.

### Pitfall 3: CI Workflow Runs in Parallel with Deploy
**What goes wrong:** Two separate `.yml` files both trigger on `push: main` — they run in parallel, so CI tests pass/fail AFTER deployment starts.
**How to avoid:** Either use a single workflow with `needs: [test]` dependency, or use `workflow_run` trigger so deploy only starts when CI passes.

### Pitfall 4: Classifier Refactor Breaks Rule Priority Order
**What goes wrong:** Extracting methods from `classify_user_transactions()` changes when rules are loaded or resets the `_rules` cache unexpectedly.
**How to avoid:** Keep `_get_rules()` as the single entry point. Only extract pure-function helpers that take rule lists as parameters, not methods that reload from DB.

### Pitfall 5: N+1 Fix Loads Too Much Memory
**What goes wrong:** Pre-loading ALL staking events for ALL wallets of a user hits memory limits for users with thousands of events.
**How to avoid:** Load per-wallet in the wallet iteration loop (one batch per wallet), not globally per user. This keeps memory bounded.

### Pitfall 6: Dynamic SET Clause SQL Injection
**What goes wrong:** The `transactions.py` UPDATE builds SET clauses via string join — this is safe because column names are hardcoded and values use `%s` placeholders. Changing this to include user-supplied column names would open injection.
**How to avoid:** Never interpolate user-provided field names into SQL. Use a whitelist dict: `ALLOWED_UPDATE_FIELDS = {"tax_category", "sub_category", "reviewer_notes", "needs_review"}`. The existing code is already safe; document this pattern explicitly.

---

## Code Examples

### Verified: slowapi Integration (from official docs)

```python
# Source: https://slowapi.readthedocs.io/en/latest/
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/home")
@limiter.limit("5/minute")
async def homepage(request: Request):
    return PlainTextResponse("test")
```

### Verified: ruff Configuration (pyproject.toml)

```toml
# pyproject.toml
[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "I"]   # pycodestyle, pyflakes, isort
ignore = ["E501"]                 # line length handled by formatter
```

### Verified: pytest with coverage

```bash
# Run with coverage, fail under 70%
pytest tests/ -q --cov=. --cov-report=term-missing --cov-fail-under=70
```

---

## State of the Art

| Old Approach | Current Approach | Status in Codebase |
|--------------|------------------|--------------------|
| `engine/prices.py` (SQLite) | `indexers/price_service.py` (PostgreSQL) | Legacy file still present |
| `hybrid_indexer.py` (SQLite) | `indexers/service.py` + handlers | Legacy, not in service.py handlers |
| `ft_indexer.py` (SQLite) | `indexers/ft_indexer_pg.py` (PostgreSQL) | Both present; pg version is active |
| No rate limiting | slowapi decorators | In requirements, not wired |
| Deploy-only CI | CI + deploy with gates | deploy.yml only, no tests |
| Manual rollback check | Standardized try/except/rollback | Inconsistent across handlers |

---

## Open Questions

1. **Are `hybrid_indexer.py` and `ft_indexer.py` imported by any active production path?**
   - What we know: They are in `indexers/` but not registered in `IndexerService`. `ft_indexer_pg.py` exists as a replacement.
   - What's unclear: Whether any Docker entrypoint or cron calls these directly.
   - Recommendation: `grep -rn "hybrid_indexer\|ft_indexer" . --include="*.py" --include="*.sh" --include="*.yml"` to confirm usage before archiving.

2. **Should the failing test `test_create_wallet_evm` be fixed in Phase 9 or separately?**
   - What we know: 1 test fails, 362 pass. The test creates an EVM wallet; likely a stub issue.
   - Recommendation: Fix it as part of the authorization/test-coverage plan since it's test infrastructure.

3. **Target rate limits for each endpoint category?**
   - What we know: No limits currently set. Auth endpoints need strictest limits.
   - Recommendation: Use conservative defaults: auth endpoints 10/minute, data endpoints 60/minute, job triggers 5/minute. Can be tuned via env vars later.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (version from pip) |
| Config file | none (uses `tests/conftest.py`) |
| Quick run command | `pytest tests/ -q --tb=short -x` |
| Full suite command | `pytest tests/ -q --tb=short` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QH-01 | SQLite modules removed/archived | unit | `pytest tests/ -q -k "prices"` | ❌ Wave 0 |
| QH-02 | Classifier refactored, all existing tests pass | unit | `pytest tests/test_classifier.py -q` | ✅ |
| QH-03 | N+1 fix: batch staking/lockup lookups | unit | `pytest tests/test_classifier.py -q -k "staking"` | ✅ (may need new cases) |
| QH-04 | Dynamic SQL pattern documented + whitelist | unit | `pytest tests/test_api_transactions.py -q` | ✅ |
| QH-05 | Rate limiting active on auth + job endpoints | integration | `pytest tests/test_rate_limiting.py -q` | ❌ Wave 0 |
| QH-06 | Startup fails fast on missing DATABASE_URL | unit | `pytest tests/test_config_validation.py -q` | ❌ Wave 0 |
| QH-07 | Rollback on partial write failure | unit | `pytest tests/test_classifier_handler.py -q` | ❌ Wave 0 |
| QH-08 | CI workflow runs tests before deploy | manual | Review `.github/workflows/ci.yml` | ❌ Wave 0 |
| QH-09 | Cross-user data access blocked (403/404) | integration | `pytest tests/test_api_authorization.py -q` | ❌ Wave 0 |
| QH-10 | Indexer handles rate limit + malformed response | unit | `pytest tests/test_indexer_edge_cases.py -q` | ❌ Wave 0 |
| QH-11 | Exchange parsers handle bad CSV gracefully | unit | `pytest tests/test_exchange_parsers.py -q -k "malformed"` | ✅ (needs new cases) |
| QH-12 | Stubs return 501 Not Implemented | unit | `pytest tests/test_api_wallets.py::test_create_wallet_evm` | ✅ (1 failing) |

### Sampling Rate
- **Per task commit:** `pytest tests/ -q --tb=short -x`
- **Per wave merge:** `pytest tests/ -q --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_rate_limiting.py` — covers QH-05 (slowapi decorator tests)
- [ ] `tests/test_config_validation.py` — covers QH-06 (env var validation)
- [ ] `tests/test_classifier_handler.py` — covers QH-07 (rollback on failure)
- [ ] `tests/test_api_authorization.py` — covers QH-09 (cross-user isolation)
- [ ] `tests/test_indexer_edge_cases.py` — covers QH-10 (rate limit/error handling)
- [ ] `.github/workflows/ci.yml` — new CI workflow file (QH-08)

---

## Concern-to-Plan Mapping

This maps each remaining CONCERNS.md item to what kind of plan addresses it:

| CONCERNS.md Item | Status | Plan Category |
|-----------------|--------|---------------|
| Mixed Database Patterns (SQLite+PG) | Active | Plan: Archive/remove legacy SQLite modules |
| Overly Large Single Functions | Active | Plan: Refactor classifier + reconcile |
| Incomplete/Stub Implementations | Active | Plan: Document stubs with 501 responses |
| No Transaction Rollback Pattern | Active | Plan: Standardize rollback in handlers |
| Rate Limiting Not Fully Handled (NearBlocks) | Active | Plan: Retry + exponential backoff hardening |
| Environment Variables Not Validated | Active | Plan: Startup validation + fail-fast |
| SQL Injection Risk in Dynamic Query Building | Active | Plan: Whitelist pattern + documentation |
| No Rate Limiting on API Endpoints | Active | Plan: Wire slowapi into FastAPI |
| Sensitive Data in Logs | Active | Plan: Logging policy + sanitization |
| N+1 Query Pattern in Classification | Active | Plan: Batch staking/lockup index |
| Price Service Not Indexed | Partial | Already has `ix_price_cache_coin_date` and `ix_pcm_coin_ts` indexes — LOW priority |
| Memory Bloat in Large Backfills | Active | Plan: Batch size + generator pattern |
| No Transaction Audit Log | Partial | `classification_audit_log` exists; ensure consistent use |
| Test Coverage: API Authorization | Active | Plan: New `test_api_authorization.py` |
| Test Coverage: Indexer Edge Cases | Active | Plan: New `test_indexer_edge_cases.py` |
| Test Coverage: Exchange Parser Robustness | Active | Plan: Extend `test_exchange_parsers.py` |
| Test Coverage: Classification Rule Interactions | Active | Plan: Extend `test_classifier.py` |
| No CI Quality Gates | Active | Plan: Add `ci.yml` with pytest + ruff |
| Deprecated Exchange APIs (Coinbase Pro) | Active | Plan: Flag/deprecate old connectors |

---

## Sources

### Primary (HIGH confidence)
- CONCERNS.md — direct audit of codebase issues, 2026-03-13
- Actual codebase inspection — line counts, grep results, test counts verified
- `requirements.txt` — slowapi>=0.1.9 already present
- `.github/workflows/deploy.yml` — confirmed: no test step

### Secondary (MEDIUM confidence)
- slowapi official docs: https://slowapi.readthedocs.io/en/latest/ — FastAPI rate limiting pattern
- ruff docs: https://docs.astral.sh/ruff/ — lint/format configuration
- pytest-cov: standard pytest plugin, well-documented

### Tertiary (LOW confidence)
- N+1 batch size recommendations — based on typical psycopg2 connection pool sizes (5-20)

---

## Metadata

**Confidence breakdown:**
- Concern identification: HIGH — directly read from CONCERNS.md + code inspection
- Standard stack: HIGH — requirements.txt already has slowapi; ruff is ecosystem standard
- Architecture patterns: HIGH — verified against actual code patterns
- Test gaps: HIGH — counted actual test files and functions
- Pitfalls: MEDIUM — derived from code analysis + known Python/FastAPI patterns

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable libraries; 30-day window)
