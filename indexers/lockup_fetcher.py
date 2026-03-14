"""
NEAR lockup contract event parser.

Provides:
    - LockupFetcher class: fetches and parses lockup contract events
    - Captures: create, transfer, withdraw, deposit events from lockup accounts
    - Enriches each event with FMV via PriceService
    - Multi-user isolated: all records tagged with user_id

Background:
    NEAR Foundation grants used lockup contracts (*.lockup.near) for vesting.
    Aaron's lockup (db59d3239f2939bb7d8a4a578aceaa8c85ee8e3f.lockup.near) is
    COMPLETE as of ~2021. This parser captures the historical events for tax records.

Lockup event types tracked:
    - create: lockup contract deployed (initial grant)
    - transfer: tokens moved from lockup to owner wallet
    - withdraw: tokens withdrawn from staking pool back to lockup
    - deposit: tokens deposited from lockup to staking pool
    - unlock: lockup vesting period ended (if detectable from transactions)
"""

import json
import base64
import logging
import requests
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import FASTNEAR_RPC
from indexers.price_service import PriceService

logger = logging.getLogger(__name__)

getcontext().prec = 50

YOCTO = Decimal("1e24")
RPC_TIMEOUT = 15

# Lockup contract method names and their event type mappings
LOCKUP_METHOD_MAP = {
    # Contract initialization
    "new": "create",
    # Token transfers out of lockup
    "transfer": "transfer",
    # Staking pool interactions
    "deposit_to_staking_pool": "deposit",
    "stake": "deposit",
    "deposit_and_stake": "deposit",
    "withdraw_from_staking_pool": "withdraw",
    "unstake": "withdraw",
    "unstake_all": "withdraw",
    # Vesting
    "check_transfers_vote": None,   # informational only, skip
    "terminate_vesting": "unlock",
}

# Methods we skip (no taxable event)
SKIP_METHODS = {
    "check_transfers_vote",
    "ping",
    "refresh_staking_pool_balance",
    "get_balance",
    "get_locked_amount",
    "get_liquid_owners_balance",
    "get_staking_pool_account_id",
    "get_known_deposited_balance",
    "get_owners_balance",
}


class LockupFetcher:
    """
    Lockup contract event parser.

    Fetches all transactions for a lockup account via NearBlocks, parses
    each for lockup-relevant methods, and stores events with FMV in lockup_events.

    Usage:
        svc = PriceService(db_pool)
        fetcher = LockupFetcher(db_pool, price_service=svc)
        fetcher.sync_lockup(job_row)
    """

    def __init__(self, db_pool, price_service: PriceService):
        self.db_pool = db_pool
        self.price_service = price_service
        self.rpc_url = FASTNEAR_RPC

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_lockup(self, job_row: dict) -> int:
        """
        Main entry point: sync lockup events for a wallet job.

        Determines the lockup account ID for the wallet, then fetches
        and parses all lockup contract transactions.

        Args:
            job_row: dict with keys: wallet_id, user_id, account_id

        Returns:
            Number of lockup events inserted
        """
        wallet_id = job_row["wallet_id"]
        user_id = job_row["user_id"]
        account_id = job_row["account_id"]

        logger.info("Syncing lockup for %s (wallet_id=%d)", account_id, wallet_id)

        # Determine lockup account(s) to process
        lockup_accounts = self._find_lockup_accounts(account_id)
        if not lockup_accounts:
            logger.info("No lockup accounts found for %s", account_id)
            return 0

        logger.info("Found lockup accounts: %s", lockup_accounts)

        total_inserted = 0
        for lockup_account_id in lockup_accounts:
            count = self.fetch_lockup_events(wallet_id, user_id, lockup_account_id)
            total_inserted += count

        logger.info("Total lockup events inserted: %d", total_inserted)
        return total_inserted

    def fetch_lockup_events(
        self,
        wallet_id: int,
        user_id: int,
        lockup_account_id: str,
    ) -> int:
        """
        Fetch all transactions for lockup_account_id and parse lockup events.

        Uses NearBlocks paginated transaction API.
        Stores meaningful events in lockup_events with FMV.

        Returns:
            Number of events inserted
        """
        logger.info("[fetch_lockup_events] %s", lockup_account_id)

        try:
            from indexers.nearblocks_client import NearBlocksClient
            client = NearBlocksClient()
        except ImportError:
            logger.warning("NearBlocksClient not available")
            return 0

        events_inserted = 0
        cursor = None
        page = 0
        max_pages = 500  # safety limit

        while page < max_pages:
            page += 1
            try:
                data = client.fetch_transactions(lockup_account_id, cursor=cursor, per_page=25)
            except Exception as e:
                logger.error("Error fetching transactions (page %d): %s", page, e)
                break

            txns = data.get("txns", [])
            if not txns:
                break

            for tx in txns:
                event = self._parse_lockup_transaction(tx, lockup_account_id)
                if event:
                    inserted = self._insert_lockup_event(
                        wallet_id=wallet_id,
                        user_id=user_id,
                        lockup_account_id=lockup_account_id,
                        event=event,
                    )
                    if inserted:
                        events_inserted += 1

            cursor = data.get("cursor")
            if not cursor:
                break  # Last page

        logger.info("Inserted %d lockup events for %s", events_inserted, lockup_account_id)
        return events_inserted

    def query_lockup_state(self, lockup_account_id: str) -> dict:
        """
        Query lockup contract state via RPC view calls.

        Calls: get_balance, get_locked_amount, get_liquid_owners_balance,
               get_owners_balance, get_staking_pool_account_id,
               get_known_deposited_balance

        Returns:
            dict with contract state values
        """
        methods = [
            "get_balance",
            "get_locked_amount",
            "get_liquid_owners_balance",
            "get_owners_balance",
            "get_staking_pool_account_id",
            "get_known_deposited_balance",
        ]

        state = {"lockup_account_id": lockup_account_id}

        for method in methods:
            result = self._call_lockup_method(lockup_account_id, method)
            if result is not None:
                state[method] = result

        return state

    # ------------------------------------------------------------------
    # Internal: lockup account discovery
    # ------------------------------------------------------------------

    def _find_lockup_accounts(self, account_id: str) -> list[str]:
        """
        Find lockup account(s) associated with a NEAR account.

        Strategies:
            1. If account_id ends in .lockup.near → it IS the lockup account
            2. Try to query known lockup suffix: {hash}.lockup.near
            3. Scan DB transactions for interactions with *.lockup.near

        Returns:
            List of lockup account IDs
        """
        lockup_accounts = []

        # Strategy 1: account IS a lockup
        if account_id.endswith(".lockup.near"):
            return [account_id]

        # Strategy 2: check DB for known lockup interactions
        db_lockups = self._find_lockup_from_db(account_id)
        lockup_accounts.extend(db_lockups)

        # Strategy 3: try the well-known lockup pattern from NearBlocks transactions
        try:
            from indexers.nearblocks_client import NearBlocksClient
            client = NearBlocksClient()
            # Fetch first page of transactions, look for lockup.near interactions
            data = client.fetch_transactions(account_id, per_page=25)
            for tx in data.get("txns", []):
                receiver = tx.get("receiver_account_id", "")
                if receiver.endswith(".lockup.near") and receiver not in lockup_accounts:
                    lockup_accounts.append(receiver)
                # Also check if account was involved as sender in lockup txs
                actions = tx.get("actions", [])
                for action in actions:
                    if isinstance(action, dict):
                        args = action.get("args", {})
                        if isinstance(args, dict):
                            for v in args.values():
                                if isinstance(v, str) and v.endswith(".lockup.near"):
                                    if v not in lockup_accounts:
                                        lockup_accounts.append(v)
        except Exception as e:
            logger.warning("Could not scan transactions for lockup accounts: %s", e)

        return lockup_accounts

    def _find_lockup_from_db(self, account_id: str) -> list[str]:
        """Check transactions table for lockup.near counterparties."""
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT counterparty
                FROM transactions
                WHERE wallet_id IN (
                    SELECT id FROM wallets WHERE account_id = %s
                )
                AND counterparty LIKE '%%.lockup.near'
                LIMIT 20
                """,
                (account_id,),
            )
            rows = cur.fetchall()
            cur.close()
            return [row[0] for row in rows if row[0]]
        except Exception:
            return []
        finally:
            self.db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # Internal: transaction parsing
    # ------------------------------------------------------------------

    def _parse_lockup_transaction(self, tx: dict, lockup_account_id: str) -> Optional[dict]:
        """
        Parse a NearBlocks transaction object for lockup events.

        Returns:
            dict with event_type, amount, block_timestamp, tx_hash
            or None if transaction is not a relevant lockup event
        """
        tx_hash = tx.get("transaction_hash") or tx.get("hash")
        block_timestamp = tx.get("block_timestamp")
        tx.get("receiver_account_id", "")
        tx.get("signer_account_id", "")

        # Parse timestamp to integer nanoseconds
        if isinstance(block_timestamp, str):
            try:
                block_timestamp = int(block_timestamp)
            except (ValueError, TypeError):
                block_timestamp = None

        # Get actions
        actions = tx.get("actions", [])
        if not actions:
            return None

        amount = Decimal("0")
        event_type = None

        for action in actions:
            if not isinstance(action, dict):
                continue

            action_kind = action.get("action") or action.get("kind", "")
            method_name = action.get("method") or ""
            args = action.get("args") or {}

            # Parse method args if they're base64 encoded
            if isinstance(args, str):
                try:
                    args = json.loads(base64.b64decode(args).decode())
                except Exception:
                    args = {}

            # FunctionCall actions
            if action_kind in ("FUNCTION_CALL", "FunctionCall", "function_call"):
                if method_name in SKIP_METHODS:
                    continue

                mapped_type = LOCKUP_METHOD_MAP.get(method_name)
                if mapped_type is None and method_name not in LOCKUP_METHOD_MAP:
                    # Unknown method, skip
                    continue
                if mapped_type is None:
                    # Explicitly skipped method
                    continue

                event_type = mapped_type

                # Extract amount from args
                if isinstance(args, dict):
                    raw_amount = args.get("amount") or args.get("deposit", "0")
                    try:
                        amount = Decimal(str(raw_amount))
                    except Exception:
                        amount = Decimal("0")

            # Transfer action
            elif action_kind in ("TRANSFER", "Transfer", "transfer"):
                event_type = "transfer"
                deposit = action.get("deposit", "0")
                try:
                    amount = Decimal(str(deposit))
                except Exception:
                    amount = Decimal("0")

        if not event_type:
            return None

        return {
            "event_type": event_type,
            "amount": amount,
            "amount_near": amount / YOCTO if amount > 0 else Decimal("0"),
            "block_timestamp": block_timestamp,
            "tx_hash": tx_hash,
        }

    # ------------------------------------------------------------------
    # Internal: database writes
    # ------------------------------------------------------------------

    def _insert_lockup_event(
        self,
        wallet_id: int,
        user_id: int,
        lockup_account_id: str,
        event: dict,
    ) -> bool:
        """
        Insert a lockup event with FMV into lockup_events table.

        Uses ON CONFLICT DO NOTHING (tx_hash is not unique constrained in schema,
        so we check for duplicates manually by tx_hash + event_type).

        Returns:
            True if inserted, False if duplicate
        """
        # Look up FMV at time of event
        fmv_usd = None
        fmv_cad = None

        block_ts = event.get("block_timestamp")
        if block_ts:
            event_date = self._ts_to_date(block_ts)
            fmv_usd = self.price_service.get_price("near", event_date, "usd")
            fmv_cad = self.price_service.get_price("near", event_date, "cad")

        amount = event.get("amount", Decimal("0"))
        amount_near = event.get("amount_near", Decimal("0"))
        tx_hash = event.get("tx_hash")

        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()

            # Check for existing record (tx_hash + event_type uniqueness)
            if tx_hash:
                cur.execute(
                    """
                    SELECT id FROM lockup_events
                    WHERE wallet_id = %s AND tx_hash = %s AND event_type = %s
                    """,
                    (wallet_id, tx_hash, event["event_type"]),
                )
                if cur.fetchone():
                    cur.close()
                    return False  # Duplicate

            cur.execute(
                """
                INSERT INTO lockup_events
                    (user_id, wallet_id, lockup_account_id, event_type,
                     amount, amount_near, fmv_usd, fmv_cad,
                     block_timestamp, tx_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    wallet_id,
                    lockup_account_id,
                    event["event_type"],
                    str(int(amount)) if amount else None,
                    float(amount_near) if amount_near else None,
                    float(fmv_usd) if fmv_usd else None,
                    float(fmv_cad) if fmv_cad else None,
                    block_ts,
                    tx_hash,
                ),
            )
            conn.commit()
            cur.close()
            return True

        except Exception as e:
            logger.error("Error inserting lockup event: %s", e)
            conn.rollback()
            return False
        finally:
            self.db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # Internal: RPC helpers
    # ------------------------------------------------------------------

    def _call_lockup_method(
        self, lockup_account_id: str, method_name: str, args: str = "{}"
    ) -> Optional[str]:
        """Call a view method on the lockup contract and return decoded result."""
        try:
            args_b64 = base64.b64encode(args.encode()).decode()
            resp = requests.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "query",
                    "params": {
                        "request_type": "call_function",
                        "finality": "final",
                        "account_id": lockup_account_id,
                        "method_name": method_name,
                        "args_base64": args_b64,
                    },
                },
                timeout=RPC_TIMEOUT,
            )
            result = resp.json().get("result", {})
            result_bytes = result.get("result", [])
            if result_bytes:
                return bytes(result_bytes).decode().strip('"')
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal: timestamp helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ts_to_date(timestamp_ns: int) -> str:
        """Convert nanosecond timestamp to ISO date string YYYY-MM-DD."""
        ts_sec = timestamp_ns / 1e9
        dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
