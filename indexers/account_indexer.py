"""
Account Block Index Builder — sidecar service for fast wallet lookups.

Walks every NEAR block via neardata.xyz, extracts all account IDs that
appear as signer, receiver, or predecessor, and stores the mapping
(account_id, block_height) in PostgreSQL.

Once built, NearFetcher can query this index to find exactly which blocks
contain transactions for a wallet — turning a multi-hour full scan into
a sub-second SQL query.

Usage:
    python -m indexers.account_indexer                # run forever (backfill + live)
    python -m indexers.account_indexer --status        # show progress
    python -m indexers.account_indexer --reset          # reset and rebuild from scratch
"""

import argparse
import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# Tuning parameters
BACKFILL_BATCH_SIZE = 5000   # Blocks per batch during backfill
BACKFILL_WORKERS = 100       # Concurrent HTTP requests during backfill
LIVE_POLL_INTERVAL = 1.0     # Seconds between checks for new blocks
INSERT_BATCH_SIZE = 5000     # Account-block pairs to insert per DB write

# NEAR mainnet genesis
GENESIS_BLOCK = 9_820_210


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
        """Reset the index — truncate and restart from genesis."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("TRUNCATE account_block_index")
            cur.execute("UPDATE account_indexer_state SET last_processed_block = 0, updated_at = NOW() WHERE id = 1")
            conn.commit()
            cur.close()
            logger.info("Account index reset. Will rebuild from genesis.")
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Block parsing — extract all account IDs from a block
    # ------------------------------------------------------------------

    # High-volume system/contract accounts that appear in nearly every block
    # but will never be user wallets. Skipping them cuts index size ~60-70%.
    _SKIP_ACCOUNTS = frozenset({
        "system",
        "relay.aurora",
        "aurora",
        "wrap.near",
        "token.sweat",
        "tge-lockup.sweat",
        "oracle.sweat",
    })

    @classmethod
    def _should_index(cls, account_id: str) -> bool:
        """Return True if this account should be indexed.

        Filters out system accounts, single-char accounts, and high-volume
        contract accounts that will never be user wallets. This reduces
        index size by ~60-70% without losing any user-relevant data.
        """
        if not account_id or len(account_id) <= 2:
            return False
        if account_id in cls._SKIP_ACCOUNTS:
            return False
        return True

    @classmethod
    def extract_accounts_from_block(cls, block: dict) -> set[str]:
        """Extract all unique account IDs from a neardata block.

        Looks at:
          - Transaction signers and receivers
          - Receipt predecessors and receivers

        Filters out system and high-volume contract accounts to keep
        the index size manageable (~20-80 GB instead of 200+ GB).
        """
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
    # Batch insert
    # ------------------------------------------------------------------

    def insert_account_blocks(self, pairs: list[tuple[str, int]]) -> int:
        """Batch insert (account_id, block_height) pairs. Returns count inserted."""
        if not pairs:
            return 0

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            # Use unnest for fast bulk insert with conflict skip
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

        final_block = self.client.get_final_block_height()
        remaining = final_block - start_block

        if remaining > BACKFILL_BATCH_SIZE:
            logger.info(
                "Backfill mode: %d → %d (%d blocks, ~%.1f hours at ~3000 blocks/sec)",
                start_block, final_block, remaining, remaining / 3000 / 3600,
            )
            self._backfill(start_block, final_block)
        else:
            logger.info("Index is near tip (block %d, tip %d). Entering live mode.",
                        last_processed, final_block)

        # Live mode: follow the chain tip
        self._live_follow()

    def _backfill(self, start_block: int, target_block: int) -> None:
        """Process historical blocks in parallel batches."""
        current = start_block
        total = target_block - start_block
        batch_start_time = time.monotonic()
        blocks_since_log = 0

        while current <= target_block and self.running:
            batch_end = min(current + BACKFILL_BATCH_SIZE, target_block + 1)
            pairs = self._process_block_range(current, batch_end)

            if pairs:
                # Insert in chunks to avoid huge single transactions
                for i in range(0, len(pairs), INSERT_BATCH_SIZE):
                    chunk = pairs[i:i + INSERT_BATCH_SIZE]
                    self.insert_account_blocks(chunk)

            self.set_last_processed_block(batch_end - 1)

            blocks_processed = batch_end - current
            blocks_since_log += blocks_processed
            elapsed = time.monotonic() - batch_start_time

            # Log progress every ~30 seconds
            if elapsed > 30:
                rate = blocks_since_log / elapsed
                done = current - start_block
                pct = (done / total) * 100 if total > 0 else 100
                eta_hours = ((target_block - current) / rate / 3600) if rate > 0 else 0
                logger.info(
                    "Backfill: %.1f%% — block %d/%d — %.0f blocks/sec — "
                    "%d account-block pairs — ETA %.1fh",
                    pct, current, target_block, rate, len(pairs), eta_hours,
                )
                batch_start_time = time.monotonic()
                blocks_since_log = 0

            current = batch_end

        if self.running:
            logger.info("Backfill complete at block %d.", target_block)

    def _process_block_range(self, start: int, end: int) -> list[tuple[str, int]]:
        """Fetch and parse a range of blocks in parallel. Returns (account_id, block_height) pairs."""
        all_pairs: list[tuple[str, int]] = []

        def _fetch_and_extract(height: int) -> list[tuple[str, int]]:
            block = self.client.fetch_block(height)
            if not block:
                return []
            accounts = self.extract_accounts_from_block(block)
            return [(acct, height) for acct in accounts]

        with ThreadPoolExecutor(max_workers=BACKFILL_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_and_extract, h): h
                for h in range(start, end)
            }
            for future in as_completed(futures):
                try:
                    pairs = future.result()
                    all_pairs.extend(pairs)
                except Exception as exc:
                    height = futures[future]
                    logger.debug("Block %d error: %s", height, exc)

        return all_pairs

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

            # Process new blocks (small batches, single-threaded is fine for ~1 block/sec)
            gap = final_block - last_processed
            if gap > 100:
                # Fell behind — use parallel mode to catch up
                logger.info("Catching up: %d blocks behind tip.", gap)
                self._backfill(last_processed + 1, final_block)
            else:
                # Normal live mode — process sequentially
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
