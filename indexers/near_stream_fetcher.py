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
        """Incremental sync via neardata.xyz — scans blocks for ALL NEAR wallets at once.

        A single block scan checks all tracked NEAR wallets simultaneously,
        so one job handles the entire user's NEAR portfolio. For full_sync,
        delegates to NearFetcher (NearBlocks wallet-centric API is better
        for historical backfill).
        """
        from indexers.near_fetcher import NearFetcher, parse_transaction

        job_type = job.get("job_type", "incremental_sync")

        # Full sync: delegate to NearFetcher (wallet-centric API is better)
        if job_type == "full_sync":
            delegate = NearFetcher(self.pool)
            delegate.sync_wallet(job)
            return

        job_id = job["id"]
        user_id = job.get("user_id")

        # Load ALL NEAR wallets for this user
        wallet_map = self._get_all_near_wallets(user_id)
        if not wallet_map:
            logger.info("No NEAR wallets for user_id=%s", user_id)
            return

        tracked_wallets = set(wallet_map.keys())
        logger.info(
            "Incremental sync via neardata.xyz for %d wallets: %s",
            len(tracked_wallets), ", ".join(sorted(tracked_wallets)),
        )

        # Determine start block from job cursor or highest block across all wallets.
        # NearBlocks cursors are large numbers (>1B) that aren't block heights.
        # NEAR block heights are currently ~190M, so reject anything > 500M.
        MAX_VALID_BLOCK = 500_000_000
        cursor = job.get("cursor")
        start_height = None
        if cursor and str(cursor).isdigit():
            val = int(cursor)
            if val <= MAX_VALID_BLOCK:
                start_height = val
            else:
                logger.info("Ignoring non-block-height cursor: %s", cursor)
        if not start_height:
            start_height = self._get_highest_block_all_wallets(user_id)
        if not start_height:
            # No existing transactions — delegate to full sync per wallet
            logger.info("No start height, delegating to NearFetcher")
            delegate = NearFetcher(self.pool)
            delegate.sync_wallet(job)
            return

        # Get chain tip and cap scan window
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
            tip = start_height + 1

        gap = tip - start_height
        MAX_SCAN_BLOCKS = 2_000  # ~20 min of NEAR blocks, ~2 min to scan

        if gap > MAX_SCAN_BLOCKS:
            logger.info(
                "Gap too large (%d blocks), skipping to last %d blocks",
                gap, MAX_SCAN_BLOCKS,
            )
            start_height = tip - MAX_SCAN_BLOCKS

        try:
            found_count = loop.run_until_complete(
                self._incremental_scan_all(
                    wallet_map, user_id, job_id,
                    start_height, parse_transaction,
                )
            )
        finally:
            loop.close()

        logger.info(
            "Incremental scan complete: %d new txs across %d wallets",
            found_count, len(tracked_wallets),
        )

    async def _incremental_scan_all(
        self, wallet_map, user_id, job_id, start_height, parse_fn,
    ):
        """Scan blocks once for ALL wallets simultaneously.

        wallet_map: {account_id: (wallet_id, user_id)}
        Returns total count of new transactions found.
        """
        import aiohttp
        from indexers.near_fetcher import NearFetcher

        found_count = 0
        fetcher_db = NearFetcher(self.pool)
        tracked = set(wallet_map.keys())

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
            scanned = 0

            for height in range(start_height + 1, last_final + 1):
                block = await self.fetch_block(session, height)
                scanned += 1

                if block:
                    txs = self.extract_wallet_txs(block, tracked)
                    if txs:
                        rows = []
                        for tx in txs:
                            # Determine which wallet this tx belongs to
                            signer = tx["signer_id"].lower()
                            receiver = tx["receiver_id"].lower()
                            matched_accounts = []
                            for acct in tracked:
                                if acct.lower() == signer or acct.lower() == receiver:
                                    matched_accounts.append(acct)

                            for acct in matched_accounts:
                                wid, uid = wallet_map[acct]
                                nearblocks_compat = {
                                    "transaction_hash": tx["tx_hash"],
                                    "receipt_id": None,
                                    "predecessor_account_id": tx["signer_id"],
                                    "receiver_account_id": tx["receiver_id"],
                                    "actions": [],
                                    "outcomes_agg": {},
                                    "block": {"block_height": tx["block_height"]},
                                    "block_timestamp": tx["block_timestamp"] * 1_000_000_000,
                                    "outcomes": {"status": True},
                                }
                                for action in tx.get("actions", []):
                                    if isinstance(action, dict) and "Transfer" in action:
                                        nearblocks_compat["actions"] = [{
                                            "action": "TRANSFER",
                                            "deposit": action["Transfer"].get("deposit", "0"),
                                        }]
                                        break

                                parsed = parse_fn(
                                    nearblocks_compat,
                                    wallet_id=wid,
                                    user_id=uid,
                                    account_id=acct,
                                )
                                if parsed:
                                    rows.append(parsed)

                        if rows:
                            fetcher_db._batch_insert(rows)
                            found_count += len(rows)

                # Update progress every 25 blocks
                if scanned % 25 == 0:
                    fetcher_db._update_job_progress(
                        job_id, str(height), scanned,
                    )

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

    def _get_all_near_wallets(self, user_id):
        """Get all NEAR wallets for a user. Returns {account_id: (wallet_id, user_id)}."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, account_id FROM wallets WHERE user_id = %s AND chain = 'NEAR'",
                (user_id,),
            )
            rows = cur.fetchall()
            cur.close()
            return {row[1]: (row[0], user_id) for row in rows}
        finally:
            self.pool.putconn(conn)

    def _get_highest_block_all_wallets(self, user_id):
        """Get the highest block_height across all NEAR wallets for a user."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT MAX(t.block_height) FROM transactions t
                JOIN wallets w ON t.wallet_id = w.id
                WHERE w.user_id = %s AND t.chain = 'near'
                """,
                (user_id,),
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row and row[0] else None
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
