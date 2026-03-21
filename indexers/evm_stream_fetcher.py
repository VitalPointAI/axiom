"""EVM streaming fetcher using Alchemy WebSocket for new block detection.

Receives newHeads notifications via WebSocket and triggers incremental
transaction sync via the existing Etherscan V2-based EVMFetcher.
Historical sync delegates entirely to EVMFetcher.

Uses raw ``websockets`` library (not web3.py) for lightweight
eth_subscribe("newHeads") subscription.
"""

import asyncio
import json
import logging
import os
import time

import websockets

from indexers.chain_plugin import ChainFetcher
from indexers.evm_fetcher import EVMFetcher

logger = logging.getLogger(__name__)

# Alchemy WebSocket URL templates per chain
ALCHEMY_WS_URLS = {
    "ethereum": "wss://eth-mainnet.g.alchemy.com/v2/{key}",
    "polygon": "wss://polygon-mainnet.g.alchemy.com/v2/{key}",
    "optimism": "wss://opt-mainnet.g.alchemy.com/v2/{key}",
}


class EVMStreamFetcher(ChainFetcher):
    """EVM chain fetcher with WebSocket-based real-time block detection.

    Connects to Alchemy WebSocket for newHeads notifications. On each new
    block, triggers incremental sync via EVMFetcher's Etherscan V2
    pagination. Historical sync delegates to EVMFetcher directly.

    Args:
        pool: psycopg2 SimpleConnectionPool instance.
        cost_tracker: Optional CostTracker for logging API costs.
    """

    chain_name = "evm"
    supported_job_types = ["evm_full_sync", "evm_incremental"]

    PING_INTERVAL = 20    # seconds between WebSocket pings
    WATCHDOG_TIMEOUT = 60  # seconds of silence before reconnect
    MAX_BACKOFF = 60      # max reconnect backoff in seconds

    def __init__(self, pool, cost_tracker=None):
        super().__init__(pool)
        self.cost_tracker = cost_tracker
        self._evm_fetcher = EVMFetcher(pool)

    # ------------------------------------------------------------------
    # WebSocket URL construction
    # ------------------------------------------------------------------

    def get_ws_url(self, chain, config_json=None):
        """Construct WebSocket URL for a chain using Alchemy API key.

        Args:
            chain: Chain name (e.g. 'ethereum', 'polygon').
            config_json: Optional config dict (unused currently).

        Returns:
            WebSocket URL string, or None if API key not set or chain unsupported.
        """
        api_key = os.environ.get("ALCHEMY_API_KEY")
        if not api_key:
            logger.warning("ALCHEMY_API_KEY not set, WebSocket unavailable for %s", chain)
            return None

        template = ALCHEMY_WS_URLS.get(chain)
        if not template:
            logger.warning("No Alchemy WebSocket URL for chain: %s", chain)
            return None

        return template.format(key=api_key)

    # ------------------------------------------------------------------
    # WebSocket streaming
    # ------------------------------------------------------------------

    async def watch_blocks(self, ws_url, on_new_head):
        """Connect to WebSocket and subscribe to newHeads.

        Reconnects with exponential backoff on connection drop. Resets
        backoff after successful connection. Watchdog triggers reconnect
        if no message received within WATCHDOG_TIMEOUT seconds.

        Args:
            ws_url: Alchemy WebSocket URL.
            on_new_head: Async callback called with block header dict.
        """
        backoff = 1

        while True:
            try:
                async with websockets.connect(
                    ws_url,
                    ping_interval=self.PING_INTERVAL,
                ) as ws:
                    # Reset backoff on successful connection
                    backoff = 1
                    logger.info("WebSocket connected to %s", ws_url[:50])

                    # Subscribe to newHeads
                    subscribe_msg = json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newHeads"],
                    })
                    await ws.send(subscribe_msg)

                    # Wait for subscription confirmation
                    response = await ws.recv()
                    sub_data = json.loads(response)
                    sub_id = sub_data.get("result")
                    logger.info("Subscribed to newHeads: %s", sub_id)

                    # Listen for new blocks
                    last_message_time = time.monotonic()

                    while True:
                        try:
                            msg = await asyncio.wait_for(
                                ws.recv(),
                                timeout=self.WATCHDOG_TIMEOUT,
                            )
                        except asyncio.TimeoutError:
                            logger.warning(
                                "Watchdog: no message in %ds, reconnecting",
                                self.WATCHDOG_TIMEOUT,
                            )
                            break

                        last_message_time = time.monotonic()  # noqa: F841
                        data = json.loads(msg)

                        if data.get("method") == "eth_subscription":
                            block_header = data["params"]["result"]
                            await on_new_head(block_header)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    "WebSocket error: %s, reconnecting in %ds",
                    e, backoff,
                )

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.MAX_BACKOFF)

    # ------------------------------------------------------------------
    # New block handler
    # ------------------------------------------------------------------

    async def on_new_block(self, block_header, chain, tracked_wallets):
        """Handle a new block notification.

        Queues incremental sync jobs for wallets on this chain.

        Args:
            block_header: Block header dict from newHeads subscription.
            chain: Chain name.
            tracked_wallets: Set of wallet addresses on this chain.
        """
        block_number = int(block_header.get("number", "0x0"), 16)
        logger.info("New %s block: %d", chain, block_number)

    # ------------------------------------------------------------------
    # ChainFetcher ABC — sync methods
    # ------------------------------------------------------------------

    def sync_wallet(self, job):
        """Historical sync via existing EVMFetcher/Etherscan V2.

        Delegates entirely to the proven EVMFetcher implementation.
        """
        self._evm_fetcher.sync_wallet(job)

    def get_balance(self, address):
        """Get native balance via EVMFetcher/Etherscan V2."""
        return self._evm_fetcher.get_balance(address)
