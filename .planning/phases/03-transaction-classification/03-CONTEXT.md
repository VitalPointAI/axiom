# Phase 3: Transaction Classification - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Automatically classify all transactions (NEAR, EVM, exchange) by tax treatment with full granularity. Build a rule-based + AI-assisted classification engine with specialist confirmation workflow, adaptive spam detection, internal transfer detection with wallet discovery, and complete audit trail. All classifications stored in a separate table with full re-classification support.

</domain>

<decisions>
## Implementation Decisions

### Classification Taxonomy
- Koinly-compatible as baseline, extended for full Canadian crypto tax law compliance
- Fine-grained categories that capture exactly what each transaction is doing: staking, transfer, trade, DeFi, TradFi, lending, collateral, liquidity, NFT, spam, etc.
- Use and extend the existing `TaxCategory` enum from `tax/categories.py` (35+ categories)
- Not just CSV export — system must support API access for integration with other business systems
- Full EVM DeFi support: decode Uniswap swaps, Aave deposits, LP positions, etc. with same granularity as NEAR DeFi contracts (using ABI/method signatures)

### Transaction Decomposition
- Full decomposition of complex transactions into individual legs (e.g., DEX swap = sell leg + buy leg + fee)
- Parent-child grouping: each complex transaction gets a parent record with child records for each leg, linked by tx_hash
- Excruciating detail under the hood, friendly summarized view for users (UX is paramount)
- User sees "Swap NEAR → USDC" with ability to drill into individual legs when needed

### Staking Event Handling
- Reference, don't duplicate: staking rewards in `staking_events` already have FMV
- Classifier marks corresponding transaction as 'reward' and links to the staking_event record
- No duplicate income records — single source of truth per event

### Deduplication
- Zero duplicate transactions — dedup must be airtight across all sources (on-chain, exchange, AI-imported)
- Classifier catches any remaining duplicates beyond Phase 2's cross-source dedup
- Staking rewards: no double-counting between `transactions` and `staking_events`

### Spam Detection
- Multi-signal auto-detection: known spam contract lists, dust amounts below threshold, tokens with no market value, unsolicited airdrops from unknown contracts
- User can manually tag transactions as spam → system learns from it
- Tagging propagates globally: mark one spam → find similar across ALL user accounts (global spam intelligence)
- Spam ruleset grows organically as users tag — constantly learning and adapting

### Ambiguous Transaction Handling
- Hybrid approach: deterministic rules handle known patterns (80%+), Claude API analyzes genuinely ambiguous ones
- AI confidence score on everything to help specialist triage
- Nothing is auto-confirmed — every classification goes through specialist review
- Confidence score helps triage: high (90%+) = quick review, medium (70-89%) = closer look, low (<70%) = deep investigation

### Specialist Confirmation Workflow
- Dedicated tax specialist/auditor section with role-based access
- Every classification rule and tax calculation displayed with clear reasoning
- Per-rule confirmation: specialist reviews a sample of transactions the rule would classify, then confirms
- Once confirmed, rule applies globally across ALL user accounts
- Audit trail: who confirmed what, when, sample reviewed — defensible under CRA scrutiny

### Internal Transfer Detection
- Amount + timing matching for cross-chain transfers: similar amount (within fee tolerance), close timestamps (within 30 min), compatible asset
- Owned-but-with-exceptions: transfers between owned wallets generally classified as internal, but flag edge cases for specialist review (DAO distributions that may be income, lockup vesting that's already in lockup_events, validator reward claims where reward portion is income)
- Auto-learn deposit addresses: when specialist confirms a transfer is internal, record the counterparty address. Future transfers to same address auto-classify as internal
- Wallet discovery: after ingesting a wallet's transactions, identify other wallets likely owned by the same user and suggest auto-adding for ingestion

### Classification Rules in Database
- Classification rules stored as database records: pattern, category, confidence, specialist_confirmed, sample_reviewed
- Enables specialist confirmation workflow, rule versioning, adaptive spam learning
- New rules can be added without code deploys

### Re-classification Policy
- New transactions: always classified fresh
- Unconfirmed classifications: re-evaluated on each run (ruleset may have improved)
- Rule update + re-confirmation: triggers re-classification of all transactions that matched the old version of that rule
- Specialist-confirmed classifications preserved unless the underlying rule is updated and re-confirmed

### Audit Trail
- Full audit log of every classification change: timestamp, old value, new value, changed_by (system/specialist/user), reason (rule update/manual override/re-import)
- Critical for CRA audit defensibility

### Claude's Discretion
- Specific inter-wallet edge cases to flag for specialist review (Canadian tax law nuance)
- AI classification prompt design and context provided to Claude API
- Spam detection signal weights and thresholds
- Wallet discovery algorithm (extending wallet_graph.py's pattern matching)
- Database migration design for new tables (classification, rules, audit log)
- EVM ABI decoding strategy and contract interaction parsing

</decisions>

<specifics>
## Specific Ideas

- "We want to protect our users" — every number in a report must be specialist-reviewed and defensible under CRA audit
- "Excruciating detail of every part of the transaction be accurately extracted and recorded, but what the user interacts with is a much more friendly view" — UX paramount, complexity abstracted
- "Tagging a transaction as spam should then trigger a search for other types of transactions like it to mark as spam as well across all user accounts" — global spam intelligence
- "Before final confirmation — show a sampling of transactions that will be classified based on the rule so specialist can confirm it's being applied correctly" — sample-based rule confirmation
- "Wallet discovery so once a user enters a wallet and transactions are updated, it should identify other wallets that are likely also the user's and suggest auto adding" — proactive wallet detection
- "A network visualization to see how wallets relate to each other and provide feedback on who is interacting with who (forensic analysis)" — deferred to Phase 7 UI
- "Must support direct connection (API) access to other business systems" — not just accountant CSV export
- Disregard the legacy 64 hardcoded wallets — those are single-user artifacts. Users add their own wallets

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tax/categories.py`: Rich Koinly-compatible TaxCategory enum (35+ categories), CategoryResult dataclass with confidence scoring, `categorize_near_transaction()` with contract pattern matching for staking pools/DEXes/lending — solid foundation to build on
- `engine/classifier.py`: Legacy classifier with `classify_near_transaction()` and `classify_exchange_transaction()` — SQLite-based, needs PostgreSQL rewrite but logic patterns are reusable
- `engine/wallet_graph.py`: Transfer graph builder with `find_potential_owned_wallets()` using interaction frequency/volume — foundation for wallet discovery, needs PostgreSQL migration
- `indexers/ai_file_agent.py`: Claude API integration pattern with confidence scoring — reusable for AI-assisted classification
- `indexers/dedup_handler.py`: Cross-source dedup with amount tolerance + time window — extends to cross-chain internal transfer detection

### Established Patterns
- Multi-user isolation: `user_id` FK on all data tables (Phase 1 schema)
- Confidence scoring: 0-1 scale with threshold-based routing (Phase 2 AI file agent)
- Job queue: PostgreSQL-backed with cursor resume (Phase 1) — classifier can run as a job
- `needs_review` boolean: already exists on `exchange_transactions` (Phase 2 migration)

### Integration Points
- `db/models.py`: Needs new models for classification table, classification rules, audit log, spam rules
- `db/migrations/`: Alembic migration 003 for classification schema
- `indexers/service.py`: Register classification as a job type in the indexer service
- `indexers/price_service.py`: FMV lookup for income events during classification

</code_context>

<deferred>
## Deferred Ideas

- Network visualization showing wallet relationships and forensic analysis — Phase 7 (UI)
- Tax specialist/auditor UI section with role-based access — Phase 7 (UI), but data model in Phase 3
- Per-minute price tables for precise FMV — pre-build as background job
- Direct API access for business system integration — Phase 7 (API layer)

</deferred>

---

*Phase: 03-transaction-classification*
*Context gathered: 2026-03-12*
