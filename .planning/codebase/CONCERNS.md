# Codebase Concerns

**Analysis Date:** 2026-03-13

## Tech Debt

**~~Bare Exception Handling Throughout Codebase~~ (FIXED 2026-03-13):**
- Fixed: Replaced all bare `except:` with specific exception types + `logger.warning()` across 11 files
- Commit: `2eadcc6`

**Mixed Database Patterns (SQLite + PostgreSQL):**
- Issue: Codebase uses both SQLite and PostgreSQL - some scripts use `sqlite3.connect()` directly while others use psycopg2 pools
- Files: `indexers/hybrid_indexer.py` (SQLite), `indexers/file_handler.py` (psycopg2 pool), `indexers/balance_snapshot.py` (psycopg2), `indexers/ft_indexer.py` (SQLite)
- Impact: Inconsistent connection management, connection leaks possible, different transaction semantics
- Fix approach: Migrate all to PostgreSQL with unified connection pool; remove SQLite usage except for tests

**~~Database Connection Resource Leaks~~ (FIXED 2026-03-13):**
- Fixed: Added `with sqlite3.connect()` context managers to all 4 scripts
- Commit: `2eadcc6`

**Overly Large Single Functions:**
- Issue: Several core modules are monolithic functions with mixed concerns
- Files: `engine/classifier.py` (1114 lines), `verify/reconcile.py` (1002 lines), `db/models.py` (961 lines), `engine/acb.py` (857 lines)
- Impact: Difficult to test, modify, debug; hard to understand flow; prone to bugs
- Fix approach: Refactor into smaller focused functions, extract validation/parsing into separate modules

**Incomplete/Stub Implementations:**
- Issue: Multiple functions return empty lists or None as placeholders
- Files: `indexers/xrp_fetcher.py:204,213` (trust line tokens stub), `api/routers/portfolio.py:138` (portfolio endpoint stub), `indexers/akash_fetcher.py:65` (marked as stub)
- Impact: APIs return incomplete data silently, users may not realize functionality is missing
- Fix approach: Document clearly in API responses when data is unavailable; implement or remove stubs

**~~Hardcoded API URLs and Configuration~~ (FIXED 2026-03-13):**
- Fixed: Extracted all URLs to `os.environ.get()` with existing defaults (NEAR_RPC_URL, NEARBLOCKS_API_URL, NEARDATA_API_URL, FASTNEAR_API_URL)
- Commit: `2eadcc6`

**No Transaction Rollback Pattern:**
- Issue: Multi-step database operations lack rollback on partial failure
- Files: `indexers/classifier_handler.py`, `indexers/file_handler.py`, all transaction write patterns
- Impact: Partial writes leave database in inconsistent state; no way to recover if classification fails midway
- Fix approach: Implement transaction wrapping with rollback on exceptions; use explicit commits

---

## Known Bugs

**Rate Limiting Not Fully Handled:**
- Symptoms: API calls to NearBlocks fail silently when rate limited, sometimes returning incomplete data
- Files: `indexers/balance_snapshot.py:48-94`, `indexers/ft_indexer.py`
- Trigger: Running full syncs during peak hours or with many wallets
- Workaround: Manually retry operations with delays or reduce batch sizes

**~~Path Traversal Validation Incomplete~~ (FIXED 2026-03-13):**
- Fixed: Added `os.path.realpath()` symlink resolution check before serving files
- Commit: `2eadcc6`

**~~Empty Placeholder Conversions~~ (FIXED 2026-03-13):**
- Fixed: Removed `str()` wrapping on nullable fields; API now returns `null` instead of `"None"`
- Commit: `2eadcc6`

---

## Security Considerations

**Environment Variables Not Validated:**
- Risk: Missing or incorrect env vars silently default to wrong values (e.g., wrong DB URL)
- Files: `indexers/balance_snapshot.py:19`, all files using `os.environ.get()` with defaults
- Current mitigation: None
- Recommendations: Add startup validation that required env vars exist and are accessible; fail fast on misconfiguration

**SQL Injection Risk in Dynamic Query Building:**
- Risk: Some queries build WHERE clauses dynamically with string concatenation
- Files: `api/routers/transactions.py:124`, `api/routers/wallets.py` (placeholders correctly used but pattern could be tighter)
- Current mitigation: Parameterized queries used for values; placeholder counts manually managed
- Recommendations: Use ORM or query builder to eliminate manual placeholder concatenation

**~~No Input Validation on User-Provided Data~~ (FIXED 2026-03-13):**
- Fixed: Added Pydantic `@field_validator` for tax categories (enum) and wallet addresses (NEAR/EVM format)
- Commit: `2eadcc6`

**No Rate Limiting on API Endpoints:**
- Risk: Attackers can spam endpoints, causing DoS
- Files: `api/main.py`, all routers
- Current mitigation: None detected
- Recommendations: Add rate limiting middleware; log suspicious access patterns

**Sensitive Data in Logs:**
- Risk: If transactions or balances are logged with amounts, PII could leak
- Files: `indexers/hybrid_indexer.py:526` (logs tx hash but not sensitive data)
- Current mitigation: Appears mostly avoided but no systematic policy
- Recommendations: Document logging policy; sanitize sensitive fields before logging

---

## Performance Bottlenecks

**N+1 Query Pattern in Classification:**
- Problem: For each transaction, multiple queries to wallet_graph, rules table, staking_events
- Files: `engine/classifier.py:80-200` (rule loading cached but per-transaction checks not batched)
- Cause: Linear scan of rules for each tx, separate queries for linked events
- Improvement path: Batch rule evaluation, use JOIN queries instead of separate lookups, cache staking_events per wallet

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

**Indexer Edge Cases Untested:**
- What's not tested: Rate limit handling, malformed API responses, network timeouts
- Files: `indexers/neardata_indexer.py`, `indexers/evm_indexer.py`, `indexers/evm_indexer_alchemy.py`
- Risk: Production failures when APIs misbehave
- Priority: High

**Exchange Parser Robustness:**
- What's not tested: Missing columns, unexpected field order, duplicate rows in CSV
- Files: `indexers/exchange_parsers/`
- Risk: Silent data loss or incorrect classification
- Priority: High

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

**API Endpoint Authorization:**
- What's not tested: Users trying to access other users' data
- Files: `api/routers/`, `api/dependencies.py`
- Risk: Data leak or unauthorized modifications
- Priority: High

---

*Concerns audit: 2026-03-13*
*Fixed 7 concerns on 2026-03-13 (commit 2eadcc6): bare exceptions, DB connection leaks, hardcoded URLs, path traversal, NULL coercion, input validation, hardcoded external URLs*
*Remaining concerns tracked for Phase 9: Code Quality & Hardening*
