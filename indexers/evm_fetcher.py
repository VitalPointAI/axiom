"""
EVM chain transaction fetcher using Etherscan V2 API.

Implements ChainFetcher ABC for Ethereum, Polygon, Cronos, and Optimism.
Stores all transactions in the unified transactions table via PostgreSQL.

Migrated from evm_indexer.py (SQLite + EVMIndexer) to:
- PostgreSQL via indexers.db pool
- Unified transactions table schema
- ChainFetcher ABC interface
- Etherscan V2 pagination (10000 per page)
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests
from psycopg2.extras import execute_values

from indexers.chain_plugin import ChainFetcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Etherscan V2 endpoint (single endpoint for all EVM chains via chainid param)
# ---------------------------------------------------------------------------
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"

# ---------------------------------------------------------------------------
# Pagination constants
# ---------------------------------------------------------------------------
PAGE_SIZE = 10000  # Etherscan max results per page

# ---------------------------------------------------------------------------
# Chain configurations
# ---------------------------------------------------------------------------
CHAIN_CONFIG: Dict[str, Dict[str, Any]] = {
    "ETH": {
        "name": "Ethereum",
        "chainid": 1,
        "decimals": 18,
        "symbol": "ETH",
        "free_tier": True,
    },
    "Polygon": {
        "name": "Polygon",
        "chainid": 137,
        "decimals": 18,
        "symbol": "MATIC",
        "free_tier": True,
    },
    "Cronos": {
        "name": "Cronos",
        "chainid": 25,
        "decimals": 18,
        "symbol": "CRO",
        "free_tier": True,
        "custom_api": "https://cronos.org/explorer/api",
        "api_key_env": "CRONOS_API_KEY",
    },
    "Optimism": {
        "name": "Optimism",
        "chainid": 10,
        "decimals": 18,
        "symbol": "ETH",
        "free_tier": False,
    },
}

# Map CHAIN_CONFIG keys to the lowercase chain names used in the transactions table
CHAIN_NAME_MAP: Dict[str, str] = {
    "ETH": "ethereum",
    "Polygon": "polygon",
    "Cronos": "cronos",
    "Optimism": "optimism",
}

# Map lowercase chain names (as stored in wallets.chain) back to CHAIN_CONFIG keys
CHAIN_KEY_MAP: Dict[str, str] = {v: k for k, v in CHAIN_NAME_MAP.items()}
# Also map the raw wallet.chain values (may be uppercase short names)
CHAIN_KEY_MAP.update({"eth": "ETH", "ETH": "ETH", "polygon": "Polygon", "cronos": "Cronos", "optimism": "Optimism"})

# ---------------------------------------------------------------------------
# EVMFetcher
# ---------------------------------------------------------------------------

class EVMFetcher(ChainFetcher):
    """
    EVM chain handler for IndexerService.

    Fetches complete transaction history for a wallet via Etherscan V2 API
    with full pagination support. Stores transactions in PostgreSQL using
    ON CONFLICT DO NOTHING for duplicate safety.

    Supports job types: evm_full_sync, evm_incremental.
    """

    chain_name: str = "evm"
    supported_job_types: list = ["evm_full_sync", "evm_incremental"]

    def __init__(self, pool):
        super().__init__(pool)
        self.api_key = os.environ.get("ETHERSCAN_API_KEY")

    # ------------------------------------------------------------------
    # Public API: ChainFetcher ABC methods
    # ------------------------------------------------------------------

    def sync_wallet(self, job: dict) -> None:
        """
        Process a full_sync or incremental_sync job for an EVM wallet.

        Args:
            job: dict with keys: id, user_id, wallet_id, chain, cursor,
                 job_type, attempts, account_id

        Fetches all transaction types (normal, internal, ERC20, NFT),
        upserts into transactions table, and updates the job cursor to
        the highest block number seen.
        """
        wallet_address = job["account_id"]
        chain_str = job["chain"]  # e.g. 'ethereum', 'polygon'
        job_id = job["id"]
        wallet_id = job["wallet_id"]
        user_id = job["user_id"]

        # Resolve chain config key from chain string
        chain_key = CHAIN_KEY_MAP.get(chain_str, chain_str)
        if chain_key not in CHAIN_CONFIG:
            raise ValueError(
                f"Unsupported EVM chain: {chain_str!r}. "
                f"Supported: {list(CHAIN_NAME_MAP.keys())}"
            )
        chain_config = CHAIN_CONFIG[chain_key]
        chain_db = CHAIN_NAME_MAP[chain_key]  # lowercase for DB column

        # Start from cursor (incremental) or block 0 (full sync)
        start_block = int(job["cursor"]) if job.get("cursor") else 0

        logger.info(
            "EVM sync: %s on %s from block %s (job_id=%s)",
            wallet_address,
            chain_str,
            start_block,
            job_id,
        )

        # Fetch all transaction types
        all_rows, max_block = self._fetch_all_tx_types(
            wallet_address, chain_config, chain_db, start_block, wallet_id, user_id
        )

        # Bulk upsert
        if all_rows:
            self._batch_upsert(all_rows)

        # Update job cursor to max block seen
        if max_block > 0:
            self._update_job_cursor(job_id, str(max_block), len(all_rows))
        else:
            self._update_job_cursor(job_id, job.get("cursor"), len(all_rows))

        logger.info(
            "EVM sync complete: %s on %s — %d rows upserted, max_block=%s",
            wallet_address,
            chain_str,
            len(all_rows),
            max_block,
        )

    def get_balance(self, address: str) -> dict:
        """
        Get native token balance for an EVM address via Etherscan V2.

        Requires chain context; returns a generic dict. For use in
        reconciliation checks when chain is known at call site.

        Returns:
            dict with native_balance (str in wei) and tokens (empty list)
        """
        # Default to ETH config when called without chain context
        chain_config = CHAIN_CONFIG["ETH"]
        params = {
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": "latest",
        }
        data = self._request(params, chain_config)
        balance_wei = data.get("result", "0") if data.get("status") == "1" else "0"
        return {
            "native_balance": balance_wei,
            "tokens": [],
        }

    # ------------------------------------------------------------------
    # Core fetch methods
    # ------------------------------------------------------------------

    def _fetch_all_tx_types(
        self,
        wallet_address: str,
        chain_config: dict,
        chain_db: str,
        start_block: int,
        wallet_id: int,
        user_id: int,
    ):
        """
        Fetch all four transaction types and transform them.

        Returns:
            (all_rows, max_block) tuple
        """
        all_rows = []
        max_block = 0

        base_params = {
            "address": wallet_address,
            "startblock": str(start_block),
            "endblock": "99999999",
            "sort": "asc",
        }

        # 1. Normal transactions (ETH/native transfers)
        normal_params = {**base_params, "module": "account", "action": "txlist"}
        normal_txs = self._fetch_paginated(normal_params, chain_config)
        for tx in normal_txs:
            row = self._transform_tx(tx, wallet_address, chain_db, "transfer", chain_config)
            if row:
                row["wallet_id"] = wallet_id
                row["user_id"] = user_id
                all_rows.append(row)
                block = int(tx.get("blockNumber", 0))
                if block > max_block:
                    max_block = block

        # 2. Internal transactions (contract calls with value)
        internal_params = {**base_params, "module": "account", "action": "txlistinternal"}
        internal_txs = self._fetch_paginated(internal_params, chain_config)
        for tx in internal_txs:
            row = self._transform_tx(tx, wallet_address, chain_db, "internal", chain_config)
            if row:
                row["wallet_id"] = wallet_id
                row["user_id"] = user_id
                all_rows.append(row)
                block = int(tx.get("blockNumber", 0))
                if block > max_block:
                    max_block = block

        # 3. ERC20 token transfers
        erc20_params = {**base_params, "module": "account", "action": "tokentx"}
        erc20_txs = self._fetch_paginated(erc20_params, chain_config)
        for tx in erc20_txs:
            row = self._transform_tx(tx, wallet_address, chain_db, "erc20", chain_config)
            if row:
                row["wallet_id"] = wallet_id
                row["user_id"] = user_id
                all_rows.append(row)
                block = int(tx.get("blockNumber", 0))
                if block > max_block:
                    max_block = block

        # 4. NFT (ERC721) transfers
        nft_params = {**base_params, "module": "account", "action": "tokennfttx"}
        nft_txs = self._fetch_paginated(nft_params, chain_config)
        for tx in nft_txs:
            row = self._transform_tx(tx, wallet_address, chain_db, "nft", chain_config)
            if row:
                row["wallet_id"] = wallet_id
                row["user_id"] = user_id
                all_rows.append(row)
                block = int(tx.get("blockNumber", 0))
                if block > max_block:
                    max_block = block

        return all_rows, max_block

    def _fetch_paginated(self, params: dict, chain_config: dict) -> List[dict]:
        """
        Paginate through Etherscan API results until all pages are fetched.

        Loops until the result count is less than PAGE_SIZE (10000).
        Adds 0.25s delay between requests to respect Etherscan rate limits.

        Args:
            params: Base API params (module, action, address, etc.)
            chain_config: Chain configuration dict from CHAIN_CONFIG

        Returns:
            Concatenated list of all result items across all pages
        """
        all_results = []
        page = 1

        while True:
            page_params = {
                **params,
                "page": str(page),
                "offset": str(PAGE_SIZE),
            }
            data = self._request(page_params, chain_config)

            if data.get("status") != "1":
                # No results or error — stop pagination
                break

            results = data.get("result", [])
            if not isinstance(results, list):
                break

            all_results.extend(results)

            # Stop if we got fewer than a full page
            if len(results) < PAGE_SIZE:
                break

            page += 1
            time.sleep(0.25)  # 4 req/sec max for Etherscan free tier

        return all_results

    def _request(self, params: dict, chain_config: dict) -> dict:
        """
        Make a single API request using the appropriate endpoint.

        For chains with custom_api (Cronos), uses that URL directly.
        For standard chains, uses Etherscan V2 with chainid param.

        Args:
            params: API query parameters
            chain_config: Chain configuration dict from CHAIN_CONFIG

        Returns:
            Parsed JSON response dict
        """
        request_params = dict(params)

        if "custom_api" in chain_config:
            api_url = chain_config["custom_api"]
            api_key_env = chain_config.get("api_key_env", "ETHERSCAN_API_KEY")
            api_key = os.environ.get(api_key_env) or self.api_key
            if api_key:
                request_params["apikey"] = api_key
        else:
            api_url = ETHERSCAN_V2_URL
            request_params["chainid"] = str(chain_config["chainid"])
            if self.api_key:
                request_params["apikey"] = self.api_key

        try:
            response = requests.get(api_url, params=request_params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("Etherscan request failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Transaction transformation
    # ------------------------------------------------------------------

    def _transform_tx(
        self,
        raw_tx: dict,
        wallet_address: str,
        chain: str,
        tx_type: str,
        chain_config: dict,
    ) -> Optional[dict]:
        """
        Transform a raw Etherscan transaction dict into a transactions table row.

        Args:
            raw_tx: Raw JSON from Etherscan API
            wallet_address: Wallet address (for direction detection)
            chain: Lowercase chain name for DB column (e.g. 'ethereum')
            tx_type: 'transfer' | 'internal' | 'erc20' | 'nft'
            chain_config: Chain configuration dict

        Returns:
            Dict matching transactions table columns, or None on error.
        """
        try:
            raw_hash = raw_tx.get("hash", "")
            log_index = raw_tx.get("logIndex")

            # ERC20 and NFT: append logIndex to hash to avoid dedup conflicts
            # Multiple transfers can share the same parent tx_hash
            if tx_type in ("erc20", "nft") and log_index is not None:
                tx_hash = f"{raw_hash}-{log_index}"
                receipt_id = raw_hash  # original hash for cross-referencing
            else:
                tx_hash = raw_hash
                receipt_id = raw_tx.get("hash", "")

            # Direction: compare addresses case-insensitively
            from_addr = (raw_tx.get("from") or "").lower()
            to_addr = (raw_tx.get("to") or "").lower()
            wallet_lower = wallet_address.lower()

            if to_addr == wallet_lower:
                direction = "in"
                counterparty = raw_tx.get("from") or ""
            elif from_addr == wallet_lower:
                direction = "out"
                counterparty = raw_tx.get("to") or ""
            else:
                # Self-transaction or contract interaction — default to 'out'
                direction = "out"
                counterparty = raw_tx.get("to") or raw_tx.get("from") or ""

            # Amount: raw value in wei / token units as NUMERIC(40,0)
            amount = None
            raw_value = raw_tx.get("value", "0")
            try:
                amount = int(raw_value) if raw_value else 0
            except (ValueError, TypeError):
                amount = 0

            # Fee: only for normal transactions (internal/ERC20/NFT don't have own gas)
            fee = None
            if tx_type == "transfer":
                gas_used = raw_tx.get("gasUsed", "0") or "0"
                gas_price = raw_tx.get("gasPrice", "0") or "0"
                try:
                    fee = int(gas_used) * int(gas_price)
                except (ValueError, TypeError):
                    fee = 0

            # Block info
            block_height = None
            block_timestamp = None
            try:
                block_height = int(raw_tx.get("blockNumber", 0) or 0)
                block_timestamp = int(raw_tx.get("timeStamp", 0) or 0)
            except (ValueError, TypeError):
                pass

            # Success
            is_error = raw_tx.get("isError", "0")
            success = is_error == "0" or is_error is None

            # Token / contract address
            # For ERC20/NFT: contractAddress is the token contract
            # For normal/internal: None
            token_id = None
            if tx_type in ("erc20", "nft"):
                token_id = raw_tx.get("contractAddress") or None

            return {
                # wallet_id and user_id are injected by caller
                "wallet_id": None,
                "user_id": None,
                "tx_hash": tx_hash,
                "receipt_id": receipt_id,
                "chain": chain,
                "direction": direction,
                "counterparty": counterparty,
                "action_type": tx_type,
                "method_name": None,
                "amount": amount,
                "fee": fee,
                "token_id": token_id,
                "block_height": block_height,
                "block_timestamp": block_timestamp,
                "success": success,
                "raw_data": raw_tx,
            }

        except Exception as exc:
            logger.warning("_transform_tx error for tx %s: %s", raw_tx.get("hash"), exc)
            return None

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _batch_upsert(self, rows: List[dict]) -> None:
        """
        Batch-upsert transformed transaction rows using ON CONFLICT DO NOTHING.

        The unique constraint (chain, tx_hash, receipt_id, wallet_id) prevents
        duplicate inserts on re-runs.
        """
        if not rows:
            return

        columns = [
            "user_id", "wallet_id", "tx_hash", "receipt_id", "chain",
            "direction", "counterparty", "action_type", "method_name",
            "amount", "fee", "token_id", "block_height", "block_timestamp",
            "success", "raw_data",
        ]

        values = []
        for r in rows:
            raw_data = r.get("raw_data")
            values.append((
                r["user_id"],
                r["wallet_id"],
                r["tx_hash"],
                r["receipt_id"],
                r["chain"],
                r["direction"],
                r["counterparty"],
                r["action_type"],
                r.get("method_name"),
                r.get("amount"),
                r.get("fee"),
                r.get("token_id"),
                r.get("block_height"),
                r.get("block_timestamp"),
                r.get("success", True),
                json.dumps(raw_data) if raw_data is not None else None,
            ))

        col_str = ", ".join(columns)
        sql = f"""
            INSERT INTO transactions ({col_str})
            VALUES %s
            ON CONFLICT (chain, tx_hash, receipt_id, wallet_id) DO NOTHING
        """

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            execute_values(cur, sql, values)
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def _update_job_cursor(
        self,
        job_id: int,
        cursor: Optional[str],
        progress_fetched: int,
    ) -> None:
        """Update job cursor (max block number seen) and progress_fetched."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE indexing_jobs
                SET cursor = %s,
                    progress_fetched = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (cursor, progress_fetched, job_id),
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
