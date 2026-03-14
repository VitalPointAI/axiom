"""XRP Ledger chain fetcher — implements ChainFetcher ABC for the Axiom indexer.

Uses the public XRPL JSON-RPC API (no API key required).
Fetches account transactions and stores them in the unified transactions table.

API reference: https://xrpl.org/public-api-methods.html#account_tx

Amount encoding:
- Native XRP is stored in drops (integer); 1 XRP = 1,000,000 drops
- Transactions are stored in the transactions table with amount as NUMERIC(40,0)
  (drops, matching the on-chain representation)
- Issued currency amounts (e.g. USDC on XRPL) are stored as string quantities
  scaled by token decimals when available

Direction encoding:
- action_type = 'out' when the wallet address is the sender (tx.Account)
- action_type = 'in'  when the wallet address is the destination (tx.Destination)
- action_type = 'self' for escrow/trust/offer ops that don't clearly transfer value

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
# XRPL public endpoints (mainnet)
# ---------------------------------------------------------------------------
XRPL_ENDPOINTS = [
    "https://xrplcluster.com",
    "https://s1.ripple.com:51234",
    "https://s2.ripple.com:51234",
]

# Ripple epoch offset — Ripple time is seconds since 2000-01-01 00:00:00 UTC
RIPPLE_EPOCH_OFFSET = 946684800

# Rate limiting
RATE_LIMIT_DELAY = 0.5  # 2 requests per second
MAX_RETRIES = 3
PAGE_LIMIT = 200  # transactions per page

# XRP decimals
XRP_DECIMALS = 6  # 1 XRP = 1,000,000 drops


class XRPFetcher(ChainFetcher):
    """XRP Ledger chain fetcher stub.

    Implements ChainFetcher ABC for the Axiom indexer service.
    Handles xrp_full_sync and xrp_incremental job types.

    Registered in service.py:
        "xrp_full_sync":   XRPFetcher(pool)
        "xrp_incremental": XRPFetcher(pool)
    """

    chain_name = "xrp"
    supported_job_types = ["xrp_full_sync", "xrp_incremental"]

    def __init__(self, pool):
        super().__init__(pool)
        self._endpoint_index = 0
        self._last_request_time = 0
        logger.warning("XRPFetcher is a STUB implementation — untested against live XRPL API")

    # ------------------------------------------------------------------
    # ChainFetcher ABC methods
    # ------------------------------------------------------------------

    def sync_wallet(self, job: dict) -> None:
        """Fetch XRP transactions for a wallet and upsert into transactions table.

        Args:
            job: dict with keys: id, user_id, wallet_id, account_id (wallet address),
                 cursor (last ledger index for incremental resume), job_type

        Cursor usage:
            cursor stores the last-seen ledger index as a string.
            Full sync: cursor=None, fetches all history.
            Incremental: cursor=str(last_ledger), fetches from that ledger onward.
        """
        wallet_id = job["wallet_id"]
        user_id = job["user_id"]
        address = job["account_id"]
        job_id = job["id"]
        cursor_str = job.get("cursor")

        # Parse cursor: last ledger index (0 = fetch all)
        since_ledger = int(cursor_str) if cursor_str and cursor_str.isdigit() else 0

        logger.info(
            "XRPFetcher.sync_wallet: address=%s wallet_id=%s since_ledger=%s",
            address, wallet_id, since_ledger,
        )

        # Fetch transaction pages from XRPL
        all_txs = []
        marker = None
        max_ledger_seen = since_ledger

        while True:
            result = self._call_account_tx(address, marker=marker)
            transactions = result.get("transactions", [])
            if not transactions:
                break

            for tx_wrapper in transactions:
                tx = tx_wrapper.get("tx", {})
                ledger_index = tx.get("ledger_index", 0)
                if since_ledger > 0 and ledger_index <= since_ledger:
                    continue  # Skip already-indexed ledgers
                all_txs.append(tx_wrapper)
                max_ledger_seen = max(max_ledger_seen, ledger_index)

            marker = result.get("marker")
            if not marker:
                break  # No more pages

            logger.debug("XRPFetcher: fetched %d txs, continuing pagination...", len(all_txs))

        logger.info("XRPFetcher: fetched %d new transactions for address=%s", len(all_txs), address)

        if not all_txs:
            return

        # Insert into unified transactions table
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            inserted = 0

            for tx_wrapper in all_txs:
                row = self._parse_to_unified(tx_wrapper, address, wallet_id, user_id)
                if row is None:
                    continue

                cur.execute(
                    """
                    INSERT INTO transactions
                        (wallet_id, user_id, chain, tx_hash, block_timestamp,
                         action_type, token_id, amount, fee, raw_data)
                    VALUES (%s, %s, %s, %s, to_timestamp(%s),
                            %s, %s, %s, %s, %s)
                    ON CONFLICT (wallet_id, tx_hash) DO NOTHING
                    """,
                    (
                        wallet_id,
                        user_id,
                        "xrp",
                        row["tx_hash"],
                        row["timestamp"],
                        row["action_type"],
                        row["token_id"],
                        row["amount"],
                        row["fee"],
                        json.dumps(row["raw_data"]),
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1

            # Update job cursor to resume from last seen ledger
            if max_ledger_seen > since_ledger:
                cur.execute(
                    """
                    UPDATE indexing_jobs
                    SET cursor = %s, progress_fetched = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (str(max_ledger_seen), inserted, job_id),
                )

            conn.commit()
            cur.close()
            logger.info(
                "XRPFetcher: inserted %d transactions for wallet_id=%s (max_ledger=%s)",
                inserted, wallet_id, max_ledger_seen,
            )

        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def get_balance(self, address: str) -> dict:
        """Get current XRP balance for the given address.

        Args:
            address: XRP Ledger address (starts with 'r')

        Returns:
            dict with:
                native_balance: str — XRP balance in human-readable units (drops / 1e6)
                tokens: list[dict] — token balances from trust lines (empty stub)
        """
        try:
            result = self._call_account_info(address)
            account_data = result.get("account_data", {})
            balance_drops = account_data.get("Balance", "0")
            balance_xrp = str(Decimal(balance_drops) / Decimal(10 ** XRP_DECIMALS))
            return {
                "native_balance": balance_xrp,
                "tokens": [],  # Trust line tokens not yet implemented
            }
        except Exception as exc:
            logger.warning("XRPFetcher.get_balance failed for address=%s: %s", address, exc)
            return {"native_balance": "0", "tokens": []}

    # ------------------------------------------------------------------
    # XRPL API helpers
    # ------------------------------------------------------------------

    def _call_account_tx(self, address: str, marker: Optional[dict] = None) -> dict:
        """Call account_tx to get transaction page.

        Args:
            address: XRP Ledger address
            marker: pagination marker from previous response (or None for first page)

        Returns:
            API result dict with 'transactions' list and optional 'marker'
        """
        params = {
            "account": address,
            "ledger_index_min": -1,
            "ledger_index_max": -1,
            "binary": False,
            "forward": True,  # Oldest first for proper cursor tracking
            "limit": PAGE_LIMIT,
        }
        if marker:
            params["marker"] = marker

        result = self._json_rpc("account_tx", params)
        return result

    def _call_account_info(self, address: str) -> dict:
        """Call account_info to get balance.

        Args:
            address: XRP Ledger address

        Returns:
            API result dict with 'account_data' containing 'Balance' in drops
        """
        return self._json_rpc("account_info", {
            "account": address,
            "ledger_index": "validated",
        })

    def _json_rpc(self, method: str, params: dict, attempt: int = 0) -> dict:
        """Make a JSON-RPC request with rate limiting and endpoint rotation.

        Args:
            method: XRPL method name (e.g. 'account_tx')
            params: method parameters dict
            attempt: retry counter (starts at 0)

        Returns:
            Parsed result dict from the XRPL response

        Raises:
            Exception: on API error or after MAX_RETRIES exhausted
        """
        # Rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

        endpoint = XRPL_ENDPOINTS[self._endpoint_index]
        payload = {"method": method, "params": [params]}

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            result = data.get("result", data)
            if result.get("status") == "error":
                error = result.get("error", "unknown")
                error_msg = result.get("error_message", "")
                raise Exception(f"XRPL error: {error} — {error_msg}")

            return result

        except requests.exceptions.RequestException as exc:
            if attempt < MAX_RETRIES:
                # Rotate to next endpoint
                self._endpoint_index = (self._endpoint_index + 1) % len(XRPL_ENDPOINTS)
                logger.warning(
                    "XRPFetcher: request failed (%s), retrying with endpoint %s",
                    exc, XRPL_ENDPOINTS[self._endpoint_index],
                )
                time.sleep(RATE_LIMIT_DELAY * (2 ** attempt))
                return self._json_rpc(method, params, attempt + 1)
            raise

    # ------------------------------------------------------------------
    # Transaction parsing
    # ------------------------------------------------------------------

    def _parse_to_unified(
        self,
        tx_wrapper: dict,
        address: str,
        wallet_id: int,
        user_id: int,
    ) -> Optional[dict]:
        """Parse XRPL transaction wrapper into unified transactions table row.

        Args:
            tx_wrapper: dict with 'tx' (transaction) and 'meta' (metadata) keys
            address: wallet address (used to determine direction)
            wallet_id: DB wallet id
            user_id: DB user id

        Returns:
            dict ready for INSERT, or None if transaction should be skipped
        """
        tx = tx_wrapper.get("tx", {})
        meta = tx_wrapper.get("meta", {})

        tx_hash = tx.get("hash", "")
        if not tx_hash:
            return None

        # Skip failed transactions
        result_code = meta.get("TransactionResult", "tesSUCCESS")
        if result_code != "tesSUCCESS":
            return None

        # Timestamp: Ripple epoch -> Unix epoch
        ripple_time = tx.get("date", 0)
        unix_timestamp = ripple_time + RIPPLE_EPOCH_OFFSET

        tx_type = tx.get("TransactionType", "Unknown")
        sender = tx.get("Account", "")
        destination = tx.get("Destination", "")

        # Determine direction
        is_sender = sender.lower() == address.lower()
        is_recipient = destination.lower() == address.lower()
        if is_sender:
            action_type = "out"
        elif is_recipient:
            action_type = "in"
        else:
            action_type = "self"  # Escrow/OfferCreate/TrustSet — no clear transfer

        # Amount
        amount_raw = tx.get("Amount", "0")
        if isinstance(amount_raw, str):
            # Native XRP in drops (store raw as NUMERIC 40,0)
            amount = amount_raw
            token_id = "XRP"
        elif isinstance(amount_raw, dict):
            # Issued currency (store quantity * 10^currency_precision approximation)
            amount = str(int(Decimal(amount_raw.get("value", "0"))))
            token_id = amount_raw.get("currency", "UNKNOWN")
        else:
            amount = "0"
            token_id = "XRP"

        # Fee in drops (store raw)
        fee = tx.get("Fee", "0")

        return {
            "tx_hash": tx_hash,
            "timestamp": unix_timestamp,
            "action_type": action_type,
            "token_id": token_id,
            "amount": amount,
            "fee": fee,
            "raw_data": {
                "TransactionType": tx_type,
                "Account": sender,
                "Destination": destination,
                "ledger_index": tx.get("ledger_index"),
                "Sequence": tx.get("Sequence"),
                "TransactionResult": result_code,
            },
        }
