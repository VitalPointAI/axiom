# Phase 15: Account Block Index Integer Encoding - Research

**Researched:** 2026-04-10
**Domain:** PostgreSQL storage optimization, Rust indexer pipeline, dictionary encoding
**Confidence:** HIGH

## Summary

This phase transforms the `account_block_index` table from `(TEXT, BIGINT)` to `(INTEGER, INTEGER)` via a dictionary table that maps account strings to compact integer IDs. The current table uses ~1.3 TB on disk (including indexes). By switching both columns to 4-byte integers, the per-row size drops from ~70 bytes to ~36 bytes on the heap, and the B-tree indexes become proportionally smaller due to narrower keys. The dictionary table for ~15M unique accounts adds only ~0.9 GB.

The Rust indexer currently writes tab-separated `(text, bigint)` pairs to stdout, which are piped to a temp file and then COPY'd into PostgreSQL via a staging table with `INSERT ... ON CONFLICT DO NOTHING`. The v2 pipeline must maintain an in-memory HashMap of account strings to integer IDs, look up (or insert) each account in the PostgreSQL `account_dictionary` table, and emit `(int, int)` pairs instead. The Python `near_fetcher.py` lookup code must join through the dictionary to resolve account strings to integer IDs before querying the v2 table.

PostgreSQL 16 (already in use) has 300% faster COPY performance. The migration of existing data can use `INSERT INTO ... SELECT` with a join to the dictionary, processed in batches to avoid locking the table for hours. Both old and new tables coexist during transition, allowing the switch to be verified before dropping the old table.

**Primary recommendation:** Use `INTEGER` for both columns (4 bytes each). NEAR block heights are at ~186M (8.7% of INTEGER max 2.1B), with ~62 years of headroom. Account count is ~15M (0.7% of INTEGER max). Use `postgres` crate v0.19 (blocking) in Rust for direct dictionary lookups, keeping the existing stdout-to-COPY pipeline pattern.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Add `account_dictionary` table: `(id SERIAL PRIMARY KEY, account_id TEXT UNIQUE NOT NULL)` -- maps string account IDs to compact integers
- Replace `account_block_index` schema from `(account_id TEXT, block_height BIGINT)` to `(account_int INTEGER, block_height INTEGER)` -- both columns fit in 4 bytes (NEAR has ~15M unique accounts < 2^31, block heights < 2^31)
- Row size drops from ~60 bytes to ~12 bytes (4+4 bytes data + ~4 bytes tuple overhead)
- Dictionary table is ~900 MB for 15M accounts -- one-time, small relative to savings
- Total target: ~260-270 GB for the full NEAR chain index (vs ~1.3 TB today)
- The Rust indexer must connect to PostgreSQL directly to look up or insert account strings into the dictionary
- On each account string encountered: check local in-memory cache first, then dictionary table, insert if new
- Emit `(account_int, block_height)` integer pairs instead of `(account_id_text, block_height)` to stdout/COPY
- Keep the in-memory cache warm across the full indexing run to minimize dictionary lookups
- New Alembic migration (020) creates `account_dictionary` and new `account_block_index_v2` table
- The migration does NOT drop the old table -- both coexist during transition
- A data migration script populates the dictionary from existing `account_block_index` distinct account_ids, then copies rows to v2
- After verification, the old table can be dropped manually
- The Rust indexer and Python lookup code switch to v2 atomically
- `indexers/near_fetcher.py` and any code querying `account_block_index` must join through `account_dictionary`
- Query pattern: `SELECT block_height FROM account_block_index_v2 WHERE account_int = (SELECT id FROM account_dictionary WHERE account_id = $1)`
- Or: resolve account_int once, then query directly
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

### Deferred Ideas (OUT OF SCOPE)
- Segment-based indexing (1K-block granules) -- can be layered on top of integer encoding later for additional reduction
- Sharding the index across multiple tables by block range
- Moving the index to a dedicated read-replica
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PostgreSQL | 16-alpine | Database (already in docker-compose) | Already deployed, has 300% faster COPY in v16 |
| psycopg2-binary | 2.9.11 | Python PostgreSQL adapter (already installed) | Already used throughout codebase |
| postgres (Rust) | 0.19.13 | Blocking Rust PostgreSQL client | Matches current Rust binary's blocking pattern (reqwest blocking) |
| Alembic | (existing) | Database migrations | Already used for all 019 migrations |

[VERIFIED: `docker-compose.yml` confirms `postgres:16-alpine`]
[VERIFIED: `pip3 show psycopg2-binary` confirms version 2.9.11]
[VERIFIED: `cargo search postgres` confirms 0.19.13]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| clap | 4.x | Rust CLI argument parsing | Already in Cargo.toml |
| reqwest | 0.12 | Rust HTTP client | Already in Cargo.toml |
| serde_json | 1.x | Rust JSON parsing | Already in Cargo.toml |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `postgres` (blocking) | `tokio-postgres` (async) | Current Rust binary uses blocking threads, not async Tokio. Adding tokio would require rewriting the entire threading model. Keep blocking. |
| Full HashMap cache | LRU cache (e.g. `lru` crate) | 15M accounts at ~40 bytes/entry = ~600 MB RAM. Fits comfortably in memory. Full HashMap is simpler and faster (no eviction overhead). Use full HashMap. |
| INTEGER block_height | BIGINT block_height | NEAR at ~186M blocks, INTEGER supports 2.1B. 62 years of headroom. INTEGER saves 4 bytes/row across billions of rows. Use INTEGER. |

**Rust Cargo.toml additions:**
```toml
[dependencies]
postgres = { version = "0.19", features = ["with-serde_json-1"] }
```

## Architecture Patterns

### Current Pipeline (as-is)
```
Rust binary (fetch archives -> parse JSON -> extract accounts)
    |
    v  stdout: "alice.near\t12345\n"
    |
    v  temp file on disk (.tsv)
    |
    v  Python/bash: COPY abi_staging FROM temp file
    |
    v  INSERT INTO account_block_index SELECT DISTINCT ... ON CONFLICT DO NOTHING
    |
    v  Update account_indexer_state cursor
```
[VERIFIED: `indexers/account_indexer.py` lines 405-510, `scripts/run_account_indexer.sh` lines 82-109]

### New Pipeline (to-be)
```
Rust binary (fetch archives -> parse JSON -> extract accounts)
    |
    v  For each account string:
    |    1. Check in-memory HashMap<String, i32>
    |    2. If miss: SELECT id FROM account_dictionary WHERE account_id = $1
    |    3. If not found: INSERT INTO account_dictionary (account_id) VALUES ($1) RETURNING id
    |    4. Cache the (string -> int) mapping
    |
    v  stdout: "42\t12345\n"  (integer pairs)
    |
    v  temp file on disk (.tsv)
    |
    v  Python/bash: COPY abi_staging_v2 FROM temp file
    |
    v  INSERT INTO account_block_index_v2 SELECT DISTINCT ... ON CONFLICT DO NOTHING
    |
    v  Update account_indexer_state cursor
```

### Recommended Project Structure Changes
```
db/migrations/versions/
    020_integer_encoded_index.py    # New Alembic migration

indexers/account-indexer-rs/
    src/main.rs                     # Modified: adds PG connection + dictionary cache
    Cargo.toml                      # Modified: adds postgres dependency

indexers/account_indexer.py         # Modified: staging table schema, v2 table name
indexers/near_fetcher.py            # Modified: query through dictionary join

scripts/run_account_indexer.sh      # Modified: staging table schema, v2 table name
scripts/migrate_to_v2.py            # NEW: data migration script (old -> new)
scripts/check_account_indexer.sh    # Modified: query v2 table
```

### Pattern 1: Dictionary Cache in Rust
**What:** HashMap<String, i32> populated lazily during indexing, with PostgreSQL as backing store
**When to use:** During the Rust indexer's fetch-extract-emit loop
**Example:**
```rust
// Source: Standard Rust + postgres crate pattern
use std::collections::HashMap;
use postgres::{Client, NoTls};

struct DictionaryCache {
    cache: HashMap<String, i32>,
    client: Client,
}

impl DictionaryCache {
    fn new(database_url: &str) -> Self {
        let client = Client::connect(database_url, NoTls)
            .expect("Failed to connect to PostgreSQL");
        Self {
            cache: HashMap::with_capacity(20_000_000), // Pre-allocate for 15M+ accounts
            client,
        }
    }

    fn resolve(&mut self, account_id: &str) -> i32 {
        // 1. Check in-memory cache (fast path)
        if let Some(&id) = self.cache.get(account_id) {
            return id;
        }

        // 2. Check PostgreSQL dictionary
        let row = self.client.query_opt(
            "SELECT id FROM account_dictionary WHERE account_id = $1",
            &[&account_id],
        ).expect("Dictionary lookup failed");

        if let Some(row) = row {
            let id: i32 = row.get(0);
            self.cache.insert(account_id.to_string(), id);
            return id;
        }

        // 3. Insert new entry
        let row = self.client.query_one(
            "INSERT INTO account_dictionary (account_id) VALUES ($1)
             ON CONFLICT (account_id) DO UPDATE SET account_id = EXCLUDED.account_id
             RETURNING id",
            &[&account_id],
        ).expect("Dictionary insert failed");

        let id: i32 = row.get(0);
        self.cache.insert(account_id.to_string(), id);
        id
    }

    /// Pre-warm cache from PostgreSQL — call once at startup
    fn warm_cache(&mut self) {
        let rows = self.client.query(
            "SELECT id, account_id FROM account_dictionary", &[],
        ).expect("Cache warm failed");
        for row in rows {
            let id: i32 = row.get(0);
            let account_id: String = row.get(1);
            self.cache.insert(account_id, id);
        }
    }
}
```
[ASSUMED — pattern based on postgres crate 0.19 API]

### Pattern 2: COPY Pipeline with Integer Staging
**What:** Same staging-table COPY pattern but with integer columns
**When to use:** Bulk loading chunks into PostgreSQL
**Example:**
```sql
-- Source: Current run_account_indexer.sh pattern, adapted for integers
CREATE TEMP TABLE IF NOT EXISTS abi_staging_v2
    (account_int INTEGER, block_height INTEGER);
TRUNCATE abi_staging_v2;
\copy abi_staging_v2 (account_int, block_height) FROM '/tmp/chunk.tsv'
INSERT INTO account_block_index_v2 (account_int, block_height)
SELECT DISTINCT account_int, block_height FROM abi_staging_v2
ON CONFLICT DO NOTHING;
DROP TABLE abi_staging_v2;
```

### Pattern 3: Python Dictionary Lookup
**What:** Resolve account_id string to integer, then query v2 table
**When to use:** In near_fetcher.py `_get_indexed_blocks()`
**Example:**
```python
# Source: Adapted from current near_fetcher.py lines 320-368
def _get_indexed_blocks(self, account_id: str) -> Optional[list]:
    conn = self.db_pool.getconn()
    try:
        cur = conn.cursor()
        # Check index state (same as current)
        try:
            cur.execute("SELECT last_processed_block FROM account_indexer_state WHERE id = 1")
            state = cur.fetchone()
            if not state or state[0] < 1_000_000:
                cur.close()
                return None
        except Exception:
            cur.close()
            conn.rollback()
            return None

        # Resolve account string to integer via dictionary
        cur.execute(
            "SELECT id FROM account_dictionary WHERE account_id = %s",
            (account_id.lower(),),
        )
        dict_row = cur.fetchone()
        if not dict_row:
            # Account not in dictionary — either not indexed or truly absent
            cur.close()
            return None  # Falls back to full scan

        account_int = dict_row[0]

        # Query v2 table with integer key
        cur.execute(
            "SELECT block_height FROM account_block_index_v2 WHERE account_int = %s ORDER BY block_height",
            (account_int,),
        )
        rows = cur.fetchall()
        cur.close()
        return [r[0] for r in rows] if rows else []
    finally:
        self.db_pool.putconn(conn)
```

### Anti-Patterns to Avoid
- **Running INSERT INTO ... SELECT on the full 10B+ row table in one transaction:** This will lock the table, consume massive WAL space, and likely OOM. Batch in chunks of 1-10M rows.
- **Keeping dictionary lookups per-row in Python during migration:** Use a single JOIN-based INSERT INTO SELECT instead of row-by-row resolution.
- **Dropping the old table before verifying the new one:** The migration creates v2 alongside v1. Only drop v1 after full verification.
- **Using ON CONFLICT with COPY directly:** PostgreSQL COPY does not support ON CONFLICT. Must use staging table pattern (already established in codebase).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dictionary encoding | Custom encoding scheme | SERIAL PRIMARY KEY + UNIQUE constraint | PostgreSQL handles concurrent inserts, sequence gaps, and index maintenance |
| Bulk data loading | Row-by-row INSERT | COPY + staging table + INSERT ON CONFLICT | 10-100x faster, already proven in codebase |
| In-memory cache | Custom eviction logic | std::collections::HashMap | 15M entries at ~40 bytes = ~600MB, fits in RAM, no eviction needed |
| Data migration | Custom export/import scripts | INSERT INTO ... SELECT with JOIN | Single SQL statement per batch, no serialization overhead |
| Connection pooling (Rust) | Manual connection management | Single persistent connection (blocking) | Rust binary is single-producer; one connection suffices for dictionary lookups |

**Key insight:** The current codebase already has the COPY + staging table + ON CONFLICT pattern fully implemented and battle-tested. The only changes are: (1) column types in the staging table, (2) adding dictionary resolution in the Rust binary, and (3) updating queries in Python.

## Common Pitfalls

### Pitfall 1: SERIAL Sequence Gaps in Dictionary
**What goes wrong:** SERIAL/SEQUENCE can have gaps (e.g., from rolled-back transactions). The dictionary IDs may not be contiguous.
**Why it happens:** PostgreSQL sequences are not transactional for performance reasons.
**How to avoid:** This is fine -- gaps don't matter. The IDs are just compact keys, not meaningful values. Do not try to make them contiguous.
**Warning signs:** Someone proposes using a counter instead of SERIAL "to avoid gaps."

### Pitfall 2: Dictionary Insert Race Conditions
**What goes wrong:** Two concurrent workers try to insert the same account_id into the dictionary simultaneously.
**Why it happens:** The Rust indexer uses multiple worker threads, and the Python migration script may run concurrently.
**How to avoid:** Use `INSERT ... ON CONFLICT (account_id) DO UPDATE SET account_id = EXCLUDED.account_id RETURNING id` (upsert pattern). This is safe for concurrent use.
**Warning signs:** Unique constraint violations during indexing.

### Pitfall 3: Data Migration OOM on Full-Table SELECT
**What goes wrong:** `INSERT INTO v2 SELECT ... FROM account_block_index JOIN account_dictionary` processes all 10B+ rows at once, consuming all available memory or WAL space.
**Why it happens:** PostgreSQL tries to build the full result set or transaction in memory.
**How to avoid:** Process in block_height range batches (e.g., 1M blocks per batch). Each batch is its own transaction.
**Warning signs:** PostgreSQL process consuming all RAM, disk filling with WAL files.

### Pitfall 4: Forgetting to Update All Query Sites
**What goes wrong:** Some code paths still query the old `account_block_index` table after the switch.
**Why it happens:** The table is referenced in multiple files: `near_fetcher.py`, `account_indexer.py`, `admin.py`, `run_account_indexer.sh`, `check_account_indexer.sh`.
**How to avoid:** Grep for all references to `account_block_index` and update systematically. There are 6+ files that reference this table.
**Warning signs:** Queries returning wrong results or errors after migration.

### Pitfall 5: Rust Binary PostgreSQL Connection During Archive Fetching
**What goes wrong:** The Rust binary's PostgreSQL connection times out or becomes stale during long archive fetch operations (minutes between dictionary lookups).
**Why it happens:** The Rust binary spends most of its time doing HTTP requests. The PG connection sits idle.
**How to avoid:** Use a simple reconnect-on-error pattern, or set `tcp_keepalive` on the connection. The `postgres` crate supports connection configuration.
**Warning signs:** "connection reset" errors after long idle periods in the Rust binary.

### Pitfall 6: Integer Overflow (Non-Issue but Verify)
**What goes wrong:** Block height or account count exceeds INTEGER (2^31 - 1 = 2,147,483,647).
**Why it happens:** Theoretical concern for very far future.
**How to avoid:** NEAR block heights are at ~186M (8.7% of max), with ~62 years of headroom at 1 block/sec. Account count is ~15M (0.7% of max). INTEGER is safe. Document the safety margin for future reference.
**Warning signs:** None for decades. If NEAR changes to sub-second blocks, revisit.

## Code Examples

### Alembic Migration 020
```python
# Source: Based on existing migration pattern in 018_account_block_index.py
"""Add dictionary-encoded integer index for account_block_index.

Creates account_dictionary (string->int mapping) and account_block_index_v2
(integer pairs). Does NOT drop the original table -- both coexist during
transition.

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"


def upgrade():
    # Dictionary: maps account_id strings to compact integers
    op.create_table(
        "account_dictionary",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Text(), nullable=False, unique=True),
    )
    op.create_index(
        "ix_account_dictionary_account_id",
        "account_dictionary",
        ["account_id"],
        unique=True,
    )

    # New integer-encoded index table
    op.create_table(
        "account_block_index_v2",
        sa.Column("account_int", sa.Integer(), nullable=False),
        sa.Column("block_height", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("account_int", "block_height"),
    )
    # Lookup index: "give me all blocks for this account"
    op.create_index(
        "ix_abiv2_account_block",
        "account_block_index_v2",
        ["account_int", "block_height"],
    )


def downgrade():
    op.drop_index("ix_abiv2_account_block", "account_block_index_v2")
    op.drop_table("account_block_index_v2")
    op.drop_index("ix_account_dictionary_account_id", "account_dictionary")
    op.drop_table("account_dictionary")
```

### Data Migration Script Pattern
```python
# Source: Based on batch migration pattern from codebase + PostgreSQL best practices
# scripts/migrate_to_v2.py

"""Migrate existing account_block_index data to v2 (integer-encoded).

Step 1: Populate account_dictionary from distinct account_ids
Step 2: Copy rows to v2 in block_height range batches
"""

import logging
import psycopg2

BATCH_SIZE = 1_000_000  # 1M block range per batch

def populate_dictionary(conn):
    """Insert all distinct account_ids into account_dictionary."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO account_dictionary (account_id)
        SELECT DISTINCT account_id FROM account_block_index
        ON CONFLICT (account_id) DO NOTHING
    """)
    conn.commit()
    count = cur.rowcount
    cur.close()
    return count

def migrate_batch(conn, start_block, end_block):
    """Copy one block range from old table to v2 via dictionary join."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO account_block_index_v2 (account_int, block_height)
        SELECT d.id, abi.block_height::integer
        FROM account_block_index abi
        JOIN account_dictionary d ON d.account_id = abi.account_id
        WHERE abi.block_height >= %s AND abi.block_height < %s
        ON CONFLICT DO NOTHING
    """, (start_block, end_block))
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    return inserted
```

### Rust Indexer Modified Output
```rust
// Source: Adaptation of current main.rs writer thread (lines 173-190)
// The writer thread changes from emitting text to emitting integer pairs

// In the writer thread:
for pairs in rx {
    for (account_int, height) in &pairs {
        // Integer pairs: "42\t12345\n"
        let _ = write!(writer, "{}\t{}\n", account_int, height as i32);
    }
    total_pairs += pairs.len() as u64;
    if total_pairs % 100_000 < 1000 {
        let _ = writer.flush();
    }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| COPY without staging table | COPY to staging + INSERT ON CONFLICT | Already in codebase | Handles duplicates during bulk load |
| Python multiprocessing backfill | Rust binary + COPY pipeline | Already in codebase | 100x faster (~2700 blocks/sec vs ~30) |
| PostgreSQL 15 COPY | PostgreSQL 16 COPY | PG 16 (2023) | 300% faster COPY due to reduced relation extension lock time |
| TEXT + BIGINT columns | INTEGER + INTEGER columns | This phase | ~5x storage reduction |

**Deprecated/outdated:**
- Nothing in the current stack is deprecated. PostgreSQL 16 is current. psycopg2 2.9.x is actively maintained.

## Storage Calculation Detail

### Per-Row Breakdown (Verified)
```
OLD (TEXT + BIGINT):
  Tuple header:     24 bytes (23 + 1 MAXALIGN padding)
  account_id TEXT:  ~34 bytes (4-byte varlena header + ~30 char avg)
  block_height:      8 bytes (BIGINT)
  Line pointer:      4 bytes
  TOTAL:           ~70 bytes/row on heap

NEW (INTEGER + INTEGER):
  Tuple header:     24 bytes (23 + 1 MAXALIGN padding)
  account_int:       4 bytes (INTEGER, int4-aligned)
  block_height:      4 bytes (INTEGER, int4-aligned)
  Line pointer:      4 bytes
  TOTAL:           ~36 bytes/row on heap
```
[VERIFIED: PostgreSQL docs on tuple headers and data alignment]
[CITED: https://www.postgresql.org/docs/current/storage-page-layout.html]
[CITED: https://www.enterprisedb.com/postgres-tutorials/data-alignment-postgresql]

### Total Size Estimate
The user's CONTEXT.md cites ~60 bytes per row and a target of ~260-270 GB. The actual PostgreSQL overhead (24-byte tuple header + 4-byte line pointer per row = 28 bytes overhead) means the per-row size is ~36 bytes, not ~12 bytes as the context optimistically estimates. However, the B-tree index on integer pairs is significantly more compact than on text+bigint pairs, so the overall savings are substantial.

**Conservative estimate with verified tuple sizes:**
- ~10B rows * 36 bytes/row (heap) = ~335 GB heap
- B-tree index on (int4, int4): ~8 bytes/index entry + overhead = ~120-150 GB
- Dictionary: ~0.9 GB
- **Total: ~460-490 GB** (vs ~1.3 TB currently = ~63% reduction)

**Note:** The user's target of ~260-270 GB may require additional optimizations (segment-based indexing, which is deferred) or may be based on different per-row assumptions. The integer encoding alone achieves a substantial reduction but the actual number depends on real-world PostgreSQL page fill efficiency and index bloat. This should be flagged during planning as a potential expectation mismatch.

### INTEGER Safety Margins
| Column | Current Value | Max INTEGER | Headroom |
|--------|--------------|-------------|----------|
| block_height | ~186M | 2,147,483,647 | 62 years at 1 block/sec |
| account_int (count) | ~15M | 2,147,483,647 | Effectively unlimited |

[VERIFIED: NEAR block height ~170M in Oct 2025, extrapolated to ~186M by April 2026]
[CITED: https://www.postgresql.org/docs/current/datatype-numeric.html]

## Discretion Recommendations

### COPY vs batch INSERT for v2 bulk loading
**Recommendation: Use COPY (via staging table pattern).** The existing codebase already has this pattern battle-tested in `account_indexer.py` and `run_account_indexer.sh`. COPY is 10-100x faster than INSERT for bulk loading. The staging table + INSERT ON CONFLICT pattern handles duplicates. No reason to change what works.

### Cache eviction strategy: LRU vs full HashMap
**Recommendation: Full HashMap (no eviction).** 15M accounts * ~40 bytes (String key + i32 value + HashMap overhead) = ~600 MB RAM. This fits comfortably in memory on any modern server. Full HashMap is simpler (no eviction logic) and faster (no LRU bookkeeping). Pre-warm the cache at startup by loading the entire dictionary table.

### Reverse index on dictionary
**Recommendation: Rely on the UNIQUE constraint index.** The `UNIQUE` constraint on `account_dictionary.account_id` automatically creates a B-tree index. For reverse lookups (int->text), the primary key index on `id` suffices. No additional index needed.

### Compression options
**Recommendation: Skip for now.** TOAST compression only applies to variable-length columns (TEXT, JSONB). The v2 table has only fixed-length INTEGER columns -- TOAST is not applicable. The `pg_compress` extension is non-standard and adds operational complexity. The integer encoding itself is the compression.

### INTEGER vs BIGINT for block_height
**Recommendation: Use INTEGER.** 62 years of headroom is more than sufficient. If NEAR ever approaches 2B blocks (which would require a fundamental protocol change to sub-second blocks sustained for decades), a migration from INTEGER to BIGINT is straightforward via ALTER TABLE. The 4 bytes saved per row across 10B+ rows is ~40 GB -- significant.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `postgres` crate 0.19 blocking API supports query_opt and query_one with typed parameters | Architecture Patterns | Rust code won't compile; would need API adjustment |
| A2 | Pre-warming HashMap with 15M entries from PostgreSQL is fast enough (<30 seconds) | Discretion Recommendations | May need to warm lazily during first indexing pass instead |
| A3 | Dictionary INSERT ... ON CONFLICT ... RETURNING id works for concurrent Rust worker threads | Common Pitfalls | May need mutex on the PG connection or per-thread connections |
| A4 | The total row count is ~10B rows based on 1.3TB / ~140 bytes per row | Storage Calculation | Actual row count may differ; run `SELECT reltuples FROM pg_class` to verify |
| A5 | User's 260-270 GB target may not be achievable with integer encoding alone due to tuple overhead | Storage Calculation | User may be disappointed; clarify expectations |

## Open Questions

1. **Exact current row count**
   - What we know: Table is ~1.3 TB. Estimated ~10B rows based on ~140 bytes/row (including index overhead).
   - What's unclear: Exact row count. `pg_class.reltuples` would give an estimate, but PostgreSQL container is not currently running.
   - Recommendation: Verify with `SELECT reltuples::bigint FROM pg_class WHERE relname = 'account_block_index'` before migration planning. This affects migration batch sizing and time estimates.

2. **Migration duration for existing data**
   - What we know: 10B rows with JOIN through dictionary, processed in 1M-block batches. Each batch involves a sequential scan of the old table's block_height range.
   - What's unclear: Whether the old table has an index on `block_height` alone (it doesn't -- only composite PK on `(account_id, block_height)`). Range scans on `block_height` may require a sequential scan per batch.
   - Recommendation: Consider adding a temporary index on `block_height` before migration, or use `TABLESAMPLE` to estimate throughput before committing.

3. **Rust binary thread safety for dictionary access**
   - What we know: Current Rust binary uses multiple worker threads + one writer thread. Workers send Vec<(String, u64)> through a channel.
   - What's unclear: Whether dictionary resolution should happen in worker threads (requiring thread-safe PG access) or in the writer thread (serial but simpler).
   - Recommendation: Resolve in the writer thread. Workers continue extracting (String, u64) pairs. The writer thread resolves strings to ints before writing. This keeps the PG connection single-threaded and avoids synchronization complexity. The writer thread is I/O-bound (stdout), so adding dictionary lookups (mostly cache hits) adds minimal overhead.

4. **Actual achievable size reduction**
   - What we know: Per-row heap size drops from ~70 to ~36 bytes. Index size also decreases (narrower keys).
   - What's unclear: Exact reduction depends on PostgreSQL page fill efficiency, B-tree internal node overhead, and whether the current 1.3 TB includes dead tuples or bloat.
   - Recommendation: After migrating, measure actual v2 table size with `pg_total_relation_size()`. Communicate to user that ~500 GB is more realistic than ~260 GB for integer encoding alone. The 260 GB target may require the deferred segment-based indexing.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 16 | Database | Yes (Docker) | 16-alpine | -- |
| Rust toolchain | Rust indexer rebuild | Yes | 1.92.0 (rustc + cargo) | -- |
| Python 3.11 | Migration script, tests | Yes | 3.11.0rc1 | -- |
| psycopg2-binary | Python PG adapter | Yes | 2.9.11 | -- |
| postgres crate (Rust) | Dictionary lookups | Not yet in Cargo.toml | 0.19.13 (on crates.io) | -- |

**Missing dependencies with no fallback:**
- None. All required tools are available.

**Missing dependencies with fallback:**
- `postgres` Rust crate needs to be added to `Cargo.toml` (trivial `cargo add`).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (Python), cargo test (Rust) |
| Config file | `pyproject.toml` [tool.ruff] section, no pytest.ini |
| Quick run command | `python -m pytest tests/test_near_fetcher.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INT-01 | Migration 020 creates account_dictionary and v2 tables | integration | Manual (run migration, inspect schema) | No -- Wave 0 |
| INT-02 | Dictionary lookup resolves account string to integer | unit | `pytest tests/test_dictionary_encoding.py::test_dictionary_lookup -x` | No -- Wave 0 |
| INT-03 | near_fetcher queries v2 table via dictionary join | unit | `pytest tests/test_near_fetcher.py::test_indexed_blocks_v2 -x` | No -- Wave 0 |
| INT-04 | Rust indexer emits integer pairs to stdout | integration | `cargo test --manifest-path indexers/account-indexer-rs/Cargo.toml` | No -- Wave 0 |
| INT-05 | Data migration script correctly transforms old->new | integration | `pytest tests/test_dictionary_encoding.py::test_data_migration -x` | No -- Wave 0 |
| INT-06 | Wallet lookup completes under 2 minutes | smoke | Manual timing test | No |
| INT-07 | Admin API reports v2 table stats | unit | `pytest tests/test_admin_api.py -x` | Exists (needs update) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_near_fetcher.py tests/test_admin_api.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green + manual verification of table sizes

### Wave 0 Gaps
- [ ] `tests/test_dictionary_encoding.py` -- covers INT-02, INT-05
- [ ] Update `tests/test_near_fetcher.py` with v2 query tests -- covers INT-03
- [ ] `indexers/account-indexer-rs/tests/` -- Rust integration tests for dictionary cache
- [ ] Add `postgres` to `Cargo.toml` dependencies

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- internal indexer, no user-facing auth |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A -- database access via existing connection pool |
| V5 Input Validation | Yes | Account IDs are lowercased and filtered (!=system) before dictionary insert |
| V6 Cryptography | No | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via account_id | Tampering | Parameterized queries ($1 placeholders), never string concatenation. Already enforced in codebase. |
| Dictionary table poisoning (inserting garbage account_ids) | Tampering | Account IDs come from NEAR blockchain data (trusted source). No user input path to dictionary. |

## Sources

### Primary (HIGH confidence)
- `indexers/account_indexer.py` -- Current Python COPY pipeline, staging table pattern, backfill logic
- `indexers/account-indexer-rs/src/main.rs` -- Current Rust indexer, worker threads, stdout writer pattern
- `indexers/near_fetcher.py` -- Current Python lookup code using account_block_index
- `db/migrations/versions/018_account_block_index.py` -- Current schema (TEXT, BIGINT)
- `scripts/run_account_indexer.sh` -- Shell COPY pipeline, staging table pattern
- `docker-compose.yml` -- PostgreSQL 16-alpine confirmed
- PostgreSQL docs: storage-page-layout, datatype-numeric -- tuple header, data alignment, integer sizes

### Secondary (MEDIUM confidence)
- [PostgreSQL COPY optimization](https://www.postgresql.org/docs/current/populate.html) -- Official docs on bulk loading best practices
- [PostgreSQL 16 COPY improvements](https://pganalyze.com/blog/5mins-postgres-16-faster-copy-bulk-load) -- 300% faster COPY in PG 16
- [Data alignment in PostgreSQL](https://www.enterprisedb.com/postgres-tutorials/data-alignment-postgresql) -- Tuple header and padding details
- [CYBERTEC bulk loading](https://www.cybertec-postgresql.com/en/postgresql-bulk-loading-huge-amounts-of-data/) -- Drop indexes before bulk load, recreate after

### Tertiary (LOW confidence)
- NEAR block height extrapolation (~186M as of April 2026) -- based on ~170M in Oct 2025 + 1 block/sec growth rate. Verify against live RPC.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all tools already in use or verified on crates.io/pip
- Architecture: HIGH -- extending existing proven patterns (COPY + staging + ON CONFLICT)
- Pitfalls: HIGH -- derived from reading actual codebase and known PostgreSQL behaviors
- Storage estimates: MEDIUM -- per-row sizes are verified, but total table size depends on page fill efficiency and B-tree overhead. The 260 GB target may be optimistic.

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable domain -- PostgreSQL and Rust patterns don't change rapidly)
