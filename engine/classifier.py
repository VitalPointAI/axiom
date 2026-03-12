"""
TransactionClassifier — core classification engine for Canadian crypto tax.

Execution flow:
1. Load active ClassificationRules from DB (cached per run)
2. For each transaction:
   a. Check spam (SpamDetector) — if spam, classify and skip rules
   b. Check internal transfer (WalletGraph) — if internal, mark TRANSFER_IN/OUT
   c. Apply deterministic rules by priority DESC (first match wins)
   d. Check staking_events linkage (CLASS-03) — link, don't duplicate
   e. Check lockup_events linkage (CLASS-04) — link, don't duplicate
   f. Decompose complex txs into parent + legs (CLASS-05)
3. Write TransactionClassification rows (upsert, preserving specialist-confirmed)
4. Write ClassificationAuditLog for every write
5. Set needs_review=True for confidence < 0.90

No SQLite or get_connection() references — PostgreSQL only via psycopg2 pool.
All amount comparisons use Decimal.
"""

import json
import logging
import re
from decimal import Decimal

from tax.categories import TaxCategory, CategoryResult
from engine.wallet_graph import WalletGraph
from engine.spam_detector import SpamDetector
from engine.evm_decoder import EVMDecoder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AI fallback constants (importable by callers)
# ---------------------------------------------------------------------------

AI_CONFIDENCE_THRESHOLD = 0.70  # Below this, AI fallback is invoked

CLASSIFICATION_SYSTEM_PROMPT = """You are a Canadian crypto tax classification expert.
Given a transaction's details, classify it for Canadian tax purposes.

Respond with ONLY a JSON object:
{
  "category": "one of: reward|airdrop|interest|income|buy|sell|trade|transfer_in|transfer_out|deposit|withdrawal|stake|unstake|liquidity_in|liquidity_out|loan_borrow|loan_repay|collateral_in|collateral_out|fee|spam|nft_mint|nft_purchase|nft_sale|internal|unknown",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation for CRA audit trail",
  "needs_review": true/false
}

Canadian tax context:
- Crypto-to-crypto trades are taxable dispositions
- Staking rewards are income at FMV when received
- Internal transfers between own wallets are non-taxable
- Set confidence < 0.70 for genuinely ambiguous transactions
- Always set needs_review: true if uncertain"""


class TransactionClassifier:
    """Core classification engine.

    Args:
        pool: psycopg2 connection pool (ThreadedConnectionPool or similar).
        price_service: Optional PriceService for FMV lookups on income events.
    """

    REVIEW_THRESHOLD = 0.90  # Below this -> needs_review=True

    def __init__(self, pool, price_service=None):
        self.pool = pool
        self.price_service = price_service
        self.wallet_graph = WalletGraph(pool)
        self.spam_detector = SpamDetector(pool)
        self.evm_decoder = EVMDecoder()
        self._rules = None  # Lazy-loaded

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------

    def _load_rules(self) -> list:
        """Load active classification_rules sorted by priority DESC.

        SELECT * FROM classification_rules WHERE is_active=TRUE ORDER BY priority DESC
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, chain, pattern, category, confidence, priority "
                "FROM classification_rules "
                "WHERE is_active = TRUE "
                "ORDER BY priority DESC"
            )
            rows = cur.fetchall()
        finally:
            self.pool.putconn(conn)

        rules = []
        for row in rows:
            pattern = row[3]
            if isinstance(pattern, str):
                pattern = json.loads(pattern)
            rules.append({
                "id": row[0],
                "name": row[1],
                "chain": row[2],
                "pattern": pattern,
                "category": row[4],
                "confidence": float(row[5]),
                "priority": row[6],
            })
        return rules

    def _get_rules(self) -> list:
        """Return cached rules, loading from DB if needed."""
        if self._rules is None:
            self._rules = self._load_rules()
        return self._rules

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def classify_user_transactions(self, user_id: int) -> dict:
        """Classify all unclassified transactions for a user.

        Returns stats: {'classified': int, 'skipped_confirmed': int, 'needs_review': int}
        """
        rules = self._get_rules()
        owned_wallets = self.wallet_graph.get_owned_wallets(user_id)

        stats = {"classified": 0, "skipped_confirmed": 0, "needs_review": 0}

        # 1. NEAR transactions
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            # Only unclassified or non-specialist-confirmed
            cur.execute(
                """
                SELECT t.id, t.wallet_id, t.tx_hash, t.action_type, t.method_name,
                       t.counterparty, t.direction, t.amount, t.block_timestamp,
                       t.success, t.raw_data, t.fee
                FROM transactions t
                WHERE t.user_id = %s
                  AND t.chain = 'near'
                  AND (t.success = TRUE OR t.success IS NULL)
                  AND NOT EXISTS (
                      SELECT 1 FROM transaction_classifications tc
                      WHERE tc.transaction_id = t.id
                        AND tc.specialist_confirmed = TRUE
                  )
                """,
                (user_id,),
            )
            near_txs = cur.fetchall()

            # 2. Exchange transactions
            cur.execute(
                """
                SELECT et.id, et.tx_type, et.amount, et.raw_data
                FROM exchange_transactions et
                WHERE et.user_id = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM transaction_classifications tc
                      WHERE tc.exchange_transaction_id = et.id
                        AND tc.specialist_confirmed = TRUE
                  )
                """,
                (user_id,),
            )
            exchange_txs = cur.fetchall()

            # 3. EVM transactions grouped by base tx_hash
            cur.execute(
                """
                SELECT t.id, t.wallet_id, t.tx_hash, t.action_type, t.method_name,
                       t.counterparty, t.direction, t.amount, t.block_timestamp,
                       t.success, t.raw_data, t.fee
                FROM transactions t
                WHERE t.user_id = %s
                  AND t.chain != 'near'
                  AND (t.success = TRUE OR t.success IS NULL)
                  AND NOT EXISTS (
                      SELECT 1 FROM transaction_classifications tc
                      WHERE tc.transaction_id = t.id
                        AND tc.specialist_confirmed = TRUE
                  )
                """,
                (user_id,),
            )
            evm_txs = cur.fetchall()
        finally:
            self.pool.putconn(conn)

        def _row_to_near_dict(row):
            return {
                "id": row[0],
                "wallet_id": row[1],
                "tx_hash": row[2],
                "action_type": row[3],
                "method_name": row[4],
                "counterparty": row[5],
                "direction": row[6],
                "amount": row[7],
                "block_timestamp": row[8],
                "success": row[9],
                "raw_data": row[10] or {},
                "fee": row[11],
            }

        # Process NEAR transactions
        for row in near_txs:
            tx = _row_to_near_dict(row)
            records = self._classify_near_tx(user_id, tx, rules, owned_wallets)
            self._write_records(user_id, records, stats)

        # Process exchange transactions
        for row in exchange_txs:
            tx = {"id": row[0], "tx_type": row[1], "amount": row[2], "raw_data": row[3] or {}}
            records = self._classify_exchange_tx(user_id, tx, rules)
            self._write_records(user_id, records, stats, is_exchange=True, exchange_tx_id=tx["id"])

        # Process EVM transaction groups
        evm_tx_dicts = [_row_to_near_dict(row) for row in evm_txs]
        groups = self.evm_decoder.group_by_base_tx_hash(evm_tx_dicts)
        for base_hash, group in groups.items():
            records = self._classify_evm_tx_group(user_id, group, rules, owned_wallets)
            self._write_records(user_id, records, stats)

        return stats

    def _write_records(self, user_id: int, records: list, stats: dict,
                       is_exchange: bool = False, exchange_tx_id: int = None) -> None:
        """Write classification records to DB, updating stats."""
        if not records:
            return
        conn = self.pool.getconn()
        try:
            for rec in records:
                tx_id = None if is_exchange else rec.get("transaction_id")
                exc_tx_id = exchange_tx_id if is_exchange else None
                classification_id = self._upsert_classification(
                    conn,
                    {**rec, "transaction_id": tx_id, "exchange_transaction_id": exc_tx_id}
                )
                self._write_audit_log(conn, classification_id, rec)
                stats["classified"] += 1
                if rec.get("needs_review"):
                    stats["needs_review"] += 1
            conn.commit()
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Chain-specific classifiers
    # ------------------------------------------------------------------

    def _classify_near_tx(self, user_id: int, tx: dict, rules: list,
                          owned_wallets: set) -> list:
        """Classify a single NEAR transaction.

        Returns list of classification record dicts (1 for simple, N for multi-leg).
        """
        tx_id = tx.get("id")
        wallet_id = tx.get("wallet_id")
        counterparty = (tx.get("counterparty") or "").lower()
        direction = tx.get("direction", "")

        # Step 1: Spam check
        spam_result = self.spam_detector.check_spam(user_id, tx)
        if spam_result["is_spam"]:
            return [self._make_record(
                transaction_id=tx_id,
                category=TaxCategory.SPAM.value,
                confidence=spam_result["confidence"],
                notes=f"Spam: {', '.join(spam_result['signals'])}",
                needs_review=False,
                classification_source="rule",
            )]

        # Step 2: Internal transfer check
        from_addr = tx.get("counterparty") or ""
        to_addr = tx.get("counterparty") or ""
        # Use direction to determine who is from/to relative to owned wallet
        # If direction=in, counterparty is sender; if out, counterparty is receiver
        if direction == "in":
            from_addr = tx.get("counterparty") or ""
        else:
            from_addr = ""  # sender is the owned wallet

        is_internal = False
        if counterparty:
            try:
                is_internal = self.wallet_graph.is_internal_transfer(
                    user_id, from_addr or counterparty, counterparty
                )
            except Exception:
                is_internal = False

        if is_internal:
            cat = TaxCategory.TRANSFER_IN.value if direction == "in" else TaxCategory.TRANSFER_OUT.value
            return [self._make_record(
                transaction_id=tx_id,
                category=cat,
                confidence=0.95,
                notes="Internal transfer between owned wallets",
                needs_review=False,
                classification_source="rule",
            )]

        # Step 3: Rule matching
        category_result = self._match_rules(tx, rules, chain="near")

        if category_result is None or category_result["confidence"] < AI_CONFIDENCE_THRESHOLD:
            # AI fallback for unmatched or low-confidence transactions
            ai_context = self._build_ai_context(tx, chain="near")
            ai_result = self._classify_with_ai(ai_context)
            # Use AI result if no rule matched, or if AI is more confident
            if category_result is None or ai_result["confidence"] > category_result["confidence"]:
                category_result = ai_result

        if category_result is None:
            # Safety net: should never reach here after AI fallback
            category_result = {
                "category": TaxCategory.UNKNOWN.value,
                "confidence": 0.30,
                "notes": f"No rule matched: {tx.get('action_type')}/{tx.get('method_name')}",
                "needs_review": True,
                "rule_id": None,
            }

        # Ensure needs_review if confidence below threshold
        confidence = category_result["confidence"]
        needs_review = confidence < self.REVIEW_THRESHOLD or category_result.get("needs_review", False)
        source = category_result.get("classification_source", "rule")

        record = self._make_record(
            transaction_id=tx_id,
            category=category_result["category"],
            confidence=confidence,
            notes=category_result.get("notes", ""),
            needs_review=needs_review,
            classification_source=source,
            rule_id=category_result.get("rule_id"),
        )

        # Step 4: Staking reward linkage (CLASS-03)
        # Only link if category is reward and counterparty is a staking pool
        if category_result["category"] == TaxCategory.REWARD.value:
            staking_event_id = self._find_staking_event(
                user_id, wallet_id, tx.get("tx_hash", ""), tx.get("block_timestamp", 0)
            )
            if staking_event_id is not None:
                record["staking_event_id"] = staking_event_id

        # Step 5: Lockup vest linkage (CLASS-04)
        # Link if counterparty ends in .lockup.near and category involves income
        if counterparty.endswith(".lockup.near") and category_result["category"] in (
            TaxCategory.INCOME.value,
            TaxCategory.REWARD.value,
            TaxCategory.DEPOSIT.value,
        ):
            lockup_event_id = self._find_lockup_event(
                user_id, wallet_id, tx.get("tx_hash", ""), tx.get("block_timestamp", 0)
            )
            if lockup_event_id is not None:
                record["lockup_event_id"] = lockup_event_id

        # Step 6: DEX swap decomposition (CLASS-05)
        if category_result["category"] == TaxCategory.TRADE.value:
            return self._decompose_swap(tx, record)

        return [record]

    def _classify_exchange_tx(self, user_id: int, tx: dict, rules: list) -> list:
        """Classify a single exchange transaction.

        Returns list of classification record dicts.
        """
        tx_id = tx.get("id")
        category_result = self._match_rules(tx, rules, chain="exchange")

        if category_result is None or category_result["confidence"] < AI_CONFIDENCE_THRESHOLD:
            # AI fallback for unmatched or low-confidence exchange transactions
            ai_context = self._build_ai_context(tx, chain="exchange")
            ai_result = self._classify_with_ai(ai_context)
            if category_result is None or ai_result["confidence"] > category_result["confidence"]:
                category_result = ai_result

        if category_result is None:
            category_result = {
                "category": TaxCategory.UNKNOWN.value,
                "confidence": 0.30,
                "notes": f"Unknown exchange tx_type: {tx.get('tx_type')}",
                "needs_review": True,
                "rule_id": None,
            }

        confidence = category_result["confidence"]
        needs_review = confidence < self.REVIEW_THRESHOLD or category_result.get("needs_review", False)
        source = category_result.get("classification_source", "rule")

        return [self._make_record(
            transaction_id=tx_id,
            category=category_result["category"],
            confidence=confidence,
            notes=category_result.get("notes", ""),
            needs_review=needs_review,
            classification_source=source,
            rule_id=category_result.get("rule_id"),
        )]

    def _classify_evm_tx_group(self, user_id: int, txs: list, rules: list,
                               owned_wallets: set) -> list:
        """Classify a group of EVM transactions sharing base tx_hash.

        Uses EVMDecoder to detect swap/defi type.
        If swap detected: create parent + legs from the group.
        If not swap: classify each individually.
        """
        if not txs:
            return []

        # Check if any tx in group is a swap
        primary_tx = txs[0]
        swap_result = self.evm_decoder.detect_swap(primary_tx)

        if swap_result["is_swap"]:
            # Decompose into parent + sell_leg + buy_leg + fee_leg
            category_result = {
                "category": TaxCategory.TRADE.value,
                "confidence": 0.90,
                "notes": f"EVM DEX swap: {swap_result['method_name']} ({swap_result['dex_type']})",
                "needs_review": False,
                "rule_id": None,
            }
            return self._decompose_swap(primary_tx, category_result)

        # Not a swap — classify each tx individually
        results = []
        for tx in txs:
            # Spam check
            spam_result = self.spam_detector.check_spam(user_id, tx)
            if spam_result["is_spam"]:
                results.append(self._make_record(
                    transaction_id=tx.get("id"),
                    category=TaxCategory.SPAM.value,
                    confidence=spam_result["confidence"],
                    notes=f"Spam: {', '.join(spam_result['signals'])}",
                    needs_review=False,
                    classification_source="rule",
                ))
                continue

            # Internal transfer check
            direction = tx.get("direction", "")
            counterparty = tx.get("counterparty") or ""
            is_internal = False
            if counterparty:
                try:
                    is_internal = self.wallet_graph.is_internal_transfer(
                        user_id, counterparty, counterparty
                    )
                except Exception:
                    is_internal = False

            if is_internal:
                cat = TaxCategory.TRANSFER_IN.value if direction == "in" else TaxCategory.TRANSFER_OUT.value
                results.append(self._make_record(
                    transaction_id=tx.get("id"),
                    category=cat,
                    confidence=0.95,
                    notes="Internal EVM transfer between owned wallets",
                    needs_review=False,
                    classification_source="rule",
                ))
                continue

            # Rule matching using EVM chain
            category_result = self._match_rules(tx, rules, chain="evm")

            if category_result is None or category_result["confidence"] < AI_CONFIDENCE_THRESHOLD:
                # AI fallback for unmatched or low-confidence EVM transactions
                ai_context = self._build_ai_context(tx, chain="evm")
                ai_result = self._classify_with_ai(ai_context)
                if category_result is None or ai_result["confidence"] > category_result["confidence"]:
                    category_result = ai_result

            if category_result is None:
                category_result = {
                    "category": TaxCategory.UNKNOWN.value,
                    "confidence": 0.30,
                    "notes": "No EVM rule matched",
                    "needs_review": True,
                    "rule_id": None,
                }

            confidence = category_result["confidence"]
            needs_review = confidence < self.REVIEW_THRESHOLD or category_result.get("needs_review", False)
            source = category_result.get("classification_source", "rule")

            results.append(self._make_record(
                transaction_id=tx.get("id"),
                category=category_result["category"],
                confidence=confidence,
                notes=category_result.get("notes", ""),
                needs_review=needs_review,
                classification_source=source,
                rule_id=category_result.get("rule_id"),
            ))

        return results

    # ------------------------------------------------------------------
    # Rule matching
    # ------------------------------------------------------------------

    def _match_rules(self, tx: dict, rules: list, chain: str) -> dict | None:
        """Match transaction against rules. First match wins (rules sorted by priority DESC).

        Pattern fields supported:
            method_name          - str or list[str]: exact match
            action_type          - str or list[str]: exact match
            counterparty_suffix  - str or list[str]: endswith check
            counterparty_in      - list[str]: exact counterparty match
            counterparty_contains - str: contains check
            tx_type              - str or list[str]: exact match (exchange rules)
            input_selector       - str or None: EVM 4-byte selector startswith
            direction            - str: exact match
            amount_gt            - numeric: amount must be > this value
            is_own_wallet        - bool: skipped (handled before rule matching)
        """
        tx_action = (tx.get("action_type") or "").upper()
        tx_method = (tx.get("method_name") or "").lower()
        tx_direction = tx.get("direction", "")
        tx_counterparty = (tx.get("counterparty") or "").lower()
        tx_type = (tx.get("tx_type") or "").lower()
        tx_amount = tx.get("amount", 0) or 0

        # Extract EVM input selector
        raw_data = tx.get("raw_data") or {}
        input_hex = raw_data.get("input", "") if isinstance(raw_data, dict) else ""
        tx_input_selector = self.evm_decoder._extract_selector(input_hex)

        for rule in rules:
            # Chain filter: rule chain must match or be 'all'
            rule_chain = rule.get("chain", "")
            if rule_chain != "all" and rule_chain != chain:
                continue

            pattern = rule.get("pattern", {})
            if isinstance(pattern, str):
                pattern = json.loads(pattern)

            matched = True

            # action_type match
            if "action_type" in pattern:
                expected = pattern["action_type"]
                if isinstance(expected, list):
                    if tx_action not in [e.upper() for e in expected]:
                        matched = False
                else:
                    if tx_action != expected.upper():
                        matched = False
            if not matched:
                continue

            # method_name match
            if "method_name" in pattern:
                expected = pattern["method_name"]
                if isinstance(expected, list):
                    if tx_method not in [e.lower() for e in expected]:
                        matched = False
                else:
                    if tx_method != expected.lower():
                        matched = False
            if not matched:
                continue

            # tx_type match (exchange)
            if "tx_type" in pattern:
                expected = pattern["tx_type"]
                if isinstance(expected, list):
                    if tx_type not in [e.lower() for e in expected]:
                        matched = False
                else:
                    if tx_type != expected.lower():
                        matched = False
            if not matched:
                continue

            # direction match
            if "direction" in pattern:
                if tx_direction != pattern["direction"]:
                    matched = False
            if not matched:
                continue

            # counterparty_suffix: counterparty must end with one of the suffixes
            if "counterparty_suffix" in pattern:
                suffixes = pattern["counterparty_suffix"]
                if isinstance(suffixes, str):
                    suffixes = [suffixes]
                if not any(tx_counterparty.endswith(s.lower()) for s in suffixes):
                    matched = False
            if not matched:
                continue

            # counterparty_in: exact match against a list of known contracts
            if "counterparty_in" in pattern:
                contracts = [c.lower() for c in pattern["counterparty_in"]]
                if tx_counterparty not in contracts:
                    matched = False
            if not matched:
                continue

            # counterparty_contains
            if "counterparty_contains" in pattern:
                needle = pattern["counterparty_contains"].lower()
                if needle not in tx_counterparty:
                    matched = False
            if not matched:
                continue

            # amount_gt
            if "amount_gt" in pattern:
                threshold = Decimal(str(pattern["amount_gt"]))
                try:
                    amt = Decimal(str(tx_amount))
                except Exception:
                    amt = Decimal("0")
                if amt <= threshold:
                    matched = False
            if not matched:
                continue

            # input_selector (EVM method selector)
            if "input_selector" in pattern:
                expected_selector = pattern["input_selector"]
                if expected_selector is None:
                    # Rule expects no selector (plain transfer)
                    if tx_input_selector is not None:
                        matched = False
                else:
                    if tx_input_selector != expected_selector.lower():
                        matched = False
            if not matched:
                continue

            # Rule matched!
            confidence = float(rule.get("confidence", 0.0))
            needs_review = confidence < self.REVIEW_THRESHOLD
            return {
                "category": rule["category"],
                "confidence": confidence,
                "notes": f"Rule: {rule['name']}",
                "needs_review": needs_review,
                "rule_id": rule.get("id"),
            }

        return None  # No rule matched

    # ------------------------------------------------------------------
    # Staking / lockup linkage (CLASS-03, CLASS-04)
    # ------------------------------------------------------------------

    def _find_staking_event(self, user_id: int, wallet_id: int,
                            tx_hash: str, block_timestamp: int) -> int | None:
        """Find staking_event matching this tx for reward linkage (CLASS-03).

        Try exact tx_hash match first, then 60-second timestamp window.
        Prevents Pitfall 1: double-counting staking rewards.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            # Try exact tx_hash match first
            cur.execute(
                "SELECT id FROM staking_events "
                "WHERE user_id = %s AND wallet_id = %s "
                "  AND tx_hash = %s AND event_type = 'reward' "
                "LIMIT 1",
                (user_id, wallet_id, tx_hash),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            # Fallback: 60-second timestamp window
            if block_timestamp:
                ts = int(block_timestamp)
                cur.execute(
                    "SELECT id FROM staking_events "
                    "WHERE user_id = %s AND wallet_id = %s "
                    "  AND event_type = 'reward' "
                    "  AND block_timestamp BETWEEN %s AND %s "
                    "LIMIT 1",
                    (user_id, wallet_id, ts - 60, ts + 60),
                )
                row = cur.fetchone()
                if row:
                    return row[0]
        finally:
            self.pool.putconn(conn)

        return None

    def _find_lockup_event(self, user_id: int, wallet_id: int,
                           tx_hash: str, block_timestamp: int) -> int | None:
        """Find lockup_event matching this tx for vest linkage (CLASS-04).

        Try exact tx_hash match first, then 60-second timestamp window.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            # Try exact tx_hash match first
            cur.execute(
                "SELECT id FROM lockup_events "
                "WHERE user_id = %s AND wallet_id = %s "
                "  AND tx_hash = %s "
                "LIMIT 1",
                (user_id, wallet_id, tx_hash),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            # Fallback: 60-second timestamp window
            if block_timestamp:
                ts = int(block_timestamp)
                cur.execute(
                    "SELECT id FROM lockup_events "
                    "WHERE user_id = %s AND wallet_id = %s "
                    "  AND block_timestamp BETWEEN %s AND %s "
                    "LIMIT 1",
                    (user_id, wallet_id, ts - 60, ts + 60),
                )
                row = cur.fetchone()
                if row:
                    return row[0]
        finally:
            self.pool.putconn(conn)

        return None

    # ------------------------------------------------------------------
    # Multi-leg decomposition (CLASS-05)
    # ------------------------------------------------------------------

    def _decompose_swap(self, parent_tx: dict, category_result: dict) -> list:
        """Decompose a swap into parent + child legs.

        Returns list of classification dicts:
        - parent: leg_type='parent', category=TRADE
        - sell_leg: leg_type='sell_leg', leg_index=0, category=SELL
        - buy_leg: leg_type='buy_leg', leg_index=1, category=BUY
        - fee_leg: leg_type='fee_leg', leg_index=2, category=FEE  (only if fee present)
        """
        tx_id = parent_tx.get("id")
        has_fee = bool(parent_tx.get("fee"))

        # Resolve category/confidence from dict or CategoryResult
        if isinstance(category_result, dict):
            cat = category_result.get("category", TaxCategory.TRADE.value)
            confidence = category_result.get("confidence", 0.90)
            notes = category_result.get("notes", "DEX swap")
            needs_review = category_result.get("needs_review", False)
            rule_id = category_result.get("rule_id")
        else:
            cat = getattr(category_result, "category", TaxCategory.TRADE).value
            confidence = getattr(category_result, "confidence", 0.90)
            notes = getattr(category_result, "notes", "DEX swap")
            needs_review = getattr(category_result, "needs_review", False)
            rule_id = None

        parent = self._make_record(
            transaction_id=tx_id,
            category=cat,
            confidence=confidence,
            notes=notes,
            needs_review=needs_review,
            classification_source="rule",
            rule_id=rule_id,
            leg_type="parent",
            leg_index=0,
        )

        sell_leg = self._make_record(
            transaction_id=tx_id,
            category=TaxCategory.SELL.value,
            confidence=confidence,
            notes=f"{notes} (sell leg)",
            needs_review=needs_review,
            classification_source="rule",
            rule_id=rule_id,
            leg_type="sell_leg",
            leg_index=0,
        )

        buy_leg = self._make_record(
            transaction_id=tx_id,
            category=TaxCategory.BUY.value,
            confidence=confidence,
            notes=f"{notes} (buy leg)",
            needs_review=needs_review,
            classification_source="rule",
            rule_id=rule_id,
            leg_type="buy_leg",
            leg_index=1,
        )

        legs = [parent, sell_leg, buy_leg]

        if has_fee:
            fee_leg = self._make_record(
                transaction_id=tx_id,
                category=TaxCategory.FEE.value,
                confidence=confidence,
                notes=f"{notes} (fee leg)",
                needs_review=needs_review,
                classification_source="rule",
                rule_id=rule_id,
                leg_type="fee_leg",
                leg_index=2,
            )
            legs.append(fee_leg)

        return legs

    # ------------------------------------------------------------------
    # DB writes
    # ------------------------------------------------------------------

    def _make_record(
        self,
        transaction_id: int | None,
        category: str,
        confidence: float,
        notes: str = "",
        needs_review: bool = False,
        classification_source: str = "rule",
        rule_id: int | None = None,
        leg_type: str = "parent",
        leg_index: int = 0,
        staking_event_id: int | None = None,
        lockup_event_id: int | None = None,
        fmv_usd=None,
        fmv_cad=None,
    ) -> dict:
        """Build a classification record dict."""
        if confidence < self.REVIEW_THRESHOLD:
            needs_review = True
        return {
            "transaction_id": transaction_id,
            "category": category,
            "confidence": confidence,
            "notes": notes,
            "needs_review": needs_review,
            "classification_source": classification_source,
            "rule_id": rule_id,
            "leg_type": leg_type,
            "leg_index": leg_index,
            "staking_event_id": staking_event_id,
            "lockup_event_id": lockup_event_id,
            "fmv_usd": fmv_usd,
            "fmv_cad": fmv_cad,
        }

    def _upsert_classification(self, conn, record: dict) -> int:
        """Upsert a classification record. Preserves specialist-confirmed records.

        Uses INSERT ... ON CONFLICT DO UPDATE WHERE specialist_confirmed = FALSE.
        Returns classification id.
        """
        cur = conn.cursor()

        tx_id = record.get("transaction_id")
        exc_tx_id = record.get("exchange_transaction_id")
        leg_type = record.get("leg_type", "parent")
        leg_index = record.get("leg_index", 0)

        cur.execute(
            """
            INSERT INTO transaction_classifications
                (user_id, transaction_id, exchange_transaction_id,
                 leg_type, leg_index, category, confidence,
                 classification_source, rule_id,
                 staking_event_id, lockup_event_id,
                 fmv_usd, fmv_cad, needs_review,
                 specialist_confirmed, created_at, updated_at)
            VALUES
                (%(user_id)s, %(transaction_id)s, %(exchange_transaction_id)s,
                 %(leg_type)s, %(leg_index)s, %(category)s, %(confidence)s,
                 %(classification_source)s, %(rule_id)s,
                 %(staking_event_id)s, %(lockup_event_id)s,
                 %(fmv_usd)s, %(fmv_cad)s, %(needs_review)s,
                 FALSE, NOW(), NOW())
            ON CONFLICT ON CONSTRAINT uq_tc_tx_leg
            DO UPDATE SET
                category = EXCLUDED.category,
                confidence = EXCLUDED.confidence,
                classification_source = EXCLUDED.classification_source,
                rule_id = EXCLUDED.rule_id,
                staking_event_id = EXCLUDED.staking_event_id,
                lockup_event_id = EXCLUDED.lockup_event_id,
                fmv_usd = EXCLUDED.fmv_usd,
                fmv_cad = EXCLUDED.fmv_cad,
                needs_review = EXCLUDED.needs_review,
                updated_at = NOW()
            WHERE transaction_classifications.specialist_confirmed = FALSE
            RETURNING id
            """,
            {
                "user_id": record.get("user_id", 0),
                "transaction_id": tx_id,
                "exchange_transaction_id": exc_tx_id,
                "leg_type": leg_type,
                "leg_index": leg_index,
                "category": record["category"],
                "confidence": record["confidence"],
                "classification_source": record.get("classification_source", "rule"),
                "rule_id": record.get("rule_id"),
                "staking_event_id": record.get("staking_event_id"),
                "lockup_event_id": record.get("lockup_event_id"),
                "fmv_usd": record.get("fmv_usd"),
                "fmv_cad": record.get("fmv_cad"),
                "needs_review": record.get("needs_review", True),
            },
        )
        row = cur.fetchone()
        return row[0] if row else 0

    def _write_audit_log(self, conn, classification_id: int, record: dict,
                         old_record: dict | None = None) -> None:
        """Write audit log entry for a classification change.

        change_reason: 'initial' for new, 'rule_update' for re-classification.
        """
        if not classification_id:
            return

        cur = conn.cursor()
        old_category = old_record["category"] if old_record else None
        old_confidence = old_record["confidence"] if old_record else None
        change_reason = "rule_update" if old_record else "initial"

        cur.execute(
            """
            INSERT INTO classification_audit_log
                (classification_id, changed_by_user_id, changed_by_type,
                 old_category, new_category, old_confidence, new_confidence,
                 change_reason, rule_id, notes, created_at)
            VALUES
                (%s, NULL, 'system', %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                classification_id,
                old_category,
                record["category"],
                old_confidence,
                record["confidence"],
                change_reason,
                record.get("rule_id"),
                record.get("notes", ""),
            ),
        )

    # ------------------------------------------------------------------
    # AI fallback (lazy Anthropic client — same pattern as AIFileAgent)
    # ------------------------------------------------------------------

    @property
    def ai_client(self):
        """Lazy Anthropic client. Returns None if SDK not installed."""
        if not hasattr(self, '_ai_client') or self._ai_client is None:
            try:
                from anthropic import Anthropic
                self._ai_client = Anthropic()
            except ImportError:
                logger.warning("anthropic SDK not installed; AI fallback disabled")
                self._ai_client = None
        return self._ai_client

    def _classify_with_ai(self, tx_context: dict) -> dict:
        """Classify an ambiguous transaction using Claude API.

        Args:
            tx_context: dict with tx details (chain, action_type, method_name,
                       counterparty, direction, amount, token_id, raw_data summary)

        Returns:
            Classification result dict with category, confidence, notes, needs_review.
        """
        if self.ai_client is None:
            return {
                "category": TaxCategory.UNKNOWN.value,
                "confidence": 0.30,
                "notes": "AI fallback unavailable (anthropic SDK not installed)",
                "needs_review": True,
                "rule_id": None,
                "classification_source": "ai",
            }

        try:
            response = self.ai_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                system=CLASSIFICATION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(tx_context, default=str)}],
            )

            result = self._parse_json_response(response.content[0].text)

            category_str = result.get("category", "unknown").lower()
            confidence = float(result.get("confidence", 0.30))
            reasoning = result.get("reasoning", "")
            needs_review = result.get("needs_review", True)

            # Validate category against known values
            try:
                TaxCategory(category_str)
            except ValueError:
                logger.warning("AI returned unknown category '%s'; falling back to unknown", category_str)
                category_str = TaxCategory.UNKNOWN.value
                confidence = min(confidence, 0.50)
                needs_review = True

            # Always flag low-confidence AI results for review
            if confidence < AI_CONFIDENCE_THRESHOLD:
                needs_review = True

            return {
                "category": category_str,
                "confidence": confidence,
                "notes": f"AI: {reasoning}" if reasoning else "AI classification",
                "needs_review": needs_review,
                "rule_id": None,
                "classification_source": "ai",
            }

        except Exception as exc:
            logger.warning("AI classification failed: %s", exc)
            return {
                "category": TaxCategory.UNKNOWN.value,
                "confidence": 0.30,
                "notes": f"AI classification error: {exc}",
                "needs_review": True,
                "rule_id": None,
                "classification_source": "ai",
            }

    def _parse_json_response(self, text: str) -> dict:
        """Parse AI JSON response with regex fallback for markdown code blocks.

        Reuses exact pattern from indexers/ai_file_agent.py.
        """
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise

    def _build_ai_context(self, tx: dict, chain: str) -> dict:
        """Build context dict for AI classification.

        Includes relevant tx fields but excludes raw_data bulk to keep
        token count low.
        """
        raw_data = tx.get("raw_data") or {}
        # Include only key raw_data fields, not entire blob
        raw_summary = {}
        if isinstance(raw_data, dict):
            for key in ("input", "logs", "events", "token_id", "memo"):
                if key in raw_data:
                    val = raw_data[key]
                    # Truncate long strings
                    if isinstance(val, str) and len(val) > 200:
                        val = val[:200] + "..."
                    raw_summary[key] = val

        return {
            "chain": chain,
            "action_type": tx.get("action_type", ""),
            "method_name": tx.get("method_name", ""),
            "counterparty": tx.get("counterparty", ""),
            "direction": tx.get("direction", ""),
            "amount": str(tx.get("amount") or 0),
            "tx_type": tx.get("tx_type", ""),
            "raw_data_summary": raw_summary,
        }

    # ------------------------------------------------------------------
    # FMV helper
    # ------------------------------------------------------------------

    def _get_fmv(self, coin_id: str, timestamp: int, currency: str = "usd") -> Decimal | None:
        """Get FMV for income events using PriceService.

        Returns None if PriceService not configured or price unavailable.
        """
        if self.price_service is None:
            return None
        try:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(timestamp / 1e9, tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
            return self.price_service.get_price(coin_id, date_str, currency)
        except Exception:
            return None
