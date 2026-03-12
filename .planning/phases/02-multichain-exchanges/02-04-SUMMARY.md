---
phase: 02-multichain-exchanges
plan: "04"
subsystem: indexer
tags: [python, typescript, nextjs, postgresql, file-upload, exchange-csv, job-queue]

requires:
  - phase: 02-02
    provides: EVMFetcher with sync_wallet() method for EVM chains
  - phase: 02-03
    provides: Exchange CSV parsers (Coinbase, Crypto.com, Wealthsimple, GenericParser) with detect()/import_to_db()
provides:
  - IndexerService dispatches evm_full_sync and evm_incremental jobs to EVMFetcher
  - IndexerService dispatches file_import jobs to FileImportHandler
  - FileImportHandler auto-detects exchange format and routes to correct parser
  - POST /api/upload-file endpoint for exchange CSV ingestion with dedup and job queuing
affects: [02-05, phase-3-classification, phase-7-ui]

tech-stack:
  added: [Node.js crypto (SHA-256), Next.js formData(), fs.mkdirSync]
  patterns:
    - Per-user virtual wallet (exchange_imports_{userId}) for exchange file imports
    - file_imports.id passed as indexing_jobs.cursor to link job to file record
    - Parser auto-detection loop: first detect() match wins, unknown → needs_ai status
    - File deduplication via SHA-256 content hash at upload boundary

key-files:
  created:
    - indexers/file_handler.py
    - web/app/api/upload-file/route.ts
  modified:
    - indexers/service.py

key-decisions:
  - "Per-user exchange wallet: exchange_imports_{userId} avoids global UNIQUE constraint on wallets.account_id"
  - "file_imports.id stored in indexing_jobs.cursor (TEXT column) so FileImportHandler knows which file to process"
  - "Unknown exchange format sets status=needs_ai for AI agent routing (plan 05), not failed"
  - "FileImportHandler._set_failed() is a safety net inside outer exception handler to ensure status never stays 'processing'"

patterns-established:
  - "File import pattern: upload API → file_imports record → indexing_jobs (file_import) → FileImportHandler.process_file() → parser.import_to_db()"
  - "Virtual wallet pattern for non-blockchain imports: exchange chain, scoped account_id per user"

requirements-completed: [DATA-04, DATA-05]

duration: 18min
completed: 2026-03-12
---

# Phase 2 Plan 04: Service Wiring + File Upload API Summary

**EVMFetcher and FileImportHandler wired into IndexerService, with POST /api/upload-file endpoint completing the exchange CSV ingestion pipeline**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-03-12T19:10:00Z
- **Completed:** 2026-03-12T19:28:00Z
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- IndexerService now dispatches 7 job types: full_sync, incremental_sync, staking_sync, lockup_sync, evm_full_sync, evm_incremental, file_import
- FileImportHandler auto-detects exchange format (Coinbase, Crypto.com, Wealthsimple, Generic) and routes to parser's import_to_db(); unrecognized formats set status=needs_ai for plan 05
- POST /api/upload-file handles multipart upload with SHA-256 dedup (409 on duplicate), 50MB limit (413), per-user virtual wallet creation, and job queuing

## Task Commits

Each task was committed atomically:

1. **Task 1: Register EVM and file import handlers in service.py** - `734406a` (feat)
2. **Task 2: Create FileImportHandler** - `d0ed052` (feat)
3. **Task 3: Create file upload API endpoint** - `f2a0408` (feat)

## Files Created/Modified

- `indexers/service.py` - Added EVMFetcher and FileImportHandler imports; registered evm_full_sync, evm_incremental, file_import in handlers dict; added dispatch branches
- `indexers/file_handler.py` - FileImportHandler: loads file_imports record, reads first 5 lines, tries each parser's detect(), routes to import_to_db(), updates file_imports with results
- `web/app/api/upload-file/route.ts` - POST endpoint: auth, multipart parse, size check (413), SHA-256 dedup (409), save to uploads/{userId}/, create file_imports + virtual wallet + indexing_jobs, return 201

## Decisions Made

- **Per-user exchange wallet name:** `exchange_imports_{userId}` instead of `exchange_imports` — the `wallets.account_id` column is `UNIQUE NOT NULL` globally, so each user needs a distinct account_id. Using `{userId}` suffix makes it user-scoped while still being a single "virtual wallet" per user.

- **file_imports.id as cursor:** The indexing_jobs.cursor column (TEXT) stores file_imports.id so FileImportHandler can look up the file record without any other join. Simple, direct, consistent with how NEAR fetcher uses cursor for resume.

- **needs_ai vs failed for unknown formats:** Unknown exchange formats set `status='needs_ai'` rather than `'failed'` because plan 05 (AIFileAgent) will handle these. Setting `'failed'` would incorrectly signal a broken import.

- **_set_failed helper:** Used inside the outer exception handler to ensure status never stays stuck at 'processing' if the main logic raises unexpectedly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed wallets.account_id unique constraint violation**
- **Found during:** Task 3 (file upload API)
- **Issue:** Plan specified `ON CONFLICT (account_id, chain) DO NOTHING` but the schema has `account_id TEXT UNIQUE NOT NULL` (not a composite constraint). All users sharing `exchange_imports` as account_id would fail after the first user.
- **Fix:** Used per-user account_id `exchange_imports_{userId}` and `ON CONFLICT (account_id) DO NOTHING` to match actual schema constraint.
- **Files modified:** web/app/api/upload-file/route.ts
- **Verification:** Unique constraint analysis confirmed against db/schema.sql
- **Committed in:** f2a0408 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Essential correctness fix; would cause 500 errors for any user after the first without it.

## Issues Encountered

None beyond the schema constraint fix documented above.

## User Setup Required

None - no external service configuration required for this plan.

## Next Phase Readiness

- Full pipeline is now wired end-to-end: wallets API → job queue → IndexerService → EVMFetcher/FileImportHandler → parsers → exchange_transactions table
- Plan 02-05 (AIFileAgent) can now handle the needs_ai status set by FileImportHandler for unrecognized formats
- Web UI (plan 07) can call POST /api/upload-file to ingest exchange CSVs

---
*Phase: 02-multichain-exchanges*
*Completed: 2026-03-12*
