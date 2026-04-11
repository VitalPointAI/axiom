---
phase: 15-account-block-index-integer-encoding
plan: "03"
subsystem: database
tags: [python, postgres, psycopg2, dictionary-encoding, integer-encoding, account-block-index, migration, segment-indexing]

# Dependency graph
requires:
  - phase: 15-01
    provides: "account_dictionary and account_block_index_v2 tables created via migration 020"
  - phase: 15-02
    provides: "Rust indexer writes integer+segment pairs to v2 table via dictionary lookup"
provides:
  - "near_fetcher.py reads from account_block_index_v2 via dictionary join and scans 1000-block segments"
  - "admin.py /account-indexer-status reports v2 table stats and dictionary_size"
  - "check_account_indexer.sh health check uses v2 table row estimate"
  - "scripts/migrate_to_v2.py converts existing account_block_index data to v2 format in batches"
affects: [wallet-sync, admin-dashboard, devops-monitoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Segment expansion: segment_start values from v2 returned to _sync_from_index which expands each to 1000-block range"
    - "Dictionary join pattern: resolve account string -> integer in Python before querying v2 table"
    - "Batch migration with per-batch transactions: 1M-block batches each committed independently"

key-files:
  created:
    - scripts/migrate_to_v2.py
  modified:
    - indexers/near_fetcher.py
    - api/routers/admin.py
    - scripts/check_account_indexer.sh

key-decisions:
  - "Segment expansion happens in Python (_sync_from_index expands each segment_start to 1000 blocks) rather than in SQL, preserving parallelism with ThreadPoolExecutor"
  - "Migration uses per-batch transactions (1M blocks each) to prevent WAL bloat and allow safe resume via --start-block"
  - "Dictionary size reported as exact COUNT(*) since account_dictionary is small; v2 row count uses pg_class reltuples estimate to avoid slow COUNT"

patterns-established:
  - "Pattern: parameterized queries for all account_id lookups (no string concatenation) - T-15-07 mitigated"
  - "Pattern: batch migration with ON CONFLICT DO NOTHING enables idempotent re-runs without data corruption"

requirements-completed: [INT-05, INT-06, INT-07, INT-08]

# Metrics
duration: 25min
completed: 2026-04-11
---

# Phase 15 Plan 03: Lookup + Admin + Migration Summary

**Wallet lookup switched to dictionary join + segment expansion via account_block_index_v2, with batch migration script to convert existing data without re-fetching from neardata.xyz**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-11T00:00:00Z
- **Completed:** 2026-04-11T00:25:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `_get_indexed_blocks()` in near_fetcher.py now resolves account_id to integer via `account_dictionary`, then queries `account_block_index_v2` for segment_start values
- `_sync_from_index()` expands each segment_start to a 1000-block range and scans those blocks in parallel via neardata.xyz, filtering for the target account
- Admin status endpoint updated to report `account_block_index_v2` reltuples and exact `account_dictionary` COUNT with new `dictionary_size` field
- Health check script updated to use fast `reltuples` estimate from `account_block_index_v2` instead of slow `COUNT(*)`
- `scripts/migrate_to_v2.py` provides a two-phase batch migration: Phase 1 populates dictionary from old table, Phase 2 copies rows in 1M-block batches with JOIN + segment calculation

## Task Commits

Each task was committed atomically:

1. **Task 1: Update near_fetcher.py lookup + admin.py + check script for v2** - `a38637b` (feat)
2. **Restore accidentally deleted files** - `041c8c1` (fix) — worktree base reset left staged deletions; restored 15-01 SUMMARY, 15-02 SUMMARY, and migration 020
3. **Task 2: Create data migration script** - `c623327` (feat)

## Files Created/Modified
- `indexers/near_fetcher.py` - Rewrote `_get_indexed_blocks()` for dictionary+v2 lookup; updated `_sync_from_index()` for segment expansion; updated log message in `sync_wallet()`
- `api/routers/admin.py` - Updated account-indexer-status endpoint to query v2 table + dictionary; added `dictionary_size` to response
- `scripts/check_account_indexer.sh` - Changed INDEX_COUNT to use `reltuples::bigint` from `account_block_index_v2`
- `scripts/migrate_to_v2.py` - New 250-line batch migration script with `--dry-run` and `--start-block` flags

## Decisions Made
- Segment expansion is done in Python (not SQL): `_sync_from_index()` builds `all_blocks = [range(seg, seg+1000) for seg in segments]` and processes them through the existing parallel `ThreadPoolExecutor` pattern. This avoids changing the SQL query shape and leverages the same parallelism as the full scan path.
- Dictionary lookup on account not found uses the same tip-proximity check as the old code: if `last_processed_block >= tip - 1000`, return `[]` (account has no activity). Otherwise return `None` (fall back to full scan).
- Migration script uses `((block_height / 1000) * 1000)::integer` SQL integer division — PostgreSQL integer division already truncates, so this correctly floors to segment boundaries.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Restored files accidentally deleted by worktree base reset**
- **Found during:** Task 1 commit
- **Issue:** `git reset --soft` to the expected base left the prior HEAD's staged deletions of `15-01-SUMMARY.md`, `15-02-SUMMARY.md`, and `020_integer_encoded_index.py` included in the commit
- **Fix:** Used `git checkout 8ac5978 -- <files>` to restore all three files, then committed the restoration
- **Files modified:** `.planning/phases/15-account-block-index-integer-encoding/15-01-SUMMARY.md`, `.planning/phases/15-account-block-index-integer-encoding/15-02-SUMMARY.md`, `db/migrations/versions/020_integer_encoded_index.py`
- **Committed in:** `041c8c1`

---

**Total deviations:** 1 auto-fixed (blocking issue from worktree setup)
**Impact on plan:** Restoration preserves the Phase 15 wave 1 and 2 outputs that this plan depends on. No functional scope change.

## Issues Encountered
- Worktree `git reset --soft` to the base commit caused staged deletions from the previous agent's commits to be included in Task 1's commit. Caught and fixed before Task 2.

## Threat Coverage
Per plan threat model:
- T-15-07 (SQL injection): All account_id lookups use parameterized `%s` placeholders. No string concatenation. Verified in both `_get_indexed_blocks()` and `migrate_to_v2.py`.
- T-15-08 (Migration OOM): Migration processes 1M-block batches, each with its own `conn.commit()`. WAL stays bounded. Resume via `--start-block` flag.
- T-15-10 (Segment scan overrun): `_sync_from_index()` logs segment count via `logger.info("Scanning %d segments (%d block ranges) for %s", ...)`. Operators can monitor.

## Known Stubs
None — all data sources are wired. The lookup reads from real v2 tables, admin reports real counts, migration script processes real data.

## Next Phase Readiness
- All active query paths (near_fetcher.py, admin.py, check_account_indexer.sh) now use account_block_index_v2 and account_dictionary
- Old account_block_index table remains intact for manual verification before dropping
- scripts/migrate_to_v2.py is ready to run against production data (`python3 scripts/migrate_to_v2.py`)
- After migration and verification, the old table can be dropped manually or via a new migration

---
*Phase: 15-account-block-index-integer-encoding*
*Completed: 2026-04-11*
