# Codebase Concerns

**Analysis Date:** 2026-03-11

## Tech Debt

**Hardcoded API Key Fallback in Production Code:**
- Issue: NearBlocks API key `0F1F69733B684BD48753570B3B9C4B27` is hardcoded as a fallback in multiple files
- Files: `web/app/api/portfolio/route.ts:6`, `web/app/api/portfolio/history/route.ts:7`, `web/app/api/portfolio/summary/route.ts:6`, `web/debug-nearblocks-staking.js:2`
- Impact: API key is committed to git and visible in source. If the env var is unset, the hardcoded key is used, masking configuration errors.
- Fix approach: Remove the fallback. Fail explicitly if `NEARBLOCKS_API_KEY` is not set. Rotate the exposed key.

**Hardcoded Database Credentials in Fallback Strings:**
- Issue: PostgreSQL connection strings with username and password are hardcoded as fallbacks
- Files: `web/app/api/sync/run/route.ts:10`, `web/app/api/admin/sync/route.ts:6`, `web/app/api/defi/positions/route.ts:6`, `web/lib/auth-db.ts:8`
- Impact: Database credentials (`neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx`) committed to git history. Even if rotated, the pattern persists.
- Fix approach: Remove all fallback connection strings. Use only `process.env.DATABASE_URL`. Rotate the exposed password.

**Duplicate Database Pool Instances:**
- Issue: Several API routes create their own `new Pool()` instead of using the shared `web/lib/db.ts` module
- Files: `web/app/api/sync/run/route.ts:9-11`, `web/app/api/admin/sync/route.ts:5-7`, `web/app/api/defi/positions/route.ts:5-7`
- Impact: Multiple connection pools competing for the same PostgreSQL max_connections. Risk of connection exhaustion under load.
- Fix approach: Refactor these routes to import from `web/lib/db.ts` instead of creating standalone pools.

**Legacy SQLite Compatibility Shim:**
- Issue: `getDb()` in `web/lib/db.ts` provides a `.prepare()` API that mimics SQLite's better-sqlite3 interface, returning Promises that look like sync calls
- Files: `web/lib/db.ts:115-167`
- Impact: Confusing DX. The `prepare().get()` pattern looks synchronous but returns Promises. Some routes use `getDb()` (legacy), others use `db` directly (modern). Mixed patterns across 62 API routes.
- Fix approach: Migrate all routes to use the async `db` object directly. Remove `getDb()` shim.

**SQLite-isms in PostgreSQL Code:**
- Issue: Some SQL still uses SQLite syntax like `INSERT OR IGNORE` which is not valid PostgreSQL
- Files: `web/app/api/import/pdf/route.ts:431`
- Impact: PDF import will fail at the database layer. Silent data loss or runtime errors.
- Fix approach: Replace `INSERT OR IGNORE` with `INSERT ... ON CONFLICT DO NOTHING` for PostgreSQL.

**Massive Debug/Utility Script Accumulation:**
- Issue: 58 debug/investigation scripts in `web/` root and 47 one-off Python scripts in project root
- Files: `web/check-*.cjs`, `web/debug-*.js`, `web/analyze-*.js`, `web/verify-*.cjs`, root `check-*.py`, `fix-*.py`, `verify-*.py`
- Impact: Cluttered codebase. Many reference SQLite databases or hardcoded wallet addresses. Creates confusion about what is production code vs. throwaway investigation.
- Fix approach: Move to a `scripts/debug/` directory or delete. These are not production code.

**Oversized Route Files:**
- Issue: Several route files exceed 500 lines with mixed concerns (data fetching, price lookups, formatting, business logic all in one file)
- Files: `web/app/api/portfolio/route.ts` (724 lines), `web/app/api/import/pdf/route.ts` (502 lines), `web/app/api/validators/route.ts` (567 lines)
- Impact: Hard to maintain, test, or modify individual pieces. The portfolio route has inline price feed mapping, spam filtering, balance calculation, and response formatting.
- Fix approach: Extract price service, spam filtering, and balance calculation into `web/lib/` modules. Keep routes thin.

**Committed SQLite Database File:**
- Issue: `neartax.db` (11MB) is tracked in git despite `.gitignore` listing `*.db`
- Files: `neartax.db` (root)
- Impact: Binary file bloating git history. May contain user data that should not be in version control.
- Fix approach: Remove from tracking with `git rm --cached neartax.db`. It is already in `.gitignore`.

## Known Bugs

**Wallet Sync Auth Uses Raw Session Token as Account ID:**
- Symptoms: `web/app/api/wallets/[id]/sync/route.ts` reads the session cookie value and queries `WHERE near_account_id = ?` using it, but the cookie contains a session token (random hex), not a NEAR account ID
- Files: `web/app/api/wallets/[id]/sync/route.ts:14,31-32`
- Trigger: Any wallet sync request. The query `SELECT id FROM users WHERE near_account_id = ?` with a session token will always return no rows.
- Workaround: The user gets a 404 error. Use `getAuthenticatedUser()` from `web/lib/auth.ts` instead.

**PDF Import Uses Unresolved Promise for Wallet ID:**
- Symptoms: `getOrCreateExchangeWallet` is async but called without `await` in the import handler
- Files: `web/app/api/import/pdf/route.ts:416` - `const walletId = getOrCreateExchangeWallet(...)` (missing `await`)
- Trigger: Any PDF import. `walletId` will be a Promise object, not a number, causing all INSERT statements to fail.
- Workaround: None - PDF imports are broken.

**Rate Limit Comment Mismatch:**
- Symptoms: Auth rate limit is set to 500 but the comment says "10 auth attempts per minute"
- Files: `web/middleware.ts:11`
- Trigger: Not a runtime bug, but the actual limit (500) is far more permissive than intended (10), potentially allowing brute-force attacks.
- Workaround: Fix the value to match intent (10 for auth).

## Security Considerations

**Command Injection via User-Controlled Input in Shell Commands:**
- Risk: Several routes pass user-controlled values (wallet addresses, user IDs, exchange names) directly into shell command strings via template literals
- Files: `web/app/api/wallets/[id]/sync/route.ts:151-161` (address, chain), `web/app/api/import/pdf/route.ts:334` (userId), `web/app/api/exchanges/[exchange]/sync/route.ts:114` (exchange, apiKey, apiSecret), `web/app/api/sync/run/route.ts:33` (userId)
- Current mitigation: Some basic validation exists for address formats (hex/NEAR patterns). User IDs are integers from the database. But exchange API keys and secrets have no sanitization.
- Recommendations: Never interpolate user input into shell commands. Use `spawn` with argument arrays (which some routes already do correctly) instead of `exec` with string interpolation. Add input sanitization for all values passed to Python scripts.

**No CSRF Protection:**
- Risk: State-changing API endpoints accept POST requests with only cookie-based authentication
- Files: `web/lib/auth.ts`, `web/middleware.ts`
- Current mitigation: `sameSite: 'lax'` on session cookie provides partial protection
- Recommendations: Add CSRF tokens for state-changing operations, or verify `Origin`/`Referer` headers in middleware.

**In-Memory Rate Limiting:**
- Risk: Rate limiting resets on server restart and does not work across multiple server instances
- Files: `web/middleware.ts:4-6`
- Current mitigation: Comment acknowledges this: "For production with multiple servers, use Redis"
- Recommendations: Migrate to Redis-backed rate limiting before horizontal scaling. Current single-instance deployment is acceptable.

**Session Tokens Have No Binding to IP or User Agent:**
- Risk: Stolen session tokens can be used from any device/location
- Files: `web/lib/auth.ts:125-148`
- Current mitigation: HttpOnly + Secure + SameSite cookies prevent most token theft vectors
- Recommendations: Consider adding IP/UA binding or shorter session lifetimes for sensitive operations.

**Hardcoded Deployment Path:**
- Risk: Auto-categorization script uses hardcoded path `/home/deploy/neartax`
- Files: `web/app/api/import/pdf/route.ts:334`, `web/app/api/sync/run/route.ts:33`
- Current mitigation: None
- Recommendations: Use relative paths from `process.cwd()` or configure via environment variable.

## Performance Bottlenecks

**Portfolio Route Makes Sequential External API Calls Per Wallet:**
- Problem: Fetches liquid balance for each NEAR wallet individually via NearBlocks API, in batches of 10
- Files: `web/app/api/portfolio/route.ts:464-474`
- Cause: No caching of balances. Each portfolio load triggers N API calls (one per wallet). With 20 wallets, this adds 2+ seconds.
- Improvement path: Cache balances in the database. Refresh asynchronously. Return cached values for fast page loads.

**Multiple Expensive DISTINCT Queries for Filter Dropdowns:**
- Problem: Transaction list endpoint runs 4 separate `SELECT DISTINCT` queries against the full transactions table on every request
- Files: `web/app/api/transactions/route.ts:143-177`
- Cause: No caching or materialized views for filter options
- Improvement path: Cache filter values. Invalidate on transaction insert. Or use a materialized view refreshed periodically.

**Portfolio Route Fetches ALL Pyth Price Feeds:**
- Problem: Requests prices for all 40+ tokens from Pyth on every portfolio load, even if user only holds 2 tokens
- Files: `web/app/api/portfolio/route.ts:297`
- Cause: `getPythPrices(Object.keys(PYTH_FEEDS))` requests everything regardless of user holdings
- Improvement path: First determine which tokens the user actually holds, then request only those prices.

## Fragile Areas

**Portfolio Route (`web/app/api/portfolio/route.ts`):**
- Files: `web/app/api/portfolio/route.ts`
- Why fragile: 724-line monolith mixing external API calls (Pyth, Ref Finance, CoinGecko, NearBlocks, ExchangeRate API), database queries, price calculations, spam filtering, and response formatting. Any external API change breaks the whole page.
- Safe modification: Extract each concern into a separate module in `web/lib/`. Test price calculation logic independently.
- Test coverage: No tests exist.

**Wallet Sync Pipeline (TypeScript -> Python Subprocess):**
- Files: `web/app/api/wallets/route.ts:171-250`, `web/app/api/wallets/[id]/sync/route.ts:100-256`, `web/app/api/sync/run/route.ts`, `web/app/api/sync/control/route.ts`
- Why fragile: Node.js spawns Python subprocesses with hardcoded paths. Relies on specific Python environment, script locations, and argument formats. Subprocess errors are silently swallowed in some paths.
- Safe modification: Add health checks for Python environment. Log all subprocess invocations. Add integration tests.
- Test coverage: No tests exist.

**Import Pipeline (CSV/PDF Parsing):**
- Files: `web/app/api/import/pdf/route.ts`, `web/app/dashboard/import/page.tsx`
- Why fragile: PDF import has a known bug (unresolved Promise for wallet ID). The generic PDF parser uses brittle regex patterns and falls back to `new Date().toISOString()` when date parsing fails, silently assigning wrong dates. Uses `INSERT OR IGNORE` which is invalid PostgreSQL.
- Safe modification: Fix the `await` bug first. Add validation tests with sample PDFs.
- Test coverage: No tests exist.

## Scaling Limits

**In-Memory Rate Limiter:**
- Current capacity: Single server instance only
- Limit: Breaks with horizontal scaling (multiple instances have independent counters)
- Scaling path: Use Redis or database-backed rate limiting

**Python Subprocess Architecture:**
- Current capacity: One sync operation per subprocess. Each wallet sync spawns a new Python process.
- Limit: Heavy memory usage with many concurrent syncs. No queue management.
- Scaling path: Implement a proper job queue (e.g., BullMQ, Celery) instead of fire-and-forget subprocesses.

## Dependencies at Risk

**`better-sqlite3` vs PostgreSQL Migration Residue:**
- Risk: Codebase was migrated from SQLite to PostgreSQL. SQLite artifacts remain (debug scripts reference SQLite, `neartax.db` still exists, `getDb()` shim mimics SQLite API)
- Impact: Confusion for developers. Some code paths may silently fail due to SQL dialect differences.
- Migration plan: Complete the migration by removing all SQLite references, the compatibility shim, and the old database file.

## Missing Critical Features

**No Test Suite:**
- Problem: Zero test files exist for the web application. Only 2 test files exist in the project root (`test_trace.py`, `test_trace_tx.py`), both for Python trace debugging.
- Blocks: Safe refactoring, regression detection, CI/CD pipeline
- Files: No `jest.config.*`, `vitest.config.*`, or `*.test.*` files in `web/`

**No Database Migrations System:**
- Problem: Schema changes are managed via standalone SQL files (`01_create_table.sql`, `fix-stuck-syncs.sql`) with no migration framework
- Blocks: Reliable deployments, schema versioning, rollbacks
- Files: `01_create_table.sql`, `bulk-update-prices.sql`

**No Error Monitoring:**
- Problem: All errors go to `console.error()`. No Sentry, Datadog, or similar error tracking.
- Blocks: Visibility into production issues. Errors are invisible unless someone checks server logs.

## Test Coverage Gaps

**Entire Web Application:**
- What's not tested: All 62 API routes, all frontend components, all lib modules
- Files: Everything under `web/`
- Risk: Any change could introduce regressions undetected. Portfolio calculations, tax reports, and import parsing are critical financial operations with no automated verification.
- Priority: High - this is a financial application where calculation errors have real monetary consequences

**Python Indexers:**
- What's not tested: All blockchain indexers (NEAR, EVM, XRP, Akash, Cosmos)
- Files: `indexers/*.py`
- Risk: Transaction parsing errors lead to incorrect balances and tax calculations
- Priority: High

**Tax Calculation Engine:**
- What's not tested: ACB (Adjusted Cost Base) calculations, capital gains/losses, income categorization
- Files: `tax/cost_basis.py`, `tax/reports.py`
- Risk: Incorrect tax reports. This is the core value proposition of the application.
- Priority: Critical

---

*Concerns audit: 2026-03-11*
