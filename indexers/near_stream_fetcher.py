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
        """Historical sync via NearBlocks (delegates to existing NearFetcher).

        For full_sync/incremental_sync jobs, uses the proven NearBlocks
        wallet-centric API. Records last block height in cursor for
        streaming pickup.
        """
        from indexers.near_fetcher import NearFetcher
        delegate = NearFetcher(self.pool)
        delegate.sync_wallet(job)

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
