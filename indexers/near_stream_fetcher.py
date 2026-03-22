"""NEAR stream fetcher using neardata.xyz block streaming.

Replaces NearBlocks polling with neardata.xyz for real-time transaction
detection. Historical backfill still delegates to NearBlocks via the
existing NearFetcher pattern.

neardata.xyz is free (no API key) and provides sub-second block latency.
"""

import asyncio
import json
import logging
import os
from indexers.chain_plugin import ChainFetcher

logger = logging.getLogger(__name__)

NEARDATA_BASE = os.environ.get("NEARDATA_API_URL", "https://mainnet.neardata.xyz")
POLL_INTERVAL = 0.6  # seconds between block checks
MAX_RETRIES = 5
RETRY_BASE_DELAY = 1.0
MAX_RETRY_DELAY = 60.0


class NearStreamFetcher(ChainFetcher):
    """NEAR chain fetcher using neardata.xyz block streaming.

    Core methods are async for use in the streaming worker. The sync_wallet
    and get_balance methods from ChainFetcher ABC are synchronous and delegate
    to the existing NearFetcher for historical sync.
    """

    chain_name = "near"
    supported_job_types = [
        "near_stream_sync", "full_sync", "incremental_sync",
        "staking_sync", "lockup_sync",
    ]

    def __init__(self, pool, cost_tracker=None):
        super().__init__(pool)
        self.cost_tracker = cost_tracker

    # ------------------------------------------------------------------
    # Async block fetching
    # ------------------------------------------------------------------

    async def fetch_block(self, session, height):
        """Fetch a single block from neardata.xyz.

        Args:
            session: aiohttp ClientSession.
            height: Block height to fetch.

        Returns:
            Parsed block dict, or None for missing/null blocks.
        """
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(f"{NEARDATA_BASE}/v0/block/{height}") as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        if not text or text.strip() == "null":
                            return None
                        return json.loads(text)
                    elif resp.status == 429 or resp.status >= 500:
                        delay = min(RETRY_BASE_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                        logger.debug(
                            "Block %s: HTTP %s, retrying in %.1fs",
                            height, resp.status, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.warning("Block %s: unexpected HTTP %s", height, resp.status)
                        return None
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    logger.error("Block %s: failed after %d attempts: %s", height, MAX_RETRIES, e)
                    return None
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                await asyncio.sleep(delay)
        return None

    async def get_last_final_block(self, session):
        """Get the latest finalized block height from neardata.xyz.

        Args:
            session: aiohttp ClientSession.

        Returns:
            int block height.
        """
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(f"{NEARDATA_BASE}/v0/last_block/final") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["block"]["header"]["height"]
                    elif resp.status == 429:
                        delay = min(RETRY_BASE_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                        await asyncio.sleep(delay)
                    else:
                        raise RuntimeError(f"HTTP {resp.status}")
            except asyncio.CancelledError:
                raise
            except RuntimeError:
                raise
            except Exception:
                if attempt == MAX_RETRIES - 1:
                    raise
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                await asyncio.sleep(delay)
        raise RuntimeError("Failed to get last final block after max retries")

    # ------------------------------------------------------------------
    # Transaction extraction
    # ------------------------------------------------------------------

    def extract_wallet_txs(self, block, tracked_wallets):
        """Extract transactions from a block that involve tracked wallets.

        Checks both transactions (signer_id, receiver_id) and receipt
        execution outcomes (predecessor_id, receiver_id).

        Args:
            block: Parsed block dict from neardata.xyz, or None.
            tracked_wallets: Set of wallet account IDs to match.

        Returns:
            List of transaction dicts with tx_hash, signer_id, receiver_id,
            actions, block_height, block_timestamp.
        """
        if not block:
            return []

        header = block.get("block", {}).get("header", {})
        block_height = header.get("height", 0)
        block_timestamp_ns = header.get("timestamp", 0)
        block_timestamp = block_timestamp_ns // 1_000_000_000 if block_timestamp_ns else 0

        tracked_lower = {w.lower() for w in tracked_wallets}
        seen_hashes = set()
        results = []

        for shard in block.get("shards", []):
            chunk = shard.get("chunk")
            if not chunk:
                continue

            # Check transactions
            for tx in chunk.get("transactions", []):
                tx_data = tx.get("transaction", {})
                tx_hash = tx_data.get("hash", "")
                signer = tx_data.get("signer_id", "").lower()
                receiver = tx_data.get("receiver_id", "").lower()

                if tx_hash in seen_hashes:
                    continue

                if signer in tracked_lower or receiver in tracked_lower:
                    seen_hashes.add(tx_hash)
                    results.append({
                        "tx_hash": tx_hash,
                        "signer_id": tx_data.get("signer_id", ""),
                        "receiver_id": tx_data.get("receiver_id", ""),
                        "actions": tx_data.get("actions", []),
                        "block_height": block_height,
                        "block_timestamp": block_timestamp,
                    })

            # Check receipt execution outcomes
            for receipt_outcome in shard.get("receipt_execution_outcomes", []):
                receipt = receipt_outcome.get("receipt", {})
                predecessor = receipt.get("predecessor_id", "").lower()
                receiver = receipt.get("receiver_id", "").lower()
                tx_hash = receipt_outcome.get("tx_hash", "")

                if not tx_hash or tx_hash in seen_hashes:
                    continue

                if predecessor in tracked_lower or receiver in tracked_lower:
                    seen_hashes.add(tx_hash)
                    results.append({
                        "tx_hash": tx_hash,
                        "signer_id": receipt.get("predecessor_id", ""),
                        "receiver_id": receipt.get("receiver_id", ""),
                        "actions": [],
                        "block_height": block_height,
                        "block_timestamp": block_timestamp,
                    })

        return results

    # ------------------------------------------------------------------
    # Streaming loop
    # ------------------------------------------------------------------

    async def stream_blocks(self, start_height, tracked_wallets, on_tx_found, session=None):
        """Continuously poll for new blocks and extract transactions.

        Args:
            start_height: Block height to start from (exclusive).
            tracked_wallets: Set of wallet account IDs.
            on_tx_found: Async callback called with list of tx dicts for each block.
            session: Optional aiohttp ClientSession (created if not provided).
        """
        owns_session = session is None
        if owns_session:
            import aiohttp
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

        try:
            current_height = start_height

            while True:
                last_final = await self.get_last_final_block(session)

                if last_final > current_height:
                    for height in range(current_height + 1, last_final + 1):
                        block = await self.fetch_block(session, height)
                        if block:
                            txs = self.extract_wallet_txs(block, tracked_wallets)
                            if txs:
                                await on_tx_found(txs)
                    current_height = last_final

                await asyncio.sleep(POLL_INTERVAL)
        finally:
            if owns_session:
                await session.close()

    # ------------------------------------------------------------------
    # ChainFetcher ABC — sync methods
    # ------------------------------------------------------------------

    def sync_wallet(self, job):
        """Incremental sync via neardata.xyz block scanning.

        For incremental_sync jobs, scans recent blocks from neardata.xyz
        (free, no rate limits) instead of NearBlocks. Cursor stores the
        last synced block height. Falls back to NearFetcher for full_sync.

        For full_sync, delegates to NearFetcher (NearBlocks wallet-centric
        API is faster for historical backfill).
        """
        from indexers.near_fetcher import NearFetcher, parse_transaction

        job_type = job.get("job_type", "incremental_sync")

        # Full sync: delegate to NearFetcher (wallet-centric API is better)
        if job_type == "full_sync":
            delegate = NearFetcher(self.pool)
            delegate.sync_wallet(job)
            return

        # Incremental sync: scan blocks via neardata.xyz
        wallet_id = job["wallet_id"]
        job_id = job["id"]
        user_id = job.get("user_id")

        account_id = job.get("account_id")
        if not account_id:
            account_id = self._get_account_id(wallet_id)
        if not account_id:
            raise ValueError(f"Wallet {wallet_id} not found")

        logger.info(
            "Incremental sync via neardata.xyz for %s (wallet_id=%s)",
            account_id, wallet_id,
        )

        # Determine start block from cursor or DB
        cursor = job.get("cursor")
        start_height = None
        if cursor and cursor.isdigit():
            start_height = int(cursor)
        else:
            start_height = self._get_last_block_height(wallet_id)

        if not start_height:
            # No cursor and no existing transactions — delegate to full sync
            logger.info("No start height for %s, delegating to NearFetcher", account_id)
            delegate = NearFetcher(self.pool)
            delegate.sync_wallet(job)
            return

        # Check gap size — if too large, skip to recent blocks
        # Block scanning is only practical for small gaps (<10K blocks)
        loop = asyncio.new_event_loop()
        try:
            import aiohttp
            async def _get_tip():
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as s:
                    return await self.get_last_final_block(s)
            tip = loop.run_until_complete(_get_tip())
        except Exception:
            loop.close()
            loop = asyncio.new_event_loop()
            tip = start_height + 1  # fallback

        gap = tip - start_height
        MAX_SCAN_BLOCKS = 10_000  # ~1.7 hours of NEAR blocks

        if gap > MAX_SCAN_BLOCKS:
            # Gap too large for block scanning — skip to recent window
            logger.info(
                "Gap too large for %s (%d blocks), skipping to last %d blocks",
                account_id, gap, MAX_SCAN_BLOCKS,
            )
            start_height = tip - MAX_SCAN_BLOCKS

        try:
            found_count = loop.run_until_complete(
                self._incremental_scan(
                    account_id, wallet_id, user_id, job_id,
                    start_height, parse_transaction,
                )
            )
        finally:
            loop.close()

        logger.info(
            "Incremental scan complete for %s: %d new txs found",
            account_id, found_count,
        )

    async def _incremental_scan(
        self, account_id, wallet_id, user_id, job_id,
        start_height, parse_fn,
    ):
        """Scan blocks from start_height to finalized tip via neardata.xyz.

        Returns count of new transactions found.
        """
        import aiohttp
        from indexers.near_fetcher import NearFetcher

        found_count = 0
        fetcher_db = NearFetcher(self.pool)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            last_final = await self.get_last_final_block(session)

            if last_final <= start_height:
                logger.info("No new blocks since %d", start_height)
                fetcher_db._update_job_progress(job_id, str(start_height), 0)
                fetcher_db._complete_job(job_id)
                return 0

            total_blocks = last_final - start_height
            fetcher_db._set_progress_total(job_id, total_blocks)

            tracked = {account_id}
            scanned = 0

            for height in range(start_height + 1, last_final + 1):
                block = await self.fetch_block(session, height)
                scanned += 1

                if block:
                    txs = self.extract_wallet_txs(block, tracked)
                    if txs:
                        # Convert neardata tx format to NearBlocks-compatible
                        # format for parse_transaction
                        rows = []
                        for tx in txs:
                            nearblocks_compat = {
                                "transaction_hash": tx["tx_hash"],
                                "receipt_id": None,
                                "predecessor_account_id": tx["signer_id"],
                                "receiver_account_id": tx["receiver_id"],
                                "actions": [
                                    {"action": a.get("type", a.get("Transfer") and "TRANSFER" or "FUNCTION_CALL")}
                                    for a in tx.get("actions", [])
                                ] if tx.get("actions") else [],
                                "outcomes_agg": {},
                                "block": {"block_height": tx["block_height"]},
                                "block_timestamp": tx["block_timestamp"] * 1_000_000_000,
                                "outcomes": {"status": True},
                            }
                            # Handle Transfer actions with deposit
                            for action in tx.get("actions", []):
                                if isinstance(action, dict) and "Transfer" in action:
                                    transfer = action["Transfer"]
                                    nearblocks_compat["actions"] = [{
                                        "action": "TRANSFER",
                                        "deposit": transfer.get("deposit", "0"),
                                    }]
                                    break

                            parsed = parse_fn(
                                nearblocks_compat,
                                wallet_id=wallet_id,
                                user_id=user_id,
                                account_id=account_id,
                            )
                            if parsed:
                                rows.append(parsed)

                        if rows:
                            fetcher_db._batch_insert(rows)
                            found_count += len(rows)

                # Update progress every 25 blocks (~2s) to prevent stale job recovery
                if scanned % 25 == 0:
                    fetcher_db._update_job_progress(
                        job_id, str(height), scanned,
                    )

            # Final progress update and complete
            fetcher_db._update_job_progress(job_id, str(last_final), scanned)
            fetcher_db._complete_job(job_id)

        return found_count

    def _get_account_id(self, wallet_id):
        """Look up account_id from wallets table."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT account_id FROM wallets WHERE id = %s",
                (wallet_id,),
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row else None
        finally:
            self.pool.putconn(conn)

    def _get_last_block_height(self, wallet_id):
        """Get the highest block_height for this wallet from transactions."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT MAX(block_height) FROM transactions
                WHERE wallet_id = %s AND chain = 'near'
                """,
                (wallet_id,),
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row and row[0] else None
        finally:
            self.pool.putconn(conn)

    def get_balance(self, address):
        """Get NEAR balance via FastNear RPC.

        Args:
            address: NEAR account ID.

        Returns:
            dict with native_balance (yoctoNEAR string) and tokens list.
        """
        import requests
        from config import FASTNEAR_RPC

        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "query",
                "params": {
                    "request_type": "view_account",
                    "account_id": address,
                    "finality": "final",
                },
                "id": "1",
            }
            response = requests.post(FASTNEAR_RPC, json=payload, timeout=10)
            data = response.json()
            result = data.get("result", {})
            return {
                "native_balance": result.get("amount", "0"),
                "tokens": [],
            }
        except Exception as e:
            logger.warning("Balance check failed for %s: %s", address, e)
            return {"native_balance": "0", "tokens": []}
