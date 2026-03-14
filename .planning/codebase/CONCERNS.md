# Codebase Concerns

**Analysis Date:** 2026-03-13

## Tech Debt

**~~Bare Exception Handling Throughout Codebase~~ (FIXED 2026-03-13):**
- Fixed: Replaced all bare `except:` with specific exception types + `logger.warning()` across 11 files
- Commit: `2eadcc6`

**~~Mixed Database Patterns (SQLite + PostgreSQL)~~ (FIXED 2026-03-14):**
- Fixed: Archived legacy SQLite modules (`engine/prices.py`, `hybrid_indexer.py`, `ft_indexer.py`) to `_archive/`; all production code now uses PostgreSQL only
- Commit: `e4aea73` (09-01)

**~~Database Connection Resource Leaks~~ (FIXED 2026-03-13):**
- Fixed: Added `with sqlite3.connect()` context managers to all 4 scripts
- Commit: `2eadcc6`

**~~Overly Large Single Functions~~ (FIXED 2026-03-14):**
- Fixed: `verify/reconcile.py` reduced from 1002→721 lines (commit `261d983`, 09-05). `engine/classifier.py` split into 7 sub-modules (commit `5356923`, 10-01). `engine/acb.py` split into 3 sub-modules (commit `5ccb78f`, 10-01). `db/models.py` converted to package (commit `5ccb78f`, 10-01).

**~~Incomplete/Stub Implementations~~ (FIXED 2026-03-14):**
- Fixed: XRP/Akash fetchers log STUB warnings on init; portfolio endpoint has OpenAPI stub description; `docs/STUB_IMPLEMENTATIONS.md` created documenting all stubs with migration paths
- Commit: `af91c12` (10-04)

**~~Hardcoded API URLs and Configuration~~ (FIXED 2026-03-13):**
- Fixed: Extracted all URLs to `os.environ.get()` with existing defaults (NEAR_RPC_URL, NEARBLOCKS_API_URL, NEARDATA_API_URL, FASTNEAR_API_URL)
- Commit: `2eadcc6`

**~~No Transaction Rollback Pattern~~ (FIXED 2026-03-14):**
- Fixed: Standardized rollback pattern in `classifier_handler.py` and `file_handler.py` with explicit `conn.rollback()` on exceptions
- Commit: `fff17c9` (09-02)

---

## Known Bugs

**~~Rate Limiting Not Fully Handled~~ (FIXED 2026-03-14):**
- Fixed: NearBlocks API calls now use exponential backoff + jitter (2^attempt + random [0,1)) with max 5 retries; raises `RuntimeError` on exhaustion instead of silent failure
- Commits: `cf0872b` (09-03), `75458cf` (09-03)

**~~Path Traversal Validation Incomplete~~ (FIXED 2026-03-13):**
- Fixed: Added `os.path.realpath()` symlink resolution check before serving files
- Commit: `2eadcc6`

**~~Empty Placeholder Conversions~~ (FIXED 2026-03-13):**
- Fixed: Removed `str()` wrapping on nullable fields; API now returns `null` instead of `"None"`
- Commit: `2eadcc6`

---

## Security Considerations

**~~Environment Variables Not Validated~~ (FIXED 2026-03-14):**
- Fixed: Added `validate_env()` in `config.py` called during FastAPI lifespan startup; fails fast on missing `DATABASE_URL`
- Commit: `dc6c3b6` (09-02)

**~~SQL Injection Risk in Dynamic Query Building~~ (FIXED 2026-03-14):**
- Fixed: Added SQL column whitelist in `transactions.py` to prevent injection via dynamic ORDER BY; all dynamic clauses validated against allowed set
- Commit: `dc6c3b6` (09-02)

**~~No Input Validation on User-Provided Data~~ (FIXED 2026-03-13):**
- Fixed: Added Pydantic `@field_validator` for tax categories (enum) and wallet addresses (NEAR/EVM format)
- Commit: `2eadcc6`

**~~No Rate Limiting on API Endpoints~~ (FIXED 2026-03-14):**
- Fixed: Wired slowapi rate limiting on auth, wallet creation/resync, report generation, and transaction endpoints
- Commit: `dc6c3b6` (09-02)

**~~Sensitive Data in Logs~~ (FIXED 2026-03-14):**
- Fixed: `sanitize_for_log()` added to `config.py` with `_SENSITIVE_KEY_PATTERNS` for case-insensitive redaction; `docs/LOGGING_POLICY.md` created
- Commit: `cac4a17` (10-04)

---

## Performance Bottlenecks

**~~N+1 Query Pattern in Classification~~ (FIXED 2026-03-14):**
- Fixed: Batch loading of staking_events and lockup_events per wallet; O(1) hash lookup via index dicts instead of per-transaction DB queries
- Commit: `75458cf` (09-03)

**~~Price Service Not Indexed~~ (FIXED 2026-03-14):**
- Fixed: Migration 007 adds `ix_price_cache_coin_date_desc ON price_cache (coin_id, date DESC)` composite index for efficient range queries
- Commit: `718f869` (10-02)

**~~Memory Bloat in Large Backfills~~ (FIXED 2026-03-14):**
- Fixed: `BACKFILL_BATCH_SIZE = 100` with periodic commits in staking_fetcher.py backfill loop; enables resume on crash
- Commit: `8f6578b` (10-03)

**~~Repeated API Calls for Same Data~~ (FIXED 2026-03-14):**
- Fixed: NearBlocks `get_transaction_count()` cached with 5-minute TTL via `_cache_get`/`_cache_set` pattern
- Commit: `8f6578b` (10-03)

**~~No Query Result Pagination in Reports~~ (FIXED 2026-03-14):**
- Fixed: Capital gains, ledger, and export reports now use named cursor streaming (`conn.cursor(name=..., withhold=True)` with `itersize=1000`) instead of fetchall
- Commit: `7df7a56` (10-03)

---

## Fragile Areas

**~~Transaction Classification Engine~~ (HARDENED 2026-03-14):**
- Fixed: `check_classifier_invariants_batch()` detects missing/duplicate parent classifications and swap leg imbalances; all violations log to `audit_log` and set `needs_review=True` without halting pipeline
- Commits: `3f9c4c8` (11-04)

**~~Cost Basis Calculation (ACB)~~ (HARDENED 2026-03-14):**
- Fixed: `check_acb_pool_invariants()` detects negative balance/cost after every acquire/dispose; violations log to `audit_log` and flag for review without halting
- Commits: `3f9c4c8` (11-04)

**~~Balance Reconciliation Process~~ (HARDENED 2026-03-14):**
- Fixed: Wallet coverage check verifies all user wallets are reconciled; undiagnosed discrepancy check flags open results with no diagnosis; both log to `audit_log`
- Commits: `9235658` (11-04)

**~~Exchange Integration~~ (HARDENED 2026-03-14):**
- Fixed: `validate_parsed_row()` in `BaseExchangeParser` validates non-zero amount, parseable date, and non-empty asset after every `parse_row()`; violations set `needs_review=True` with `_invariant_violations` list
- Commits: `9235658` (11-04)

---

## Scaling Limits

**~~Single SQLite Database~~ (FIXED 2026-03-14):**
- Fixed: Fully migrated to PostgreSQL; legacy SQLite modules archived; all docs purged of SQLite references
- Commits: `e4aea73` (09-01), `af91c12` (10-04)

**~~API Connection Pool Size~~ (FIXED 2026-03-14):**
- Fixed: `DB_POOL_MIN`/`DB_POOL_MAX` configurable via env vars (default 1/10); `pool_stats()` introspection helper added
- Commit: `718f869` (10-02)

**NearBlocks API Rate Limit:**
- Current capacity: Tier-dependent, typically 5-10 calls/second with backoff
- Limit: Full data refresh for 64 wallets + multi-chain takes hours; spike in requests causes timeouts
- Scaling path: Implement request queuing with exponential backoff; consider NEAR Lake for historical data

**~~Report Generation Memory~~ (FIXED 2026-03-14):**
- Fixed: Report CSV generation now uses named cursor streaming (itersize=1000); no full result set in memory
- Commit: `7df7a56` (10-03)

---

## Dependencies at Risk

**~~Deprecated Exchange APIs~~ (FIXED 2026-03-14):**
- Fixed: `coinbase_pro_indexer.py` emits `DeprecationWarning` at module level directing users to `exchange_parsers/coinbase.py`; marked `# DEPRECATED` in header
- Commit: `af91c12` (10-04)

**~~Python Version Compatibility~~ (FIXED 2026-03-14):**
- Fixed: `pyproject.toml` declares `requires-python = ">=3.11"` in `[project]` table
- Commit: `718f869` (10-02)

**~~Hardcoded External URLs~~ (FIXED 2026-03-13):**
- Fixed: All URLs now read from env vars (NEAR_RPC_URL, NEARBLOCKS_API_URL, NEARDATA_API_URL, FASTNEAR_API_URL) with existing defaults
- Commit: `2eadcc6`

---

## Missing Critical Features

**~~No Transaction Audit Log~~ (FIXED 2026-03-14):**
- Fixed: Unified `audit_log` table (migration 008) replaces `classification_audit_log`; `write_audit()` helper wired into all mutation points (classifier, ACB, duplicates, manual edits, verification, reports); `GET /api/audit/history` endpoint with entity_type/entity_id filters
- Commits: `130e420`, `fbc5962` (11-01), `86ff6e0`, `445ec54` (11-05)

**~~No Multi-Currency Support~~ (FIXED 2026-03-14):**
- Fixed: `EVMDecoder.decode_multihop_path()` parses packed Uniswap V3 path encoding; `_decompose_swap()` produces intermediate legs for multi-hop swaps (A→B→C→D); `evm_classifier.py` forwards `token_path`/`hop_count` from swap detection
- Commits: `673e319`, `43b3da0` (11-03), `da054a5` (11 fix)

**~~No Offline Mode~~ (FIXED 2026-03-14):**
- Fixed: `OFFLINE_MODE` config with `_detect_offline_mode()` auto-detection; network-dependent jobs requeued with backoff; health and status endpoints expose offline state
- Commits: `9f75958` (11-05)

**~~No Data Export Validation~~ (FIXED 2026-03-14):**
- Fixed: `MANIFEST.json` with SHA-256 per file + source data fingerprint generated by PackageBuilder; stale report detection via `_check_staleness()` on list endpoint
- Commits: `ca10d95`, `b01df2b` (11-02)

---

## Test Coverage Gaps

**~~Indexer Edge Cases Untested~~ (FIXED 2026-03-14):**
- Fixed: 7 tests covering 429 rate limits, timeouts, connection errors, empty responses, missing fields, None amounts
- Commits: `5111afd`, `98cc69c` (09-04)

**~~Exchange Parser Robustness~~ (FIXED 2026-03-14):**
- Fixed: 7 tests covering missing columns, extra columns, empty CSV, malformed amounts, missing dates, Unicode BOM, wrong format detection
- Commit: `98cc69c` (09-04)

**~~Classification Rule Interactions~~ (FIXED 2026-03-14):**
- Fixed: 7 new tests covering priority resolution, equal priority tie-breaking, chain filter, unknown fallthrough, specialist_confirmed preservation, idempotency
- Commit: `865bbb4` (10-05)

**~~ACB with Gap Data~~ (FIXED 2026-03-14):**
- Fixed: 4 new tests covering missing price, None amount, estimated price flagging, oversell clamp with needs_review
- Commit: `c3cc5ca` (10-05)

**~~Concurrent Classification~~ (FIXED 2026-03-14):**
- Fixed: Tests verify specialist_confirmed preservation on upsert and duplicate classify call idempotency
- Commit: `865bbb4` (10-05)

**~~API Endpoint Authorization~~ (FIXED 2026-03-14):**
- Fixed: 6 cross-user isolation tests verifying user_id filtering on wallets, transactions, verification endpoints
- Commit: `5111afd` (09-04)

---

*Concerns audit: 2026-03-14*
*Fixed 7 concerns on 2026-03-13 (commit 2eadcc6): bare exceptions, DB connection leaks, hardcoded URLs, path traversal, NULL coercion, input validation, hardcoded external URLs*
*Fixed 10 concerns on 2026-03-14 (Phase 9): SQLite cleanup, N+1 queries, rate limiting (API + NearBlocks), env validation, SQL injection, rollback pattern, reconcile refactor, authorization tests, indexer edge cases, parser robustness*
*Fixed 14 concerns on 2026-03-14 (Phase 10): module splitting, price index, streaming reports, batch backfill, API caching, pool config, log sanitization, stubs documented, deprecation warnings, pyproject.toml, SQLite refs removed, rule priority tests, ACB edge case tests, concurrent classification tests*
*Fixed 8 concerns on 2026-03-14 (Phase 11): unified audit log, audit wiring + API, multi-hop swap decomposition, data export validation (MANIFEST.json), offline mode, ACB/classifier/reconciler/exchange parser invariant hardening*
