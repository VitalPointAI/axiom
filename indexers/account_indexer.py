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
import os
import signal
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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
# Each .tgz archive contains 10 blocks. With API key authentication,
# there is no rate limit — 16 workers achieves ~2300 blocks/sec.
ARCHIVE_WORKERS = 16
ARCHIVE_BLOCKS_PER_FILE = 10
# Flush to DB every N archives (N * 10 blocks)
FLUSH_EVERY_ARCHIVES = 100   # = 1000 blocks per flush
INSERT_BATCH_SIZE = 10000
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

        # HTTP session for archive fetching (separate from NeardataClient)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=ARCHIVE_WORKERS + 4,
            pool_maxsize=ARCHIVE_WORKERS + 4,
        )
        self.session.mount("https://", adapter)
        self.session.headers["User-Agent"] = "Axiom/1.0 AccountIndexer"

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

    def _get_genesis_backfill_done(self) -> bool:
        """Check if genesis (sparse) backfill has been completed."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            # Use a simple convention: if last_processed_block > 30M, pass 1 is done.
            # But we also need to know if pass 2 (genesis) is done.
            # Store it as a negative sentinel: -1 means genesis done.
            cur.execute(
                "SELECT last_processed_block FROM account_indexer_state WHERE id = 2"
            )
            row = cur.fetchone()
            cur.close()
            return row is not None and row[0] == -1
        except Exception:
            return False
        finally:
            self.pool.putconn(conn)

    def _set_genesis_backfill_done(self) -> None:
        """Mark genesis backfill as complete."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO account_indexer_state (id, last_processed_block) VALUES (2, -1) "
                "ON CONFLICT (id) DO UPDATE SET last_processed_block = -1, updated_at = NOW()"
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def reset(self) -> None:
        """Reset the index — truncate and restart from genesis."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("TRUNCATE account_block_index")
            cur.execute("UPDATE account_indexer_state SET last_processed_block = 0, updated_at = NOW() WHERE id = 1")
            cur.execute("DELETE FROM account_indexer_state WHERE id = 2")
            conn.commit()
            cur.close()
            logger.info("Account index reset. Will rebuild from dense blocks first, then genesis.")
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

            for reo in shard.get("receipt_execution_outcomes", []):
                receipt = reo.get("receipt", {})
                predecessor = receipt.get("predecessor_id")
                receiver = receipt.get("receiver_id")
                if predecessor:
                    p = predecessor.lower()
                    if cls._should_index(p):
                        accounts.add(p)
                if receiver:
                    r = receiver.lower()
                    if cls._should_index(r):
                        accounts.add(r)

        return accounts

    # ------------------------------------------------------------------
    # Archive fetching
    # ------------------------------------------------------------------

    def fetch_archive(self, archive_block: int) -> list[tuple[dict, int]]:
        """Fetch a .tgz archive and return list of (block_data, block_height).

        Each archive contains up to 10 blocks. Missing blocks within the
        range are simply absent from the archive (not an error).
        """
        url = _archive_url(archive_block)
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    tar = tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz")
                    blocks = []
                    for member in tar.getmembers():
                        f = tar.extractfile(member)
                        if f:
                            data = json.loads(f.read())
                            height = data.get("block", {}).get("header", {}).get("height", 0)
                            blocks.append((data, height))
                    return blocks
                if resp.status_code == 404:
                    return []  # Archive doesn't exist (sparse range)
                if resp.status_code == 429:
                    time.sleep(min(5 * (attempt + 1), 15))
                    continue
                return []
            except Exception as exc:
                if attempt < 2:
                    time.sleep(2)
                    continue
                logger.warning("Archive fetch failed for block %d: %s", archive_block, exc)
                return []
        return []

    # ------------------------------------------------------------------
    # Batch insert
    # ------------------------------------------------------------------

    def insert_account_blocks(self, pairs: list[tuple[str, int]]) -> int:
        """Batch insert (account_id, block_height) pairs. Returns count inserted."""
        if not pairs:
            return 0

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            accounts = [p[0] for p in pairs]
            heights = [p[1] for p in pairs]
            cur.execute(
                """
                INSERT INTO account_block_index (account_id, block_height)
                SELECT unnest(%s::text[]), unnest(%s::bigint[])
                ON CONFLICT DO NOTHING
                """,
                (accounts, heights),
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
        DENSE_START = 30_000_000

        if remaining > ARCHIVE_BLOCKS_PER_FILE * 10:
            if start_block < DENSE_START:
                # Two-pass strategy: dense blocks first, sparse genesis after.
                # This gets 90%+ of useful account data indexed in ~30 hours
                # instead of spending days on sparse early blocks first.

                # Check if we already completed pass 1 (genesis_backfill_done flag)
                genesis_done = self._get_genesis_backfill_done()

                if not genesis_done:
                    # Pass 1: Dense blocks (30M → tip) — fast, ~1500 blocks/sec
                    dense_remaining = final_block - DENSE_START
                    logger.info(
                        "Pass 1 — Dense blocks: %d → %d (%d blocks, ~%.1f hours at ~1500 blocks/sec)",
                        DENSE_START, final_block, dense_remaining, dense_remaining / 1500 / 3600,
                    )
                    self._backfill(DENSE_START, final_block)

                    # Pass 2: Sparse genesis (9.8M → 30M) — slow, ~30 blocks/sec
                    sparse_remaining = DENSE_START - GENESIS_BLOCK
                    logger.info(
                        "Pass 2 — Sparse genesis: %d → %d (%d blocks, ~%.1f hours at ~30 blocks/sec)",
                        GENESIS_BLOCK, DENSE_START - 1, sparse_remaining, sparse_remaining / 30 / 3600,
                    )
                    self._backfill(GENESIS_BLOCK, DENSE_START - 1)
                    self._set_genesis_backfill_done()
                    # Update cursor to chain tip so live mode works
                    self.set_last_processed_block(final_block)
                else:
                    # Both passes done previously — just catch up from cursor
                    logger.info(
                        "Catching up: %d → %d (%d blocks)",
                        start_block, final_block, remaining,
                    )
                    self._backfill(start_block, final_block)
            else:
                eta_hours = remaining / 1500 / 3600
                logger.info(
                    "Backfill mode: %d → %d (%d blocks, ~%.1f hours at ~1500 blocks/sec)",
                    start_block, final_block, remaining, eta_hours,
                )
                self._backfill(start_block, final_block)
        else:
            logger.info("Index is near tip (block %d, tip %d). Entering live mode.",
                        last_processed, final_block)

        self._live_follow()

    def _backfill(self, start_block: int, target_block: int) -> None:
        """Process historical blocks using parallel archive .tgz fetching.

        Each archive contains 10 blocks. With 8 parallel workers, we process
        ~80 blocks per round-trip, achieving ~1500 blocks/sec.

        Archives are fetched in order. The cursor only advances to the highest
        contiguous block that was successfully processed — no gaps possible.
        """
        # Align start to archive boundary
        current_archive = _align_to_archive(start_block)
        target_archive = _align_to_archive(target_block)
        total = target_block - start_block

        log_time = time.monotonic()
        log_blocks = 0
        pair_buffer: list[tuple[str, int]] = []
        archives_since_flush = 0
        max_block_seen = start_block - 1

        while current_archive <= target_archive and self.running:
            # Build batch of archive heights to fetch in parallel
            batch_archives = []
            for i in range(ARCHIVE_WORKERS * 4):  # Queue up 4x workers worth
                a = current_archive + i * ARCHIVE_BLOCKS_PER_FILE
                if a > target_archive:
                    break
                batch_archives.append(a)

            if not batch_archives:
                break

            # Fetch archives in parallel
            succeeded: dict[int, list[tuple[dict, int]]] = {}
            failed: set[int] = set()

            with ThreadPoolExecutor(max_workers=ARCHIVE_WORKERS) as executor:
                futures = {
                    executor.submit(self.fetch_archive, a): a
                    for a in batch_archives
                }
                for future in as_completed(futures):
                    archive_height = futures[future]
                    try:
                        blocks = future.result()
                        succeeded[archive_height] = blocks
                    except Exception:
                        failed.add(archive_height)

            # Process results IN ORDER to maintain gap-safe cursor
            safe_archive = current_archive - ARCHIVE_BLOCKS_PER_FILE
            for a in batch_archives:
                if a in failed:
                    logger.warning("Archive %d failed — stopping at safe point %d", a, safe_archive)
                    break

                blocks = succeeded.get(a, [])
                for block_data, height in blocks:
                    if height >= start_block:
                        accounts = self.extract_accounts_from_block(block_data)
                        pair_buffer.extend((acct, height) for acct in accounts)
                        max_block_seen = max(max_block_seen, height)

                safe_archive = a
                archives_since_flush += 1
                log_blocks += ARCHIVE_BLOCKS_PER_FILE

                # Flush buffer periodically
                if archives_since_flush >= FLUSH_EVERY_ARCHIVES:
                    if pair_buffer:
                        for i in range(0, len(pair_buffer), INSERT_BATCH_SIZE):
                            chunk = pair_buffer[i:i + INSERT_BATCH_SIZE]
                            self.insert_account_blocks(chunk)
                        pair_buffer = []
                    cursor_block = safe_archive + ARCHIVE_BLOCKS_PER_FILE - 1
                    self.set_last_processed_block(cursor_block)
                    archives_since_flush = 0

            # Advance to next batch
            current_archive = safe_archive + ARCHIVE_BLOCKS_PER_FILE

            # Log progress
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

        # Final flush
        if pair_buffer:
            for i in range(0, len(pair_buffer), INSERT_BATCH_SIZE):
                chunk = pair_buffer[i:i + INSERT_BATCH_SIZE]
                self.insert_account_blocks(chunk)
        if max_block_seen >= start_block:
            self.set_last_processed_block(max_block_seen)

        if self.running:
            logger.info("Backfill complete at block %d.", max_block_seen)

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
            cur.execute("SELECT COUNT(*) FROM account_block_index")
            total_pairs = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT account_id) FROM account_block_index")
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
