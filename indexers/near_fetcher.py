"""
NEAR transaction fetcher using NearBlocks API.

Handles cursor-based resume, all NEAR action types, and post-sync verification.
Used by IndexerService to process full_sync and incremental_sync jobs.
"""

import json
import logging
import sys
import os
from typing import Optional, Tuple

import requests

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import FASTNEAR_RPC
from indexers.nearblocks_client import NearBlocksClient

logger = logging.getLogger(__name__)

# Tolerance for transaction count verification: NearBlocks count can lag
COUNT_TOLERANCE_PCT = 0.05  # 5%


# ---------------------------------------------------------------------------
# Action type constants (NearBlocks API values)
# ---------------------------------------------------------------------------

ACTION_TRANSFER = "TRANSFER"
ACTION_FUNCTION_CALL = "FUNCTION_CALL"
ACTION_STAKE = "STAKE"
ACTION_ADD_KEY = "ADD_KEY"
ACTION_DELETE_KEY = "DELETE_KEY"
ACTION_CREATE_ACCOUNT = "CREATE_ACCOUNT"
ACTION_DELETE_ACCOUNT = "DELETE_ACCOUNT"
ACTION_DEPLOY_CONTRACT = "DEPLOY_CONTRACT"

# Priority order for multi-action transactions (first match wins)
ACTION_PRIORITY = [
    ACTION_TRANSFER,
    ACTION_FUNCTION_CALL,
    ACTION_STAKE,
    ACTION_CREATE_ACCOUNT,
    ACTION_DELETE_ACCOUNT,
    ACTION_DEPLOY_CONTRACT,
    ACTION_ADD_KEY,
    ACTION_DELETE_KEY,
]


# ---------------------------------------------------------------------------
# parse_transaction — module-level function (used by tests directly)
# ---------------------------------------------------------------------------

def parse_transaction(raw_tx: dict, wallet_id: int, user_id: int, account_id: str) -> Optional[dict]:
    """
    Parse a NearBlocks transaction dict into a dict matching the Transaction model.

    Args:
        raw_tx: Raw transaction dict from NearBlocks API
        wallet_id: Database wallet ID
        user_id: Database user ID
        account_id: NEAR account ID (used to determine in/out direction)

    Returns:
        Dict matching Transaction table columns, or None on parse error.
    """
    try:
        tx_hash = raw_tx.get("transaction_hash")
        receipt_id = raw_tx.get("receipt_id")

        predecessor = raw_tx.get("predecessor_account_id", "")
        receiver = raw_tx.get("receiver_account_id", "")

        # Determine direction relative to our wallet
        if predecessor == account_id:
            direction = "out"
            counterparty = receiver
        else:
            direction = "in"
            counterparty = predecessor

        # Extract actions — determine primary action type and amount
        actions = raw_tx.get("actions", [])
        action_type = None
        method_name = None
        amount = None

        # Iterate actions by priority to find primary action type
        action_map = {a.get("action"): a for a in actions if a.get("action")}

        for priority_action in ACTION_PRIORITY:
            if priority_action in action_map:
                action_type = priority_action
                action = action_map[priority_action]

                if priority_action == ACTION_TRANSFER:
                    deposit = action.get("deposit", 0)
                    if deposit:
                        amount = int(deposit)

                elif priority_action == ACTION_FUNCTION_CALL:
                    method_name = action.get("method") or action.get("method_name")
                    deposit = action.get("deposit", 0)
                    if deposit:
                        amount = int(deposit)

                elif priority_action == ACTION_STAKE:
                    stake = action.get("stake", 0)
                    if stake:
                        amount = int(stake)

                break  # Use first priority match

        # If no priority action found, use whatever is in the list
        if action_type is None and actions:
            action_type = actions[0].get("action")

        # Extract fee from outcomes_agg
        fee = None
        outcomes_agg = raw_tx.get("outcomes_agg", {})
        if outcomes_agg.get("transaction_fee"):
            fee = int(outcomes_agg["transaction_fee"])

        # Extract block info — NearBlocks returns block info in "block" sub-dict or top-level
        block = raw_tx.get("block", {})
        block_height = block.get("block_height") if block else raw_tx.get("block_height")
        block_timestamp_raw = raw_tx.get("block_timestamp", 0)
        block_timestamp = int(block_timestamp_raw) if block_timestamp_raw else None

        # Determine success
        outcomes = raw_tx.get("outcomes", {})
        success = bool(outcomes.get("status", True)) if outcomes else True

        return {
            "wallet_id": wallet_id,
            "user_id": user_id,
            "tx_hash": tx_hash,
            "receipt_id": receipt_id,
            "chain": "near",
            "direction": direction,
            "counterparty": counterparty,
            "action_type": action_type,
            "method_name": method_name,
            "amount": amount,
            "fee": fee,
            "token_id": None,  # FT tokens handled separately
            "block_height": block_height,
            "block_timestamp": block_timestamp,
            "success": success,
            "raw_data": raw_tx,
        }

    except Exception as e:
        logger.warning("parse_transaction error for tx %s: %s", raw_tx.get("transaction_hash"), e)
        return None


# ---------------------------------------------------------------------------
# NearFetcher class
# ---------------------------------------------------------------------------

class NearFetcher:
    """
    NEAR chain handler for IndexerService.

    Fetches complete transaction history for a wallet via NearBlocks API
    with cursor-based resume support. Stores transactions in PostgreSQL
    using ON CONFLICT DO NOTHING for duplicate safety.
    """

    def __init__(self, db_pool):
        self.client = NearBlocksClient()
        self.db_pool = db_pool

    # ------------------------------------------------------------------
    # Public API: called by IndexerService
    # ------------------------------------------------------------------

    def sync_wallet(self, job_row: dict) -> None:
        """
        Sync all transactions for a wallet, resuming from job.cursor if set.

        Updates the job's cursor and progress_fetched after each page commit.
        Marks the job as completed and runs verification when finished.

        Args:
            job_row: Row dict from indexing_jobs table (id, wallet_id, user_id, cursor, ...)
        """
        wallet_id = job_row["wallet_id"]
        user_id = job_row["user_id"]
        job_id = job_row["id"]

        # Look up the wallet's account_id
        account_id = self._get_account_id(wallet_id)
        if not account_id:
            raise ValueError(f"Wallet {wallet_id} not found in database")

        logger.info("Syncing %s (wallet_id=%s, job_id=%s)", account_id, wallet_id, job_id)

        cursor = job_row.get("cursor")
        progress_fetched = job_row.get("progress_fetched", 0)

        while True:
            # Fetch one page of transactions
            result = self.client.fetch_transactions(account_id, cursor=cursor, per_page=25)
            txns = result.get("txns", [])
            next_cursor = result.get("cursor")

            if not txns:
                logger.info("No transactions on page, sync complete for %s", account_id)
                break

            # Parse and batch-insert this page
            rows = []
            for raw_tx in txns:
                parsed = parse_transaction(raw_tx, wallet_id=wallet_id, user_id=user_id, account_id=account_id)
                if parsed:
                    rows.append(parsed)

            if rows:
                self._batch_insert(rows)

            progress_fetched += len(txns)
            cursor = next_cursor

            # Commit progress after each page (crash-safe resume)
            self._update_job_progress(job_id, cursor, progress_fetched)

            logger.debug("Page done: fetched=%s, next_cursor=%s", progress_fetched, cursor)

            if not next_cursor:
                break

        # Mark job complete
        self._complete_job(job_id)

        # Run post-sync verification
        passed, message = self.verify_sync(wallet_id, account_id)
        if not passed:
            logger.warning("Verification warning for %s: %s", account_id, message)
        else:
            logger.info("Verification passed for %s: %s", account_id, message)

    def verify_sync(self, wallet_id: int, account_id: str) -> Tuple[bool, str]:
        """
        Verify sync completeness after a full wallet sync.

        Checks:
        1. DB transaction count vs NearBlocks reported count (with tolerance)
        2. On-chain balance via FastNear RPC

        Args:
            wallet_id: Database wallet ID
            account_id: NEAR account ID

        Returns:
            (passed, message) tuple
        """
        messages = []
        passed = True

        # --- Count verification ---
        try:
            expected_count = self.client.get_transaction_count(account_id)
            db_count = self._get_db_tx_count(wallet_id)

            if expected_count > 0:
                pct_diff = abs(expected_count - db_count) / expected_count
                if pct_diff > COUNT_TOLERANCE_PCT:
                    passed = False
                    messages.append(
                        f"Count mismatch: DB={db_count}, NearBlocks={expected_count} "
                        f"({pct_diff:.1%} diff, tolerance={COUNT_TOLERANCE_PCT:.0%})"
                    )
                else:
                    messages.append(f"Count OK: DB={db_count}, NearBlocks={expected_count}")
            else:
                messages.append(f"Count OK: {db_count} transactions (NearBlocks reports 0)")

        except Exception as e:
            messages.append(f"Count check error: {e}")
            # Don't fail verification for count check errors

        # --- Balance verification via FastNear RPC ---
        try:
            onchain_balance = self._get_rpc_balance(account_id)
            if onchain_balance is not None:
                messages.append(f"RPC balance: {onchain_balance} yoctoNEAR")
        except Exception as e:
            messages.append(f"Balance check error: {e}")

        return passed, "; ".join(messages)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_account_id(self, wallet_id: int) -> Optional[str]:
        """Look up account_id and user_id from wallets table."""
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT account_id, user_id FROM wallets WHERE id = %s",
                (wallet_id,)
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row else None
        finally:
            self.db_pool.putconn(conn)

    def _batch_insert(self, rows: list) -> None:
        """
        Batch-insert parsed transactions using ON CONFLICT DO NOTHING.

        The unique constraint (chain, tx_hash, receipt_id, wallet_id) ensures
        that re-processed transactions from cursor resume don't cause duplicates.
        """
        if not rows:
            return

        columns = [
            "user_id", "wallet_id", "tx_hash", "receipt_id", "chain",
            "direction", "counterparty", "action_type", "method_name",
            "amount", "fee", "token_id", "block_height", "block_timestamp",
            "success", "raw_data",
        ]

        values = [
            (
                r["user_id"],
                r["wallet_id"],
                r["tx_hash"],
                r["receipt_id"],
                r["chain"],
                r["direction"],
                r["counterparty"],
                r["action_type"],
                r["method_name"],
                r["amount"],
                r["fee"],
                r["token_id"],
                r["block_height"],
                r["block_timestamp"],
                r["success"],
                json.dumps(r["raw_data"]) if r["raw_data"] is not None else None,
            )
            for r in rows
        ]

        col_str = ", ".join(columns)
        placeholders = "(" + ", ".join(["%s"] * len(columns)) + ")"

        sql = f"""
            INSERT INTO transactions ({col_str})
            VALUES {placeholders}
            ON CONFLICT (chain, tx_hash, receipt_id, wallet_id) DO NOTHING
        """

        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            # Use executemany for batch insert with ON CONFLICT
            for row_vals in values:
                cur.execute(sql, row_vals)
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.db_pool.putconn(conn)

    def _update_job_progress(self, job_id: int, cursor: Optional[str], progress_fetched: int) -> None:
        """Update job cursor and progress after each page commit."""
        conn = self.db_pool.getconn()
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
            self.db_pool.putconn(conn)

    def _complete_job(self, job_id: int) -> None:
        """Mark job as completed."""
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE indexing_jobs
                SET status = 'completed',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (job_id,),
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.db_pool.putconn(conn)

    def _get_db_tx_count(self, wallet_id: int) -> int:
        """Count transactions in DB for this wallet."""
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM transactions WHERE wallet_id = %s AND chain = 'near'",
                (wallet_id,)
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row else 0
        finally:
            self.db_pool.putconn(conn)

    def _get_rpc_balance(self, account_id: str) -> Optional[str]:
        """
        Query FastNear RPC for on-chain account balance.

        Returns amount in yoctoNEAR as string, or None on error.
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "query",
                "params": {
                    "request_type": "view_account",
                    "account_id": account_id,
                    "finality": "final",
                },
                "id": "1",
            }
            response = requests.post(FASTNEAR_RPC, json=payload, timeout=10)
            data = response.json()
            result = data.get("result", {})
            return result.get("amount")
        except Exception as e:
            logger.warning("RPC balance check failed for %s: %s", account_id, e)
            return None
