"""Balance reconciliation engine for Axiom verification pipeline.

Reconciles calculated balances (ACBPool snapshots + raw tx replay) against
on-chain state for NEAR (decomposed: liquid + locked + staked) and EVM
(Etherscan V2 native balance). Exchange accounts support manual balance entry.

Auto-diagnoses discrepancies in 4 categories (delegated to ReconcileDiagnoser):
  1. missing_staking_rewards
  2. uncounted_fees
  3. unindexed_period
  4. classification_error
"""

import base64
import json
import logging
import os
from decimal import Decimal
from typing import Optional, Tuple

import requests

from config import FASTNEAR_RPC, RECONCILIATION_TOLERANCES
from indexers.evm_fetcher import (
    CHAIN_CONFIG,
    CHAIN_KEY_MAP,
    ETHERSCAN_V2_URL,
)
from db.audit import write_audit
from verify.diagnosis import ReconcileDiagnoser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
YOCTO_NEAR = Decimal("1" + "0" * 24)  # 10^24
WEI = Decimal("1" + "0" * 18)  # 10^18

# Chain divisors for converting raw amounts to human units
CHAIN_DIVISORS = {
    "near": YOCTO_NEAR,
    "ethereum": WEI,
    "polygon": WEI,
    "cronos": WEI,
    "optimism": WEI,
}


class BalanceReconciler:
    """PostgreSQL-backed balance reconciler.

    Compares calculated balances (ACBPool snapshots + raw transaction replay)
    against on-chain state. Supports NEAR (decomposed: liquid + locked + staked),
    EVM chains (Etherscan V2 native balance), and exchange accounts (manual
    balance entry).

    Args:
        pool: psycopg2 connection pool
    """

    def __init__(self, pool):
        self.pool = pool
        self.etherscan_api_key = os.environ.get("ETHERSCAN_API_KEY", "")
        self.diagnoser = ReconcileDiagnoser(pool)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile_user(self, user_id: int) -> dict:
        """Reconcile all wallets for a user.

        Queries all wallets, groups by chain, reconciles each wallet,
        and returns aggregate stats.

        Args:
            user_id: User ID to reconcile.

        Returns:
            Dict with keys: wallets_checked, within_tolerance, flagged, errors.
        """
        stats = {
            "wallets_checked": 0,
            "within_tolerance": 0,
            "flagged": 0,
            "errors": 0,
        }

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, account_id, chain FROM wallets WHERE user_id = %s",
                (user_id,),
            )
            wallets = cur.fetchall()
            cur.close()
        finally:
            self.pool.putconn(conn)

        for wallet_id, account_id, chain in wallets:
            try:
                # Normalize chain to lowercase for consistent matching
                chain = chain.lower() if chain else chain
                # Determine token symbol based on chain
                token_symbol = self._chain_to_token(chain)
                result = self._reconcile_wallet(
                    user_id, wallet_id, account_id, chain, token_symbol
                )
                stats["wallets_checked"] += 1
                if result == "within_tolerance":
                    stats["within_tolerance"] += 1
                elif result == "flagged":
                    stats["flagged"] += 1
                elif result == "error":
                    stats["errors"] += 1
            except Exception as exc:
                logger.error(
                    "Error reconciling wallet_id=%s account=%s: %s",
                    wallet_id,
                    account_id,
                    exc,
                )
                stats["errors"] += 1

        # --- Wallet coverage invariant check ---
        all_wallet_ids = {w[0] for w in wallets}
        reconciled_wallet_ids = set()
        for wallet_id, account_id, chain in wallets:
            reconciled_wallet_ids.add(wallet_id)
        skipped_wallets = all_wallet_ids - reconciled_wallet_ids
        stats["coverage_complete"] = len(skipped_wallets) == 0

        if skipped_wallets:
            logger.warning(
                "Reconciler wallet coverage: %d wallets skipped for user_id=%s: %s",
                len(skipped_wallets), user_id, skipped_wallets,
            )
            conn = self.pool.getconn()
            try:
                write_audit(
                    conn,
                    user_id=user_id,
                    entity_type="verification_result",
                    action="invariant_violation",
                    new_value={
                        "skipped_wallets": list(skipped_wallets),
                        "reason": "wallet_not_reconciled",
                    },
                    actor_type="system",
                )
                conn.commit()
            except Exception:
                logger.warning("Failed to write reconciler invariant audit", exc_info=True)
            finally:
                self.pool.putconn(conn)

        # --- Undiagnosed discrepancy check ---
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id FROM verification_results
                WHERE user_id = %s AND status = 'open' AND diagnosis_category IS NULL
                LIMIT 50
                """,
                (user_id,),
            )
            undiagnosed = cur.fetchall()
            cur.close()
            if undiagnosed:
                logger.warning(
                    "Reconciler: %d undiagnosed discrepancies for user_id=%s",
                    len(undiagnosed), user_id,
                )
                write_audit(
                    conn,
                    user_id=user_id,
                    entity_type="verification_result",
                    action="invariant_violation",
                    new_value={
                        "undiagnosed_count": len(undiagnosed),
                        "result_ids": [r[0] for r in undiagnosed[:10]],
                    },
                    actor_type="system",
                )
                conn.commit()
        except Exception:
            logger.warning("Failed to check undiagnosed discrepancies", exc_info=True)
        finally:
            self.pool.putconn(conn)

        logger.info(
            "Reconciliation complete for user_id=%s: %s",
            user_id,
            stats,
        )
        return stats

    # ------------------------------------------------------------------
    # Core reconciliation
    # ------------------------------------------------------------------

    def _reconcile_wallet(
        self,
        user_id: int,
        wallet_id: int,
        account_id: str,
        chain: str,
        token_symbol: str,
    ) -> str:
        """Reconcile a single wallet.

        Gets expected balance via dual cross-check (ACBPool + raw replay),
        gets actual on-chain balance, computes difference, runs auto-diagnosis
        if outside tolerance, and upserts result.

        Returns:
            "within_tolerance", "flagged", or "error"
        """
        rpc_error = None

        # --- Expected balances (dual cross-check) ---
        expected_acb = self._get_acb_expected(user_id, token_symbol)
        expected_replay = self._get_replay_expected(user_id, wallet_id, chain)

        # --- Actual on-chain balance ---
        actual_balance = None
        onchain_liquid = None
        onchain_locked = None
        onchain_staked = None

        if chain == "near":
            try:
                liquid, locked, staked, total = self._get_near_balance(
                    account_id, wallet_id
                )
                actual_balance = total
                onchain_liquid = liquid
                onchain_locked = locked
                onchain_staked = staked
            except Exception as exc:
                rpc_error = str(exc)
                logger.warning(
                    "NEAR RPC error for %s: %s", account_id, exc
                )
        elif chain in CHAIN_KEY_MAP:
            try:
                actual_balance = self._get_evm_balance(account_id, chain)
            except Exception as exc:
                rpc_error = str(exc)
                logger.warning(
                    "EVM balance error for %s on %s: %s",
                    account_id,
                    chain,
                    exc,
                )
        elif chain.startswith("exchange") or chain in (
            "coinbase",
            "crypto_com",
            "wealthsimple",
            "uphold",
            "coinsquare",
        ):
            # Exchange wallets: use manual balance if available
            actual_balance = self._get_manual_balance(wallet_id, token_symbol)
        else:
            # Unknown chain -- skip on-chain query
            logger.info(
                "Skipping on-chain query for unsupported chain=%s wallet_id=%s",
                chain,
                wallet_id,
            )

        # --- Compute difference ---
        # Use replay expected for per-wallet comparison (ACB is user-level)
        compare_expected = expected_replay if expected_replay is not None else Decimal("0")
        if actual_balance is not None:
            difference = actual_balance - compare_expected
        else:
            difference = None

        # --- Tolerance check ---
        tolerance_str = RECONCILIATION_TOLERANCES.get(chain, "0.01")
        tolerance = Decimal(tolerance_str)

        if difference is not None and abs(difference) <= tolerance:
            status = "within_tolerance"
            diagnosis_category = "within_tolerance"
            diagnosis_detail = {}
            diagnosis_confidence = Decimal("1.0")
        elif difference is not None:
            status = "flagged"
            diagnosis_category, diagnosis_detail, diagnosis_confidence = (
                self.diagnoser.auto_diagnose(user_id, wallet_id, chain, difference)
            )
        elif rpc_error:
            status = "error"
            diagnosis_category = None
            diagnosis_detail = {"rpc_error": rpc_error}
            diagnosis_confidence = None
        else:
            # No actual balance obtainable (exchange without manual entry)
            status = "unverified"
            diagnosis_category = None
            diagnosis_detail = {}
            diagnosis_confidence = None

        # Map status to DB status values
        db_status_map = {
            "within_tolerance": "resolved",
            "flagged": "open",
            "error": "open",
            "unverified": "unverified",
        }
        db_status = db_status_map.get(status, "open")

        # --- Upsert result ---
        result_dict = {
            "user_id": user_id,
            "wallet_id": wallet_id,
            "chain": chain,
            "token_symbol": token_symbol,
            "expected_balance_acb": expected_acb,
            "expected_balance_replay": expected_replay,
            "actual_balance": actual_balance,
            "difference": difference,
            "tolerance": tolerance,
            "onchain_liquid": onchain_liquid,
            "onchain_locked": onchain_locked,
            "onchain_staked": onchain_staked,
            "status": db_status,
            "diagnosis_category": diagnosis_category,
            "diagnosis_detail": json.dumps(diagnosis_detail) if diagnosis_detail else None,
            "diagnosis_confidence": diagnosis_confidence,
            "rpc_error": rpc_error,
        }

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            self._upsert_result(cur, result_dict)
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

        logger.info(
            "Reconciled wallet_id=%s account=%s chain=%s status=%s diff=%s",
            wallet_id,
            account_id,
            chain,
            status,
            difference,
        )

        return status

    # ------------------------------------------------------------------
    # Expected balance methods
    # ------------------------------------------------------------------

    def _get_acb_expected(
        self, user_id: int, token_symbol: str
    ) -> Optional[Decimal]:
        """Get expected balance from latest ACBPool snapshot (user-level).

        The ACB pool is user-scoped (all wallets pooled), so this returns
        the aggregate expected balance per token for the entire user.

        Args:
            user_id: User ID.
            token_symbol: Token symbol (e.g. 'NEAR', 'ETH').

        Returns:
            Decimal units_after from latest snapshot, or None if no snapshots.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT units_after FROM acb_snapshots
                WHERE user_id = %s AND token_symbol = %s
                ORDER BY block_timestamp DESC, id DESC
                LIMIT 1
                """,
                (user_id, token_symbol),
            )
            row = cur.fetchone()
            cur.close()
            return Decimal(str(row[0])) if row else None
        finally:
            self.pool.putconn(conn)

    def _get_replay_expected(
        self, user_id: int, wallet_id: int, chain: str
    ) -> Optional[Decimal]:
        """Get expected balance via raw transaction replay (per-wallet).

        Sums all in amounts, subtracts all out amounts and fees from the
        transactions table for this specific wallet.

        Args:
            user_id: User ID.
            wallet_id: Wallet ID.
            chain: Chain name (e.g. 'near', 'ethereum').

        Returns:
            Decimal balance in human units, or None on error.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN direction='in' THEN amount ELSE 0 END), 0) as total_in,
                    COALESCE(SUM(CASE WHEN direction='out' THEN amount ELSE 0 END), 0) as total_out,
                    COALESCE(SUM(CASE WHEN direction='out' THEN COALESCE(fee, 0) ELSE 0 END), 0) as total_fees
                FROM transactions
                WHERE wallet_id = %s AND chain = %s
                """,
                (wallet_id, chain),
            )
            row = cur.fetchone()
            cur.close()

            if row is None:
                return None

            total_in = Decimal(str(row[0])) if row[0] else Decimal("0")
            total_out = Decimal(str(row[1])) if row[1] else Decimal("0")
            total_fees = Decimal(str(row[2])) if row[2] else Decimal("0")

            # Convert from raw units to human units
            divisor = CHAIN_DIVISORS.get(chain, YOCTO_NEAR)
            balance = (total_in - total_out - total_fees) / divisor

            return balance
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # On-chain balance methods
    # ------------------------------------------------------------------

    def _get_near_balance(
        self, account_id: str, wallet_id: int
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """Get decomposed NEAR balance: liquid + locked + staked.

        Makes RPC calls:
          1. view_account for liquid (amount) and locked balance
          2. Query staking_events for known validators
          3. NearBlocks kitwallet fallback for pre-indexing validators
          4. get_account_staked_balance per validator pool

        Args:
            account_id: NEAR account ID.
            wallet_id: Wallet ID for DB queries.

        Returns:
            Tuple of (liquid, locked, staked, total) in NEAR (not yocto).
        """
        liquid = Decimal("0")
        locked = Decimal("0")
        staked = Decimal("0")

        # 1. view_account for liquid + locked
        try:
            response = requests.post(
                FASTNEAR_RPC,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "query",
                    "params": {
                        "request_type": "view_account",
                        "finality": "final",
                        "account_id": account_id,
                    },
                },
                timeout=10,
            )
            result = response.json().get("result", {})
            liquid_yocto = Decimal(str(result.get("amount", "0")))
            locked_yocto = Decimal(str(result.get("locked", "0")))
            liquid = liquid_yocto / YOCTO_NEAR
            locked = locked_yocto / YOCTO_NEAR
        except Exception as exc:
            logger.warning(
                "NEAR view_account error for %s: %s", account_id, exc
            )
            raise

        # 2. Enumerate validators from staking_events table
        validator_ids = set()
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT se.validator_id
                FROM staking_events se
                JOIN wallets w ON se.wallet_id = w.id
                WHERE w.account_id = %s AND se.event_type IN ('deposit', 'reward')
                """,
                (account_id,),
            )
            for row in cur.fetchall():
                if row[0]:
                    validator_ids.add(row[0])
            cur.close()
        finally:
            self.pool.putconn(conn)

        # 3. NearBlocks kitwallet fallback for pre-indexing validators
        try:
            from indexers.nearblocks_client import NearBlocksClient

            client = NearBlocksClient()
            deposits = client.fetch_staking_deposits(account_id)
            if isinstance(deposits, list):
                for item in deposits:
                    vid = item.get("validator_id")
                    deposit = int(item.get("deposit", 0))
                    if vid and deposit > 0:
                        validator_ids.add(vid)
        except Exception as exc:
            logger.debug(
                "NearBlocks staking fallback unavailable for %s: %s",
                account_id,
                exc,
            )

        # 4. Query staked balance from each validator pool
        for pool_id in validator_ids:
            try:
                pool_balance = self._query_staked_balance(account_id, pool_id)
                staked += pool_balance
            except Exception as exc:
                logger.warning(
                    "Error querying staked balance for %s at %s: %s",
                    account_id,
                    pool_id,
                    exc,
                )

        total = liquid + locked + staked

        logger.info(
            "NEAR balance for %s: liquid=%s locked=%s staked=%s total=%s",
            account_id,
            liquid,
            locked,
            staked,
            total,
        )

        return (liquid, locked, staked, total)

    def _query_staked_balance(
        self, account_id: str, pool_id: str
    ) -> Decimal:
        """Query a single validator pool for staked balance.

        Args:
            account_id: NEAR account ID.
            pool_id: Validator pool contract ID.

        Returns:
            Staked balance in NEAR (not yocto).
        """
        args = json.dumps({"account_id": account_id})
        args_b64 = base64.b64encode(args.encode()).decode()

        response = requests.post(
            FASTNEAR_RPC,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "query",
                "params": {
                    "request_type": "call_function",
                    "finality": "final",
                    "account_id": pool_id,
                    "method_name": "get_account_staked_balance",
                    "args_base64": args_b64,
                },
            },
            timeout=10,
        )

        result = response.json().get("result", {})
        if "result" in result:
            balance_bytes = bytes(result["result"])
            balance_str = balance_bytes.decode().strip('"')
            if balance_str.isdigit():
                return Decimal(balance_str) / YOCTO_NEAR

        return Decimal("0")

    def _get_evm_balance(self, account_id: str, chain: str) -> Decimal:
        """Get native token balance for an EVM address via Etherscan V2.

        Args:
            account_id: EVM wallet address.
            chain: Lowercase chain name (e.g. 'ethereum', 'polygon').

        Returns:
            Balance in human units (e.g. ETH, not wei).
        """
        chain_key = CHAIN_KEY_MAP.get(chain)
        if not chain_key or chain_key not in CHAIN_CONFIG:
            logger.warning("Unsupported EVM chain for balance: %s", chain)
            return Decimal("0")

        chain_config = CHAIN_CONFIG[chain_key]

        params = {
            "module": "account",
            "action": "balance",
            "address": account_id,
            "tag": "latest",
            "chainid": str(chain_config["chainid"]),
        }
        if self.etherscan_api_key:
            params["apikey"] = self.etherscan_api_key

        try:
            response = requests.get(
                ETHERSCAN_V2_URL, params=params, timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1":
                balance_wei = Decimal(str(data.get("result", "0")))
                return balance_wei / WEI
            else:
                logger.warning(
                    "Etherscan balance query failed for %s on %s: %s",
                    account_id,
                    chain,
                    data.get("message", "unknown error"),
                )
                return Decimal("0")
        except Exception as exc:
            logger.warning(
                "EVM balance request error for %s on %s: %s",
                account_id,
                chain,
                exc,
            )
            raise

    def _get_manual_balance(
        self, wallet_id: int, token_symbol: str
    ) -> Optional[Decimal]:
        """Get manually entered balance for exchange wallets.

        Looks up existing verification_results for this wallet to find
        a previously entered manual balance.

        Args:
            wallet_id: Wallet ID.
            token_symbol: Token symbol.

        Returns:
            Decimal manual balance if set, else None.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT manual_balance FROM verification_results
                WHERE wallet_id = %s AND token_symbol = %s
                    AND manual_balance IS NOT NULL
                ORDER BY verified_at DESC
                LIMIT 1
                """,
                (wallet_id, token_symbol),
            )
            row = cur.fetchone()
            cur.close()
            return Decimal(str(row[0])) if row else None
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    def _upsert_result(self, conn_or_cur, result_dict: dict) -> None:
        """Upsert a verification result row.

        Uses INSERT ... ON CONFLICT (wallet_id, token_symbol) DO UPDATE
        to maintain one active result per wallet+token.

        Args:
            conn_or_cur: psycopg2 cursor.
            result_dict: Dict with all column values.
        """
        cur = conn_or_cur

        cur.execute(
            """
            INSERT INTO verification_results (
                user_id, wallet_id, chain, token_symbol,
                expected_balance_acb, expected_balance_replay,
                actual_balance, difference, tolerance,
                onchain_liquid, onchain_locked, onchain_staked,
                status, diagnosis_category, diagnosis_detail,
                diagnosis_confidence, rpc_error,
                verified_at, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                NOW(), NOW(), NOW()
            )
            ON CONFLICT (wallet_id, token_symbol) DO UPDATE SET
                expected_balance_acb = EXCLUDED.expected_balance_acb,
                expected_balance_replay = EXCLUDED.expected_balance_replay,
                actual_balance = EXCLUDED.actual_balance,
                difference = EXCLUDED.difference,
                tolerance = EXCLUDED.tolerance,
                onchain_liquid = EXCLUDED.onchain_liquid,
                onchain_locked = EXCLUDED.onchain_locked,
                onchain_staked = EXCLUDED.onchain_staked,
                status = EXCLUDED.status,
                diagnosis_category = EXCLUDED.diagnosis_category,
                diagnosis_detail = EXCLUDED.diagnosis_detail,
                diagnosis_confidence = EXCLUDED.diagnosis_confidence,
                rpc_error = EXCLUDED.rpc_error,
                verified_at = NOW(),
                updated_at = NOW()
            """,
            (
                result_dict["user_id"],
                result_dict["wallet_id"],
                result_dict["chain"],
                result_dict["token_symbol"],
                result_dict.get("expected_balance_acb"),
                result_dict.get("expected_balance_replay"),
                result_dict.get("actual_balance"),
                result_dict.get("difference"),
                result_dict.get("tolerance"),
                result_dict.get("onchain_liquid"),
                result_dict.get("onchain_locked"),
                result_dict.get("onchain_staked"),
                result_dict.get("status"),
                result_dict.get("diagnosis_category"),
                result_dict.get("diagnosis_detail"),
                result_dict.get("diagnosis_confidence"),
                result_dict.get("rpc_error"),
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _chain_to_token(chain: str) -> str:
        """Map chain name to native token symbol.

        Args:
            chain: Lowercase chain name.

        Returns:
            Token symbol string.
        """
        mapping = {
            "near": "NEAR",
            "ethereum": "ETH",
            "polygon": "MATIC",
            "cronos": "CRO",
            "optimism": "ETH",
        }
        return mapping.get(chain, chain.upper())
