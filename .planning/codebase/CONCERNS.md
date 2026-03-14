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

**Overly Large Single Functions (PARTIALLY FIXED 2026-03-14):**
- Fixed: `verify/reconcile.py` reduced from 1002→721 lines; diagnosis logic extracted to `verify/diagnosis.py` (commit `261d983`, 09-05). Classifier N+1 batch loading added (commit `75458cf`, 09-03).
- Remaining: `engine/classifier.py` (1114 lines), `db/models.py` (961 lines), `engine/acb.py` (857 lines) still large

**Incomplete/Stub Implementations:**
- Issue: Multiple functions return empty lists or None as placeholders
- Files: `indexers/xrp_fetcher.py:204,213` (trust line tokens stub), `api/routers/portfolio.py:138` (portfolio endpoint stub), `indexers/akash_fetcher.py:65` (marked as stub)
- Impact: APIs return incomplete data silently, users may not realize functionality is missing
- Fix approach: Document clearly in API responses when data is unavailable; implement or remove stubs

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

**Sensitive Data in Logs:**
- Risk: If transactions or balances are logged with amounts, PII could leak
- Files: `indexers/hybrid_indexer.py:526` (logs tx hash but not sensitive data)
- Current mitigation: Appears mostly avoided but no systematic policy
- Recommendations: Document logging policy; sanitize sensitive fields before logging

---

## Performance Bottlenecks

**~~N+1 Query Pattern in Classification~~ (FIXED 2026-03-14):**
- Fixed: Batch loading of staking_events and lockup_events per wallet; O(1) hash lookup via index dicts instead of per-transaction DB queries
- Commit: `75458cf` (09-03)

**Price Service Not Indexed:**
- Problem: Price lookups for every transaction classification may scan large price_cache table
- Files: `indexers/price_service.py:580-600` (no evidence of indexed lookups)
- Cause: Historical price lookups by timestamp require full table scan
- Improvement path: Add composite index on (symbol, timestamp); use binary search or interval queries

**Memory Bloat in Large Backfills:**
- Problem: Full transaction history loaded into memory before processing
- Files: `indexers/full_backfill.py`, `indexers/hybrid_indexer.py` (BACKFILL_BATCH_SIZE=100)
- Cause: Batch size too small, many round trips; no streaming/generator pattern
- Improvement path: Increase batch size to 1000+; implement generator pattern for processing

**Repeated API Calls for Same Data:**
- Problem: NearBlocks API called per-wallet despite paginated response containing many wallets
- Files: `indexers/ft_indexer.py` (per-contract token lookup), `indexers/balance_snapshot.py` (per-account FT fetch)
- Cause: API design doesn't support bulk lookups
- Improvement path: Cache results locally; batch similar requests; use alternative APIs that support bulk operations

**No Query Result Pagination in Reports:**
- Problem: Report generation may load entire ledger into memory before formatting
- Files: `reports/export.py:600-700` (unclear if streaming or full load)
- Cause: No evidence of chunked processing
- Improvement path: Implement streaming CSV export; process results in fixed-size chunks

---

## Fragile Areas

**Transaction Classification Engine:**
- Files: `engine/classifier.py` (1114 lines), `engine/evm_decoder.py`
- Why fragile: Complex state machine with multiple branching paths; heavy reliance on rule priority ordering; linkage to staking/lockup events can silently fail if relationships broken
- Safe modification: Add comprehensive unit tests for each rule type; test classification matrix (every input→output combination); verify linkage integrity before writing
- Test coverage: `tests/test_classifier.py` exists but only 722 lines for 1114-line module; gaps likely in complex multi-leg transactions

**Cost Basis Calculation (ACB):**
- Files: `engine/acb.py` (857 lines)
- Why fragile: Financial calculation with no reconciliation; rounding errors accumulate; depends on correct transaction ordering
- Safe modification: Test with known scenarios (FIFO, LIFO, AVG); verify against manual calculations; add comprehensive audit trail
- Test coverage: `tests/test_acb.py` exists but integration with real price data unclear

**Balance Reconciliation Process:**
- Files: `verify/reconcile.py` (1002 lines), `verify/duplicates.py` (885 lines)
- Why fragile: Reconciliation logic compares calculated vs on-chain; any indexer miss or price data gap breaks it; manual fixups bypass logic
- Safe modification: Add immutable audit log for all corrections; implement strict mode that fails on mismatch; separate reporting from fixing
- Test coverage: Unknown if test suite covers gap scenarios

**Exchange Integration:**
- Files: `indexers/exchange_parsers/`, multiple connector implementations
- Why fragile: Each exchange has different CSV format; no validation of data completeness; silent drops of unrecognized fields
- Safe modification: Add schema validation per exchange; log dropped fields; implement test with real sample CSV files
- Test coverage: `tests/test_api_auth.py` but no exchange parser tests visible

---

## Scaling Limits

**Single SQLite Database:**
- Current capacity: Single file on disk, concurrent write conflicts
- Limit: More than 3-4 concurrent users cause SQLITE_BUSY errors; full historical data ~500MB+
- Scaling path: Already migrated to PostgreSQL (partial); complete migration required

**API Connection Pool Size:**
- Current capacity: Not configured explicitly, defaults vary by psycopg2 version (typically 5-10 connections)
- Limit: More than pool size concurrent requests block or error
- Scaling path: Configure pool size based on expected concurrency; add connection pool monitoring

**NearBlocks API Rate Limit:**
- Current capacity: Tier-dependent, typically 5-10 calls/second with backoff
- Limit: Full data refresh for 64 wallets + multi-chain takes hours; spike in requests causes timeouts
- Scaling path: Implement request queuing with exponential backoff; consider NEAR Lake for historical data

**Report Generation Memory:**
- Current capacity: Full year ledger loaded into memory
- Limit: Years with >100K transactions may cause OOM on low-memory systems
- Scaling path: Implement streaming CSV generation; chunk processing by month or token

---

## Dependencies at Risk

**Deprecated Exchange APIs:**
- Risk: Coinbase Pro API sunset date 2024, migration to unified API incomplete
- Files: `indexers/coinbase_pro_indexer.py`, `indexers/exchange_connectors/coinbase.py`
- Impact: Coinbase imports will fail after sunset
- Migration plan: Replace with new Coinbase API; test with sample data; add deprecation warning

**Python Version Compatibility:**
- Risk: Code uses f-strings (3.6+), no explicit version constraint; psycopg2 has version-specific issues
- Files: All Python files
- Impact: May fail on Python <3.8; psycopg2 binary incompatibility on ARM Macs
- Migration plan: Add `python_requires=">=3.9"` to setup.py; test on CI across versions

**~~Hardcoded External URLs~~ (FIXED 2026-03-13):**
- Fixed: All URLs now read from env vars (NEAR_RPC_URL, NEARBLOCKS_API_URL, NEARDATA_API_URL, FASTNEAR_API_URL) with existing defaults
- Commit: `2eadcc6`

---

## Missing Critical Features

**No Transaction Audit Log:**
- Problem: Changes to transaction classification not tracked; impossible to audit who changed what when
- Blocks: Full compliance with financial audit trails; forensic investigation of discrepancies
- Status: Partially addressed with `classification_audit_log` table but not consistently used

**No Multi-Currency Support:**
- Problem: Amount field assumes single token type; multi-asset swaps need decomposition
- Blocks: Accurate reporting on multi-leg transactions (e.g., swap A→B→C)
- Status: Decomposition logic exists but may not cover all cases

**No Offline Mode:**
- Problem: All indexers require live API access; no way to work with cached data
- Blocks: Development/testing without API calls; reduced API usage for cost savings
- Status: Caching partially implemented but incomplete

**No Data Export Validation:**
- Problem: Reports generated but no checksum/signature verification
- Blocks: Detecting if exported data was modified post-generation
- Status: Not implemented

---

## Test Coverage Gaps

**~~Indexer Edge Cases Untested~~ (FIXED 2026-03-14):**
- Fixed: 7 tests covering 429 rate limits, timeouts, connection errors, empty responses, missing fields, None amounts
- Commits: `5111afd`, `98cc69c` (09-04)

**~~Exchange Parser Robustness~~ (FIXED 2026-03-14):**
- Fixed: 7 tests covering missing columns, extra columns, empty CSV, malformed amounts, missing dates, Unicode BOM, wrong format detection
- Commit: `98cc69c` (09-04)

**Classification Rule Interactions:**
- What's not tested: Multiple rules matching same transaction (priority resolution), rule conflicts
- Files: `engine/classifier.py`
- Risk: Inconsistent classification across similar transactions
- Priority: High

**ACB with Gap Data:**
- What's not tested: ACB calculation when transaction history has gaps, missing prices
- Files: `engine/acb.py`
- Risk: Incorrect cost basis on incomplete data
- Priority: High

**Concurrent Classification:**
- What's not tested: Multiple workers classifying same wallet simultaneously
- Files: `engine/classifier.py`, `indexers/classifier_handler.py`
- Risk: Lost writes, duplicate processing
- Priority: Medium

**~~API Endpoint Authorization~~ (FIXED 2026-03-14):**
- Fixed: 6 cross-user isolation tests verifying user_id filtering on wallets, transactions, verification endpoints
- Commit: `5111afd` (09-04)

---

*Concerns audit: 2026-03-14*
*Fixed 7 concerns on 2026-03-13 (commit 2eadcc6): bare exceptions, DB connection leaks, hardcoded URLs, path traversal, NULL coercion, input validation, hardcoded external URLs*
*Fixed 10 concerns on 2026-03-14 (Phase 9): SQLite cleanup, N+1 queries, rate limiting (API + NearBlocks), env validation, SQL injection, rollback pattern, reconcile refactor, authorization tests, indexer edge cases, parser robustness*
