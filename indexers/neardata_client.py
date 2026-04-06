"""Synchronous neardata.xyz client for historical block scanning.

Fetches blocks from neardata.xyz (free, no API key, no rate limits)
and filters for wallet-relevant transactions.

Used by NearFetcher for full_sync and incremental_sync jobs.
"""

import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

NEARDATA_BASE = os.environ.get("NEARDATA_API_URL", "https://mainnet.neardata.xyz")
MAX_RETRIES = 5
RETRY_BASE_DELAY = 1.0
MAX_RETRY_DELAY = 30.0


class NeardataClient:
    """Synchronous neardata.xyz client for block-level scanning."""

    def __init__(self, base_url=None):
        self.base_url = base_url or NEARDATA_BASE
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=25, pool_maxsize=25,
        )
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers["User-Agent"] = "Axiom/1.0"

    def get_final_block_height(self) -> int:
        """Get the latest finalized block height."""
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(
                    f"{self.base_url}/v0/last_block/final", timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["block"]["header"]["height"]
                if resp.status_code == 429 or resp.status_code >= 500:
                    self._backoff(attempt)
                    continue
                resp.raise_for_status()
            except requests.RequestException:
                self._backoff(attempt)
        raise RuntimeError("Failed to get final block height after retries")

    def fetch_block(self, height: int) -> dict | None:
        """Fetch a single block. Returns parsed dict or None for missing blocks."""
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(
                    f"{self.base_url}/v0/block/{height}", timeout=15
                )
                if resp.status_code == 200:
                    text = resp.text
                    if not text or text.strip() == "null":
                        return None
                    return json.loads(text)
                if resp.status_code == 429 or resp.status_code >= 500:
                    self._backoff(attempt)
                    continue
                return None
            except requests.RequestException:
                self._backoff(attempt)
        return None

    def extract_wallet_txs(self, block: dict, account_id: str) -> list[dict]:
        """Extract transactions involving account_id from a neardata block.

        Converts neardata format to NearBlocks-compatible dicts so the
        existing parse_transaction() function can process them unchanged.

        Returns list of dicts matching the NearBlocks API response format.
        """
        if not block:
            return []

        header = block.get("block", {}).get("header", {})
        block_height = header.get("height", 0)
        block_timestamp = header.get("timestamp", 0)

        account_lower = account_id.lower()
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

                if signer == account_lower or receiver == account_lower:
                    seen_hashes.add(tx_hash)
                    # Convert to NearBlocks-compatible format
                    results.append(
                        self._to_nearblocks_format(
                            tx_data, tx, block_height, block_timestamp
                        )
                    )

            # Check receipt execution outcomes
            for receipt_outcome in shard.get("receipt_execution_outcomes", []):
                receipt = receipt_outcome.get("receipt", {})
                predecessor = receipt.get("predecessor_id", "").lower()
                receiver = receipt.get("receiver_id", "").lower()

                if predecessor == account_lower or receiver == account_lower:
                    receipt_id = receipt.get("receipt_id", "")

                    if receipt_id and receipt_id not in seen_hashes:
                        seen_hashes.add(receipt_id)
                        results.append(
                            self._receipt_to_nearblocks_format(
                                receipt, receipt_outcome, block_height,
                                block_timestamp, receipt_id
                            )
                        )

        return results

    def _to_nearblocks_format(self, tx_data, tx_wrapper, block_height, block_timestamp):
        """Convert a neardata transaction to NearBlocks API format.

        This lets parse_transaction() work unchanged.
        """
        # Extract actions — neardata stores them differently
        actions = []
        for action in tx_data.get("actions", []):
            if isinstance(action, str):
                # Simple action like "CreateAccount"
                actions.append({"action": action.upper()})
            elif isinstance(action, dict):
                # Complex action like {"FunctionCall": {...}}
                for action_type, params in action.items():
                    act = {"action": self._normalize_action_type(action_type)}
                    if action_type == "FunctionCall":
                        act["method"] = params.get("method_name", "")
                        act["deposit"] = params.get("deposit", "0")
                        # Args may be base64
                        act["args"] = params.get("args", "")
                    elif action_type == "Transfer":
                        act["deposit"] = params.get("deposit", "0")
                    elif action_type == "Stake":
                        act["stake"] = params.get("stake", "0")
                        act["public_key"] = params.get("public_key", "")
                    elif action_type == "AddKey":
                        act["public_key"] = params.get("public_key", "")
                        act["access_key"] = params.get("access_key", {})
                    elif action_type == "DeleteKey":
                        act["public_key"] = params.get("public_key", "")
                    elif action_type == "DeployContract":
                        pass  # No extra fields needed
                    actions.append(act)

        # Extract fee from outcome
        outcome = tx_wrapper.get("outcome", {})
        exec_outcome = outcome.get("execution_outcome", {}).get("outcome", {})
        tokens_burnt = exec_outcome.get("tokens_burnt", "0")

        # Status
        status = outcome.get("execution_outcome", {}).get("outcome", {}).get("status", {})
        success = "SuccessValue" in status or "SuccessReceiptId" in status

        return {
            "transaction_hash": tx_data.get("hash", ""),
            "receipt_id": None,
            "predecessor_account_id": tx_data.get("signer_id", ""),
            "receiver_account_id": tx_data.get("receiver_id", ""),
            "actions": actions,
            "block": {"block_height": block_height},
            "block_timestamp": str(block_timestamp),
            "outcomes_agg": {"transaction_fee": tokens_burnt},
            "outcomes": {"status": success},
        }

    def _receipt_to_nearblocks_format(self, receipt, receipt_outcome, block_height,
                                       block_timestamp, receipt_id):
        """Convert a receipt execution outcome to NearBlocks-compatible format."""
        exec_outcome = receipt_outcome.get("execution_outcome", {}).get("outcome", {})
        tokens_burnt = exec_outcome.get("tokens_burnt", "0")
        status = exec_outcome.get("status", {})
        success = "SuccessValue" in status or "SuccessReceiptId" in status

        # Extract actions from receipt
        actions = []
        receipt_action = receipt.get("Action", receipt.get("action", {}))
        if isinstance(receipt_action, dict):
            for action in receipt_action.get("actions", []):
                if isinstance(action, str):
                    actions.append({"action": action.upper()})
                elif isinstance(action, dict):
                    for action_type, params in action.items():
                        act = {"action": self._normalize_action_type(action_type)}
                        if action_type == "FunctionCall":
                            act["method"] = params.get("method_name", "")
                            act["deposit"] = params.get("deposit", "0")
                            act["args"] = params.get("args", "")
                        elif action_type == "Transfer":
                            act["deposit"] = params.get("deposit", "0")
                        actions.append(act)

        return {
            "transaction_hash": receipt_id,
            "receipt_id": receipt_id,
            "predecessor_account_id": receipt.get("predecessor_id", ""),
            "receiver_account_id": receipt.get("receiver_id", ""),
            "actions": actions,
            "block": {"block_height": block_height},
            "block_timestamp": str(block_timestamp),
            "outcomes_agg": {"transaction_fee": tokens_burnt},
            "outcomes": {"status": success},
        }

    @staticmethod
    def _normalize_action_type(neardata_type: str) -> str:
        """Convert neardata action type names to NearBlocks format.

        neardata uses CamelCase (FunctionCall), NearBlocks uses UPPER_SNAKE (FUNCTION_CALL).
        """
        mapping = {
            "FunctionCall": "FUNCTION_CALL",
            "Transfer": "TRANSFER",
            "Stake": "STAKE",
            "AddKey": "ADD_KEY",
            "DeleteKey": "DELETE_KEY",
            "CreateAccount": "CREATE_ACCOUNT",
            "DeleteAccount": "DELETE_ACCOUNT",
            "DeployContract": "DEPLOY_CONTRACT",
        }
        return mapping.get(neardata_type, neardata_type.upper())

    @staticmethod
    def _backoff(attempt):
        delay = min(RETRY_BASE_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
        time.sleep(delay)
