#!/usr/bin/env python3
"""
SpamDetector — multi-signal spam detection with adaptive user learning.

Signals (each contributes to overall confidence score):
  1. known_spam_contract  — counterparty matches a spam_rules.contract_address entry
  2. dust_amount          — transaction value below DUST_THRESHOLD_USD
  3. unsolicited          — incoming (direction='in') with no market value
  4. user_tagged_pattern  — matches a user-created pattern rule

Confidence thresholds:
  >= 0.90: Auto-classify as spam (requires 2+ signals to reach this level)
  0.70-0.89: Suggest spam, set needs_review=True
  < 0.70: Not spam

PITFALL PREVENTION: A single signal NEVER reaches 0.90 automatically.
Each signal adds ~0.30 confidence; two signals are required for auto-spam.
Known spam contracts are an exception — they get 0.99 confidence as they
are explicit human-curated or confirmed rules.

Requires a psycopg2 connection pool from indexers.db.get_pool(). No SQLite.
"""


class SpamDetector:
    """Multi-signal spam detection with adaptive user learning.

    Args:
        pool: psycopg2 ThreadedConnectionPool (or SimpleConnectionPool)
              from indexers.db.get_pool().
    """

    DUST_THRESHOLD_USD = 0.001
    SPAM_AUTO_THRESHOLD = 0.90
    # Per-signal contribution to confidence (2 signals needed for auto-spam)
    SIGNAL_WEIGHT = 0.46

    def __init__(self, pool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _getconn(self):
        return self.pool.getconn()

    def _putconn(self, conn):
        self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_rules(self, user_id: int) -> list:
        """Load active spam rules: global (user_id IS NULL) + user-specific.

        Returns list of dicts with keys: id, user_id, rule_type, value, is_active.
        """
        conn = self._getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, user_id, rule_type, value, is_active "
                "FROM spam_rules "
                "WHERE is_active = TRUE "
                "  AND (user_id IS NULL OR user_id = %s)",
                (user_id,),
            )
            rows = cur.fetchall()
        finally:
            self._putconn(conn)

        return [
            {
                "id": r[0],
                "user_id": r[1],
                "rule_type": r[2],
                "value": r[3],
                "is_active": r[4],
            }
            for r in rows
        ]

    def check_spam(self, user_id: int, tx: dict) -> dict:
        """Check if a transaction is spam.

        Args:
            user_id: The owning user (for loading user-specific rules).
            tx: Transaction dict with keys:
                - id, direction, amount, amount_usd, counterparty,
                  action_type, token_id

        Returns:
            {
                'is_spam': bool,
                'confidence': float,  # 0.0 to 1.0
                'signals': list[str], # detected signal names
            }
        """
        rules = self.load_rules(user_id)
        signals = []
        confidence = 0.0

        counterparty = (tx.get("counterparty") or "").lower()
        amount_usd = float(tx.get("amount_usd") or 0.0)
        direction = tx.get("direction", "")

        # Signal 1: Known spam contract (explicit rule match — high confidence)
        for rule in rules:
            if rule["rule_type"] == "contract_address":
                rule_value = (rule["value"] or "").lower()
                if rule_value and counterparty and rule_value == counterparty:
                    # Known spam contract is a hard signal — auto-spam at 0.99
                    return {
                        "is_spam": True,
                        "confidence": 0.99,
                        "signals": ["known_spam_contract"],
                    }

        # Signal 2: Dust amount (value below threshold)
        if amount_usd < self.DUST_THRESHOLD_USD and amount_usd >= 0:
            signals.append("dust_amount")
            confidence += self.SIGNAL_WEIGHT

        # Signal 3: Unsolicited incoming (direction='in' with negligible value)
        # Only counts as a separate signal if the transfer is incoming (user didn't initiate)
        if direction == "in" and amount_usd < self.DUST_THRESHOLD_USD:
            signals.append("unsolicited")
            confidence += self.SIGNAL_WEIGHT

        # Signal 4: User-tagged pattern rules
        for rule in rules:
            if rule["rule_type"] == "token_symbol" and tx.get("token_id"):
                token_id = (tx.get("token_id") or "").lower()
                rule_value = (rule["value"] or "").lower()
                if rule_value and token_id.startswith(rule_value):
                    signals.append("user_tagged_token")
                    confidence += self.SIGNAL_WEIGHT
                    break

        # Cap confidence at 1.0
        confidence = min(1.0, round(confidence, 4))
        is_spam = confidence >= self.SPAM_AUTO_THRESHOLD

        return {
            "is_spam": is_spam,
            "confidence": confidence,
            "signals": signals,
        }

    def tag_as_spam(self, user_id: int, tx_id: int, source_type: str) -> None:
        """User tags a transaction as spam. Creates a spam_rules entry.

        Looks up the transaction to extract the counterparty address,
        then inserts a contract_address rule scoped to the user.

        Args:
            user_id: The user marking the transaction.
            tx_id: The transaction.id to look up.
            source_type: Rule type to create ('contract_address', 'token_symbol', etc.)
        """
        conn = self._getconn()
        try:
            cur = conn.cursor()
            # Look up the transaction to get counterparty
            cur.execute(
                "SELECT id, counterparty, token_id FROM transactions WHERE id = %s",
                (tx_id,),
            )
            row = cur.fetchone()
            if row is None:
                return

            _, counterparty, token_id = row

            # Determine the value to store based on source_type
            if source_type == "contract_address":
                value = counterparty or token_id or ""
            elif source_type == "token_symbol":
                value = token_id or counterparty or ""
            else:
                value = counterparty or ""

            if not value:
                return

            cur.execute(
                "INSERT INTO spam_rules (user_id, rule_type, value, created_by, is_active) "
                "VALUES (%s, %s, %s, %s, TRUE)",
                (user_id, source_type, value, user_id),
            )
            conn.commit()
        finally:
            self._putconn(conn)

    def find_similar_spam(self, rule_id: int) -> list:
        """Find transactions matching a spam rule across ALL users.

        Global intelligence: once a rule is confirmed, find all transactions
        that match it regardless of which user owns them. This allows bulk
        spam classification across the platform.

        Args:
            rule_id: The spam_rules.id to search for.

        Returns:
            List of dicts with 'tx_id' and 'user_id' for matching transactions.
        """
        conn = self._getconn()
        try:
            cur = conn.cursor()
            # Load the rule
            cur.execute(
                "SELECT id, user_id, rule_type, value, is_active FROM spam_rules WHERE id = %s",
                (rule_id,),
            )
            rule = cur.fetchone()
            if rule is None:
                return []

            _, _rule_user_id, rule_type, value, is_active = rule

            if not is_active or not value:
                return []

            # Search transactions across ALL users — no user_id filter (global propagation)
            if rule_type == "contract_address":
                cur.execute(
                    "SELECT id, user_id FROM transactions "
                    "WHERE LOWER(counterparty) = LOWER(%s)",
                    (value,),
                )
            elif rule_type == "token_symbol":
                cur.execute(
                    "SELECT id, user_id FROM transactions "
                    "WHERE LOWER(token_id) LIKE LOWER(%s)",
                    (f"{value}%",),
                )
            else:
                return []

            rows = cur.fetchall()
        finally:
            self._putconn(conn)

        return [{"tx_id": row[0], "user_id": row[1]} for row in rows]
