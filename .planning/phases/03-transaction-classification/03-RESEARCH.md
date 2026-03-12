# Phase 3: Transaction Classification - Research

**Researched:** 2026-03-12
**Domain:** Crypto tax classification engine — rule-based + AI-assisted, PostgreSQL-backed, Canadian tax law
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Classification Taxonomy**
- Koinly-compatible as baseline, extended for full Canadian crypto tax law compliance
- Fine-grained categories: staking, transfer, trade, DeFi, TradFi, lending, collateral, liquidity, NFT, spam, etc.
- Use and extend the existing `TaxCategory` enum from `tax/categories.py` (35+ categories)
- Not just CSV export — system must support API access for integration with other business systems
- Full EVM DeFi support: decode Uniswap swaps, Aave deposits, LP positions, etc. with same granularity as NEAR DeFi contracts (using ABI/method signatures)

**Transaction Decomposition**
- Full decomposition of complex transactions into individual legs (e.g., DEX swap = sell leg + buy leg + fee)
- Parent-child grouping: each complex transaction gets a parent record with child records for each leg, linked by tx_hash
- Excruciating detail under the hood, friendly summarized view for users
- User sees "Swap NEAR → USDC" with ability to drill into individual legs when needed

**Staking Event Handling**
- Reference, don't duplicate: staking rewards in `staking_events` already have FMV
- Classifier marks corresponding transaction as 'reward' and links to the staking_event record
- No duplicate income records — single source of truth per event

**Deduplication**
- Zero duplicate transactions — dedup must be airtight across all sources
- Classifier catches any remaining duplicates beyond Phase 2's cross-source dedup
- Staking rewards: no double-counting between `transactions` and `staking_events`

**Spam Detection**
- Multi-signal auto-detection: known spam contract lists, dust amounts below threshold, tokens with no market value, unsolicited airdrops from unknown contracts
- User can manually tag transactions as spam → system learns from it
- Tagging propagates globally: mark one spam → find similar across ALL user accounts
- Spam ruleset grows organically as users tag

**Ambiguous Transaction Handling**
- Hybrid approach: deterministic rules handle known patterns (80%+), Claude API analyzes genuinely ambiguous ones
- AI confidence score on everything to help specialist triage
- Nothing is auto-confirmed — every classification goes through specialist review
- Confidence score routing: high (90%+) = quick review, medium (70-89%) = closer look, low (<70%) = deep investigation

**Specialist Confirmation Workflow**
- Dedicated tax specialist/auditor section with role-based access
- Per-rule confirmation: specialist reviews a sample of transactions the rule would classify, then confirms
- Once confirmed, rule applies globally across ALL user accounts
- Audit trail: who confirmed what, when, sample reviewed — defensible under CRA scrutiny

**Internal Transfer Detection**
- Amount + timing matching for cross-chain transfers: similar amount (within fee tolerance), close timestamps (within 30 min), compatible asset
- Auto-learn deposit addresses when specialist confirms a transfer is internal
- Wallet discovery: suggest other wallets likely owned by same user after ingesting a wallet

**Classification Rules in Database**
- Classification rules stored as database records: pattern, category, confidence, specialist_confirmed, sample_reviewed
- Enables specialist confirmation workflow, rule versioning, adaptive spam learning
- New rules can be added without code deploys

**Re-classification Policy**
- New transactions: always classified fresh
- Unconfirmed classifications: re-evaluated on each run
- Rule update + re-confirmation: triggers re-classification of all transactions that matched old version of the rule
- Specialist-confirmed classifications preserved unless the underlying rule is updated and re-confirmed

**Audit Trail**
- Full audit log: timestamp, old value, new value, changed_by, reason
- Critical for CRA audit defensibility

### Claude's Discretion
- Specific inter-wallet edge cases to flag for specialist review (Canadian tax law nuance)
- AI classification prompt design and context provided to Claude API
- Spam detection signal weights and thresholds
- Wallet discovery algorithm (extending wallet_graph.py's pattern matching)
- Database migration design for new tables (classification, rules, audit log)
- EVM ABI decoding strategy and contract interaction parsing

### Deferred Ideas (OUT OF SCOPE)
- Network visualization showing wallet relationships and forensic analysis — Phase 7 (UI)
- Tax specialist/auditor UI section with role-based access — Phase 7 (UI), but data model in Phase 3
- Per-minute price tables for precise FMV — pre-build as background job
- Direct API access for business system integration — Phase 7 (API layer)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CLASS-01 | Classify transactions as income/gain/loss/transfer/fee | `TaxCategory` enum already has 35+ categories; `categorize_near_transaction()` in `tax/categories.py` is the foundation; needs migration 003 for `transaction_classifications` table |
| CLASS-02 | Detect internal transfers (between owned wallets) and mark as non-taxable | `wallet_graph.py::find_potential_owned_wallets()` + `is_internal_transfer()` already exist; cross-chain detection uses amount+timestamp matching (extend DedupHandler pattern); needs PostgreSQL rewrite of both files |
| CLASS-03 | Identify staking reward distributions and mark as income | `staking_events` table has event_type='reward' and FMV; classifier references staking_event.id not duplicates; link via tx_hash or timestamp range |
| CLASS-04 | Identify lockup vesting events and mark as income | `lockup_events` table has event_type='vest'/'unlock'; classifier references lockup_event.id; Canadian tax treatment: lockup vesting = income at FMV when accessible |
| CLASS-05 | Identify token swaps/trades and calculate gain/loss | Decompose into parent+legs (sell_leg + buy_leg + fee_leg); EVM needs ABI/event-log decoding for Uniswap/etc.; NEAR uses method_name patterns from `tax/categories.py` |
</phase_requirements>

---

## Summary

Phase 3 builds the classification engine that sits between raw transaction ingestion (Phase 2) and cost basis calculation (Phase 4). The core challenge is multi-source classification: NEAR transactions, EVM transactions, and exchange transactions each have different data shapes and need unified treatment for Canadian tax purposes.

The existing codebase provides strong foundations: `tax/categories.py` contains a 35-category `TaxCategory` enum with working `categorize_near_transaction()` logic, `engine/classifier.py` has SQLite-based logic that needs PostgreSQL rewrite, `engine/wallet_graph.py` has transfer graph detection, and `indexers/ai_file_agent.py` establishes the Claude API pattern with confidence scoring. The migration pattern (Alembic with `op.create_table()`) and job handler pattern (implement a handler class, register in `IndexerService`) are both well-established.

The primary architecture decision is the classification data model: a separate `transaction_classifications` table (not columns on the source tables) is mandatory because: classifications need re-classification support, multi-leg decomposition requires child records, and audit trail needs its own table. This is a clean separation of concerns and enables the specialist confirmation workflow.

**Primary recommendation:** Build migration 003 first (4 new tables: `transaction_classifications`, `classification_rules`, `spam_rules`, `classification_audit_log`), then implement the classifier as a job handler registered in `IndexerService` as `classify_transactions` job type.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg2 | 2.9.x (already in use) | PostgreSQL connection pool | Project standard — used across all handlers |
| anthropic | 0.x (already in use) | Claude API for ambiguous tx classification | Phase 2 established pattern in `AIFileAgent` |
| sqlalchemy | 2.0.x (already in use) | ORM models for new tables | Phase 1/2 standard |
| alembic | 1.x (already in use) | Database migrations | Project standard — migration 003 follows 002b |
| web3 | 6.x (check requirements.txt) | EVM ABI decoding, event log parsing | Industry standard for EVM interaction |
| eth-abi | 4.x | Low-level ABI decoding | Used by web3.py internally; can use directly for efficiency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| decimal | stdlib | Precise amount comparisons | All amount math — NEVER use float for currency |
| dataclasses | stdlib | ClassificationResult, ClassificationRule data structs | Pattern from `CategoryResult` in `tax/categories.py` |
| json | stdlib | Serializing `raw_data` JSONB fields | Established pattern in all existing handlers |
| logging | stdlib | Structured logging | All handlers use `logging.getLogger(__name__)` |

### EVM ABI Decoding — Critical for CLASS-05 EVM swaps
| Library | Purpose | Source |
|---------|---------|--------|
| web3.py `decode_function_input()` | Decode `input` data for known contract ABIs | Uniswap Router ABI required |
| web3.py `eth.get_transaction_receipt()` events | Decode event logs (Transfer events, Swap events) | Swap detection for EVM |

**Note on web3.py availability:** Check `requirements.txt`. If not present, `pip install web3` — it is the canonical EVM Python library. For ABI-based decoding without a live node, only the ABI JSON + raw input hex is needed (no RPC call required).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Claude API for ambiguous tx | Rule-only expansion | Claude handles genuinely novel patterns; rules miss edge cases |
| Separate classifications table | columns on transactions | Separate table required for multi-leg decomposition and re-classification |
| JSONB for rule patterns | separate columns | JSONB allows flexible pattern structure without schema changes per new pattern type |

**Installation (if web3 missing):**
```bash
pip install web3 eth-abi
```

---

## Architecture Patterns

### Recommended File Structure
```
engine/
├── classifier.py          # REWRITE: TransactionClassifier class (PostgreSQL, multi-source)
├── wallet_graph.py        # REWRITE: WalletGraph class (PostgreSQL, user-scoped)
├── prices.py              # NEW: thin wrapper around price_service.py for classifier use
├── evm_decoder.py         # NEW: EVM ABI/event decoder for Uniswap/Aave/LP patterns
└── spam_detector.py       # NEW: SpamDetector class (multi-signal, user-learning)

db/
├── models.py              # EXTEND: add TransactionClassification, ClassificationRule,
│                          #         SpamRule, ClassificationAuditLog models
└── migrations/
    └── versions/
        └── 003_classification_schema.py   # NEW: Alembic migration

indexers/
└── classifier_handler.py  # NEW: ClassifierHandler job handler, registered in service.py

tests/
├── test_classifier.py     # NEW: unit tests for TransactionClassifier
├── test_wallet_graph.py   # NEW: unit tests for WalletGraph
├── test_evm_decoder.py    # NEW: unit tests for EVM ABI decoder
└── test_spam_detector.py  # NEW: unit tests for SpamDetector
```

### Pattern 1: Classification Data Model (4 new tables)

**What:** Separate classification table — NOT columns added to `transactions` or `exchange_transactions`. Parent-child for multi-leg decomposition.

**When to use:** Any time a transaction needs a tax classification stored, including multi-leg decomposition.

```python
# db/models.py additions (pseudo-schema — migration 003 is authoritative)
class TransactionClassification(Base):
    """One row per transaction leg. Complex txs have 1 parent + N children."""
    __tablename__ = "transaction_classifications"

    id              # PK
    user_id         # FK → users.id (multi-user isolation)

    # Source references — exactly one of these is non-null
    transaction_id         # FK → transactions.id (NEAR / EVM on-chain)
    exchange_transaction_id  # FK → exchange_transactions.id

    # Multi-leg decomposition
    parent_classification_id  # FK → self (NULL = parent/standalone, non-NULL = child leg)
    leg_type                  # 'parent', 'sell_leg', 'buy_leg', 'fee_leg'
    leg_index                 # 0-based ordering for display

    # Classification result
    category          # TaxCategory enum value as VARCHAR
    confidence        # NUMERIC(4,3) — 0.000 to 1.000
    classification_source  # 'rule', 'ai', 'manual', 'specialist'
    rule_id           # FK → classification_rules.id (NULL if AI/manual)

    # Staking/lockup linkage (CLASS-03, CLASS-04)
    staking_event_id   # FK → staking_events.id (non-null when category = 'reward')
    lockup_event_id    # FK → lockup_events.id (non-null when category = 'vesting')

    # FMV at time of event (income events need this for CRA reporting)
    fmv_usd    # NUMERIC(18,8)
    fmv_cad    # NUMERIC(18,8)

    # Specialist workflow
    needs_review          # BOOLEAN — routes to specialist queue
    specialist_confirmed  # BOOLEAN — set when specialist approves
    confirmed_by          # user_id of specialist who confirmed
    confirmed_at          # TIMESTAMPTZ

    notes         # TEXT
    created_at    # TIMESTAMPTZ
    updated_at    # TIMESTAMPTZ


class ClassificationRule(Base):
    """Database-driven rules — no code deploy needed for new rules."""
    __tablename__ = "classification_rules"

    id             # PK
    name           # Human-readable rule name
    chain          # 'near', 'evm', 'exchange', 'all'
    pattern        # JSONB: {"method_name": "deposit_and_stake", "counterparty_suffix": ".poolv1.near"}
    category       # TaxCategory value
    confidence     # NUMERIC(4,3) — assigned by rule
    priority       # INT — higher runs first (enables rule ordering)

    # Specialist confirmation workflow
    specialist_confirmed   # BOOLEAN
    confirmed_by           # user_id
    confirmed_at           # TIMESTAMPTZ
    sample_tx_count        # How many transactions were reviewed in confirmation sample

    is_active      # BOOLEAN — soft-delete / disable without losing history
    created_at     # TIMESTAMPTZ
    updated_at     # TIMESTAMPTZ


class SpamRule(Base):
    """Per-user spam detection patterns. Global when user_id IS NULL."""
    __tablename__ = "spam_rules"

    id          # PK
    user_id     # FK → users.id (NULL = global/system rule)
    rule_type   # VARCHAR: 'contract_address', 'dust_threshold', 'token_symbol', 'pattern'
    value       # TEXT: the contract address, threshold, symbol, etc.
    created_by  # user_id who triggered this rule (for 'learned' rules)
    is_active   # BOOLEAN
    created_at  # TIMESTAMPTZ


class ClassificationAuditLog(Base):
    """Full audit trail — every classification change. CRA defensibility."""
    __tablename__ = "classification_audit_log"

    id                      # PK
    classification_id       # FK → transaction_classifications.id
    changed_by_user_id      # FK → users.id (NULL = system)
    changed_by_type         # 'system', 'specialist', 'user'
    old_category            # VARCHAR (NULL for first classification)
    new_category            # VARCHAR
    old_confidence          # NUMERIC(4,3) (NULL for first)
    new_confidence          # NUMERIC(4,3)
    change_reason           # 'initial', 'rule_update', 'manual_override', 're_import', 'specialist_confirm'
    rule_id                 # FK → classification_rules.id if triggered by rule change
    notes                   # TEXT
    created_at              # TIMESTAMPTZ (immutable — audit logs never updated)
```

### Pattern 2: TransactionClassifier — Core Engine

**What:** Stateless classifier that loads rules from DB, applies them in priority order, falls back to AI for low-confidence results.

**Execution flow:**
```
1. Load active ClassificationRules from DB (cached per job run)
2. For each transaction (NEAR / EVM / exchange):
   a. Apply deterministic rules by priority (highest first)
   b. First rule match with confidence >= threshold wins
   c. If no rule match OR confidence < 0.70 → AI fallback
   d. Decompose complex txs into parent + legs
3. For staking rewards: find matching staking_event, link by tx_hash / timestamp
4. For lockup vests: find matching lockup_event, link by tx_hash
5. Write TransactionClassification rows (upsert on source_id + source_type)
6. Write ClassificationAuditLog for every write
7. Set needs_review=True for confidence < 0.90
```

**Rule matching logic (NEAR transactions):**
```python
# Source: existing tax/categories.py patterns — port to rule-based system
def _match_near_rules(self, tx: dict, rules: list[ClassificationRule]) -> ClassificationResult | None:
    method = (tx.get("method_name") or "").lower()
    counterparty = (tx.get("counterparty") or "").lower()
    action_type = (tx.get("action_type") or "").upper()

    for rule in rules:  # already sorted by priority DESC
        if rule.chain not in ("near", "all"):
            continue
        pattern = rule.pattern  # JSONB dict

        if "method_name" in pattern and pattern["method_name"] != method:
            continue
        if "action_type" in pattern and pattern["action_type"] != action_type:
            continue
        if "counterparty_suffix" in pattern and not counterparty.endswith(pattern["counterparty_suffix"]):
            continue
        if "counterparty_contains" in pattern and pattern["counterparty_contains"] not in counterparty:
            continue

        return ClassificationResult(
            category=TaxCategory(rule.category),
            confidence=rule.confidence,
            rule_id=rule.id,
            source="rule",
        )
    return None
```

### Pattern 3: Multi-Leg Decomposition

**What:** Complex transactions (DEX swaps, LP deposits) decomposed into parent + child legs.

**When to use:** Any transaction that has multiple taxable events or needs both sides tracked.

```python
# DEX swap decomposition pattern
def _decompose_swap(self, tx: dict, sell_token: str, buy_token: str, fee_amount: Decimal):
    """Create parent + 3 child legs for a DEX swap."""
    parent = ClassificationRecord(
        category=TaxCategory.TRADE,
        leg_type="parent",
        notes=f"Swap {sell_token} → {buy_token}",
    )
    sell_leg = ClassificationRecord(
        parent_id=parent.id,
        category=TaxCategory.SELL,  # or TRADE disposition
        leg_type="sell_leg",
        leg_index=0,
    )
    buy_leg = ClassificationRecord(
        parent_id=parent.id,
        category=TaxCategory.BUY,  # cost basis establishment
        leg_type="buy_leg",
        leg_index=1,
    )
    fee_leg = ClassificationRecord(
        parent_id=parent.id,
        category=TaxCategory.FEE,
        leg_type="fee_leg",
        leg_index=2,
    )
    return [parent, sell_leg, buy_leg, fee_leg]
```

### Pattern 4: Classifier as IndexerService Job Handler

**What:** Register `ClassifierHandler` in `indexers/service.py` following the exact pattern used by `DedupHandler`.

```python
# indexers/classifier_handler.py
class ClassifierHandler:
    def __init__(self, pool, price_service):
        self.pool = pool
        self.price_service = price_service
        self.classifier = TransactionClassifier(pool, price_service)

    def run_classify(self, job: dict) -> None:
        """Classify all unclassified transactions for job["user_id"]."""
        user_id = job["user_id"]
        # ... classify transactions, EVM transactions, exchange transactions

# indexers/service.py addition
from indexers.classifier_handler import ClassifierHandler
# In __init__:
self.handlers["classify_transactions"] = ClassifierHandler(self.pool, self.price_service)
# In run() dispatch:
elif job_type == "classify_transactions":
    handler.run_classify(job)
```

### Pattern 5: Wallet Graph — PostgreSQL Rewrite

**What:** `engine/wallet_graph.py` rewritten for PostgreSQL + multi-user isolation.

```python
class WalletGraph:
    def __init__(self, pool):
        self.pool = pool

    def get_owned_wallets(self, user_id: int) -> set[tuple[str, str]]:
        """Returns set of (chain, address) for confirmed owned wallets."""

    def is_internal_transfer(self, user_id: int, from_addr: str, to_addr: str) -> bool:
        """Both addresses must be in user's owned wallets."""

    def find_cross_chain_transfer_pairs(self, user_id: int, amount_tolerance: float = 0.05, window_minutes: int = 30) -> list[dict]:
        """Amount+timing match across chains for cross-chain bridge detection."""
        # Extend DedupHandler's algorithm: 30 min window (vs 10 min for dedup)
        # Tolerance: 5% (fee tolerance, not 1% dedup tolerance)

    def suggest_wallet_discovery(self, user_id: int, min_transfers: int = 3) -> list[dict]:
        """Find high-frequency counterparties suggesting ownership — extend wallet_graph.py logic."""
```

### Anti-Patterns to Avoid

- **Adding tax_category column to `transactions` table:** Classifications are separate. Source tables are immutable raw data.
- **Using Python float for amounts:** Always `Decimal`. NEAR yoctoNEAR is 24 decimals, float precision fails.
- **Classifying failed transactions:** Always check `success = True` (or `success IS NULL` for legacy rows) before classifying.
- **Re-classifying specialist-confirmed classifications without rule change:** Once a specialist confirms, preserve unless the underlying rule is updated and re-confirmed.
- **Double-counting staking rewards:** `staking_events` already has event_type='reward' with FMV. Classifier links to these — does not create a new income record for the same event.
- **Auto-committing AI classifications without confidence check:** AI confidence < 0.70 must route to needs_review=True.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| EVM event log decoding | Custom hex parser | `web3.py` `decode_function_input()` + ABI JSON | 256-bit types, indexed params, tuple types — enormous edge case surface |
| Amount precision math | float arithmetic | `Decimal` from stdlib | yoctoNEAR (24 decimals) + wei (18 decimals) will silently lose precision with float |
| AI JSON response parsing | Custom parser | Existing `_parse_json_response()` pattern from `ai_file_agent.py` | Already handles markdown code block wrapping, regex fallback |
| PostgreSQL upsert | manual INSERT + UPDATE | `INSERT ... ON CONFLICT DO UPDATE` | Atomic — no race condition between check and write |
| Connection pool management | Custom pooling | `psycopg2.pool.ThreadedConnectionPool` via `indexers/db.py::get_pool()` | Project already has this abstraction |
| Historical price lookup | Custom price fetcher | `PriceService.get_price(coin_id, date_str, currency)` | Already implemented with CoinGecko + CryptoCompare + caching |

**Key insight:** EVM ABI decoding for DEX swaps (Uniswap V2/V3, Curve, Balancer) involves packed tuple types, dynamic fee tiers, tick math, and path encoding. Do not attempt to decode raw input data manually — use web3.py with the published ABI JSONs.

---

## Common Pitfalls

### Pitfall 1: Staking Reward Double-Counting
**What goes wrong:** Classifier creates a `REWARD` classification for a `transactions` row AND `staking_events` already recorded the same event. Phase 4 cost basis engine then counts income twice.
**Why it happens:** NEAR staking rewards appear as both a FUNCTION_CALL transaction and a `staking_events` row from the StakingFetcher.
**How to avoid:** When classifying as REWARD, first check `staking_events` for a matching row (by wallet_id + tx_hash or by timestamp range within 30 seconds). If found, set `staking_event_id` FK on the classification and mark the `transactions` row as "reference only, income recorded in staking_events".
**Warning signs:** Income total vastly exceeds expected staking yield; staking_event count == transaction REWARD count for same wallet.

### Pitfall 2: Internal Transfer False Positives (DAO Distributions / Vesting)
**What goes wrong:** A transfer between two addresses both in the user's wallet list gets classified as TRANSFER_OUT/TRANSFER_IN, but one is actually a DAO distribution (taxable income) or lockup vesting (taxable income).
**Why it happens:** Wallet graph sees both addresses as "owned" and marks as internal.
**How to avoid:** For transfers from known DAO/lockup contract patterns, flag for specialist review even if both endpoints are "owned". Check if source address ends in `.lockup.near` or is a known DAO treasury. The `lockup_events` table records the canonical vesting events — link to those rather than re-classifying.
**Warning signs:** Lockup vesting events classified as TRANSFER instead of INCOME.

### Pitfall 3: EVM Transaction Multi-Token Transfers Sharing tx_hash
**What goes wrong:** Phase 2 ERC20 transfers use `{tx_hash}-{logIndex}` as the composite key. A Uniswap swap generates: the parent ETH transaction + a USDC Transfer event + a WETH Transfer event + a Swap event — all with the same base tx_hash. Classifying each independently produces 3+ disconnected classifications instead of one unified swap.
**Why it happens:** EVM's event model emits multiple Transfer events per swap.
**How to avoid:** When an EVM tx has method_name matching a DEX router (e.g., `swapExactTokensForTokens`), group all related logIndex records under one parent classification. Key: group by base tx_hash (strip the `-logIndex` suffix).
**Warning signs:** Multiple SELL classifications for what should be one swap.

### Pitfall 4: Spam Detection Overfiring on Legitimate Tokens
**What goes wrong:** Token with zero CoinGecko price gets marked as spam, but it's an in-house utility token or a legitimate low-liquidity token.
**Why it happens:** "No market value" is a spam signal, but not all no-price tokens are spam.
**How to avoid:** Spam confidence must be multi-signal (not single signal). A token with zero price AND unsolicited airdrop AND known spam contract list is spam. A token with zero price but user-initiated transaction should not be auto-spammed. Set spam confidence threshold to 0.90 minimum (2+ signals required).
**Warning signs:** User reports legitimate tokens being hidden.

### Pitfall 5: Re-classification Breaking Confirmed Classifications
**What goes wrong:** A rule is updated and triggers re-classification of all transactions that matched it — including ones the specialist confirmed for different reasons.
**Why it happens:** Re-classification logic doesn't distinguish between "confirmed because rule X was right" vs "confirmed despite rule X being the mechanism".
**How to avoid:** Re-classification on rule update should set `needs_review=True` on previously-confirmed records (not auto-reclassify and lose the confirmation). Specialist must re-confirm. Write an audit log entry explaining the re-trigger.
**Warning signs:** Specialist-confirmed classifications reverting to unconfirmed.

### Pitfall 6: Cross-Chain Internal Transfer Misdetection
**What goes wrong:** Amount+timing matching for cross-chain bridge transfers (NEAR → Aurora, ETH → Polygon) falsely identifies unrelated coincidental transfers from different users.
**Why it happens:** 30-min window + 5% tolerance is broad enough to match unrelated transfers of similar amounts.
**How to avoid:** Cross-chain transfer detection is per-user (only compares transactions belonging to the same user_id). Always filter by `user_id`. Flag candidates as `needs_review=True` for specialist confirmation before marking internal.
**Warning signs:** Transfers to random addresses being marked as internal.

---

## Code Examples

### Classification Result Writing Pattern
```python
# Source: established pattern from dedup_handler.py + ai_file_agent.py
def _upsert_classification(self, conn, classification: dict) -> int:
    """Upsert a classification record. Returns classification id."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transaction_classifications
            (user_id, transaction_id, exchange_transaction_id, parent_classification_id,
             leg_type, leg_index, category, confidence, classification_source, rule_id,
             staking_event_id, lockup_event_id, fmv_usd, fmv_cad,
             needs_review, notes, created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (user_id, transaction_id, leg_type) DO UPDATE SET
            category = EXCLUDED.category,
            confidence = EXCLUDED.confidence,
            classification_source = EXCLUDED.classification_source,
            rule_id = EXCLUDED.rule_id,
            needs_review = EXCLUDED.needs_review,
            notes = EXCLUDED.notes,
            updated_at = NOW()
        WHERE transaction_classifications.specialist_confirmed = FALSE
        RETURNING id
        """,
        (...),
    )
    return cur.fetchone()[0]
```

### Staking Reward Linkage
```python
# Source: existing staking_events schema (db/models.py)
def _find_staking_event(self, conn, user_id: int, wallet_id: int, tx_hash: str, block_timestamp: int) -> int | None:
    """Find staking_event matching this transaction for reward linkage."""
    cur = conn.cursor()
    # Try exact tx_hash match first
    cur.execute(
        "SELECT id FROM staking_events WHERE user_id=%s AND wallet_id=%s AND tx_hash=%s AND event_type='reward'",
        (user_id, wallet_id, tx_hash),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    # Fallback: timestamp range (epoch seconds, 60-second window)
    cur.execute(
        """SELECT id FROM staking_events
           WHERE user_id=%s AND wallet_id=%s AND event_type='reward'
             AND block_timestamp BETWEEN %s AND %s
           LIMIT 1""",
        (user_id, wallet_id, block_timestamp - 60, block_timestamp + 60),
    )
    row = cur.fetchone()
    return row[0] if row else None
```

### AI Classification Fallback (extending AIFileAgent pattern)
```python
# Source: indexers/ai_file_agent.py established pattern
CLASSIFICATION_SYSTEM_PROMPT = """You are a Canadian crypto tax classification expert.
Given a transaction's details, classify it for Canadian tax purposes.

Respond with ONLY a JSON object:
{
  "category": "one of: reward|airdrop|interest|income|buy|sell|trade|transfer_in|transfer_out|
               deposit|withdrawal|stake|unstake|liquidity_in|liquidity_out|loan_borrow|
               loan_repay|collateral_in|collateral_out|fee|spam|nft_mint|nft_purchase|
               nft_sale|internal|unknown",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation for CRA audit trail",
  "needs_review": true/false
}

Set confidence < 0.70 for genuinely ambiguous transactions.
Canadian tax context: crypto-to-crypto trades are taxable dispositions."""

def _classify_with_ai(self, tx_context: dict) -> CategoryResult:
    response = self.client.messages.create(
        model="claude-sonnet-4-20250514",  # same model as ai_file_agent.py
        max_tokens=512,
        system=CLASSIFICATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(tx_context, default=str)}],
    )
    result = self._parse_json_response(response.content[0].text)
    return CategoryResult(
        category=TaxCategory(result["category"]),
        confidence=float(result.get("confidence", 0.5)),
        notes=result.get("reasoning", ""),
        needs_review=result.get("needs_review", True),
    )
```

### EVM Swap Detection via Method Signature
```python
# Known Uniswap V2/V3 router method signatures (first 4 bytes of keccak256 of signature)
# Source: verified against Uniswap open-source contracts
EVM_DEX_SIGNATURES = {
    # Uniswap V2 Router
    "0x38ed1739": "swapExactTokensForTokens",
    "0x8803dbee": "swapTokensForExactTokens",
    "0x7ff36ab5": "swapExactETHForTokens",
    "0x4a25d94a": "swapTokensForExactETH",
    "0x18cbafe5": "swapExactTokensForETH",
    "0xfb3bdb41": "swapETHForExactTokens",
    # Uniswap V3 Router
    "0x414bf389": "exactInputSingle",
    "0xc04b8d59": "exactInput",
    "0xdb3e2198": "exactOutputSingle",
    "0xf28c0498": "exactOutput",
}

def detect_evm_swap(self, tx: dict) -> bool:
    """Check if EVM transaction is a DEX swap by method signature."""
    input_data = tx.get("raw_data", {}).get("input", "")
    if len(input_data) < 10:
        return False
    method_sig = input_data[:10].lower()
    return method_sig in EVM_DEX_SIGNATURES
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLite-based classifier (`engine/classifier.py`) | PostgreSQL + connection pool | Phase 1 (completed) | Multi-user isolation, concurrent access |
| Single-table classification (columns on transactions) | Separate `transaction_classifications` table | This phase | Re-classification, multi-leg, audit trail |
| Hardcoded wallet list (64 wallets) | Dynamic user-owned wallets from DB | Phase 1 | Multi-user system — each user manages their own wallets |
| No audit trail | Full `classification_audit_log` table | This phase | CRA defensibility requirement |

**Deprecated/outdated:**
- `engine/classifier.py` SQLite `get_connection()`: Replace with pool-based pattern from all Phase 2 handlers.
- `engine/wallet_graph.py` SQLite `get_all_owned_addresses()`: Replace with PostgreSQL query scoped by `user_id`.
- `tax/categories.py` module-level `categorize_near_transaction()`: Refactor into `TransactionClassifier` class that loads rules from DB, but keep the logic patterns.

---

## Open Questions

1. **EVM ABI JSONs for known contracts**
   - What we know: web3.py can decode contract calls if given the ABI JSON.
   - What's unclear: Which specific contracts (Uniswap V2/V3 router, Aave, Curve, Balancer) are present in the user's EVM transaction history? Need to check `evm_transactions` raw_data for contract addresses.
   - Recommendation: Bundle known DeFi contract ABIs as static JSON files in `engine/abis/`. Start with Uniswap V2/V3, Aave V2/V3. Add others as needed.

2. **Cross-chain transfer matching thresholds**
   - What we know: DedupHandler uses 10-min window and 1% tolerance for cross-source dedup.
   - What's unclear: Are 30-min window and 5% tolerance correct for cross-chain bridges (NEAR → Aurora, ETH → Polygon)?
   - Recommendation: Use 30-min window (standard bridge settlement time) and 5% tolerance (bridge fees can be ~1-3%). Flag all matches as `needs_review=True` — specialist confirms before marking internal.

3. **Token ID mapping for NEAR FT contracts**
   - What we know: `transactions.token_id` stores FT contract addresses (e.g., `wrap.near`, `usdc.near`). PriceService uses CoinGecko coin_id (e.g., `near`, `usd-coin`).
   - What's unclear: Complete mapping from NEAR FT contract addresses to CoinGecko coin IDs.
   - Recommendation: Build a static mapping table for common NEAR FTs. Unknown tokens get `fmv_usd = NULL` and `needs_review = True`.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already in use — see `tests/` directory) |
| Config file | none — tests run via `pytest tests/` from project root |
| Quick run command | `pytest tests/test_classifier.py -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLASS-01 | NEAR transaction classified with correct TaxCategory and confidence | unit | `pytest tests/test_classifier.py::TestNearClassification -x` | Wave 0 |
| CLASS-01 | Exchange transaction classified correctly (buy→cost_basis, sell→disposition, reward→income) | unit | `pytest tests/test_classifier.py::TestExchangeClassification -x` | Wave 0 |
| CLASS-01 | EVM transaction classified by method signature | unit | `pytest tests/test_classifier.py::TestEVMClassification -x` | Wave 0 |
| CLASS-01 | Multi-leg decomposition creates parent + correct child legs | unit | `pytest tests/test_classifier.py::TestMultiLegDecomposition -x` | Wave 0 |
| CLASS-02 | Internal transfer detected when both addresses are owned wallets | unit | `pytest tests/test_wallet_graph.py::TestInternalTransferDetection -x` | Wave 0 |
| CLASS-02 | Cross-chain transfer pair matching (amount+timing tolerance) | unit | `pytest tests/test_wallet_graph.py::TestCrossChainMatching -x` | Wave 0 |
| CLASS-02 | Non-owned addresses NOT marked internal | unit | `pytest tests/test_wallet_graph.py::TestFalsePositivePrevention -x` | Wave 0 |
| CLASS-03 | Staking reward tx linked to staking_event record, not duplicated | unit | `pytest tests/test_classifier.py::TestStakingRewardLinkage -x` | Wave 0 |
| CLASS-04 | Lockup vest event linked to lockup_events record | unit | `pytest tests/test_classifier.py::TestLockupVestLinkage -x` | Wave 0 |
| CLASS-05 | DEX swap decomposed into sell_leg + buy_leg + fee_leg | unit | `pytest tests/test_classifier.py::TestSwapDecomposition -x` | Wave 0 |
| CLASS-05 | EVM swap detected via method signature | unit | `pytest tests/test_evm_decoder.py::TestSwapDetection -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_classifier.py tests/test_wallet_graph.py -x -q`
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_classifier.py` — covers CLASS-01, CLASS-03, CLASS-04, CLASS-05
- [ ] `tests/test_wallet_graph.py` — covers CLASS-02
- [ ] `tests/test_evm_decoder.py` — covers CLASS-05 EVM path
- [ ] `tests/test_spam_detector.py` — covers spam detection logic

*(All test files are new — existing test infrastructure covers all other handlers but not classifier)*

---

## Sources

### Primary (HIGH confidence)
- Existing codebase: `tax/categories.py` — verified 35-category TaxCategory enum, `categorize_near_transaction()` logic patterns
- Existing codebase: `engine/classifier.py` — legacy SQLite classifier; logic patterns verified, SQLite API to be replaced
- Existing codebase: `engine/wallet_graph.py` — `find_potential_owned_wallets()` algorithm, `is_internal_transfer()` pattern
- Existing codebase: `indexers/ai_file_agent.py` — Claude API integration pattern with confidence scoring (CONFIDENCE_THRESHOLD=0.8)
- Existing codebase: `indexers/dedup_handler.py` — amount+timing matching algorithm (1% tolerance, 10-min window)
- Existing codebase: `indexers/price_service.py` — `PriceService.get_price(coin_id, date_str, currency)` API
- Existing codebase: `db/models.py` — all existing table structures; new tables follow identical patterns
- Existing codebase: `indexers/service.py` — job handler registration pattern for `classify_transactions` job type
- Existing migrations `001`, `002`, `002b` — Alembic `op.create_table()` pattern for migration 003

### Secondary (MEDIUM confidence)
- Canadian crypto tax guidance: CRA position on crypto-to-crypto trades as taxable dispositions (consistent with existing TaxCategory TRADE treatment in `tax/categories.py`)
- Uniswap V2/V3 router method signatures: well-documented in open-source contracts; 4-byte selectors verified against published ABIs

### Tertiary (LOW confidence)
- EVM contract ABIs for Aave, Curve, Balancer: need to be fetched from official sources and bundled as static files; not yet verified for this codebase
- CoinGecko NEAR FT token ID mapping: partial (NEAR native is "near"; USDC on NEAR is "usd-coin"); full mapping for all user FT contracts requires investigation of actual transaction history

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all core libraries already in use in the project
- Architecture: HIGH — patterns directly derived from Phase 1/2 implementations
- Pitfalls: HIGH — identified by inspecting actual existing code paths and data model
- EVM ABI decoding specifics: MEDIUM — method signatures are public but need validation against actual user transaction history

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable domain — Python psycopg2/SQLAlchemy/Alembic patterns don't change rapidly)
