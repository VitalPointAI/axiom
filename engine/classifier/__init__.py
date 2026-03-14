"""
TransactionClassifier — core classification engine for Canadian crypto tax.

Sub-modules: near_classifier, evm_classifier, exchange_classifier, writer,
rules, ai_fallback. PostgreSQL only via psycopg2 pool.
"""

import json
import logging
import re  # noqa: F401 — used by sub-modules via classifier reference
from decimal import Decimal

from tax.categories import TaxCategory, CategoryResult  # noqa: F401 — re-exported
from engine.wallet_graph import WalletGraph
from engine.spam_detector import SpamDetector
from engine.evm_decoder import EVMDecoder

# Sub-module imports (functions accept classifier instance as first arg)
from engine.classifier.near_classifier import (
    classify_near_tx as _classify_near_tx_fn,
    load_staking_event_index as _load_staking_event_index_fn,
    load_lockup_event_index as _load_lockup_event_index_fn,
    find_staking_event as _find_staking_event_fn,
    find_lockup_event as _find_lockup_event_fn,
)
from engine.classifier.evm_classifier import classify_evm_tx_group as _classify_evm_tx_group_fn
from engine.classifier.exchange_classifier import classify_exchange_tx as _classify_exchange_tx_fn
from engine.classifier.rules import (
    match_rules as _match_rules_fn,
    decompose_swap as _decompose_swap_fn,
)
from engine.classifier.writer import (
    make_record as _make_record_fn,
    write_records as _write_records_fn,
    upsert_classification as _upsert_classification_fn,
    write_audit_log as _write_audit_log_fn,
)
from engine.classifier.ai_fallback import (
    classify_with_ai as _classify_with_ai_fn,
    parse_json_response as _parse_json_response_fn,
    build_ai_context as _build_ai_context_fn,
    get_fmv as _get_fmv_fn,
)

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

REVIEW_THRESHOLD = 0.90  # Below this -> needs_review=True (class-level, also importable)


class TransactionClassifier:
    """Core classification engine.

    Args:
        pool: psycopg2 connection pool (ThreadedConnectionPool or similar).
        price_service: Optional PriceService for FMV lookups on income events.
    """

    REVIEW_THRESHOLD = REVIEW_THRESHOLD

    def __init__(self, pool, price_service=None):
        self.pool = pool
        self.price_service = price_service
        self.wallet_graph = WalletGraph(pool)
        self.spam_detector = SpamDetector(pool)
        self.evm_decoder = EVMDecoder()
        self._rules = None  # Lazy-loaded

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

    # Main entry point

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

        # Process NEAR transactions — batch event loading per wallet (N+1 elimination)
        # Group by wallet_id so we load staking/lockup indexes once per wallet
        near_by_wallet: dict[int, list] = {}
        for row in near_txs:
            wid = row[1]
            near_by_wallet.setdefault(wid, []).append(row)

        for wallet_id, wallet_rows in near_by_wallet.items():
            # Load staking + lockup event indexes once for this wallet
            conn = self.pool.getconn()
            try:
                staking_index = self._load_staking_event_index(conn, user_id, wallet_id)
                lockup_index = self._load_lockup_event_index(conn, user_id, wallet_id)
            finally:
                self.pool.putconn(conn)

            for row in wallet_rows:
                tx = _row_to_near_dict(row)
                records = self._classify_near_tx(
                    user_id, tx, rules, owned_wallets,
                    staking_index=staking_index,
                    lockup_index=lockup_index,
                )
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

    # Chain-specific classifiers (delegating to sub-modules)

    def _classify_near_tx(self, user_id: int, tx: dict, rules: list,
                          owned_wallets: set,
                          staking_index: dict | None = None,
                          lockup_index: dict | None = None) -> list:
        """Classify a single NEAR transaction. Delegates to near_classifier module."""
        return _classify_near_tx_fn(
            self, user_id, tx, rules, owned_wallets,
            staking_index=staking_index,
            lockup_index=lockup_index,
        )

    def _classify_exchange_tx(self, user_id: int, tx: dict, rules: list) -> list:
        """Classify a single exchange transaction. Delegates to exchange_classifier module."""
        return _classify_exchange_tx_fn(self, user_id, tx, rules)

    def _classify_evm_tx_group(self, user_id: int, txs: list, rules: list,
                               owned_wallets: set) -> list:
        """Classify a group of EVM transactions. Delegates to evm_classifier module."""
        return _classify_evm_tx_group_fn(self, user_id, txs, rules, owned_wallets)

    # Staking / lockup event index loading (N+1 elimination)

    def _load_staking_event_index(self, conn, user_id: int, wallet_id: int) -> dict:
        """Load all staking reward events for a wallet into an in-memory index."""
        return _load_staking_event_index_fn(self, conn, user_id, wallet_id)

    def _load_lockup_event_index(self, conn, user_id: int, wallet_id: int) -> dict:
        """Load all lockup events for a wallet into an in-memory index."""
        return _load_lockup_event_index_fn(self, conn, user_id, wallet_id)

    # Staking / lockup linkage (CLASS-03, CLASS-04)

    def _find_staking_event(self, user_id: int, wallet_id: int,
                            tx_hash: str, block_timestamp: int,
                            index: dict | None = None) -> int | None:
        """Find staking_event matching this tx for reward linkage (CLASS-03)."""
        return _find_staking_event_fn(self, user_id, wallet_id, tx_hash, block_timestamp, index=index)

    def _find_lockup_event(self, user_id: int, wallet_id: int,
                           tx_hash: str, block_timestamp: int,
                           index: dict | None = None) -> int | None:
        """Find lockup_event matching this tx for vest linkage (CLASS-04)."""
        return _find_lockup_event_fn(self, user_id, wallet_id, tx_hash, block_timestamp, index=index)

    # Rule matching

    def _match_rules(self, tx: dict, rules: list, chain: str) -> dict | None:
        """Match transaction against rules. Delegates to rules.match_rules()."""
        return _match_rules_fn(self, tx, rules, chain)

    # Multi-leg decomposition (CLASS-05)

    def _decompose_swap(self, parent_tx: dict, category_result: dict) -> list:
        """Decompose a swap into parent + child legs. Delegates to rules.decompose_swap()."""
        return _decompose_swap_fn(self, parent_tx, category_result)

    # DB writes (delegating to writer module)

    def _make_record(
        self,
        transaction_id,
        category: str,
        confidence: float,
        notes: str = "",
        needs_review: bool = False,
        classification_source: str = "rule",
        rule_id=None,
        leg_type: str = "parent",
        leg_index: int = 0,
        staking_event_id=None,
        lockup_event_id=None,
        fmv_usd=None,
        fmv_cad=None,
    ) -> dict:
        """Build a classification record dict."""
        return _make_record_fn(
            self, transaction_id, category, confidence, notes=notes,
            needs_review=needs_review, classification_source=classification_source,
            rule_id=rule_id, leg_type=leg_type, leg_index=leg_index,
            staking_event_id=staking_event_id, lockup_event_id=lockup_event_id,
            fmv_usd=fmv_usd, fmv_cad=fmv_cad,
        )

    def _write_records(self, user_id: int, records: list, stats: dict,
                       is_exchange: bool = False, exchange_tx_id=None) -> None:
        """Write classification records to DB, updating stats."""
        _write_records_fn(self, user_id, records, stats,
                          is_exchange=is_exchange, exchange_tx_id=exchange_tx_id)

    def _upsert_classification(self, conn, record: dict) -> int:
        """Upsert a classification record. Preserves specialist-confirmed records."""
        return _upsert_classification_fn(self, conn, record)

    def _write_audit_log(self, conn, classification_id: int, record: dict,
                         old_record: dict | None = None) -> None:
        """Write audit log entry for a classification change."""
        _write_audit_log_fn(self, conn, classification_id, record, old_record=old_record)

    # AI fallback (delegating to ai_fallback module)

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
        """Classify an ambiguous transaction using Claude API."""
        return _classify_with_ai_fn(self, tx_context)

    def _parse_json_response(self, text: str) -> dict:
        """Parse AI JSON response with regex fallback."""
        return _parse_json_response_fn(text)

    def _build_ai_context(self, tx: dict, chain: str) -> dict:
        """Build context dict for AI classification."""
        return _build_ai_context_fn(tx, chain)

    def _get_fmv(self, coin_id: str, timestamp: int, currency: str = "usd") -> Decimal | None:
        """Get FMV for income events using PriceService."""
        return _get_fmv_fn(self, coin_id, timestamp, currency)
