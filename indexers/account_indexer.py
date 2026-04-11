"""
Account Block Index Builder — sidecar service for fast wallet lookups.

Walks every NEAR block via neardata.xyz archive .tgz files (10 blocks per
request), extracts all account IDs that appear as signer, receiver, or
predecessor, and stores the mapping (account_id, block_height) in PostgreSQL.

Once built, NearFetcher can query this index to find exactly which blocks
contain transactions for a wallet — turning a multi-hour full scan into
a sub-second SQL query.

Usage:
    python -m indexers.account_indexer                # run forever (backfill + live)
    python -m indexers.account_indexer --status        # show progress
    python -m indexers.account_indexer --reset          # reset and rebuild from scratch
"""

import argparse
import io
import json
import logging
import multiprocessing
import os
import signal
import sys
import tarfile
import time

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from indexers.db import get_pool, close_pool
from indexers.neardata_client import NeardataClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Archive fetching parameters
# Each .tgz archive contains 10 blocks. Using multiprocessing to bypass
# Python's GIL — each process does its own HTTP + decompress + JSON parse.
# 8 processes achieves ~650 blocks/sec (vs 30/sec with threading).
ARCHIVE_PROCESSES = 8
ARCHIVE_BLOCKS_PER_FILE = 10
# Flush to DB every N blocks
FLUSH_EVERY_BLOCKS = 5000
INSERT_BATCH_SIZE = 50000
LIVE_POLL_INTERVAL = 1.0

# NEAR mainnet genesis block
GENESIS_BLOCK = 9_820_210

# Archive node routing (from fastnear-neardata-fetcher source)
# Blocks < 122M  → a0.mainnet.neardata.xyz
# Blocks 122M-142M → a1.mainnet.neardata.xyz
# Blocks >= 142M → a2.mainnet.neardata.xyz
MAINNET_ARCHIVE_BOUNDARIES = [122_000_000, 142_000_000]


# API key for authenticated access (removes rate limit)
FASTNEAR_API_KEY = os.environ.get("FASTNEAR_API_KEY", "")


def _fetch_and_extract(archive_block: int) -> list[tuple[str, int]]:
    """Fetch a .tgz archive, parse blocks, extract account pairs.

    Module-level function so it can be used with multiprocessing.Pool
    (instance methods can't be pickled). Each worker process gets its
    own HTTP session, JSON parser, and GIL — true parallelism.
    """
    url = _archive_url(archive_block)
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                tar = tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz")
                pairs: list[tuple[str, int]] = []
                for member in tar.getmembers():
                    f = tar.extractfile(member)
                    if f:
                        data = json.loads(f.read())
                        height = data.get("block", {}).get("header", {}).get("height", 0)
                        for shard in data.get("shards", []):
                            chunk = shard.get("chunk")
                            if chunk:
                                for tx in chunk.get("transactions", []):
                                    td = tx.get("transaction", {})
                                    si = td.get("signer_id", "")
                                    ri = td.get("receiver_id", "")
                                    if si and si != "system":
                                        pairs.append((si.lower(), height))
                                    if ri and ri != "system":
                                        pairs.append((ri.lower(), height))
                            # Receipt execution outcomes: only index receiver_id
                            # (where actions land). predecessor_id is typically a
                            # contract and inflates the index without helping lookups.
                            for reo in shard.get("receipt_execution_outcomes", []):
                                receipt = reo.get("receipt", {})
                                ri = receipt.get("receiver_id", "")
                                if ri and ri != "system":
                                    pairs.append((ri.lower(), height))
                return pairs
            if resp.status_code == 404:
                return []
            if resp.status_code == 429:
                time.sleep(min(5 * (attempt + 1), 15))
                continue
            return []
        except Exception:
            if attempt < 2:
                time.sleep(2)
                continue
            return []
    return []


def _archive_url(block_height: int) -> str:
    """Build the archive .tgz URL for a given block height.

    Block height must be aligned to ARCHIVE_BLOCKS_PER_FILE (10).
    Uses ?apiKey= param for authentication (survives redirects between
    archive nodes, unlike Authorization headers).
    """
    padded = f"{block_height:012d}"
    suffix = f"{padded[:6]}/{padded[6:9]}/{padded}.tgz"

    # Route to the correct archive node
    node_idx = len(MAINNET_ARCHIVE_BOUNDARIES)
    for i, boundary in enumerate(MAINNET_ARCHIVE_BOUNDARIES):
        if block_height < boundary:
            node_idx = i
            break

    url = f"https://a{node_idx}.mainnet.neardata.xyz/raw/{suffix}"
    if FASTNEAR_API_KEY:
        url += f"?apiKey={FASTNEAR_API_KEY}"
    return url


def _align_to_archive(block_height: int) -> int:
    """Round down to nearest archive boundary (multiple of 10)."""
    return (block_height // ARCHIVE_BLOCKS_PER_FILE) * ARCHIVE_BLOCKS_PER_FILE


class AccountIndexer:
    """Builds and maintains the account_block_index table."""

    def __init__(self):
        self.pool = get_pool(min_conn=2, max_conn=5)
        self.client = NeardataClient()
        self.running = True
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received. Finishing current batch...")
        self.running = False

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def get_last_processed_block(self) -> int:
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT last_processed_block FROM account_indexer_state WHERE id = 1")
            row = cur.fetchone()
            cur.close()
            return row[0] if row else 0
        finally:
            self.pool.putconn(conn)

    def set_last_processed_block(self, block_height: int) -> None:
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE account_indexer_state SET last_processed_block = %s, updated_at = NOW() WHERE id = 1",
                (block_height,),
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def reset(self) -> None:
        """Reset the index — truncate v2 tables and restart from genesis.

        Truncates both account_block_index_v2 and account_dictionary since
        they form a single logical dataset. The old account_block_index table
        is left untouched (coexists during transition).
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("TRUNCATE account_block_index_v2")
            cur.execute("TRUNCATE account_dictionary")
            cur.execute("UPDATE account_indexer_state SET last_processed_block = 0, updated_at = NOW() WHERE id = 1")
            conn.commit()
            cur.close()
            logger.info("Account index reset (v2 + dictionary truncated). Will rebuild from genesis.")
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Block parsing — extract all account IDs from a block
    # ------------------------------------------------------------------

    @staticmethod
    def _should_index(account_id: str) -> bool:
        """Only skips 'system' — gas refund receipts. Everything else indexed."""
        if not account_id:
            return False
        return account_id != "system"

    @classmethod
    def extract_accounts_from_block(cls, block: dict) -> set[str]:
        """Extract all unique account IDs from a neardata block."""
        accounts: set[str] = set()
        if not block:
            return accounts

        for shard in block.get("shards", []):
            chunk = shard.get("chunk")
            if chunk:
                for tx in chunk.get("transactions", []):
                    tx_data = tx.get("transaction", {})
                    signer = tx_data.get("signer_id")
                    receiver = tx_data.get("receiver_id")
                    if signer:
                        s = signer.lower()
                        if cls._should_index(s):
                            accounts.add(s)
                    if receiver:
                        r = receiver.lower()
                        if cls._should_index(r):
                            accounts.add(r)

            # Receipt execution outcomes: only index receiver_id
            for reo in shard.get("receipt_execution_outcomes", []):
                receipt = reo.get("receipt", {})
                receiver = receipt.get("receiver_id")
                if receiver:
                    r = receiver.lower()
                    if cls._should_index(r):
                        accounts.add(r)

        return accounts

    # ------------------------------------------------------------------
    # Archive fetching
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Batch insert
    # ------------------------------------------------------------------

    def insert_account_blocks(self, pairs: list[tuple[str, int]]) -> int:
        """Batch insert (account_id, block_height) pairs into account_block_index_v2.

        Resolves account_id strings to integer IDs via account_dictionary,
        converts block_height to segment_start (floor to nearest 1000), then
        inserts (account_int, segment_start) into account_block_index_v2.

        Uses ON CONFLICT DO NOTHING to skip duplicates.
        """
        if not pairs:
            return 0

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Collect unique account strings
            unique_accounts = list({p[0] for p in pairs})

            # Ensure all accounts exist in dictionary (batch upsert, ignore existing)
            cur.execute(
                """
                INSERT INTO account_dictionary (account_id)
                SELECT unnest(%s::text[])
                ON CONFLICT (account_id) DO NOTHING
                """,
                (unique_accounts,),
            )

            # Fetch integer IDs for all accounts in this batch
            cur.execute(
                "SELECT id, account_id FROM account_dictionary WHERE account_id = ANY(%s::text[])",
                (unique_accounts,),
            )
            id_map = {row[1]: row[0] for row in cur.fetchall()}

            # Build (account_int, segment_start) integer pairs
            account_ints = []
            segment_starts = []
            for account_id, block_height in pairs:
                if account_id in id_map:
                    account_ints.append(id_map[account_id])
                    segment_starts.append((block_height // 1000) * 1000)

            if not account_ints:
                conn.commit()
                cur.close()
                return 0

            # Insert into v2 table using integer columns
            cur.execute(
                """
                INSERT INTO account_block_index_v2 (account_int, segment_start)
                SELECT unnest(%s::integer[]), unnest(%s::integer[])
                ON CONFLICT DO NOTHING
                """,
                (account_ints, segment_starts),
            )
            inserted = cur.rowcount
            conn.commit()
            cur.close()
            return inserted
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def _rebuild_indexes(self) -> None:
        """Ensure PK and indexes exist on account_block_index_v2 after bulk loading.

        No dedup needed — ON CONFLICT DO NOTHING prevents duplicates during insert.
        Just ensures the primary key and lookup index are in place on the v2 table.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Check if v2 PK exists already
            cur.execute("""
                SELECT 1 FROM pg_constraint
                WHERE conname = 'account_block_index_v2_pkey'
            """)
            if not cur.fetchone():
                logger.info("Adding primary key constraint on account_block_index_v2...")
                cur.execute("""
                    ALTER TABLE account_block_index_v2
                    ADD CONSTRAINT account_block_index_v2_pkey
                    PRIMARY KEY (account_int, segment_start)
                """)
                conn.commit()
            else:
                logger.info("Primary key already exists on account_block_index_v2.")

            # Lookup index on v2
            logger.info("Ensuring lookup index exists on account_block_index_v2...")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_abiv2_account_segment
                ON account_block_index_v2 (account_int, segment_start)
            """)
            conn.commit()
            cur.close()

            logger.info("Index rebuild complete.")
        except Exception as exc:
            conn.rollback()
            logger.error("Index rebuild failed: %s", exc)
            raise
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Main loop: backfill historical blocks, then follow the tip."""
        last_processed = self.get_last_processed_block()
        start_block = max(last_processed + 1, GENESIS_BLOCK)

        # Retry getting chain tip
        final_block = None
        for attempt in range(10):
            try:
                final_block = self.client.get_final_block_height()
                break
            except Exception as exc:
                wait = min(10 * (attempt + 1), 60)
                logger.warning("Failed to get chain tip (attempt %d): %s. Retrying in %ds.",
                               attempt + 1, exc, wait)
                time.sleep(wait)
        if final_block is None:
            raise RuntimeError("Cannot reach neardata.xyz after 10 attempts. Check network.")

        remaining = final_block - start_block

        if remaining > ARCHIVE_BLOCKS_PER_FILE * 10:
            eta_hours = remaining / 2000 / 3600  # ~2000 blocks/sec with API key
            logger.info(
                "Backfill: %d → %d (%d blocks, ~%.1f hours at ~2000 blocks/sec)",
                start_block, final_block, remaining, eta_hours,
            )
            self._backfill(start_block, final_block)
        else:
            logger.info("Index is near tip (block %d, tip %d). Entering live mode.",
                        last_processed, final_block)

        self._live_follow()

    def _backfill(self, start_block: int, target_block: int) -> None:
        """Process historical blocks using Rust binary + COPY bulk load.

        The Rust binary (account-indexer-rs) handles fetch + decompress +
        parse + extract at ~3000 blocks/sec. It outputs TSV to stdout.
        We pipe that into PostgreSQL via COPY FROM STDIN for maximum
        insert throughput.

        Falls back to Python multiprocessing if the Rust binary isn't found.
        """
        import shutil

        rust_binary = shutil.which("account-indexer-rs")
        if not rust_binary:
            # Check common locations
            for path in ["/usr/local/bin/account-indexer-rs", "/app/account-indexer-rs",
                         "/home/deploy/account-indexer-rs"]:
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    rust_binary = path
                    break

        if rust_binary:
            self._backfill_rust(rust_binary, start_block, target_block)
        else:
            logger.warning("Rust binary not found — falling back to Python multiprocessing (slow)")
            self._backfill_python(start_block, target_block)

    def _backfill_rust(self, binary: str, start_block: int, target_block: int) -> None:
        """Run Rust indexer in chunks, COPY each chunk, update progress.

        Splits the full range into chunks of 1M blocks. For each chunk:
        1. Rust binary fetches archives and writes TSV to stdout
        2. Python COPY's the TSV into PostgreSQL
        3. Progress cursor is updated so the admin dashboard shows real progress

        This means progress is visible every ~6 minutes (1M blocks at ~2700/sec)
        and crash recovery only loses one chunk.
        """
        import subprocess
        import threading

        api_key = os.environ.get("FASTNEAR_API_KEY", "")
        database_url = os.environ.get("DATABASE_URL", "")
        chunk_size = 1_000_000  # 1M blocks per chunk

        current = start_block
        while current < target_block and self.running:
            chunk_end = min(current + chunk_size, target_block)

            logger.info("Rust chunk: %d → %d (%d blocks)",
                        current, chunk_end, chunk_end - current)

            cmd = [
                binary,
                "--start", str(current),
                "--end", str(chunk_end),
                "--workers", "16",
                "--progress-interval", "1000",
            ]
            if api_key:
                cmd.extend(["--api-key", api_key])
            if database_url:
                cmd.extend(["--database-url", database_url])

            # Write to temp file, then COPY from file (avoids pipe backpressure)
            import tempfile
            tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False, dir='/tmp')
            tmp_path = tmp.name
            tmp.close()

            proc = subprocess.Popen(
                cmd, stdout=open(tmp_path, 'w'), stderr=subprocess.PIPE,
                bufsize=1024 * 1024,
            )

            # Stream Rust stderr to logger
            def _log_stderr(p=proc):
                for line in p.stderr:
                    line = line.decode().strip()
                    if line:
                        logger.info("Rust: %s", line)

            stderr_thread = threading.Thread(target=_log_stderr, daemon=True)
            stderr_thread.start()

            proc.wait()
            stderr_thread.join(timeout=5)

            if proc.returncode != 0:
                logger.error("Rust indexer exited with code %d at block %d",
                             proc.returncode, current)
                os.unlink(tmp_path)
                break

            # Bulk COPY from the temp file (no pipe backpressure)
            file_size = os.path.getsize(tmp_path)
            logger.info("Loading %s into PostgreSQL (%d MB)...",
                        tmp_path, file_size // (1024 * 1024))

            # COPY into v2 staging table (integer columns), then INSERT ... ON CONFLICT DO NOTHING.
            # (COPY doesn't support ON CONFLICT directly; staging table pattern handles duplicates.)
            conn = self.pool.getconn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TEMP TABLE IF NOT EXISTS abi_staging_v2
                    (account_int INTEGER, segment_start INTEGER)
                    ON COMMIT DELETE ROWS
                """)
                with open(tmp_path, 'r') as f:
                    cur.copy_expert(
                        "COPY abi_staging_v2 (account_int, segment_start) FROM STDIN",
                        f,
                    )
                cur.execute("""
                    INSERT INTO account_block_index_v2 (account_int, segment_start)
                    SELECT DISTINCT account_int, segment_start FROM abi_staging_v2
                    ON CONFLICT DO NOTHING
                """)
                inserted = cur.rowcount
                conn.commit()
                cur.close()
                logger.info("Inserted %d rows into account_block_index_v2 (deduped via ON CONFLICT).", inserted)
            except Exception as exc:
                conn.rollback()
                logger.error("COPY failed at block %d: %s", current, exc)
                raise
            finally:
                self.pool.putconn(conn)
                os.unlink(tmp_path)

            # Update cursor — visible in admin dashboard
            self.set_last_processed_block(chunk_end)
            logger.info("Chunk complete: block %d → %d. Progress saved.", current, chunk_end)

            current = chunk_end + 1

        if self.running and current >= target_block:
            logger.info("Backfill complete at block %d. Rebuilding indexes...", target_block)
            self._rebuild_indexes()

    def _backfill_python(self, start_block: int, target_block: int) -> None:
        """Fallback: Python multiprocessing backfill (slower, ~30 blocks/sec)."""
        current_archive = _align_to_archive(start_block)
        target_archive = _align_to_archive(target_block)
        total = target_block - start_block

        archive_heights = range(current_archive, target_archive + 1, ARCHIVE_BLOCKS_PER_FILE)

        log_time = time.monotonic()
        log_blocks = 0
        pair_buffer: list[tuple[str, int]] = []
        max_block_seen = start_block - 1
        blocks_since_flush = 0

        pool = multiprocessing.Pool(processes=ARCHIVE_PROCESSES)

        try:
            for pairs in pool.imap_unordered(_fetch_and_extract, archive_heights, chunksize=16):
                if not self.running:
                    break

                if pairs:
                    pair_buffer.extend(pairs)

                log_blocks += ARCHIVE_BLOCKS_PER_FILE
                blocks_since_flush += ARCHIVE_BLOCKS_PER_FILE

                if blocks_since_flush >= FLUSH_EVERY_BLOCKS:
                    if pair_buffer:
                        max_block_seen = max(max_block_seen, max(h for _, h in pair_buffer))
                        for i in range(0, len(pair_buffer), INSERT_BATCH_SIZE):
                            chunk = pair_buffer[i:i + INSERT_BATCH_SIZE]
                            self.insert_account_blocks(chunk)
                        pair_buffer = []
                    self.set_last_processed_block(max_block_seen)
                    blocks_since_flush = 0

                elapsed = time.monotonic() - log_time
                if elapsed > 15:
                    rate = log_blocks / elapsed if elapsed > 0 else 0
                    done = max_block_seen - start_block
                    pct = (done / total) * 100 if total > 0 else 100
                    eta_hours = ((target_block - max_block_seen) / rate / 3600) if rate > 0 else 0
                    logger.info(
                        "Backfill: %.1f%% — block %d/%d — %.0f blocks/sec — "
                        "%d pairs buffered — ETA %.1fh",
                        pct, max_block_seen, target_block, rate, len(pair_buffer), eta_hours,
                    )
                    log_time = time.monotonic()
                    log_blocks = 0

        finally:
            pool.terminate()
            pool.join()

        if pair_buffer:
            for i in range(0, len(pair_buffer), INSERT_BATCH_SIZE):
                chunk = pair_buffer[i:i + INSERT_BATCH_SIZE]
                self.insert_account_blocks(chunk)
        if max_block_seen >= start_block:
            self.set_last_processed_block(max_block_seen)

        if self.running:
            logger.info("Backfill complete at block %d. Rebuilding indexes...", max_block_seen)
            self._rebuild_indexes()

    def _live_follow(self) -> None:
        """Follow the chain tip, processing new blocks as they appear."""
        logger.info("Live mode: following chain tip.")

        while self.running:
            last_processed = self.get_last_processed_block()
            try:
                final_block = self.client.get_final_block_height()
            except Exception as exc:
                logger.warning("Failed to get chain tip: %s", exc)
                time.sleep(5)
                continue

            if final_block <= last_processed:
                time.sleep(LIVE_POLL_INTERVAL)
                continue

            gap = final_block - last_processed
            if gap > 100:
                # Fell behind — use archive mode to catch up
                logger.info("Catching up: %d blocks behind tip.", gap)
                self._backfill(last_processed + 1, final_block)
            else:
                # Near tip — fetch individual blocks (archives may not exist yet)
                for height in range(last_processed + 1, final_block + 1):
                    if not self.running:
                        break
                    try:
                        block = self.client.fetch_block(height)
                        if block:
                            accounts = self.extract_accounts_from_block(block)
                            pairs = [(acct, height) for acct in accounts]
                            if pairs:
                                self.insert_account_blocks(pairs)
                        self.set_last_processed_block(height)
                    except Exception as exc:
                        logger.warning("Error processing block %d: %s", height, exc)
                        time.sleep(1)

    # ------------------------------------------------------------------
    # Status / stats
    # ------------------------------------------------------------------

    def print_status(self) -> None:
        """Print current indexer status."""
        last_processed = self.get_last_processed_block()
        try:
            final_block = self.client.get_final_block_height()
        except Exception:
            final_block = None

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            # Use reltuples for fast approximate count on large v2 table
            cur.execute(
                "SELECT reltuples::bigint FROM pg_class WHERE relname = 'account_block_index_v2'"
            )
            row = cur.fetchone()
            total_pairs = row[0] if row else 0
            # Unique accounts comes from dictionary table (authoritative count)
            cur.execute("SELECT COUNT(*) FROM account_dictionary")
            unique_accounts = cur.fetchone()[0]
            cur.execute("SELECT updated_at FROM account_indexer_state WHERE id = 1")
            updated_at = cur.fetchone()[0]
            cur.close()
        finally:
            self.pool.putconn(conn)

        print("\n  Account Block Index Status")
        print(f"  {'─' * 40}")
        print(f"  Last processed block:  {last_processed:,}")
        if final_block:
            remaining = final_block - last_processed
            pct = (last_processed - GENESIS_BLOCK) / (final_block - GENESIS_BLOCK) * 100
            print(f"  Chain tip:             {final_block:,}")
            print(f"  Blocks remaining:      {remaining:,}")
            print(f"  Progress:              {pct:.1f}%")
        print(f"  Total index entries:   {total_pairs:,}")
        print(f"  Unique accounts:       {unique_accounts:,}")
        print(f"  Last updated:          {updated_at}")
        print()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Account Block Index Builder — maps NEAR accounts to block heights"
    )
    parser.add_argument("--status", action="store_true", help="Show index status and exit")
    parser.add_argument("--reset", action="store_true", help="Reset index and rebuild from scratch")
    args = parser.parse_args()

    indexer = AccountIndexer()

    if args.status:
        indexer.print_status()
    elif args.reset:
        indexer.reset()
    else:
        indexer.run()

    close_pool()
