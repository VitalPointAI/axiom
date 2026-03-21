"""Asyncio-based long-running worker for near real-time block monitoring.

Runs alongside the job queue service (service.py). Launches asyncio tasks
for each enabled streaming chain: NearStreamFetcher.stream_blocks() for
NEAR, EVMStreamFetcher.watch_blocks() for EVM chains. Refreshes tracked
wallets periodically and queues classification jobs on new transactions.

Usage:
    python -m indexers.streaming_worker          # standalone
    python -m indexers.service --streaming       # alongside job queue
"""

import asyncio
import json
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from indexers.near_stream_fetcher import NearStreamFetcher
from indexers.evm_stream_fetcher import EVMStreamFetcher

logger = logging.getLogger(__name__)

WALLET_REFRESH_INTERVAL = 60  # seconds


class StreamingWorker:
    """Multi-chain streaming worker managing asyncio tasks.

    Args:
        pool: psycopg2 connection pool.
        cost_tracker: Optional CostTracker instance.
    """

    def __init__(self, pool, cost_tracker=None):
        self.pool = pool
        self.cost_tracker = cost_tracker
        self._tasks = []
        self._tracked_wallets = {}  # chain -> set of account_ids
        self._wallet_to_ids = {}    # (chain, account_id) -> (user_id, wallet_id)
        self._near_fetcher = NearStreamFetcher(pool, cost_tracker)
        self._evm_fetcher = EVMStreamFetcher(pool, cost_tracker)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Load chain config and launch streaming tasks."""
        await self._refresh_wallets()

        chains = self._load_streaming_chains()
        logger.info("Streaming worker starting for chains: %s", list(chains.keys()))

        for chain, config in chains.items():
            if chain == "near":
                task = asyncio.ensure_future(self._run_near_stream(config))
                self._tasks.append(task)
            elif config.get("ws_url"):
                task = asyncio.ensure_future(
                    self._run_evm_stream(chain, config)
                )
                self._tasks.append(task)

        # Periodic wallet refresh
        self._tasks.append(asyncio.ensure_future(self._wallet_refresh_loop()))

        logger.info("Streaming worker started with %d tasks", len(self._tasks))

    async def stop(self):
        """Cancel all streaming tasks and wait for cleanup."""
        logger.info("Stopping streaming worker...")
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Streaming worker stopped.")

    # ------------------------------------------------------------------
    # Chain configuration
    # ------------------------------------------------------------------

    def _load_streaming_chains(self):
        """Load enabled streaming chains from chain_sync_config or fallback.

        Returns:
            Dict of chain_name -> config dict.
        """
        chains = {}
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT chain, config_json, fetcher_class
                    FROM chain_sync_config
                    WHERE enabled = true
                    """
                )
                for chain, config_json, fetcher_class in cur.fetchall():
                    config = config_json if isinstance(config_json, dict) else {}
                    config["fetcher_class"] = fetcher_class
                    if fetcher_class in ("NearStreamFetcher",):
                        chains[chain] = config
                    elif fetcher_class in ("EVMStreamFetcher",):
                        ws_url = self._evm_fetcher.get_ws_url(chain, config)
                        if ws_url:
                            config["ws_url"] = ws_url
                            chains[chain] = config
            except Exception:
                # Table doesn't exist yet — use hardcoded fallback
                conn.rollback()
                logger.info("chain_sync_config not available, using fallback config")
                chains = self._fallback_chains()
            else:
                conn.commit()
            cur.close()
        finally:
            self.pool.putconn(conn)

        return chains

    def _fallback_chains(self):
        """Hardcoded fallback when chain_sync_config table doesn't exist."""
        chains = {"near": {"fetcher_class": "NearStreamFetcher"}}

        # Add EVM chains if Alchemy key is set
        for chain in ("ethereum", "polygon", "optimism"):
            ws_url = self._evm_fetcher.get_ws_url(chain, {})
            if ws_url:
                chains[chain] = {
                    "fetcher_class": "EVMStreamFetcher",
                    "ws_url": ws_url,
                }

        return chains

    # ------------------------------------------------------------------
    # Wallet management
    # ------------------------------------------------------------------

    async def _refresh_wallets(self):
        """Load tracked wallets from DB, grouped by chain."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, user_id, account_id, chain FROM wallets"
            )
            wallets_by_chain = {}
            wallet_to_ids = {}
            for wallet_id, user_id, account_id, chain in cur.fetchall():
                wallets_by_chain.setdefault(chain, set()).add(account_id)
                wallet_to_ids[(chain, account_id.lower())] = (user_id, wallet_id)
            cur.close()
            conn.commit()
            self._tracked_wallets = wallets_by_chain
            self._wallet_to_ids = wallet_to_ids
            logger.debug(
                "Refreshed wallets: %s",
                {k: len(v) for k, v in wallets_by_chain.items()},
            )
        except Exception:
            conn.rollback()
            logger.warning("Failed to refresh wallets", exc_info=True)
        finally:
            self.pool.putconn(conn)

    async def _wallet_refresh_loop(self):
        """Periodically refresh tracked wallets."""
        while True:
            await asyncio.sleep(WALLET_REFRESH_INTERVAL)
            await self._refresh_wallets()

    # ------------------------------------------------------------------
    # NEAR streaming
    # ------------------------------------------------------------------

    async def _run_near_stream(self, config):
        """Run NEAR block streaming."""
        import aiohttp

        wallets = self._tracked_wallets.get("near", set())

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            start_height = self._get_last_near_block()
            if start_height == 0:
                # No cursor in DB — start from latest finalized block
                start_height = await self._near_fetcher.get_last_final_block(session)
                logger.info("No NEAR cursor found, starting stream from block %d", start_height)

            await self._near_fetcher.stream_blocks(
                start_height,
                wallets,
                lambda txs: self._on_near_txs_found(txs),
                session=session,
            )

    def _get_last_near_block(self):
        """Get the last indexed NEAR block height from DB."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT MAX(CAST(cursor AS BIGINT))
                FROM indexing_jobs
                WHERE chain = 'near'
                  AND status = 'completed'
                  AND cursor IS NOT NULL
                  AND cursor ~ '^[0-9]+$'
                """
            )
            row = cur.fetchone()
            cur.close()
            conn.commit()
            return row[0] if row and row[0] else 0
        except Exception:
            conn.rollback()
            return 0
        finally:
            self.pool.putconn(conn)

    async def _on_near_txs_found(self, txs):
        """Handle new NEAR transactions: upsert and queue classification.

        Args:
            txs: List of transaction dicts from NearStreamFetcher.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            inserted_count = 0

            for tx in txs:
                signer = tx.get("signer_id", "").lower()
                receiver = tx.get("receiver_id", "").lower()

                # Find matching tracked wallets
                for account_id in (signer, receiver):
                    key = ("near", account_id)
                    if key not in self._wallet_to_ids:
                        continue

                    user_id, wallet_id = self._wallet_to_ids[key]
                    direction = "out" if account_id == signer else "in"

                    cur.execute(
                        """
                        INSERT INTO transactions (
                            wallet_id, user_id, chain, tx_hash,
                            block_height, block_timestamp,
                            sender, receiver, direction, source
                        ) VALUES (%s, %s, 'near', %s, %s, to_timestamp(%s),
                                  %s, %s, %s, 'neardata_stream')
                        ON CONFLICT (wallet_id, tx_hash, direction) DO NOTHING
                        RETURNING id
                        """,
                        (
                            wallet_id, user_id, tx["tx_hash"],
                            tx["block_height"], tx["block_timestamp"],
                            tx.get("signer_id", ""), tx.get("receiver_id", ""),
                            direction,
                        ),
                    )
                    if cur.fetchone():
                        inserted_count += 1

                        # Notify frontend
                        cur.execute(
                            "SELECT pg_notify('new_transactions', %s)",
                            (json.dumps({"wallet_id": wallet_id, "chain": "near"}),),
                        )

            conn.commit()

            if inserted_count > 0:
                logger.info("Inserted %d new NEAR transactions from stream", inserted_count)
                # Queue classification jobs for affected wallets
                self._queue_classify_jobs(cur, txs)
                conn.commit()

            cur.close()
        except Exception:
            conn.rollback()
            logger.error("Error processing NEAR stream transactions", exc_info=True)
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # EVM streaming
    # ------------------------------------------------------------------

    async def _run_evm_stream(self, chain, config):
        """Run EVM WebSocket block streaming for a single chain."""
        ws_url = config["ws_url"]

        async def on_new_head(block_header):
            await self._on_evm_new_block(block_header, chain)

        await self._evm_fetcher.watch_blocks(ws_url, on_new_head)

    async def _on_evm_new_block(self, block_header, chain):
        """Handle new EVM block: queue incremental sync for tracked wallets.

        Args:
            block_header: Block header dict from newHeads subscription.
            chain: Chain name.
        """
        block_number = int(block_header.get("number", "0x0"), 16)
        wallets = self._tracked_wallets.get(chain, set())

        if not wallets:
            return

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            for account_id in wallets:
                key = (chain, account_id.lower())
                if key not in self._wallet_to_ids:
                    continue
                user_id, wallet_id = self._wallet_to_ids[key]

                # Queue incremental sync job
                cur.execute(
                    """
                    INSERT INTO indexing_jobs
                        (user_id, wallet_id, job_type, chain, status, priority, cursor)
                    VALUES (%s, %s, 'evm_incremental', %s, 'queued', 1, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (user_id, wallet_id, chain, str(block_number)),
                )
            conn.commit()
            cur.close()
            logger.debug("Queued EVM incremental syncs for %s block %d", chain, block_number)
        except Exception:
            conn.rollback()
            logger.error("Error queuing EVM incremental sync", exc_info=True)
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _queue_classify_jobs(self, cur, txs):
        """Queue classify_transactions jobs for wallets with new transactions."""
        queued = set()
        for tx in txs:
            for account_id in (tx.get("signer_id", ""), tx.get("receiver_id", "")):
                key = ("near", account_id.lower())
                if key in self._wallet_to_ids and key not in queued:
                    user_id, wallet_id = self._wallet_to_ids[key]
                    cur.execute(
                        """
                        INSERT INTO indexing_jobs
                            (user_id, wallet_id, job_type, chain, status, priority)
                        VALUES (%s, %s, 'classify_transactions', 'near', 'queued', 2)
                        ON CONFLICT DO NOTHING
                        """,
                        (user_id, wallet_id),
                    )
                    queued.add(key)


async def run_streaming_worker(pool, cost_tracker=None):
    """Entry point: create worker, start, and run until interrupted."""
    worker = StreamingWorker(pool, cost_tracker)
    await worker.start()
    try:
        # Run forever until cancelled
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await worker.stop()


if __name__ == "__main__":
    from indexers.db import get_pool

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pool = get_pool(min_conn=2, max_conn=5)
    asyncio.run(run_streaming_worker(pool))
