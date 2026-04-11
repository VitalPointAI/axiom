# Phase 15: Account Block Index Integer Encoding - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Optimize the NEAR account_block_index table from ~1.3 TB (TEXT account_id, BIGINT block_height) to ~260 GB by introducing dictionary-encoded integer IDs. The Rust indexer must emit integer pairs, Python lookup code must join through the dictionary, and wallet lookup performance must remain under 2 minutes end-to-end.

</domain>

<decisions>
## Implementation Decisions

### Storage Optimization (TWO techniques combined)
- **Technique 1: Integer encoding** — Add `account_dictionary` table: `(id SERIAL PRIMARY KEY, account_id TEXT UNIQUE NOT NULL)` maps string account IDs to compact integers. Replace `account_block_index` schema from `(account_id TEXT, block_height BIGINT)` to `(account_int INTEGER, block_height INTEGER)`. Both columns fit in 4 bytes.
- **Technique 2: Segment-based indexing** — Store `(account_int, segment_start INTEGER)` instead of exact block heights. Segment size = 1,000 blocks. A wallet active in block 50,123,456 is stored as segment 50,123,000. Measurement scripts showed 93% row count reduction in early eras (fewer unique segments than exact blocks).
- Combined effect: integer encoding reduces per-row bytes (~70 -> ~36 with PG overhead), segment indexing reduces row COUNT by 50-93% depending on era. Together, target is **under 250 GB** to fit on 500 GB disk with room for user data + PG overhead.
- Dictionary table is ~900 MB for 15M accounts — one-time, small relative to savings
- Disk budget: 500 GB total (provisioned on DigitalOcean, cannot downsize)

### Rust Indexer Changes
- The Rust indexer (`indexers/account-indexer-rs/src/main.rs`) must connect to PostgreSQL directly to look up or insert account strings into the dictionary
- On each account string encountered: check local in-memory cache first, then dictionary table, insert if new
- Emit `(account_int, block_height)` integer pairs instead of `(account_id_text, block_height)` to stdout/COPY
- Keep the in-memory cache warm across the full indexing run to minimize dictionary lookups

### Migration Strategy
- New Alembic migration (020) creates `account_dictionary` and new `account_block_index_v2` table
- The migration does NOT drop the old table — both coexist during transition
- A data migration script populates the dictionary from existing `account_block_index` distinct account_ids, then copies rows to v2
- After verification, the old table can be dropped manually
- The Rust indexer and Python lookup code switch to v2 atomically

### Python Lookup Changes
- `indexers/near_fetcher.py` and any code querying `account_block_index` must join through `account_dictionary`
- Query pattern: `SELECT block_height FROM account_block_index_v2 WHERE account_int = (SELECT id FROM account_dictionary WHERE account_id = $1)`
- Or: resolve account_int once, then query directly

### Performance Requirements
- Wallet lookup (from address to block list): under 2 minutes end-to-end
- Dictionary lookup (string to int): under 10ms with index
- Bulk indexing throughput: at least as fast as current Rust indexer (~2,700 blocks/sec)
- The integer B-tree index is more compact and faster to scan than a text B-tree

### Claude's Discretion
- Whether to use COPY or batch INSERT for bulk loading the v2 table
- Cache eviction strategy in the Rust indexer (LRU vs full HashMap)
- Whether to add a reverse index (int -> text) on the dictionary or rely on the UNIQUE constraint
- Compression options (TOAST, pg_compress) for additional savings
- Whether block_height should be INTEGER (4 bytes, supports up to 2.1B blocks) or keep BIGINT (8 bytes) for future-proofing

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Database Schema
- `db/migrations/versions/018_account_block_index.py` — Current account_block_index schema (TEXT, BIGINT)

### Rust Indexer
- `indexers/account-indexer-rs/src/main.rs` — Current Rust indexer that emits (text, bigint) pairs
- `indexers/account-indexer-rs/Cargo.toml` — Rust dependencies

### Measurement Scripts
- `scripts/measure_index_size.py` — Measures exact index size across eras
- `scripts/measure_segment_size.py` — Measures segmented index size reduction

### Python Lookup Code
- `indexers/near_fetcher.py` — Uses account_block_index for wallet lookups

</canonical_refs>

<specifics>
## Specific Ideas

- User wants to provision a 500 GB DigitalOcean disk instead of 1.5 TB — this optimization is the gate
- The full NEAR chain is ~160M+ blocks with ~75-100 unique accounts per block
- Unique account count is ~15M — fits comfortably in INTEGER (max 2.1B)
- Block heights are currently ~175M — fits in INTEGER with room to grow

</specifics>

<deferred>
## Deferred Ideas

- Sharding the index across multiple tables by block range
- Moving the index to a dedicated read-replica

</deferred>

---

*Phase: 15-account-block-index-integer-encoding*
*Context gathered: 2026-04-11*
