"""Akash Network chain fetcher — implements ChainFetcher ABC for the Axiom indexer.

Uses the public Cosmos LCD REST API (no API key required).
Fetches account transactions and stores them in the unified transactions table.

API reference: https://cosmos.github.io/cosmos-rest-api/

Amount encoding:
- Native AKT is stored in uakt (integer); 1 AKT = 1,000,000 uakt
- Transactions are stored in the transactions table with amount as NUMERIC(40,0)
  (uakt, matching the on-chain representation)

Direction encoding:
- action_type = 'out'  when the wallet is the sender (MsgSend.from_address, delegate, etc.)
- action_type = 'in'   when the wallet is the recipient
- action_type = 'self' for governance, create_deployment, and other non-transfer ops

Rate limiting: 0.5s between requests (2 req/s), MAX_RETRIES=3 with endpoint rotation.
"""

import json
import logging
import time
from decimal import Decimal
from typing import Optional

import requests

from indexers.chain_plugin import ChainFetcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Akash LCD public endpoints
# ---------------------------------------------------------------------------
AKASH_LCD_ENDPOINTS = [
    "https://rest.cosmos.directory/akash",
    "https://api.akash.forbole.com",
    "https://akash-api.polkachu.com",
]

# Rate limiting
RATE_LIMIT_DELAY = 0.5  # 2 requests per second
MAX_RETRIES = 3
PAGE_LIMIT = 100  # transactions per page

# AKT decimals
AKT_DECIMALS = 6  # 1 AKT = 1,000,000 uakt

# Cosmos SDK message types that indicate outgoing direction from the sender
MSG_SEND_TYPES = {
    "/cosmos.bank.v1beta1.MsgSend",
    "/cosmos.staking.v1beta1.MsgDelegate",
    "/cosmos.staking.v1beta1.MsgUndelegate",
    "/cosmos.staking.v1beta1.MsgBeginRedelegate",
    "/cosmos.distribution.v1beta1.MsgWithdrawDelegatorReward",
    "/akash.deployment.v1beta3.MsgCreateDeployment",
    "/akash.deployment.v1beta2.MsgCreateDeployment",
    "/akash.deployment.v1beta1.MsgCreateDeployment",
    "/akash.deployment.v1beta3.MsgCloseDeployment",
}


class AkashFetcher(ChainFetcher):
    """Akash Network (Cosmos SDK) chain fetcher.

    Implements ChainFetcher ABC for the Axiom indexer service.
    Handles akash_full_sync and akash_incremental job types.

    Registered in service.py:
        "akash_full_sync":   AkashFetcher(pool)
        "akash_incremental": AkashFetcher(pool)
    """

    chain_name = "akash"
    supported_job_types = ["akash_full_sync", "akash_incremental"]

    def __init__(self, pool, cost_tracker=None):
        super().__init__(pool)
        self._endpoint_index = 0
        self._last_request_time = 0
        self.cost_tracker = cost_tracker

    # ------------------------------------------------------------------
    # ChainFetcher ABC methods
    # ------------------------------------------------------------------

    def sync_wallet(self, job: dict) -> None:
        """Fetch Akash transactions for a wallet and upsert into transactions table.

        Args:
            job: dict with keys: id, user_id, wallet_id, account_id (wallet address),
                 cursor (last block height for incremental resume), job_type

        Cursor usage:
            cursor stores the last-seen block height as a string.
            Full sync: cursor=None, fetches all history.
            Incremental: cursor=str(last_height), used for page ordering.
        """
        wallet_id = job["wallet_id"]
        user_id = job["user_id"]
        address = job["account_id"]
        job_id = job["id"]
        cursor_str = job.get("cursor")

        # Parse cursor: last block height (0 = fetch all)
        since_height = int(cursor_str) if cursor_str and cursor_str.isdigit() else 0

        logger.info(
            "AkashFetcher.sync_wallet: address=%s wallet_id=%s since_height=%s",
            address, wallet_id, since_height,
        )

        # Fetch transaction pages from Cosmos LCD
        all_txs = []
        pagination_key = None
        max_height_seen = since_height

        while True:
            sent_result = self._call_tx_search_sent(address, pagination_key)
            received_result = self._call_tx_search_received(address, pagination_key)

            # Merge by txhash to deduplicate
            tx_map = {}
            for tx_resp in sent_result.get("tx_responses", []):
                tx_map[tx_resp.get("txhash", "")] = tx_resp
            for tx_resp in received_result.get("tx_responses", []):
                tx_map.setdefault(tx_resp.get("txhash", ""), tx_resp)

            page_txs = list(tx_map.values())
            if not page_txs:
                break

            for tx_resp in page_txs:
                height = int(tx_resp.get("height", 0))
                if since_height > 0 and height <= since_height:
                    continue
                all_txs.append(tx_resp)
                max_height_seen = max(max_height_seen, height)

            # Pagination: use sent result's next_key (received is typically fewer)
            pagination = sent_result.get("pagination", {})
            pagination_key = pagination.get("next_key")
            if not pagination_key:
                break

            logger.debug("AkashFetcher: fetched %d txs so far, continuing...", len(all_txs))

        logger.info("AkashFetcher: fetched %d new transactions for address=%s", len(all_txs), address)

        if not all_txs:
            return

        # Insert into unified transactions table
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            inserted = 0

            for tx_resp in all_txs:
                row = self._parse_to_unified(tx_resp, address, wallet_id, user_id)
                if row is None:
                    continue

                cur.execute(
                    """
                    INSERT INTO transactions
                        (wallet_id, user_id, chain, tx_hash, block_timestamp,
                         action_type, token_id, amount, fee, raw_data)
                    VALUES (%s, %s, %s, %s, %s::timestamptz,
                            %s, %s, %s, %s, %s)
                    ON CONFLICT (wallet_id, tx_hash) DO NOTHING
                    """,
                    (
                        wallet_id,
                        user_id,
                        "akash",
                        row["tx_hash"],
                        row["block_timestamp"],
                        row["action_type"],
                        row["token_id"],
                        row["amount"],
                        row["fee"],
                        json.dumps(row["raw_data"]),
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1

            # Update job cursor to resume from last seen height
            if max_height_seen > since_height:
                cur.execute(
                    """
                    UPDATE indexing_jobs
                    SET cursor = %s, progress_fetched = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (str(max_height_seen), inserted, job_id),
                )

            conn.commit()
            cur.close()
            logger.info(
                "AkashFetcher: inserted %d transactions for wallet_id=%s (max_height=%s)",
                inserted, wallet_id, max_height_seen,
            )

        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def get_balance(self, address: str) -> dict:
        """Get current AKT balance for the given Akash address.

        Args:
            address: Akash address (starts with 'akash1')

        Returns:
            dict with:
                native_balance: str — AKT balance in human-readable units (uakt / 1e6)
                tokens: list[dict] — IBC token balances
        """
        try:
            data = self._get(f"/cosmos/bank/v1beta1/balances/{address}")
            balances = data.get("balances", [])

            native_balance = "0"
            tokens = []

            for b in balances:
                denom = b.get("denom", "")
                amount_str = b.get("amount", "0")
                if denom == "uakt":
                    akt_amount = Decimal(amount_str) / Decimal(10 ** AKT_DECIMALS)
                    native_balance = str(akt_amount)
                else:
                    tokens.append({"token_id": denom, "balance": amount_str})

            return {"native_balance": native_balance, "tokens": tokens}

        except Exception as exc:
            logger.warning("AkashFetcher.get_balance failed for address=%s: %s", address, exc)
            return {"native_balance": "0", "tokens": []}

    # ------------------------------------------------------------------
    # Cosmos LCD API helpers
    # ------------------------------------------------------------------

    def _call_tx_search_sent(self, address: str, pagination_key: Optional[str] = None) -> dict:
        """Search for transactions sent by address.

        Args:
            address: Akash address
            pagination_key: base64 pagination key from previous response

        Returns:
            API response with 'tx_responses' list and 'pagination' info
        """
        params = {
            "events": f"message.sender='{address}'",
            "pagination.limit": str(PAGE_LIMIT),
            "order_by": "ORDER_BY_ASC",
        }
        if pagination_key:
            params["pagination.key"] = pagination_key
        try:
            return self._get("/cosmos/tx/v1beta1/txs", params=params)
        except Exception as exc:
            logger.warning("AkashFetcher: sent tx search failed: %s", exc)
            return {"tx_responses": [], "pagination": {}}

    def _call_tx_search_received(self, address: str, pagination_key: Optional[str] = None) -> dict:
        """Search for transactions received by address.

        Args:
            address: Akash address
            pagination_key: base64 pagination key from previous response

        Returns:
            API response with 'tx_responses' list and 'pagination' info
        """
        params = {
            "events": f"transfer.recipient='{address}'",
            "pagination.limit": str(PAGE_LIMIT),
            "order_by": "ORDER_BY_ASC",
        }
        if pagination_key:
            params["pagination.key"] = pagination_key
        try:
            return self._get("/cosmos/tx/v1beta1/txs", params=params)
        except Exception as exc:
            logger.warning("AkashFetcher: received tx search failed: %s", exc)
            return {"tx_responses": [], "pagination": {}}

    def _get(self, path: str, params: Optional[dict] = None, attempt: int = 0) -> dict:
        """Make a GET request to the Cosmos LCD API with rate limiting and retry.

        Args:
            path: API path (e.g. '/cosmos/bank/v1beta1/balances/akash1...')
            params: query parameters dict
            attempt: retry counter (starts at 0)

        Returns:
            Parsed JSON response dict

        Raises:
            Exception: after MAX_RETRIES exhausted
        """
        # Rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

        endpoint = AKASH_LCD_ENDPOINTS[self._endpoint_index]
        url = f"{endpoint}{path}"

        # Extract call_type from path for cost tracking (use last non-empty segment)
        path_segment = path.strip("/").split("/")[-1] if path else "unknown"

        try:
            if self.cost_tracker:
                with self.cost_tracker.track("akash", "cosmos_lcd", path_segment):
                    response = requests.get(url, params=params, timeout=30)
            else:
                response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as exc:
            if attempt < MAX_RETRIES:
                # Rotate to next endpoint
                self._endpoint_index = (self._endpoint_index + 1) % len(AKASH_LCD_ENDPOINTS)
                logger.warning(
                    "AkashFetcher: request failed (%s), retrying with endpoint %s",
                    exc, AKASH_LCD_ENDPOINTS[self._endpoint_index],
                )
                time.sleep(RATE_LIMIT_DELAY * (2 ** attempt))
                return self._get(path, params, attempt + 1)
            raise

    # ------------------------------------------------------------------
    # Transaction parsing
    # ------------------------------------------------------------------

    def _parse_to_unified(
        self,
        tx_resp: dict,
        address: str,
        wallet_id: int,
        user_id: int,
    ) -> Optional[dict]:
        """Parse Cosmos tx_response into unified transactions table row.

        Args:
            tx_resp: Cosmos tx_response dict (from /cosmos/tx/v1beta1/txs)
            address: wallet address (used to determine direction)
            wallet_id: DB wallet id
            user_id: DB user id

        Returns:
            dict ready for INSERT, or None if transaction should be skipped
        """
        tx_hash = tx_resp.get("txhash", "")
        if not tx_hash:
            return None

        # Skip failed transactions (code != 0)
        code = tx_resp.get("code", 0)
        if code != 0:
            return None

        block_timestamp = tx_resp.get("timestamp", "")  # ISO 8601 with Z suffix

        # Parse messages for amount/direction
        tx = tx_resp.get("tx", {})
        body = tx.get("body", {})
        messages = body.get("messages", [])

        action_type = "self"
        amount = "0"
        token_id = "AKT"
        tx_type = "unknown"

        for msg in messages:
            msg_type = msg.get("@type", "")
            tx_type = msg_type.split(".")[-1] if msg_type else "unknown"

            if "MsgSend" in msg_type:
                sender = msg.get("from_address", "")
                recipient = msg.get("to_address", "")
                amounts = msg.get("amount", [])
                if amounts:
                    amt = amounts[0]
                    amount = amt.get("amount", "0")
                    denom = amt.get("denom", "uakt")
                    token_id = "AKT" if denom == "uakt" else denom

                if sender.lower() == address.lower():
                    action_type = "out"
                elif recipient.lower() == address.lower():
                    action_type = "in"
                break

            elif "MsgDelegate" in msg_type or "MsgUndelegate" in msg_type:
                delegator = msg.get("delegator_address", "")
                amt = msg.get("amount", {})
                amount = amt.get("amount", "0") if isinstance(amt, dict) else "0"
                token_id = "AKT"
                if delegator.lower() == address.lower():
                    action_type = "out" if "MsgDelegate" in msg_type else "in"
                break

            elif "MsgWithdrawDelegatorReward" in msg_type:
                delegator = msg.get("delegator_address", "")
                if delegator.lower() == address.lower():
                    action_type = "in"  # Claiming rewards = incoming
                token_id = "AKT"
                break

            elif "MsgCreateDeployment" in msg_type or "MsgCloseDeployment" in msg_type:
                owner = msg.get("owner", "") or msg.get("id", {}).get("owner", "")
                if owner.lower() == address.lower():
                    action_type = "out"  # Deployment creation/closure spends AKT
                break

        # Fee extraction
        auth_info = tx.get("auth_info", {})
        fee_info = auth_info.get("fee", {})
        fee_amounts = fee_info.get("amount", [])
        fee = "0"
        if fee_amounts:
            fee = fee_amounts[0].get("amount", "0")

        return {
            "tx_hash": tx_hash,
            "block_timestamp": block_timestamp,
            "action_type": action_type,
            "token_id": token_id,
            "amount": amount,
            "fee": fee,
            "raw_data": {
                "tx_type": tx_type,
                "height": tx_resp.get("height"),
                "code": code,
                "gas_used": tx_resp.get("gas_used"),
                "timestamp": block_timestamp,
            },
        }
