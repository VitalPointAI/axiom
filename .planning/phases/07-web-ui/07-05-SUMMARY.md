---
phase: 07-web-ui
plan: 05
subsystem: api
tags: [fastapi, psycopg2, reports, verification, job-queue, file-download, fileresponse]

# Dependency graph
requires:
  - phase: 07-01
    provides: FastAPI app factory, get_effective_user, require_admin, test infrastructure
  - phase: 07-03
    provides: Wallet CRUD patterns, job queue INSERT pattern, run_in_threadpool usage
  - phase: 06-05
    provides: PackageBuilder, generate_reports job type, output/{year}_tax_package/ directory
  - phase: 05-01
    provides: verification_results table with diagnosis_category, needs_review columns
provides:
  - POST /api/reports/generate — queue generate_reports job with year/treatment/override
  - GET /api/reports/preview/{type} — 6 inline report previews (LIMIT 50 each)
  - GET /api/reports/download/{year} — list tax package files
  - GET /api/reports/download/{year}/{filename} — FileResponse with path-traversal guard
  - GET /api/reports/status — check if package exists for year
  - POST /api/exchanges/import — CSV upload + file_import job queue
  - GET /api/exchanges — list supported exchanges
  - GET /api/verification/summary — grouped issue counts with severity
  - GET /api/verification/issues — detailed issues with optional category filter
  - POST /api/verification/resolve/{id} — mark issue resolved
  - POST /api/verification/resync/{id} — queue re-sync job per diagnosis_category
  - GET /api/verification/needs-review-count — cross-table unresolved count
affects:
  - 07-06
  - 07-07
  - frontend-ui

# Tech tracking
tech-stack:
  added: []
  patterns:
    - FileResponse for file downloads with path-traversal guard using Path.resolve().relative_to()
    - _get_output_dir() helper function for patchable output path in tests
    - category meta dict mapping diagnosis_category to (severity, description, action)
    - RESYNC_JOB_MAP dict for diagnosis_category -> job_type routing

key-files:
  created:
    - api/routers/reports.py
    - api/routers/verification.py
    - api/schemas/reports.py
    - api/schemas/verification.py
    - tests/test_api_reports.py
    - tests/test_api_verification.py
  modified:
    - api/routers/__init__.py
    - api/main.py

key-decisions:
  - "_get_output_dir() as a patchable helper function allows tests to override output path with tmp_path without environment variables"
  - "Path traversal guard: check '..' in filename AND resolve().relative_to() — defense in depth"
  - "year query param range widened to 1900-2200 (not 2000-2100) to avoid 422 for year=1999 in status endpoint"
  - "specialist_override admin check in route handler (not dependency) — uses user dict from get_effective_user directly"
  - "_CATEGORY_META dict maps diagnosis_category to severity/description/action — single source of truth"
  - "_RESYNC_JOB_MAP maps diagnosis_category to job_type — extensible without if/elif chains"
  - "Verification resync uses wallet_id from issue row to target correct wallet (not user-level)"

patterns-established:
  - "Patchable helper pattern: _get_output_dir() so tests use tmp_path without monkeypatching os.getcwd()"
  - "FileResponse with explicit path-traversal validation before serving"
  - "Category metadata dict pattern for mapping codes to human-readable UI content"

requirements-completed:
  - UI-06
  - UI-07

# Metrics
duration: 5min
completed: 2026-03-13
---

# Phase 7 Plan 05: Reports + Verification API Summary

**Report generation via job queue (generate_reports), 6 inline previews with LIMIT 50, FileResponse downloads with path-traversal guard, SHA-256 exchange CSV import, and verification dashboard grouping issues by diagnosis_category with severity metadata and resync job routing**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-13T21:56:10Z
- **Completed:** 2026-03-13T22:01:04Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Report generation queues generate_reports job with year/tax_treatment/specialist_override in cursor JSON; admin gate enforces specialist_override restriction
- Six preview endpoints (capital-gains, income, ledger, t1135, superficial-losses, holdings) run targeted LIMIT 50 queries against existing tables
- File download endpoints list tax package directory contents and serve files via FastAPI FileResponse with double path-traversal guard
- Exchange CSV import computes SHA-256 hash, upserts file_imports, and queues file_import job
- Verification summary groups issues by diagnosis_category with severity/description/action metadata; needs_review_count aggregates across verification_results + transaction_classifications + capital_gains_ledger
- Resync routes diagnosis_category to appropriate job_type (staking_sync, full_sync, classify_transactions)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — failing reports tests** - `f68b532` (test)
2. **Task 1: GREEN — reports + exchanges implementation** - `0f9c9ad` (feat)
3. **Task 2: RED+GREEN — verification tests + verification router already implemented** - `43e295a` (test)

**Plan metadata:** (this commit)

_Note: TDD tasks have separate RED (test) and GREEN (feat) commits. Verification tests were written after implementation was already in place from Task 1's commit batch._

## Files Created/Modified

- `api/schemas/reports.py` — ReportGenerateRequest/Response, ReportPreviewResponse, ReportFileResponse, ReportStatusResponse, ExchangeImportResponse, SupportedExchange schemas
- `api/routers/reports.py` — All report + exchange endpoints (POST generate, GET preview/*, GET download/*, GET status, POST /api/exchanges/import, GET /api/exchanges)
- `api/schemas/verification.py` — IssueGroup, VerificationSummary, VerificationIssue, ResolveRequest, NeedsReviewCountResponse schemas
- `api/routers/verification.py` — All verification endpoints (GET summary, GET issues, POST resolve, POST resync, GET needs-review-count)
- `api/routers/__init__.py` — Replaced stub reports/verification routers with real implementations; added exchanges_router import
- `api/main.py` — Added exchanges_router mount
- `tests/test_api_reports.py` — 16 tests covering generate, preview, download, exchange import
- `tests/test_api_verification.py` — 12 tests covering summary, issues, resolve, resync, needs-review-count

## Decisions Made

- `_get_output_dir()` as a patchable helper function allows tests to override output path with `tmp_path` without environment variables or monkeypatching os.getcwd()
- Path traversal guard uses both `.." in filename` string check AND `resolve().relative_to()` — defense in depth
- Year query param range widened to 1900-2200 (not 2000-2100) to avoid 422 for year=1999 in status endpoint tests
- `_CATEGORY_META` dict maps diagnosis_category to (severity, description, suggested_action) — single source of truth, extensible
- `_RESYNC_JOB_MAP` maps diagnosis_category to job_type — avoids if/elif chains, easy to extend

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Year range too narrow for status endpoint**
- **Found during:** Task 1 (test_report_status_not_found used year=1999)
- **Issue:** Query constraint `ge=2000` returned 422 Unprocessable Entity for year=1999
- **Fix:** Widened range to `ge=1900, le=2200` — valid tax years should not be artificially restricted
- **Files modified:** api/routers/reports.py
- **Verification:** test_report_status_not_found now returns 200 with exists=False
- **Committed in:** 0f9c9ad (Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Minor range validation fix. No scope creep.

## Issues Encountered

None — all endpoints implemented cleanly following patterns established in Plans 07-01 through 07-03.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Reports + verification API complete; 28 tests pass
- Ready for Plan 07-06 (jobs router + pipeline auto-chain, if applicable) or frontend integration
- `_get_output_dir()` returns `output/` relative to CWD; production deployment should ensure this path is writable

---
*Phase: 07-web-ui*
*Completed: 2026-03-13*
