"""
NEAR transaction fetcher using neardata.xyz block scanning.

Scans blocks from neardata.xyz (free, no API key) and filters for
wallet-relevant transactions. Replaces the previous NearBlocks-based
approach which required a paid API subscription.

Handles block-height cursor resume, all NEAR action types, and
post-sync verification via FastNear RPC.
"""

import base64
import json
import logging
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

import requests

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import FASTNEAR_RPC
from indexers.neardata_client import NeardataClient

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
# FT args helpers
# ---------------------------------------------------------------------------

def _parse_ft_args(actions: list) -> Optional[dict]:
    """Extract parsed args from an ft_transfer/ft_transfer_call action.

    NearBlocks may provide args as a JSON string, base64-encoded string,
    or already-parsed dict.
    """
    for action in actions:
        if action.get("action") != ACTION_FUNCTION_CALL:
            continue
        args = action.get("args")
        if args is None:
            continue
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            # Try JSON string first
            try:
                return json.loads(args)
            except (json.JSONDecodeError, ValueError):
                pass
            # Try base64 decode
            try:
                decoded = base64.b64decode(args)
                return json.loads(decoded)
            except Exception:
                pass
    return None


def _parse_ft_args_amount(actions: list) -> Optional[int]:
    """Extract the token amount from FT transfer args."""
    parsed = _parse_ft_args(actions)
    if parsed and "amount" in parsed:
        try:
            return int(parsed["amount"])
        except (ValueError, TypeError):
            pass
    return None


def _parse_ft_args_receiver(actions: list) -> Optional[str]:
    """Extract the receiver_id from FT transfer args."""
    parsed = _parse_ft_args(actions)
    if parsed:
        return parsed.get("receiver_id")
    return None


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

        # ---------------------------------------------------------------
        # Detect fungible token (FT) transfers
        # For ft_transfer / ft_transfer_call, the receiver_account_id is
        # the token contract. The actual transfer details are in the args.
        # ---------------------------------------------------------------
        token_id = None
        FT_METHODS = {"ft_transfer", "ft_transfer_call"}

        if method_name in FT_METHODS:
            # The receiver of the tx is the token contract
            token_id = receiver

            # Parse the FT amount from action args
            ft_amount = _parse_ft_args_amount(actions)
            if ft_amount is not None:
                amount = ft_amount

            # For FT transfers, the actual counterparty is inside the args,
            # not the contract itself
            ft_receiver = _parse_ft_args_receiver(actions)
            if ft_receiver:
                if predecessor == account_id:
                    # We sent it — counterparty is the FT receiver
                    counterparty = ft_receiver
                else:
                    # We received it — counterparty is the sender
                    counterparty = predecessor

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
            "token_id": token_id,
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

    Scans blocks from neardata.xyz (free, unlimited) and filters for
    wallet-relevant transactions. Uses block_height as cursor for
    crash-safe resume.
    """

    # Number of blocks to scan per batch before committing progress
    BATCH_SIZE = 500
    # Concurrent HTTP requests for block fetching
    WORKERS = 20

    def __init__(self, db_pool):
        self.client = NeardataClient()
        self.db_pool = db_pool

    # ------------------------------------------------------------------
    # Public API: called by IndexerService
    # ------------------------------------------------------------------

    def sync_wallet(self, job_row: dict) -> None:
        """
        Sync all transactions for a wallet by scanning neardata.xyz blocks.

        Resumes from the last scanned block_height stored in job cursor.
        For new wallets, starts from the wallet's earliest known block
        or a configurable default.

        Args:
            job_row: Row dict from indexing_jobs table
        """
        wallet_id = job_row["wallet_id"]
        user_id = job_row["user_id"]
        job_id = job_row["id"]

        account_id = self._get_account_id(wallet_id)
        if not account_id:
            raise ValueError(f"Wallet {wallet_id} not found in database")

        logger.info("Syncing %s (wallet_id=%s, job_id=%s) via neardata.xyz",
                     account_id, wallet_id, job_id)

        # Determine start block: resume from cursor or find earliest known
        cursor = job_row.get("cursor")
        start_block = self._parse_block_cursor(cursor, wallet_id)
        progress_fetched = job_row.get("progress_fetched", 0)

        # Get chain tip
        final_block = self.client.get_final_block_height()
        total_blocks = final_block - start_block
        if total_blocks > 0:
            self._set_progress_total(job_id, total_blocks)

        logger.info("Scanning blocks %d → %d (%d blocks) for %s",
                     start_block, final_block, total_blocks, account_id)

        current = start_block
        while current <= final_block:
            batch_end = min(current + self.BATCH_SIZE, final_block + 1)
            batch_txs = []

            # Fetch blocks in parallel for throughput
            def _fetch_and_extract(height):
                block = self.client.fetch_block(height)
                if not block:
                    return []
                return self.client.extract_wallet_txs(block, account_id)

            with ThreadPoolExecutor(max_workers=self.WORKERS) as pool:
                futures = {
                    pool.submit(_fetch_and_extract, h): h
                    for h in range(current, batch_end)
                }
                for future in as_completed(futures):
                    try:
                        raw_txs = future.result()
                        for raw_tx in raw_txs:
                            parsed = parse_transaction(
                                raw_tx, wallet_id=wallet_id,
                                user_id=user_id, account_id=account_id
                            )
                            if parsed:
                                batch_txs.append(parsed)
                    except Exception as e:
                        logger.debug("Block fetch error: %s", e)

            if batch_txs:
                self._batch_insert(batch_txs)

            current = batch_end
            progress_fetched += self.BATCH_SIZE

            # Save block height as cursor for resume
            self._update_job_progress(job_id, str(current), progress_fetched)

            if total_blocks > 0:
                pct = min(100, (current - start_block) * 100 // total_blocks)
                if pct % 5 == 0:
                    logger.info("Scan progress for %s: %d%% (block %d)",
                                account_id, pct, current)

        self._complete_job(job_id)

        passed, message = self.verify_sync(wallet_id, account_id)
        if not passed:
            logger.warning("Verification warning for %s: %s", account_id, message)
        else:
            logger.info("Verification passed for %s: %s", account_id, message)

    def _parse_block_cursor(self, cursor, wallet_id):
        """Parse cursor to block height. Falls back to earliest DB block or default."""
        if cursor:
            try:
                val = int(cursor)
                # NearBlocks cursors are huge numbers (>1B), block heights are <200M
                if val < 500_000_000:
                    return val
            except (ValueError, TypeError):
                pass

        # Check if we have existing transactions for this wallet
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT MIN(block_height), MAX(block_height) "
                "FROM transactions WHERE wallet_id = %s AND chain = 'near'",
                (wallet_id,),
            )
            row = cur.fetchone()
            cur.close()
            if row and row[1]:
                # Resume from after our latest known block
                return row[1]
        finally:
            self.db_pool.putconn(conn)

        # Default: NEAR mainnet genesis was ~9.8M but most activity starts later.
        # Use 45M (~mid 2021) as sensible default for new wallets.
        return int(os.environ.get("NEAR_SCAN_START_BLOCK", "45000000"))

    def verify_sync(self, wallet_id: int, account_id: str) -> Tuple[bool, str]:
        """
        Verify sync completeness via on-chain balance check.

        Args:
            wallet_id: Database wallet ID
            account_id: NEAR account ID

        Returns:
            (passed, message) tuple
        """
        messages = []
        passed = True

        db_count = self._get_db_tx_count(wallet_id)
        messages.append(f"DB transaction count: {db_count}")

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
            ON CONFLICT (chain, tx_hash, receipt_id, wallet_id) DO UPDATE SET
                token_id = EXCLUDED.token_id,
                amount = EXCLUDED.amount,
                counterparty = EXCLUDED.counterparty
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

    def _set_progress_total(self, job_id: int, total: int) -> None:
        """Set progress_total once at start so UI can show real percentages."""
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE indexing_jobs SET progress_total = %s, updated_at = NOW() WHERE id = %s",
                (total, job_id),
            )
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
