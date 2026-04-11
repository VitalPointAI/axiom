---
phase: 15-account-block-index-integer-encoding
plan: "02"
subsystem: database
tags: [rust, postgres, python, psycopg2, dictionary-encoding, integer-encoding, account-block-index]

# Dependency graph
requires:
  - phase: 15-account-block-index-integer-encoding/15-01
    provides: "Alembic migration 020 creating account_dictionary and account_block_index_v2 tables"

provides:
  - "Rust indexer with DictionaryCache: pre-warms from PostgreSQL, resolves account strings to integer IDs"
  - "Rust indexer emits (account_int, segment_start) integer pairs to stdout"
  - "Python account_indexer.py COPY pipeline using abi_staging_v2 (INTEGER, INTEGER)"
  - "Python insert_account_blocks() resolves strings through account_dictionary for live/fallback paths"
  - "run_account_indexer.sh uses abi_staging_v2 and inserts into account_block_index_v2"

affects: [near_fetcher, admin_api, data_migration]

# Tech tracking
tech-stack:
  added:
    - "postgres crate 0.19.13 (blocking Rust PostgreSQL client)"
  patterns:
    - "DictionaryCache: full HashMap pre-warmed at startup, no eviction, postgres crate backing"
    - "segment_start = (block_height / 1000) * 1000 for segment-based indexing"
    - "Single reconnect-on-error retry for idle PG connection timeout"
    - "TCP keepalives (30s idle) on postgres::Config"

key-files:
  created: []
  modified:
    - "indexers/account-indexer-rs/src/main.rs"
    - "indexers/account-indexer-rs/Cargo.toml"
    - "indexers/account_indexer.py"
    - "scripts/run_account_indexer.sh"

key-decisions:
  - "Dictionary resolution in writer thread only (single PG connection, no thread-safety complexity)"
  - "Full HashMap pre-warm at startup: 15M entries ~600MB RAM, simpler than LRU, no eviction needed"
  - "TCP keepalives + single reconnect-on-error guards against idle timeout during long archive fetches"
  - "segment_start column instead of block_height: reduces cardinality by 1000x per account"
  - "ON COMMIT DELETE ROWS on temp staging table for automatic cleanup on transaction commit"

patterns-established:
  - "Pattern: DictionaryCache — struct owning HashMap<String, i32> + postgres::Client, warm at startup"
  - "Pattern: Segment start = (block_height / 1000) * 1000 for compacted block range storage"
  - "Pattern: insert_account_blocks() first upserts strings into account_dictionary then queries ids"

requirements-completed: [INT-02, INT-03, INT-04]

# Metrics
duration: 35min
completed: 2026-04-11
---

# Phase 15 Plan 02: Rust Dictionary Cache + Python v2 Pipeline Summary

**Rust indexer resolves account strings to integer IDs via PostgreSQL DictionaryCache and emits (account_int, segment_start) pairs; Python COPY pipeline switches to abi_staging_v2 (INTEGER, INTEGER) and inserts into account_block_index_v2**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-04-11T20:30:00Z
- **Completed:** 2026-04-11T21:05:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Rust indexer now connects to PostgreSQL at startup, pre-warms the full account_dictionary into a HashMap (capacity 20M), and resolves account strings to integer IDs during the write loop with >99% cache hits after warm
- Segment start calculated as `(block_height / 1000) * 1000` in the writer thread; stdout output changed from `"alice.near\t12345\n"` to `"42\t12000\n"` (integer pairs)
- Python `_backfill_rust()` COPY pipeline updated to use `abi_staging_v2 (account_int INTEGER, segment_start INTEGER)` and inserts into `account_block_index_v2`
- `insert_account_blocks()` (live/fallback path) resolves account strings through `account_dictionary` via batch upsert + SELECT, calculates segment_start, and inserts into `account_block_index_v2`
- `reset()`, `print_status()`, `_rebuild_indexes()` all updated to reference v2 tables
- `run_account_indexer.sh` constructs DATABASE_URL from env, passes `--database-url` to Rust binary, uses `abi_staging_v2` SQL block and verifies `ix_abiv2_account_segment`
- `cargo check` passes with no errors

## Task Commits

1. **Task 1: Rust indexer — PG dictionary cache + segment output** - `5002eb4` (feat)
2. **Task 2: Python COPY pipeline — v2 staging + account_block_index_v2** - `e02085f` (feat)

## Files Created/Modified

- `indexers/account-indexer-rs/Cargo.toml` - Added `postgres = { version = "0.19", features = ["with-serde_json-1"] }`
- `indexers/account-indexer-rs/src/main.rs` - Added DictionaryCache struct, warm_cache(), resolve(), --database-url arg, modified writer thread
- `indexers/account_indexer.py` - Updated _backfill_rust(), insert_account_blocks(), reset(), print_status(), _rebuild_indexes() for v2 tables
- `scripts/run_account_indexer.sh` - DATABASE_URL construction, --database-url arg, abi_staging_v2 SQL, v2 index verification

## Decisions Made

- **Dictionary resolution in writer thread only:** Workers still send `Vec<(String, u64)>` via channel unchanged. The writer thread owns the single PG connection and DictionaryCache, avoiding any locking. The writer was I/O bound on stdout; adding dictionary lookups (cache hits) adds minimal overhead.
- **Full HashMap, no eviction:** 15M accounts × ~40 bytes ≈ 600MB RAM. Fits in server memory. Pre-warming at startup means cold-start resolve() calls hit the DB briefly, then >99% are cache hits for the entire indexing run.
- **TCP keepalives + reconnect-on-error:** `keepalives_idle(30s)` prevents OS from killing idle connections. Single retry on connection error handles rare timeouts during long HTTP archive fetch windows.
- **segment_start column name:** Plan specified `segment_start` (not `block_height`) in abi_staging_v2 to match the v2 schema exactly. This is a segment-based index, not an exact block height index.

## Deviations from Plan

None — plan executed exactly as written. The plan's interfaces section accurately described the existing code, and all specified changes were applied without deviation.

## Issues Encountered

- **git reset --soft side effect:** The worktree branch reset accidentally staged deletion of `15-01-SUMMARY.md` and `020_integer_encoded_index.py` (from wave 1). These were restored from git history after the Task 1 commit and left as untracked files (not recommitted, as they belong to wave 1 and will be merged by the orchestrator).

## Known Stubs

None — all v2 table references are wired end-to-end from Rust output through Python COPY into account_block_index_v2.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: information-disclosure | scripts/run_account_indexer.sh | DATABASE_URL constructed from PG_PASS (grep'd from .env) and passed as CLI arg — visible in process listing. This matches T-15-05 in the plan's threat model; acceptable for single-user server. |

## Next Phase Readiness

- Rust binary and Python pipeline are ready to populate `account_block_index_v2` once Alembic migration 020 has run
- `near_fetcher.py` still queries the old `account_block_index` table — that update is in a separate plan (wave 3 or later)
- Data migration from old table to v2 is deferred (see 15-RESEARCH.md migrate_to_v2.py pattern)

## Self-Check

Files modified exist:
- `indexers/account-indexer-rs/Cargo.toml` — FOUND (contains `postgres = ...`)
- `indexers/account-indexer-rs/src/main.rs` — FOUND (contains `DictionaryCache`, `warm_cache`, `resolve`, `segment_start`)
- `indexers/account_indexer.py` — FOUND (contains `abi_staging_v2`, `account_block_index_v2`, `account_dictionary`)
- `scripts/run_account_indexer.sh` — FOUND (contains `DATABASE_URL`, `abi_staging_v2`, `account_block_index_v2`)

Commits exist:
- `5002eb4` — FOUND (feat(15-02): Rust indexer)
- `e02085f` — FOUND (feat(15-02): Python pipeline)

## Self-Check: PASSED

---
*Phase: 15-account-block-index-integer-encoding*
*Completed: 2026-04-11*
