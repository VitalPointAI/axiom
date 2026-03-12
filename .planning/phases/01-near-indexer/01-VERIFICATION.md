---
phase: 01-near-indexer
verified: 2026-03-11T12:00:00Z
status: passed
score: 14/14 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 10/14
  gaps_closed:
    - "Indexer service dispatches to all three fetchers (transactions, staking, lockup)"
    - "Adding a wallet via web API creates queued background jobs (not immediate sync)"
    - "Full staking history is backfilled from first stake event, not just current tax year"
  gaps_remaining: []
  regressions: []
---

# Phase 1: NEAR Indexer Verification Report

**Phase Goal:** Pull complete transaction history for all 64 NEAR accounts including staking rewards and lockup vesting.
**Verified:** 2026-03-11
**Status:** passed
**Re-verification:** Yes — after gap closure (plans 01-05 and 01-06)

## Gap Closure Summary

Three gaps identified in initial verification (2026-03-11) were all closed by commits `7cb7d08`, `e500c27`, and `cbf06bd`.

| Gap | Fix Applied | Verified |
|-----|-------------|---------|
| Gap 1: `account_id` missing from job dict causing KeyError in staking/lockup fetchers | `service._claim_next_job()` now JOINs `wallets` table and includes `w.account_id` in both SELECT and columns dict (lines 169, 189) | CLOSED |
| Gap 2: GET /api/wallets JOINed non-existent `indexing_progress` table; POST inserted non-existent `sync_status` column | GET handler now derives `sync_status` via EXISTS subqueries on `indexing_jobs`; POST INSERT limited to `(account_id, chain, label, user_id)` — no `sync_status` column | CLOSED |
| Gap 3: `_get_first_stake_timestamp()` returned None for all fresh wallets because `staking_events` was never pre-populated | Function now falls back to `transactions` table querying `action_type = 'STAKE'` or `FUNCTION_CALL` to the validator address; backfill can proceed from transaction history alone | CLOSED |

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | PostgreSQL schema exists with proper types (SERIAL, NUMERIC, JSONB, TIMESTAMPTZ) | VERIFIED | db/migrations/versions/001_initial_schema.py: NUMERIC(40,0) for amounts, JSONB for raw_data, DateTime(timezone=True) throughout |
| 2 | All tables have user_id foreign key for multi-user isolation | VERIFIED | db/models.py: all 6 data tables have user_id FK |
| 3 | Alembic migration framework is configured and initial migration runs cleanly | VERIFIED | db/migrations/env.py imports Base.metadata; 001_initial_schema.py uses op.create_table() for all 8 tables |
| 4 | No SQLite references remain in config.py or indexer database module | VERIFIED | config.py has DATABASE_URL only; indexers/db.py imports only psycopg2 |
| 5 | Schema supports multi-chain extensibility | VERIFIED | chain column on wallets and transactions; price_cache uses coin_id |
| 6 | Indexer service polls job queue and processes NEAR sync jobs autonomously | VERIFIED | service.py: FOR UPDATE SKIP LOCKED polling, exponential backoff, graceful shutdown, --once flag |
| 7 | Transaction fetcher resumes from last cursor on interruption | VERIFIED | near_fetcher.py: cursor persisted to DB after each page commit; sync_wallet() resumes from job_row['cursor'] |
| 8 | Rate limiting adapts based on API key presence | VERIFIED | config.py: RATE_LIMIT_DELAY = 1.0 if NEARBLOCKS_API_KEY else 3.0 |
| 9 | Indexer auto-retries failed jobs with exponential backoff | VERIFIED | service._mark_failed_or_retry(): min(300, 5 * 2^attempts) seconds, 100 attempt max |
| 10 | Price service fetches from multiple sources and filters outliers | VERIFIED | price_service.py: CoinGecko primary + CryptoCompare fallback; OUTLIER_THRESHOLD=0.5 aggregation |
| 11 | Indexer service dispatches to all three fetchers (transactions, staking, lockup) | VERIFIED | service._claim_next_job() JOINs wallets to supply account_id; staking_sync and lockup_sync handlers receive complete job dict |
| 12 | Adding a wallet via web API creates queued background jobs (not immediate sync) | VERIFIED | GET derives sync_status from indexing_jobs via EXISTS subqueries; POST INSERT is schema-correct (no sync_status column); three indexing_jobs records created for NEAR wallets |
| 13 | Sync status API reads from indexing_jobs table | VERIFIED | web/app/api/sync/status/route.ts: JOINs indexing_jobs with wallets, groups by wallet_id, computes per-wallet aggregated status |
| 14 | Full staking history backfilled from first stake event | VERIFIED | _get_first_stake_timestamp() queries staking_events first, then falls back to transactions WHERE action_type='STAKE' OR FUNCTION_CALL to validator; backfill proceeds for any wallet with transaction history |

**Score:** 14/14 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db/migrations/versions/001_initial_schema.py` | Initial PostgreSQL schema migration | VERIFIED | Creates all 8 tables with proper types |
| `db/models.py` | SQLAlchemy models for Alembic | VERIFIED | All 8 models present |
| `indexers/db.py` | PostgreSQL connection helper | VERIFIED | get_connection(), get_pool(), close_pool(), db_cursor() all present |
| `config.py` | Centralized config with no SQLite | VERIFIED | DATABASE_URL present, no SQLite |
| `indexers/service.py` | Standalone indexer service with job queue | VERIFIED | 400+ lines; FOR UPDATE SKIP LOCKED; JOIN wallets for account_id in _claim_next_job() |
| `indexers/near_fetcher.py` | NEAR transaction fetcher | VERIFIED | 467 lines, parse_transaction() + NearFetcher.sync_wallet() fully implemented |
| `tests/test_near_fetcher.py` | Unit tests for transaction parsing | VERIFIED | 477 lines, substantive test coverage |
| `indexers/price_service.py` | Multi-source price aggregation | VERIFIED | 462 lines, CoinGecko + CryptoCompare + outlier filtering |
| `indexers/staking_fetcher.py` | Epoch-level staking reward calculator | VERIFIED | 600 lines; dispatch works; backfill has transactions-table fallback; logging via logger throughout |
| `indexers/lockup_fetcher.py` | Lockup contract event parser | VERIFIED | 514 lines; dispatch works; logging via logger throughout |
| `tests/test_price_service.py` | Price service tests | VERIFIED | 322 lines, 17 tests |
| `web/app/api/wallets/route.ts` | Wallet API with job queue creation | VERIFIED | GET derives status from indexing_jobs EXISTS subqueries; POST INSERT is schema-correct; three background jobs created |
| `web/app/api/sync/status/route.ts` | Sync status reading from job queue | VERIFIED | Full JOIN with wallets, per-wallet aggregation |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| db/migrations/env.py | db/models.py | SQLAlchemy metadata import | WIRED | from db.models import Base; target_metadata = Base.metadata |
| indexers/db.py | config.py | DATABASE_URL import | WIRED | from config import DATABASE_URL |
| indexers/service.py | indexers/db.py | Job queue polling | WIRED | get_pool(), close_pool() used throughout |
| indexers/service.py | indexers/near_fetcher.py | full_sync handler dispatch | WIRED | "full_sync": NearFetcher(self.pool) |
| indexers/service.py | indexers/staking_fetcher.py | staking_sync handler dispatch | WIRED | "staking_sync": StakingFetcher; job dict includes account_id via wallets JOIN |
| indexers/service.py | indexers/lockup_fetcher.py | lockup_sync handler dispatch | WIRED | "lockup_sync": LockupFetcher; job dict includes account_id via wallets JOIN |
| indexers/near_fetcher.py | indexers/nearblocks_client.py | API calls | WIRED | NearBlocksClient() used for all fetches |
| indexers/staking_fetcher.py | indexers/price_service.py | FMV lookup | WIRED | PriceService.get_price() called in backfill loop |
| indexers/lockup_fetcher.py | indexers/price_service.py | FMV lookup | WIRED | PriceService.get_price() called in _insert_lockup_event() |
| indexers/staking_fetcher.py | transactions table | Backfill timestamp fallback | WIRED | _get_first_stake_timestamp() queries transactions WHERE action_type='STAKE' OR FUNCTION_CALL to validator |
| web/app/api/wallets/route.ts | indexing_jobs table | GET: sync_status derivation | WIRED | EXISTS subqueries on indexing_jobs for running/queued/failed/completed states |
| web/app/api/wallets/route.ts | indexing_jobs table | POST: three job inserts | WIRED | INSERT INTO indexing_jobs for full_sync, staking_sync, lockup_sync |
| web/app/api/sync/status/route.ts | indexing_jobs table | GET: per-wallet status | WIRED | Full JOIN with wallets, breakdown by job_type |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| DATA-01 | 01-02, 01-04 | Complete transaction history for any NEAR account via RPC/indexer | SATISFIED | NearFetcher.sync_wallet() with cursor resume; service dispatches full_sync with complete job dict |
| DATA-02 | 01-03, 01-04 | Staking rewards history from validator pool contracts | SATISFIED | StakingFetcher dispatch works (account_id fix); backfill fallback to transactions table ensures timestamp is found for any funded wallet |
| DATA-03 | 01-03, 01-04 | Lockup contract vesting events | SATISFIED | LockupFetcher dispatch works (account_id fix); _find_lockup_accounts() discovers lockup contract addresses |
| DATA-06 | 01-01 | Store all transactions in PostgreSQL with consistent schema | SATISFIED | 8-table schema with NUMERIC, JSONB, TIMESTAMPTZ, user_id FKs, Alembic migration |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `web/app/api/wallets/[id]/route.ts` | 34 | DELETE FROM indexing_progress — table does not exist in new Alembic schema | Warning (pre-existing, out-of-scope) | DELETE wallet endpoint will fail at runtime; not touched by Phase 1 gap closure |
| `web/app/api/wallets/[id]/sync/route.ts` | 85 | LEFT JOIN indexing_progress — table does not exist | Warning (pre-existing, out-of-scope) | Individual wallet sync status route broken; not touched by Phase 1 gap closure |
| `web/app/api/indexers/status/route.ts` | 27, 44 | LEFT JOIN indexing_progress, evm_indexing_progress — tables do not exist | Warning (pre-existing, out-of-scope) | Indexer admin status route broken; not touched by Phase 1 gap closure |

Note: These anti-patterns are in routes not modified during Phase 1 (git log confirms no Phase 1 commits touched them). They are pre-existing technical debt. The routes specifically claimed by Phase 1 plans (`web/app/api/wallets/route.ts`, `web/app/api/sync/status/route.ts`) are both schema-correct and verified.

### Human Verification Required

None — all automated checks were conclusive.

### Regressions

None. All 10 previously passing truths still pass. No new anti-patterns were introduced in the files modified by gap closure commits (`indexers/service.py`, `indexers/staking_fetcher.py`, `indexers/lockup_fetcher.py`, `web/app/api/wallets/route.ts`).

---

_Verified: 2026-03-11_
_Verifier: Claude (gsd-verifier)_
