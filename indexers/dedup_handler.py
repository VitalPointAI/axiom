"""Cross-source deduplication handler for Axiom multi-source transaction data.

Detects potential duplicate transactions between:
- exchange_transactions table (imported from CSV files or AI agent)
- transactions table (fetched from on-chain: ETH, NEAR, XRP, Akash, etc.)

Dedup algorithm:
  1. Query exchange_transactions not yet checked for duplicates (filter by user_id
     and exclude rows where notes already reference on-chain duplication)
  2. For each exchange tx, search transactions table for on-chain matches:
     - Same asset (exchange asset maps to transactions.token_id)
     - Amount within 1% tolerance (exchange: human units, on-chain: wei/drops/yocto)
     - Timestamp within 10 minutes
     - Direction alignment: exchange 'send'/'withdrawal' <-> on-chain 'out';
       exchange 'receive'/'deposit' <-> on-chain 'in'
  3. If match found, flag exchange tx:
     - needs_review = TRUE
     - notes = 'Potential duplicate of on-chain tx {tx_hash} on {chain}'

This leverages existing columns (needs_review, notes) to avoid schema changes.
The handler runs as a 'dedup_scan' job_type in the IndexerService queue.

Usage:
    handler = DedupHandler(pool)
    handler.run_scan(job)   # job must have user_id
"""

import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Timestamp window: exchange and on-chain timestamps within this many minutes
# are considered potential matches (network propagation + exchange recording lag)
TIMESTAMP_WINDOW_MINUTES = 10

# Amount tolerance: exchange quantity vs on-chain amount must be within this fraction
# e.g. 0.01 = 1%
AMOUNT_TOLERANCE = 0.01

# Asset decimals for on-chain amount conversion (raw integer -> human-readable)
# Maps token_id (on-chain) / asset symbol (exchange) to decimal places
ASSET_DECIMALS = {
    "ETH": 18,
    "MATIC": 18,
    "CRO": 18,
    "OP": 18,       # Optimism
    "NEAR": 24,     # yoctoNEAR
    "XRP": 6,       # drops
    "AKT": 6,       # uakt
    "BTC": 8,       # satoshis (if ever stored raw)
    "USDC": 6,
    "USDT": 6,
    "DAI": 18,
    "WETH": 18,
    "WBTC": 8,
}

# Direction mapping: exchange tx_type -> expected on-chain action_type
# exchange 'send' / 'withdrawal' correspond to money going out (action_type='out')
# exchange 'receive' / 'deposit' correspond to money coming in (action_type='in')
EXCHANGE_SEND_TYPES = {"send", "withdrawal", "sell", "trade"}
EXCHANGE_RECEIVE_TYPES = {"receive", "deposit", "buy", "reward", "interest",
                          "staking_reward", "airdrop", "mining"}


class DedupHandler:
    """Cross-source duplicate detector for exchange vs on-chain transactions.

    Registered in IndexerService as the 'dedup_scan' job handler.
    Flags exchange_transactions that appear to also exist in the transactions
    table (on-chain data), avoiding double-counting in cost basis calculations.
    """

    def __init__(self, pool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_scan(self, job: dict) -> None:
        """Scan for cross-source duplicate transactions for a user.

        Args:
            job: dict with at minimum:
                 - user_id: int — scan this user's exchange_transactions

        Steps:
        1. Fetch exchange_transactions not yet dedup-scanned for this user
        2. For each, search transactions table for potential on-chain matches
        3. Flag matches with needs_review=True and explanatory note
        """
        user_id = job["user_id"]
        logger.info("DedupHandler: starting dedup scan for user_id=%s", user_id)

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Step 1: Get exchange transactions not yet checked for duplicates.
            # Exclude rows that already have a dedup note (notes LIKE '%Potential duplicate%')
            # to avoid re-processing already-flagged rows.
            cur.execute(
                """
                SELECT id, exchange, tx_id, tx_type, asset, quantity, tx_date
                FROM exchange_transactions
                WHERE user_id = %s
                  AND (notes IS NULL OR notes NOT LIKE %s)
                ORDER BY tx_date
                """,
                (user_id, "%Potential duplicate of on-chain tx%"),
            )
            exchange_txs = cur.fetchall()

            if not exchange_txs:
                logger.info("DedupHandler: no unchecked exchange txs for user_id=%s", user_id)
                return

            logger.info(
                "DedupHandler: checking %d exchange txs for user_id=%s",
                len(exchange_txs), user_id,
            )

            matched_count = 0

            for ex_id, exchange, tx_id, tx_type, asset, quantity, tx_date in exchange_txs:
                # Determine expected on-chain direction
                on_chain_direction = self._get_expected_direction(tx_type)
                if on_chain_direction is None:
                    # Unknown direction — skip (can't safely match)
                    continue

                # Step 2: Search transactions table for on-chain matches.
                # Match criteria:
                #   - Same user
                #   - Asset (token_id) matches exchange asset
                #   - Direction matches (action_type = 'in' or 'out')
                #   - Timestamp within TIMESTAMP_WINDOW_MINUTES of exchange tx_date
                # Amount matching is done in Python (decimal precision; varying units)
                if tx_date is None:
                    continue

                # Ensure tx_date is timezone-aware for safe comparison
                if hasattr(tx_date, 'tzinfo') and tx_date.tzinfo is None:
                    tx_date = tx_date.replace(tzinfo=timezone.utc)

                window_start = tx_date - timedelta(minutes=TIMESTAMP_WINDOW_MINUTES)
                window_end = tx_date + timedelta(minutes=TIMESTAMP_WINDOW_MINUTES)

                cur.execute(
                    """
                    SELECT tx_hash, chain, action_type, token_id, amount, block_timestamp
                    FROM transactions
                    WHERE wallet_id IN (
                        SELECT id FROM wallets WHERE user_id = %s
                    )
                      AND token_id = %s
                      AND action_type = %s
                      AND block_timestamp BETWEEN %s AND %s
                    """,
                    (user_id, asset, on_chain_direction, window_start, window_end),
                )
                candidates = cur.fetchall()

                # Step 3: Check amount tolerance in Python
                match_hash = None
                match_chain = None
                for tx_hash, chain, action_type, token_id, raw_amount, block_ts in candidates:
                    if self._amounts_match(quantity, raw_amount, asset):
                        match_hash = tx_hash
                        match_chain = chain
                        break

                # Flag exchange tx if we found a match
                if match_hash:
                    note = (
                        f"Potential duplicate of on-chain tx {match_hash} on {match_chain}. "
                        f"Verify before including in cost basis."
                    )
                    cur.execute(
                        """
                        UPDATE exchange_transactions
                        SET needs_review = TRUE,
                            notes = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (note, ex_id),
                    )
                    matched_count += 1
                    logger.info(
                        "DedupHandler: flagged exchange tx id=%s (exchange=%s tx_id=%s) "
                        "as potential duplicate of on-chain tx %s",
                        ex_id, exchange, tx_id, match_hash,
                    )

            conn.commit()
            cur.close()

            logger.info(
                "DedupHandler: scan complete for user_id=%s — %d/%d exchange txs flagged",
                user_id, matched_count, len(exchange_txs),
            )

        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_expected_direction(self, tx_type: str) -> Optional[str]:
        """Map exchange tx_type to expected on-chain action_type direction.

        Args:
            tx_type: exchange transaction type (e.g. 'send', 'receive', 'deposit')

        Returns:
            'in' for incoming transactions, 'out' for outgoing, None if unknown.
        """
        tx_type_lower = (tx_type or "").lower().strip()
        if tx_type_lower in EXCHANGE_SEND_TYPES:
            return "out"
        if tx_type_lower in EXCHANGE_RECEIVE_TYPES:
            return "in"
        return None

    def _amounts_match(
        self,
        exchange_qty: str,
        onchain_raw: str,
        asset: str,
    ) -> bool:
        """Check if exchange quantity and on-chain raw amount are within tolerance.

        Exchange quantities are in human-readable units (e.g. 1.0 ETH).
        On-chain amounts are stored as raw integers in smallest units
        (e.g. 1000000000000000000 for 1 ETH in wei).

        Converts on-chain raw amount to human units using ASSET_DECIMALS,
        then checks if the difference is within AMOUNT_TOLERANCE (1%).

        Args:
            exchange_qty: exchange quantity as a decimal string (e.g. "1.0")
            onchain_raw: on-chain amount as raw integer string (e.g. "1000000000000000000")
            asset: asset symbol used to look up decimal places (e.g. "ETH")

        Returns:
            True if amounts match within tolerance, False otherwise.
        """
        try:
            ex_amount = Decimal(str(exchange_qty))
        except (InvalidOperation, TypeError):
            return False

        try:
            raw = Decimal(str(onchain_raw))
        except (InvalidOperation, TypeError):
            return False

        # Get decimal places for this asset (default to 18 for unknown ERC20s)
        decimals = ASSET_DECIMALS.get(asset.upper() if asset else "", 18)
        onchain_amount = raw / Decimal(10 ** decimals)

        # Avoid division by zero
        if onchain_amount == 0:
            return ex_amount == 0

        # Calculate relative difference
        diff = abs(ex_amount - onchain_amount)
        relative_diff = diff / onchain_amount

        return relative_diff <= Decimal(str(AMOUNT_TOLERANCE))
