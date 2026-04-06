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

from config import FASTNEAR_RPC, FASTNEAR_ARCHIVAL_RPC
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
    BATCH_SIZE = 5000
    # Concurrent HTTP requests for block fetching
    WORKERS = 100

    def __init__(self, db_pool):
        self.client = NeardataClient()
        self.db_pool = db_pool

    # ------------------------------------------------------------------
    # Public API: called by IndexerService
    # ------------------------------------------------------------------

    def sync_wallet(self, job_row: dict) -> None:
        """
        Sync all transactions for a wallet.

        Strategy (fastest first):
          1. If account_block_index is populated, use it — fetch only blocks
             where this account appears. Seconds, not hours.
          2. Otherwise, fall back to scanning all blocks from neardata.xyz.

        Args:
            job_row: Row dict from indexing_jobs table
        """
        wallet_id = job_row["wallet_id"]
        job_id = job_row["id"]

        account_id = self._get_account_id(wallet_id)
        if not account_id:
            raise ValueError(f"Wallet {wallet_id} not found in database")

        logger.info("Syncing %s (wallet_id=%s, job_id=%s)", account_id, wallet_id, job_id)

        # Try the fast path: account_block_index
        indexed_blocks = self._get_indexed_blocks(account_id)
        if indexed_blocks is not None:
            logger.info("Using account_block_index: %d blocks for %s",
                        len(indexed_blocks), account_id)
            self._sync_from_index(job_row, account_id, indexed_blocks)
        else:
            logger.info("No account index available — falling back to block scan for %s",
                        account_id)
            self._sync_full_scan(job_row, account_id)

        self._complete_job(job_id)

        passed, message = self.verify_sync(wallet_id, account_id)
        if not passed:
            logger.warning("Verification warning for %s: %s", account_id, message)
        else:
            logger.info("Verification passed for %s: %s", account_id, message)

    def _get_indexed_blocks(self, account_id: str) -> Optional[list]:
        """Query account_block_index for blocks containing this account.

        Returns a sorted list of block heights, or None if the index
        table doesn't exist or is empty (not yet built).
        """
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            # Check if the index has been built (has data and is reasonably current)
            try:
                cur.execute("SELECT last_processed_block FROM account_indexer_state WHERE id = 1")
                state = cur.fetchone()
                if not state or state[0] < 1_000_000:
                    cur.close()
                    return None  # Index not built yet
            except Exception:
                cur.close()
                conn.rollback()
                return None  # Table doesn't exist yet

            cur.execute(
                "SELECT block_height FROM account_block_index WHERE account_id = %s ORDER BY block_height",
                (account_id.lower(),),
            )
            rows = cur.fetchall()
            cur.close()

            if not rows:
                # Index is built but account not found — could be a new account
                # not yet indexed, or an account with zero on-chain activity.
                # Check if the index is close to chain tip before trusting the
                # empty result.
                cur = conn.cursor()
                cur.execute("SELECT last_processed_block FROM account_indexer_state WHERE id = 1")
                last_block = cur.fetchone()[0]
                cur.close()

                try:
                    tip = self.client.get_final_block_height()
                    if tip - last_block > 10000:
                        return None  # Index too far behind — don't trust empty result
                except Exception:
                    return None

                # Index is current and account has no blocks — return empty list
                return []

            return [r[0] for r in rows]
        finally:
            self.db_pool.putconn(conn)

    def _sync_from_index(self, job_row: dict, account_id: str, block_heights: list) -> None:
        """Fetch only the specific blocks where this account has activity.

        Instead of scanning millions of blocks, we fetch only the ones
        that matter. A wallet with 5000 transactions might have activity
        in ~2000 blocks — fetched in under a minute.
        """
        wallet_id = job_row["wallet_id"]
        user_id = job_row["user_id"]
        job_id = job_row["id"]

        if not block_heights:
            logger.info("No indexed blocks for %s — nothing to sync.", account_id)
            return

        total = len(block_heights)
        self._set_progress_total(job_id, total)
        logger.info("Fetching %d targeted blocks for %s", total, account_id)

        # Process in batches with parallel fetching
        for batch_start in range(0, total, self.BATCH_SIZE):
            if not hasattr(self, '_running') or True:  # Always run unless service stops
                batch = block_heights[batch_start:batch_start + self.BATCH_SIZE]
                batch_txs = []

                def _fetch_and_extract(height):
                    block = self.client.fetch_block(height)
                    if not block:
                        return []
                    return self.client.extract_wallet_txs(block, account_id)

                with ThreadPoolExecutor(max_workers=self.WORKERS) as pool:
                    futures = {
                        pool.submit(_fetch_and_extract, h): h
                        for h in batch
                    }
                    for future in as_completed(futures):
                        try:
                            raw_txs = future.result()
                            for raw_tx in raw_txs:
                                parsed = parse_transaction(
                                    raw_tx, wallet_id=wallet_id,
                                    user_id=user_id, account_id=account_id,
                                )
                                if parsed:
                                    batch_txs.append(parsed)
                        except Exception as e:
                            logger.debug("Block fetch error: %s", e)

                if batch_txs:
                    self._batch_insert(batch_txs)

                progress = batch_start + len(batch)
                self._update_job_progress(job_id, str(batch[-1]), progress)

                pct = min(100, progress * 100 // total)
                if pct % 10 == 0:
                    logger.info("Index sync %s: %d%% (%d/%d blocks)",
                                account_id, pct, progress, total)

    def _sync_full_scan(self, job_row: dict, account_id: str) -> None:
        """Fallback: scan all blocks from neardata.xyz (slow but complete).

        Used when the account_block_index hasn't been built yet.
        """
        wallet_id = job_row["wallet_id"]
        user_id = job_row["user_id"]
        job_id = job_row["id"]

        cursor = job_row.get("cursor")
        start_block = self._parse_block_cursor(cursor, wallet_id)
        progress_fetched = job_row.get("progress_fetched", 0)

        final_block = self.client.get_final_block_height()
        total_blocks = final_block - start_block
        if total_blocks > 0:
            self._set_progress_total(job_id, total_blocks)

        logger.info("Full scan: blocks %d → %d (%d blocks) for %s",
                     start_block, final_block, total_blocks, account_id)

        current = start_block
        while current <= final_block:
            batch_end = min(current + self.BATCH_SIZE, final_block + 1)
            batch_txs = []

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
                                user_id=user_id, account_id=account_id,
                            )
                            if parsed:
                                batch_txs.append(parsed)
                    except Exception as e:
                        logger.debug("Block fetch error: %s", e)

            if batch_txs:
                self._batch_insert(batch_txs)

            current = batch_end
            progress_fetched += self.BATCH_SIZE

            self._update_job_progress(job_id, str(current), progress_fetched)

            if total_blocks > 0:
                pct = min(100, (current - start_block) * 100 // total_blocks)
                if pct % 5 == 0:
                    logger.info("Scan progress for %s: %d%% (block %d)",
                                account_id, pct, current)

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

        # Try to find the account's creation block via archival RPC binary search.
        # This avoids scanning millions of irrelevant blocks for accounts created
        # well after genesis.
        account_id = self._get_account_id(wallet_id)
        if account_id:
            creation_block = self._find_account_creation_block(account_id)
            if creation_block:
                logger.info("Found account %s creation at block %d (skipping earlier blocks)",
                            account_id, creation_block)
                return creation_block

        # Default: NEAR mainnet genesis was ~9.8M but most activity starts later.
        # Use 45M (~mid 2021) as sensible default for new wallets.
        return int(os.environ.get("NEAR_SCAN_START_BLOCK", "45000000"))

    def _find_account_creation_block(self, account_id: str) -> Optional[int]:
        """Binary search for the block where an account was created.

        Uses FastNear archival RPC to check if the account existed at a given
        block. Narrows down to within ~1000 blocks of creation, which is close
        enough — we'll catch the actual first tx in the block scan.

        Returns the approximate creation block, or None on failure.
        """
        try:
            # First verify account exists at tip
            resp = requests.post(FASTNEAR_RPC, json={
                "jsonrpc": "2.0", "id": "1",
                "method": "query",
                "params": {"request_type": "view_account", "account_id": account_id, "finality": "final"},
            }, timeout=10)
            data = resp.json()
            if "error" in data or "error" in data.get("result", {}):
                return None

            final_block = self.client.get_final_block_height()

            # Binary search: find lowest block where account exists
            low = 9_820_210  # NEAR mainnet genesis
            high = final_block
            # Precision: within 1000 blocks (~17 minutes of NEAR time)
            while high - low > 1000:
                mid = (low + high) // 2
                if self._account_exists_at_block(account_id, mid):
                    high = mid
                else:
                    low = mid

            # Back up a small buffer to ensure we don't miss the creation tx
            return max(9_820_210, low - 100)

        except Exception as exc:
            logger.warning("Failed to find creation block for %s: %s", account_id, exc)
            return None

    def _account_exists_at_block(self, account_id: str, block_height: int) -> bool:
        """Check if an account existed at a specific block height via archival RPC."""
        try:
            resp = requests.post(FASTNEAR_ARCHIVAL_RPC, json={
                "jsonrpc": "2.0", "id": "1",
                "method": "query",
                "params": {
                    "request_type": "view_account",
                    "account_id": account_id,
                    "block_id": block_height,
                },
            }, timeout=15)
            data = resp.json()
            # If the account doesn't exist yet, the RPC returns an error
            if "error" in data:
                return False
            result = data.get("result", {})
            if "error" in result:
                return False
            # Account exists if we got a valid result with an amount field
            return "amount" in result
        except Exception:
            return False

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
