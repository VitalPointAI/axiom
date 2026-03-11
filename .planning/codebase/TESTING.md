# Testing Patterns

**Analysis Date:** 2026-03-11

## Test Framework

**Runner:** None configured

No test framework is set up for either the Python backend or the TypeScript frontend:
- No `jest.config.*`, `vitest.config.*`, `pytest.ini`, `pyproject.toml` (with test config), or `setup.cfg`
- No test dependencies in `web/package.json` (no jest, vitest, @testing-library, etc.)
- No test scripts in `web/package.json` (only `dev`, `build`, `start`, `lint`)
- No `requirements.txt` at project root for Python dependencies
- `indexers/requirements.txt` exists but contains only runtime dependencies

**Run Commands:**
```bash
cd web && npm run lint   # Only linting is available, no test runner
```

## Test Files

**Total test files found:** 2

Both are ad-hoc debug/investigation scripts, not automated tests:

- `test_trace.py` - Manual script to test Alchemy `trace_filter` API for Ethereum traces. Runs requests and prints results. No assertions.
- `test_trace_tx.py` - Manual script to test Alchemy `trace_transaction` API. Queries a hardcoded database path and prints results. No assertions.

These files are **not automated tests**. They are one-off debugging scripts that:
- Make live API calls (require `ALCHEMY_API_KEY` env var)
- Query a hardcoded production database path (`/home/deploy/neartax/neartax.db`)
- Print output to stdout for manual inspection
- Have no assertions, no test structure, no pass/fail reporting

## Test File Organization

**Location:** No established pattern. The two `test_*.py` files sit in the project root.

**No test directories exist:**
- No `tests/`, `__tests__/`, `test/`, `spec/` directories
- No co-located test files alongside source code
- No test files in `web/`, `engine/`, `indexers/`, `tax/`, or `db/`

## Test Structure

No structured tests exist. There are no `describe`/`it` blocks, no `unittest.TestCase` subclasses, no `pytest` functions, and no assertion library usage.

## Mocking

**Framework:** None

No mocking is done anywhere in the codebase. The debug scripts in the root make live API calls.

## Fixtures and Factories

**Test Data:** None

The only test data patterns are:
- Inline example usage in `if __name__ == "__main__":` blocks (e.g., `engine/acb.py` has example transactions)
- Hardcoded addresses and transaction hashes in debug scripts

## Coverage

**Requirements:** None enforced
**Coverage tooling:** Not configured

## Test Types

**Unit Tests:** None exist

**Integration Tests:** None exist

**E2E Tests:** Not configured (no Playwright, Cypress, or similar)

## Recommended Testing Setup

When adding tests, follow these patterns based on the existing codebase structure:

### Python (engine, tax, indexers)

Use `pytest` as it requires minimal boilerplate and matches the functional style of the codebase.

**Suggested structure:**
```
tests/
  engine/
    test_acb.py          # ACBTracker, PortfolioACB calculations
    test_classifier.py   # Transaction classification logic
    test_prices.py       # Price fetching and caching
  tax/
    test_categories.py   # TaxCategory classification
    test_cost_basis.py   # Cost basis calculations
    test_reports.py      # Report generation
  indexers/
    test_nearblocks_client.py  # API client (mock HTTP)
```

**Priority test targets (pure logic, no DB/API needed):**
- `engine/acb.py` - `ACBTracker.acquire()`, `ACBTracker.dispose()`, `PortfolioACB` - pure math
- `engine/classifier.py` - `classify_near_transaction()`, `classify_exchange_transaction()` - pure classification logic
- `tax/categories.py` - `TaxCategory` enum and `categorize_transaction()` - pure mapping logic
- `tax/cost_basis.py` - Cost basis calculations

**Example test pattern matching codebase style:**
```python
# tests/engine/test_acb.py
import pytest
from engine.acb import ACBTracker, PortfolioACB, check_superficial_loss
from datetime import datetime

def test_acquire_updates_cost_basis():
    tracker = ACBTracker("NEAR")
    tracker.acquire(1000, 5000, fee_cad=10, date=datetime(2023, 1, 15))
    assert tracker.total_units == 1000
    assert tracker.total_cost == 5010  # cost + fee
    assert tracker.acb_per_unit == pytest.approx(5.01)

def test_dispose_calculates_gain():
    tracker = ACBTracker("NEAR")
    tracker.acquire(1000, 5000)
    result = tracker.dispose(500, 4000)
    assert result['gain_loss'] == pytest.approx(1500)  # 4000 - (500 * 5.0)
    assert result['is_gain'] is True

def test_superficial_loss_within_30_days():
    # Test the 30-day rebuy rule
    dispositions = [{'gain_loss': -500, 'date': datetime(2023, 6, 15)}]
    acquisition_dates = [datetime(2023, 6, 20)]  # rebuy within 30 days
    result = check_superficial_loss(dispositions, acquisition_dates)
    assert result[0]['superficial_loss'] is True
```

### TypeScript (web app)

Use `vitest` as it integrates well with Next.js and requires minimal config.

**Suggested structure:**
```
web/
  __tests__/
    lib/
      auth.test.ts
      db.test.ts
      utils.test.ts
    api/
      wallets.test.ts
      transactions.test.ts
```

**Priority test targets:**
- `web/lib/utils.ts` - `formatCurrency()`, `formatNumber()`, `cn()` - pure functions
- `web/lib/db.ts` - `convertPlaceholders()` (internal function) - pure SQL transform
- `web/lib/auth.ts` - `canWrite()` - pure logic check
- API route handlers (mock `db` and `getAuthenticatedUser`)

**Example test pattern matching codebase style:**
```typescript
// web/__tests__/lib/utils.test.ts
import { describe, it, expect } from 'vitest';
import { formatCurrency, formatNumber, cn } from '@/lib/utils';

describe('formatCurrency', () => {
  it('formats USD with 2 decimal places', () => {
    expect(formatCurrency(1234.5)).toBe('$1,234.50');
  });

  it('handles string-like numbers', () => {
    expect(formatCurrency(0)).toBe('$0.00');
  });
});

describe('cn', () => {
  it('merges tailwind classes', () => {
    expect(cn('p-4', 'p-2')).toBe('p-2');
  });
});
```

## What NOT to Mock

Based on codebase patterns, these should use integration tests with a test database rather than mocking:
- Database queries in API routes (complex SQL with joins, filters, pagination)
- Multi-step wallet creation flows (insert + trigger indexer)
- Authentication session management (cookie + DB interaction)

## Critical Untested Areas

| Area | Files | Risk |
|------|-------|------|
| ACB calculations | `engine/acb.py` | Incorrect tax calculations |
| Transaction classification | `engine/classifier.py`, `tax/categories.py` | Wrong tax categories |
| Cost basis tracking | `tax/cost_basis.py` | Incorrect capital gains |
| Superficial loss detection | `engine/acb.py` | Missing Canadian tax rule |
| API auth guards | `web/lib/auth.ts`, all `route.ts` files | Authorization bypass |
| DB placeholder conversion | `web/lib/db.ts` `convertPlaceholders()` | SQL injection or query errors |
| Currency formatting | `web/lib/utils.ts` | Display errors |

---

*Testing analysis: 2026-03-11*
