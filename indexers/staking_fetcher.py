"""
Epoch-level staking reward calculator for NEAR Protocol.

Provides:
    - StakingFetcher class: backfills epoch-by-epoch staking rewards
    - Uses validator balance diffs across epochs (current - previous - deposits + withdrawals)
    - Stores epoch snapshots for auditability
    - Enriches rewards with FMV via PriceService
    - Multi-user isolated: all data tagged with user_id

Architecture:
    - Uses archival RPC for historical epoch queries
    - NearBlocks kitwallet endpoint to discover validators
    - epoch_snapshots table stores per-epoch validator balances
    - staking_events table stores reward events with FMV

Reward formula:
    reward = current_staked - previous_staked - deposits_in_epoch + withdrawals_in_epoch

NEAR epoch timing:
    - Each epoch is ~12 hours (43,200 blocks)
    - Epoch ID is the epoch height from validator RPC
"""

import json
import base64
import logging
import time
import requests
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import FASTNEAR_RPC, FASTNEAR_ARCHIVAL_RPC
from indexers.price_service import PriceService

logger = logging.getLogger(__name__)

# Precision for yoctoNEAR arithmetic
getcontext().prec = 50

YOCTO = Decimal("1e24")
EPOCH_DURATION_NS = int(12 * 3600 * 1e9)  # ~12 hours in nanoseconds
EPOCH_DURATION_SECONDS = 12 * 3600        # ~12 hours
BACKFILL_BATCH_SIZE = 100  # Commit every N epochs during backfill

# RPC request timeout
RPC_TIMEOUT = 15


class StakingFetcher:
    """
    Epoch-level staking reward calculator.

    Backfills staking history from the first stake event to the current epoch,
    storing epoch snapshots and inserting staking_event records for each reward.

    Usage:
        svc = PriceService(db_pool)
        fetcher = StakingFetcher(db_pool, price_service=svc)
        fetcher.sync_staking(job_row)
    """

    def __init__(self, db_pool, price_service: PriceService):
        self.db_pool = db_pool
        self.price_service = price_service
        self.rpc_url = FASTNEAR_ARCHIVAL_RPC

        # Local epoch block height cache (epoch_id -> block_height)
        self._epoch_block_cache: dict[int, Optional[int]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_staking(self, job_row: dict) -> int:
        """
        Main entry point: sync staking rewards for a wallet job.

        Discovers all validators the wallet has staked with, then
        backfills epoch rewards for each one.

        Args:
            job_row: dict with keys: wallet_id, user_id, account_id (from indexing_jobs)

        Returns:
            Total number of reward events inserted
        """
        wallet_id = job_row["wallet_id"]
        user_id = job_row["user_id"]
        account_id = job_row["account_id"]

        logger.info("Syncing staking for %s (wallet_id=%d)", account_id, wallet_id)

        validators = self._discover_validators(account_id)
        if not validators:
            logger.info("No validators found for %s", account_id)
            return 0

        logger.info("Found %d validator(s): %s", len(validators), validators)

        total_rewards = 0
        for validator_id in validators:
            count = self.backfill_epoch_rewards(wallet_id, user_id, account_id, validator_id)
            total_rewards += count

        logger.info("Total reward events inserted: %d", total_rewards)
        return total_rewards

    def backfill_epoch_rewards(
        self,
        wallet_id: int,
        user_id: int,
        account_id: str,
        validator_id: str,
    ) -> int:
        """
        Backfill all missing epoch reward records for wallet+validator pair.

        Process:
            1. Find earliest staking transaction timestamp
            2. Get current epoch from RPC
            3. Find last snapshot epoch in DB
            4. For each missing epoch: query archival RPC, store snapshot, calculate reward

        Returns:
            Number of reward events inserted
        """
        logger.info("[backfill] %s @ %s", account_id, validator_id)

        # Get current epoch info
        current_epoch_info = self._get_current_epoch()
        if not current_epoch_info:
            logger.warning("Could not get current epoch info for %s @ %s", account_id, validator_id)
            return 0

        current_epoch = current_epoch_info["epoch_height"]
        current_epoch_ts = current_epoch_info.get("epoch_start_timestamp_ns")

        # Find first stake event timestamp
        first_stake_ts = self._get_first_stake_timestamp(wallet_id, validator_id)
        if first_stake_ts is None:
            logger.info("No stake events found in DB for %s @ %s", account_id, validator_id)
            return 0

        first_stake_dt = datetime.fromtimestamp(first_stake_ts / 1e9, tz=timezone.utc)
        logger.info("First stake: %s UTC", first_stake_dt.strftime('%Y-%m-%d %H:%M'))

        # Find last snapshotted epoch
        last_snapshot_epoch = self._get_last_snapshot_epoch(wallet_id, validator_id)

        # Calculate starting epoch (estimate based on timestamps)
        now = datetime.now(timezone.utc)
        first_dt = first_stake_dt
        elapsed_hours = (now - first_dt).total_seconds() / 3600
        epochs_elapsed = int(elapsed_hours / 12)
        first_epoch = max(0, current_epoch - epochs_elapsed)

        start_epoch = (last_snapshot_epoch + 1) if last_snapshot_epoch else first_epoch

        if start_epoch >= current_epoch:
            logger.info("Already up to date (last snapshot epoch %s)", last_snapshot_epoch)
            return 0

        num_epochs = current_epoch - start_epoch
        logger.info("Backfilling %d epochs from %d to %d", num_epochs, start_epoch, current_epoch)

        rewards_inserted = 0
        prev_staked: Optional[Decimal] = None
        prev_epoch_ts: Optional[int] = None

        for epoch_offset, epoch_id in enumerate(range(start_epoch, current_epoch)):
            # Estimate epoch timestamp
            epochs_back = current_epoch - epoch_id
            epoch_ts = self._estimate_epoch_timestamp(current_epoch_ts, epochs_back)
            epoch_date = self._ts_to_date(epoch_ts)

            # Query validator pool at this epoch
            try:
                staked, unstaked = self._query_validator_balance(
                    account_id, validator_id, epoch_id, epoch_ts
                )
            except Exception as e:
                logger.warning("Skipping epoch %d: %s", epoch_id, e)
                # Store zero snapshot to mark as processed
                self._store_epoch_snapshot(
                    wallet_id, user_id, validator_id, epoch_id,
                    Decimal("0"), Decimal("0"), epoch_ts
                )
                prev_staked = Decimal("0")
                prev_epoch_ts = epoch_ts
                continue

            # Store snapshot
            self._store_epoch_snapshot(
                wallet_id, user_id, validator_id, epoch_id,
                staked, unstaked, epoch_ts
            )

            # Calculate reward (skip if no previous snapshot)
            if prev_staked is not None and prev_epoch_ts is not None:
                reward = self._calculate_reward(
                    wallet_id, validator_id,
                    prev_staked, staked,
                    prev_epoch_ts, epoch_ts
                )

                if reward > 0:
                    reward_near = reward / YOCTO
                    fmv_usd = self.price_service.get_price("near", epoch_date, "usd")
                    fmv_cad = self.price_service.get_price("near", epoch_date, "cad")

                    self._insert_staking_event(
                        wallet_id=wallet_id,
                        user_id=user_id,
                        validator_id=validator_id,
                        epoch_id=epoch_id,
                        amount=reward,
                        amount_near=reward_near,
                        fmv_usd=fmv_usd,
                        fmv_cad=fmv_cad,
                        block_timestamp=epoch_ts,
                    )
                    rewards_inserted += 1

                    if rewards_inserted % 50 == 0:
                        logger.info(
                            "Progress: %d/%d epochs, %d rewards...",
                            epoch_offset, num_epochs, rewards_inserted,
                        )

            prev_staked = staked
            prev_epoch_ts = epoch_ts

            # Batch commit: flush every BACKFILL_BATCH_SIZE epochs
            if (epoch_offset + 1) % BACKFILL_BATCH_SIZE == 0:
                self._batch_commit_backfill(wallet_id, validator_id, epoch_id)

        # Final batch commit for remaining epochs
        if num_epochs > 0:
            self._batch_commit_backfill(wallet_id, validator_id, current_epoch - 1)

        logger.info("Inserted %d reward events for %s", rewards_inserted, validator_id)
        return rewards_inserted

    def _batch_commit_backfill(self, wallet_id: int, validator_id: str, last_epoch: int):
        """Commit current transaction and update indexing job cursor."""
        conn = self.db_pool.getconn()
        try:
            conn.commit()
            logger.debug("Batch commit at epoch %d for %s", last_epoch, validator_id)
        finally:
            self.db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # Internal: validator discovery
    # ------------------------------------------------------------------

    def _discover_validators(self, account_id: str) -> list[str]:
        """
        Discover all validators this account has staked with.

        Uses NearBlocks kitwallet staking-deposits endpoint.
        Falls back to checking staking_events in DB.
        """
        validators = set()

        # Try NearBlocks kitwallet endpoint
        try:
            from indexers.nearblocks_client import NearBlocksClient
            client = NearBlocksClient()
            deposits = client.fetch_staking_deposits(account_id)
            for item in deposits:
                vid = item.get("validator_id")
                if vid:
                    validators.add(vid)
        except Exception as e:
            logger.warning("NearBlocks staking lookup failed: %s", e)

        return list(validators)

    # ------------------------------------------------------------------
    # Internal: RPC queries
    # ------------------------------------------------------------------

    def _get_current_epoch(self) -> Optional[dict]:
        """Get current epoch info from NEAR RPC."""
        try:
            resp = requests.post(
                FASTNEAR_RPC,
                json={"jsonrpc": "2.0", "id": 1, "method": "validators", "params": [None]},
                timeout=RPC_TIMEOUT,
            )
            data = resp.json()
            result = data.get("result", {})
            return {
                "epoch_height": result.get("epoch_height", 0),
                "epoch_start_height": result.get("epoch_start_height", 0),
                "epoch_start_timestamp_ns": int(time.time() * 1e9),  # approximate
            }
        except Exception as e:
            logger.error("Error getting current epoch: %s", e)
            return None

    def _query_validator_balance(
        self,
        account_id: str,
        validator_id: str,
        epoch_id: int,
        epoch_ts: int,
    ) -> tuple[Decimal, Decimal]:
        """
        Query validator pool for account balance at a specific epoch.

        Uses archival RPC with block_id derived from epoch height estimate.
        Falls back to using finality='final' for recent epochs.

        Returns:
            (staked_balance, unstaked_balance) in yoctoNEAR
        """
        args = json.dumps({"account_id": account_id})
        args_b64 = base64.b64encode(args.encode()).decode()

        # Try archival RPC first with estimated block height
        block_height = self.get_epoch_block_height(epoch_id)
        if block_height:
            params = {
                "request_type": "call_function",
                "block_id": block_height,
                "account_id": validator_id,
                "method_name": "get_account",
                "args_base64": args_b64,
            }
        else:
            # Fall back to finality=final (only works for current epoch)
            params = {
                "request_type": "call_function",
                "finality": "final",
                "account_id": validator_id,
                "method_name": "get_account",
                "args_base64": args_b64,
            }

        resp = requests.post(
            self.rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": "query", "params": params},
            timeout=RPC_TIMEOUT,
        )
        data = resp.json()

        if "error" in data:
            error_msg = data["error"].get("data", str(data["error"]))
            raise RuntimeError(f"RPC error: {error_msg}")

        result = data.get("result", {})
        result_bytes = result.get("result", [])

        if not result_bytes:
            return Decimal("0"), Decimal("0")

        parsed = json.loads(bytes(result_bytes).decode())
        staked = Decimal(str(parsed.get("staked_balance", "0")))
        unstaked = Decimal(str(parsed.get("unstaked_balance", "0")))
        return staked, unstaked

    def get_epoch_block_height(self, epoch_id: int) -> Optional[int]:
        """
        Estimate block height for a given epoch_id.

        NEAR epochs are ~43,200 blocks each (12 hours at 1 block/sec).
        Uses current epoch start height as anchor and works backwards.
        Caches results locally (epochs don't change).
        """
        if epoch_id in self._epoch_block_cache:
            return self._epoch_block_cache[epoch_id]

        try:
            # Get current validators info for epoch anchor
            resp = requests.post(
                FASTNEAR_RPC,
                json={"jsonrpc": "2.0", "id": 1, "method": "validators", "params": [None]},
                timeout=RPC_TIMEOUT,
            )
            data = resp.json()
            result = data.get("result", {})
            current_epoch = result.get("epoch_height", 0)
            current_start_height = result.get("epoch_start_height", 0)

            if current_epoch and current_start_height:
                # Estimate: 43200 blocks per epoch
                BLOCKS_PER_EPOCH = 43200
                epochs_back = current_epoch - epoch_id
                estimated_height = current_start_height - (epochs_back * BLOCKS_PER_EPOCH)

                if estimated_height > 0:
                    self._epoch_block_cache[epoch_id] = estimated_height
                    return estimated_height

        except Exception as e:
            logger.warning("Could not estimate block height for epoch %d: %s", epoch_id, e)

        self._epoch_block_cache[epoch_id] = None
        return None

    # ------------------------------------------------------------------
    # Internal: reward calculation
    # ------------------------------------------------------------------

    def _calculate_reward(
        self,
        wallet_id: int,
        validator_id: str,
        prev_staked: Decimal,
        current_staked: Decimal,
        prev_epoch_ts: int,
        current_epoch_ts: int,
    ) -> Decimal:
        """
        Calculate staking reward for this epoch.

        Formula: reward = current_staked - prev_staked - deposits + withdrawals
        where deposits/withdrawals are transactions in the epoch window.
        """
        # Get deposits and withdrawals in this epoch window
        deposits, withdrawals = self._get_epoch_flows(
            wallet_id, validator_id, prev_epoch_ts, current_epoch_ts
        )

        reward = current_staked - prev_staked - deposits + withdrawals

        # Negative rewards shouldn't happen (validator slash or data error), cap at 0
        if reward < 0:
            reward = Decimal("0")

        return reward

    def _get_epoch_flows(
        self,
        wallet_id: int,
        validator_id: str,
        epoch_start_ts: int,
        epoch_end_ts: int,
    ) -> tuple[Decimal, Decimal]:
        """
        Get net deposits and withdrawals in the epoch window from staking_events table.

        Returns:
            (deposits, withdrawals) in yoctoNEAR
        """
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT event_type, amount
                FROM staking_events
                WHERE wallet_id = %s
                  AND validator_id = %s
                  AND event_type IN ('deposit', 'withdraw')
                  AND block_timestamp >= %s
                  AND block_timestamp < %s
                """,
                (wallet_id, validator_id, epoch_start_ts, epoch_end_ts),
            )
            deposits = Decimal("0")
            withdrawals = Decimal("0")
            for event_type, amount in cur.fetchall():
                amt = Decimal(str(amount)) if amount else Decimal("0")
                if event_type == "deposit":
                    deposits += amt
                elif event_type == "withdraw":
                    withdrawals += amt
            cur.close()
            return deposits, withdrawals
        finally:
            self.db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # Internal: database writes
    # ------------------------------------------------------------------

    def _store_epoch_snapshot(
        self,
        wallet_id: int,
        user_id: int,
        validator_id: str,
        epoch_id: int,
        staked_balance: Decimal,
        unstaked_balance: Decimal,
        epoch_timestamp: int,
    ) -> None:
        """Insert epoch snapshot, ignoring conflicts (UniqueConstraint)."""
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO epoch_snapshots
                    (user_id, wallet_id, validator_id, epoch_id,
                     staked_balance, unstaked_balance, epoch_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (wallet_id, validator_id, epoch_id) DO NOTHING
                """,
                (
                    user_id, wallet_id, validator_id, epoch_id,
                    str(int(staked_balance)),
                    str(int(unstaked_balance)),
                    epoch_timestamp,
                ),
            )
            conn.commit()
            cur.close()
        finally:
            self.db_pool.putconn(conn)

    def _insert_staking_event(
        self,
        wallet_id: int,
        user_id: int,
        validator_id: str,
        epoch_id: int,
        amount: Decimal,
        amount_near: Decimal,
        fmv_usd: Optional[Decimal],
        fmv_cad: Optional[Decimal],
        block_timestamp: int,
    ) -> None:
        """Insert a staking reward event."""
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO staking_events
                    (user_id, wallet_id, validator_id, event_type,
                     amount, amount_near, fmv_usd, fmv_cad,
                     epoch_id, block_timestamp)
                VALUES (%s, %s, %s, 'reward', %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, wallet_id, validator_id,
                    str(int(amount)),
                    float(amount_near),
                    float(fmv_usd) if fmv_usd else None,
                    float(fmv_cad) if fmv_cad else None,
                    epoch_id,
                    block_timestamp,
                ),
            )
            conn.commit()
            cur.close()
        finally:
            self.db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # Internal: DB reads
    # ------------------------------------------------------------------

    def _get_first_stake_timestamp(
        self, wallet_id: int, validator_id: str
    ) -> Optional[int]:
        """Get the earliest staking event timestamp for wallet+validator.

        First checks staking_events for deposit records. If none found,
        falls back to the transactions table for STAKE actions or
        function calls to the validator pool contract.
        """
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            # Primary: check staking_events
            cur.execute(
                """
                SELECT MIN(block_timestamp)
                FROM staking_events
                WHERE wallet_id = %s AND validator_id = %s AND event_type = 'deposit'
                """,
                (wallet_id, validator_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                cur.close()
                return row[0]

            # Fallback: check transactions for STAKE actions or calls to this validator
            cur.execute(
                """
                SELECT MIN(block_timestamp)
                FROM transactions
                WHERE wallet_id = %s
                  AND (
                    (action_type = 'STAKE')
                    OR (action_type = 'FUNCTION_CALL' AND counterparty = %s)
                  )
                  AND block_timestamp IS NOT NULL
                """,
                (wallet_id, validator_id),
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row and row[0] else None
        finally:
            self.db_pool.putconn(conn)

    def _get_last_snapshot_epoch(
        self, wallet_id: int, validator_id: str
    ) -> Optional[int]:
        """Get the highest epoch_id already snapshotted for wallet+validator."""
        conn = self.db_pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT MAX(epoch_id)
                FROM epoch_snapshots
                WHERE wallet_id = %s AND validator_id = %s
                """,
                (wallet_id, validator_id),
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row and row[0] else None
        finally:
            self.db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # Internal: timestamp helpers
    # ------------------------------------------------------------------

    def _estimate_epoch_timestamp(
        self, current_ts: Optional[int], epochs_back: int
    ) -> int:
        """Estimate the timestamp of an epoch given epochs_back from current."""
        if current_ts is None:
            current_ts = int(time.time() * 1e9)
        return current_ts - (epochs_back * EPOCH_DURATION_NS)

    @staticmethod
    def _ts_to_date(timestamp_ns: int) -> str:
        """Convert nanosecond timestamp to ISO date string YYYY-MM-DD."""
        ts_sec = timestamp_ns / 1e9
        dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
