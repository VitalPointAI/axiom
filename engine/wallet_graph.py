#!/usr/bin/env python3
"""
WalletGraph — PostgreSQL-backed wallet ownership graph.

Detects internal transfers between wallets owned by the same user,
finds cross-chain bridge transfer pairs by amount+timing matching,
and suggests wallet discovery candidates based on transfer frequency.

Multi-user isolation: every query is scoped by user_id.
No SQLite — requires a psycopg2 connection pool from indexers.db.get_pool().
"""

from decimal import Decimal


class WalletGraph:
    """PostgreSQL-backed wallet graph with internal transfer detection.

    Args:
        pool: psycopg2 ThreadedConnectionPool (or SimpleConnectionPool)
              from indexers.db.get_pool().
    """

    def __init__(self, pool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _getconn(self):
        """Acquire a connection from the pool."""
        return self.pool.getconn()

    def _putconn(self, conn):
        """Return a connection to the pool."""
        self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_owned_wallets(self, user_id: int) -> set:
        """Return set of (chain, address) for all owned wallets of user.

        Uses case-insensitive address storage (LOWER()) to prevent
        duplicates from mixed-case EVM addresses.
        """
        conn = self._getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT chain, LOWER(account_id) FROM wallets "
                "WHERE user_id = %s AND is_owned = TRUE",
                (user_id,),
            )
            return {(row[0], row[1]) for row in cur.fetchall()}
        finally:
            self._putconn(conn)

    def is_internal_transfer(self, user_id: int, from_addr: str, to_addr: str) -> bool:
        """Return True if both addresses are owned wallets of the given user.

        Performs a single DB query using an IN clause — if both addresses
        are present in the user's wallets table the count will be >= 2.
        Case-insensitive via LOWER().
        """
        conn = self._getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT account_id FROM wallets "
                "WHERE user_id = %s "
                "  AND LOWER(account_id) IN (LOWER(%s), LOWER(%s)) "
                "  AND is_owned = TRUE",
                (user_id, from_addr, to_addr),
            )
            rows = cur.fetchall()
            # Need at least 2 distinct addresses found
            return len(rows) >= 2
        finally:
            self._putconn(conn)

    def find_cross_chain_transfer_pairs(
        self,
        user_id: int,
        amount_tolerance: float = 0.05,
        window_minutes: int = 30,
    ) -> list:
        """Find potential cross-chain bridge transfers by amount + timing matching.

        Extends DedupHandler's 1%/10-min same-chain pattern with wider tolerances
        to handle bridge fees and settlement latency:
          - Amount tolerance: 5% (covers bridge fees)
          - Time window: 30 minutes (covers cross-chain settlement)

        CRITICAL: All queries filtered by user_id to prevent cross-user false positives.

        Returns list of dicts:
            {
                'tx_a': int,           # outgoing tx id
                'tx_b': int,           # incoming tx id
                'confidence': float,   # 0-1 match confidence
                'amount_diff_pct': float,
                'time_diff_min': float,
            }

        All matches have needs_review=True implied — specialist must confirm.
        Uses Decimal for amount math to prevent floating-point precision loss.
        """
        window_seconds = window_minutes * 60

        conn = self._getconn()
        try:
            cur = conn.cursor()

            # Outgoing transactions for this user (potential bridge sends)
            cur.execute(
                "SELECT id, chain, amount, block_timestamp "
                "FROM transactions "
                "WHERE user_id = %s AND direction = 'out' AND amount IS NOT NULL "
                "  AND block_timestamp IS NOT NULL",
                (user_id,),
            )
            out_txs = cur.fetchall()

            # Incoming transactions for this user (potential bridge receives)
            cur.execute(
                "SELECT id, chain, amount, block_timestamp "
                "FROM transactions "
                "WHERE user_id = %s AND direction = 'in' AND amount IS NOT NULL "
                "  AND block_timestamp IS NOT NULL",
                (user_id,),
            )
            in_txs = cur.fetchall()

        finally:
            self._putconn(conn)

        pairs = []

        for out_id, out_chain, out_amount, out_ts in out_txs:
            if out_amount is None or out_ts is None:
                continue
            out_dec = Decimal(str(out_amount))

            for in_id, in_chain, in_amount, in_ts in in_txs:
                # Must be on different chains
                if in_chain == out_chain:
                    continue
                if in_amount is None or in_ts is None:
                    continue

                in_dec = Decimal(str(in_amount))

                # Amount within tolerance
                if out_dec == 0:
                    continue
                diff = abs(out_dec - in_dec) / out_dec
                if diff > Decimal(str(amount_tolerance)):
                    continue

                # Timestamp within window (incoming can be after outgoing)
                time_diff_sec = abs(int(in_ts) - int(out_ts))
                if time_diff_sec > window_seconds:
                    continue

                time_diff_min = time_diff_sec / 60.0
                amount_diff_pct = float(diff)

                # Confidence: closer in time and amount = higher confidence
                time_score = 1.0 - (time_diff_sec / window_seconds)
                amount_score = 1.0 - (amount_diff_pct / amount_tolerance)
                confidence = round((time_score + amount_score) / 2, 4)

                pairs.append(
                    {
                        "tx_a": out_id,
                        "tx_b": in_id,
                        "confidence": confidence,
                        "amount_diff_pct": amount_diff_pct,
                        "time_diff_min": time_diff_min,
                    }
                )

        return pairs

    def suggest_wallet_discovery(self, user_id: int, min_transfers: int = 3) -> list:
        """Find high-frequency counterparties that suggest ownership.

        Adapts legacy find_potential_owned_wallets() for PostgreSQL.
        Counts transfers between owned wallets and external counterparties.
        Counterparties meeting min_transfers threshold are returned as suggestions.

        Returns list of dicts:
            {
                'address': str,
                'chain': str,
                'transfer_count': int,
                'related_to': str,   # which owned wallet triggered suggestion
                'confidence': float, # 0-1 based on transfer count
            }
        """
        conn = self._getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    t.counterparty    AS address,
                    t.chain           AS chain,
                    COUNT(*)          AS transfer_count,
                    w.account_id      AS related_to
                FROM transactions t
                JOIN wallets w ON t.wallet_id = w.id
                WHERE t.user_id = %s
                  AND t.counterparty IS NOT NULL
                  AND w.is_owned = TRUE
                  -- Exclude already-owned counterparties
                  AND LOWER(t.counterparty) NOT IN (
                      SELECT LOWER(account_id) FROM wallets
                      WHERE user_id = %s AND is_owned = TRUE
                  )
                GROUP BY t.counterparty, t.chain, w.account_id
                HAVING COUNT(*) >= %s
                ORDER BY transfer_count DESC
                """,
                (user_id, user_id, min_transfers),
            )
            rows = cur.fetchall()
        finally:
            self._putconn(conn)

        suggestions = []
        for address, chain, transfer_count, related_to in rows:
            # Cap confidence at 1.0; 10 transfers = full confidence
            confidence = min(1.0, round(transfer_count / 10.0, 4))
            suggestions.append(
                {
                    "address": address,
                    "chain": chain,
                    "transfer_count": transfer_count,
                    "related_to": related_to,
                    "confidence": confidence,
                }
            )

        return suggestions
