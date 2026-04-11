#!/usr/bin/env python3
"""Migrate account_block_index data to account_dictionary + account_block_index_v2.

Two-phase migration:
  Phase 1: Populate account_dictionary from DISTINCT account_ids in old table.
  Phase 2: Copy rows in 1M-block batches, joining through dictionary and
           collapsing exact block heights into 1000-block segments.

Usage:
  python3 scripts/migrate_to_v2.py
  python3 scripts/migrate_to_v2.py --dry-run
  python3 scripts/migrate_to_v2.py --start-block 50000000

Environment:
  DATABASE_URL — PostgreSQL connection string (default: postgresql://neartax:neartax@127.0.0.1:5433/neartax)
"""

import argparse
import logging
import os
import sys
import time

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENESIS_BLOCK = 9_820_210
BATCH_SIZE = 1_000_000  # block-height range per batch


# ---------------------------------------------------------------------------
# Phase 1: Populate account_dictionary
# ---------------------------------------------------------------------------


def populate_dictionary(conn) -> int:
    """Insert all distinct account_ids from old table into account_dictionary.

    Returns the number of newly inserted accounts (0 if already populated).
    """
    cur = conn.cursor()
    logger.info("Phase 1: Populating account_dictionary from existing index...")
    cur.execute("""
        INSERT INTO account_dictionary (account_id)
        SELECT DISTINCT account_id FROM account_block_index
        ON CONFLICT (account_id) DO NOTHING
    """)
    conn.commit()
    count = cur.rowcount
    cur.close()
    logger.info("Inserted %d accounts into dictionary.", count)
    return count


def count_dictionary(conn) -> int:
    """Return the current number of rows in account_dictionary."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM account_dictionary")
    n = cur.fetchone()[0]
    cur.close()
    return n


# ---------------------------------------------------------------------------
# Phase 2: Copy rows in batches
# ---------------------------------------------------------------------------


def migrate_batch(conn, start_block: int, end_block: int) -> int:
    """Copy one block range from old table to v2 via dictionary join + segment calculation.

    Uses PostgreSQL integer division to floor block_height to segment_start:
      ((block_height / 1000) * 1000)::integer

    The DISTINCT clause collapses multiple rows in the same segment to one row
    per (account_int, segment_start) pair — this is where the space savings come from.
    ON CONFLICT DO NOTHING handles re-runs and partial migrations safely.

    Returns the number of rows inserted (0 if already present).
    """
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO account_block_index_v2 (account_int, segment_start)
        SELECT DISTINCT d.id, ((abi.block_height / 1000) * 1000)::integer
        FROM account_block_index abi
        JOIN account_dictionary d ON d.account_id = abi.account_id
        WHERE abi.block_height >= %s AND abi.block_height < %s
        ON CONFLICT DO NOTHING
    """, (start_block, end_block))
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    return inserted


# ---------------------------------------------------------------------------
# Dry-run estimation
# ---------------------------------------------------------------------------


def estimate_v2_rows(conn) -> int:
    """Estimate the number of rows that would be in v2 after migration.

    Counts DISTINCT (account_id, segment_start) pairs from the old table.
    This is an exact count but can be slow on large tables.
    """
    logger.info("Estimating v2 row count (this may take a few minutes on large tables)...")
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT (account_id, (block_height / 1000) * 1000))
        FROM account_block_index
    """)
    n = cur.fetchone()[0]
    cur.close()
    return n


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate account_block_index to v2 format.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run Phase 1 only and estimate v2 row count without inserting v2 rows.",
    )
    parser.add_argument(
        "--start-block",
        type=int,
        default=None,
        help="Resume Phase 2 from this block height (skips earlier batches).",
    )
    args = parser.parse_args()

    import psycopg2  # imported here so the script has no hard dep for Phase 1 check

    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://neartax:neartax@127.0.0.1:5433/neartax",
    )
    logger.info("Connecting to database...")
    conn = psycopg2.connect(database_url)

    script_start = time.monotonic()

    # ------------------------------------------------------------------
    # Phase 1: Dictionary
    # ------------------------------------------------------------------
    populate_dictionary(conn)
    dict_count = count_dictionary(conn)
    logger.info("account_dictionary now contains %d accounts.", dict_count)

    if args.dry_run:
        estimated = estimate_v2_rows(conn)
        logger.info(
            "DRY RUN: estimated v2 rows after migration: %d (from %d dictionary accounts).",
            estimated,
            dict_count,
        )
        logger.info("DRY RUN complete. No v2 rows were inserted.")
        conn.close()
        return

    # ------------------------------------------------------------------
    # Phase 2: Batch migration
    # ------------------------------------------------------------------

    # Determine max block from indexer state
    cur = conn.cursor()
    cur.execute("SELECT last_processed_block FROM account_indexer_state WHERE id = 1")
    row = cur.fetchone()
    cur.close()

    if not row:
        logger.error("account_indexer_state has no row with id=1. Has the indexer run?")
        conn.close()
        sys.exit(1)

    max_block = row[0]
    logger.info("account_indexer_state: last_processed_block = %d", max_block)

    start = args.start_block if args.start_block is not None else GENESIS_BLOCK
    if start != GENESIS_BLOCK:
        logger.info("Resuming from --start-block %d", start)

    total_inserted = 0
    batch_count = 0

    logger.info("Phase 2: Migrating blocks %d -> %d in batches of %d...", start, max_block, BATCH_SIZE)

    while start < max_block:
        end = min(start + BATCH_SIZE, max_block + 1)
        t0 = time.monotonic()
        inserted = migrate_batch(conn, start, end)
        elapsed = time.monotonic() - t0
        total_inserted += inserted
        batch_count += 1

        pct = (end - GENESIS_BLOCK) / max(1, max_block - GENESIS_BLOCK) * 100
        logger.info(
            "Batch %d-%d: %d rows (%.1fs) | Total: %d | %.1f%%",
            start, end, inserted, elapsed, total_inserted, pct,
        )
        start = end

    logger.info(
        "Migration complete. %d batches processed. Total rows inserted in v2: %d",
        batch_count,
        total_inserted,
    )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM account_dictionary")
    dict_final = cur.fetchone()[0]
    cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'account_block_index_v2'")
    v2_estimate = cur.fetchone()[0]
    cur.close()

    logger.info(
        "Verification: %d dictionary entries, ~%d v2 rows (pg_class estimate)",
        dict_final,
        v2_estimate,
    )

    total_elapsed = time.monotonic() - script_start
    logger.info("Total elapsed time: %.1f seconds (%.1f minutes)", total_elapsed, total_elapsed / 60)

    conn.close()


if __name__ == "__main__":
    main()
