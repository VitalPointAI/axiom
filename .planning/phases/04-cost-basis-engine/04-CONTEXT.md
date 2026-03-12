# Phase 4: Cost Basis Engine - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Calculate Adjusted Cost Base (ACB) per Canadian average cost method for all tokens across all wallets. Track capital gains/losses on disposals, capture FMV for income events (staking rewards, lockup vesting), detect and auto-calculate superficial losses with pro-rated partial rebuy handling. Produce both capital gains and income ledgers. Verification and reporting are separate phases.

</domain>

<decisions>
## Implementation Decisions

### ACB Persistence & Recalculation
- Hybrid approach: recalculate ACB from scratch by replaying all classified transactions chronologically, then cache the result. Re-run only when underlying data changes (new transactions, reclassifications)
- Per-transaction ACB snapshots stored in DB — full audit trail showing ACB-per-unit, total units, total cost, and gain/loss at every acquisition and disposal event (CRA defensible)
- Dual trigger: background job queue (`calculate_acb` job type in IndexerService, triggered after classification completes) + on-demand recalc via API (for specialist reclassification scenarios)
- Per-user scope: one job calculates ACB for all tokens a user holds (typical user has 5-15 tokens)

### FMV & Price Handling
- Minute-level price granularity — fetch closest-minute price for each transaction timestamp, not daily
- On-demand with cache: fetch minute-level price from CoinGecko market_chart/range API when needed, cache in price_cache with minute granularity. Extends existing PriceService caching pattern
- Previous-period fallback: when no price available for exact minute, use most recent available price (last 1-2 minutes). Flag transaction as `price_estimated` for specialist review
- Stablecoin handling: configurable per token — default to 1:1 USD peg for USDT/USDC/DAI, but allow specialist to flag specific stablecoins for real price lookup (e.g., depeg events)
- CAD conversion: Bank of Canada daily rates (CRA-preferred). Fetch USD price from CoinGecko, convert using official BoC CAD/USD rate
- Income events (staking/vesting): use pre-captured FMV from StakingEvent/LockupEvent tables directly as acquisition cost. No re-derivation — ensures consistency with indexing-time values

### Superficial Loss Treatment
- Auto-calculate + flag: engine detects 30-day window matches, calculates denied loss amount, proposes ACB adjustment to replacement property. Flags for specialist review but shows the proposed adjustment
- All wallets pooled: check across ALL user wallets for rebuys within 30 days of any disposal at a loss (CRA-correct — rule applies across all taxpayer accounts)
- All sources: check on-chain transactions AND exchange transactions for rebuys (retail often rebuys on exchanges)
- Pro-rate partial rebuys: if sold 100 NEAR at loss and rebought 50 within 30 days, deny 50% of loss and add denied portion to ACB of the 50 replacement units

### Multi-leg Disposal Mapping
- FMV-based swap treatment: sell leg disposed at FMV of tokens sold (capital gain/loss), buy leg acquired at FMV of tokens received (= same value). CRA barter transaction treatment
- Gas/network fees on swaps: add to acquisition cost of the buy leg (increases ACB, reduces future gains). CRA treats transaction costs as part of acquisition cost
- Consume Phase 3's multi-leg decomposition: parent + sell_leg + buy_leg + fee_leg from TransactionClassification table

### Output Ledgers
- Produce both capital gains ledger (all disposals with gain/loss calculations) and income ledger (staking rewards + lockup vesting with FMV at receipt)
- Both ledgers feed directly into Phase 6 (Reporting)

### Claude's Discretion
- Database schema design for ACB snapshot tables and income ledger tables
- Cache invalidation strategy (dirty flag, version counter, or timestamp comparison)
- Exact CoinGecko market_chart/range API pagination for minute-level data
- Bank of Canada rate API integration details
- ACB recalculation optimization (e.g., only replay from first changed transaction forward)
- How to handle zero-value or dust transactions in ACB calculation

</decisions>

<specifics>
## Specific Ideas

- "Price intervals should be closer to minute vice daily — hopefully be able to find a previous period (last minute or two) fallback and flag it" — minute-level precision is a priority
- "100% data accuracy" principle from Phase 1 context carries forward — ACB must be fully auditable and CRA-defensible
- Per-transaction snapshots enable the specialist to trace any gain/loss calculation back to its exact inputs
- Existing `engine/acb.py` has correct ACB math (acquire/dispose/superficial loss) but is in-memory and float-based — needs PostgreSQL rewrite with Decimal precision

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `engine/acb.py`: Legacy ACBTracker with correct Canadian average cost logic (acquire, dispose, superficial loss detection). In-memory, float-based — needs PostgreSQL migration with Decimal precision
- `engine/prices.py`: Legacy SQLite price fetcher — superseded by `indexers/price_service.py`
- `indexers/price_service.py`: Modern PostgreSQL-backed multi-source price service (CoinGecko + CryptoCompare, outlier filtering, CAD conversion). Currently daily granularity — needs minute-level extension
- `db/models.py`: TransactionClassification model with multi-leg decomposition (parent/sell_leg/buy_leg/fee_leg), category, confidence, fmv_usd/fmv_cad fields
- `db/models.py`: StakingEvent and LockupEvent models with pre-captured fmv_usd/fmv_cad
- `db/models.py`: PriceCache model — coin_id/date/currency with daily granularity (needs minute extension or separate table)

### Established Patterns
- Job queue: PostgreSQL-backed IndexerService with job_type dispatch (Phase 1) — ACB engine registers as `calculate_acb` job type
- Multi-user isolation: user_id FK on all data tables
- Confidence scoring + needs_review: established in classification (Phase 3)
- Decimal precision: NUMERIC types throughout schema (40,0 for yocto/wei, 24,8 for human amounts, 18,8 for FMV)

### Integration Points
- `indexers/service.py`: Register `calculate_acb` job handler
- `indexers/classifier_handler.py`: Trigger ACB job after classification completes
- `db/models.py`: New models for ACB snapshots, income ledger
- `db/migrations/`: Alembic migration 004 for cost basis schema
- `indexers/price_service.py`: Extend for minute-level granularity + Bank of Canada rates

</code_context>

<deferred>
## Deferred Ideas

- Tax-loss harvesting suggestions (optimization, not reporting) — future feature
- Multi-year ACB carryforward reporting — Phase 6 (Reporting)
- T1135 threshold calculation using ACB data — Phase 6 (Reporting)
- Affiliated persons superficial loss detection (beyond user's own wallets) — future enhancement

</deferred>

---

*Phase: 04-cost-basis-engine*
*Context gathered: 2026-03-12*
