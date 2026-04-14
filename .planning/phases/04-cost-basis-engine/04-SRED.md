# Phase 4 — SR&ED Brief

**Phase:** 4 — Cost Basis Engine
**Fiscal year:** 2025 (phase work conducted in that fiscal year for the 2025 tax filing)
**Eligibility:** LIKELY — requires review before filing
**Status:** DRAFT (populated from completed phase artifacts — confirm eligibility and narrative before filing)
**Last updated:** 2026-04-14

> ⚠️ **Eligibility caveat:** This phase is borderline. It implements Canadian ACB rules, which are a known specification — *applying a known tax rule to data is not, by itself, SR&ED*. What may qualify is the **pooled cross-wallet pro-rated superficial loss detection across heterogeneous data sources** and **minute-level FMV reconciliation across multiple providers with CAD conversion**, both of which have no off-the-shelf implementation and required experimentation to get right. Before claiming, confirm with Aaron (and ideally a SR&ED consultant) that the novelty argument holds. If it doesn't, drop this phase to WEAK and don't claim — a weak claim dilutes the stronger ones.

---

## 1. Project summary

Phase 4 is Axiom's Adjusted Cost Base (ACB) engine — the core tax calculation layer that replays every user's classified transactions chronologically, tracks average-cost basis per token per wallet, detects disposals and income events, and produces capital-gains and income ledgers that feed the Phase 6 reporting layer. It implements the Canadian Revenue Agency's average-cost method and the superficial loss rule (Income Tax Act s.54), both of which are fixed specifications. The engineering challenge is not the math; the engineering challenge is making it correct against messy real-world data.

Specifically, the engine must: pool *all* user wallets across on-chain and exchange sources when evaluating superficial-loss windows (CRA-correct; the rule applies across all taxpayer accounts), pro-rate partial rebuys within the 30-day window and fold the denied portion into the replacement property's ACB, map multi-leg DeFi swaps as barter transactions (disposal of sold leg at FMV, acquisition of bought leg at FMV, gas added to the buy leg's ACB), reconcile income events against pre-captured FMV from `staking_events` / `lockup_events` (single source of truth, no re-derivation), fetch minute-level USD prices from CoinGecko and convert to CAD using official Bank of Canada daily rates (CRA-preferred), and cache every intermediate ACB snapshot with full audit-trail granularity so a specialist can trace any gain/loss back to its inputs under CRA audit.

---

## 2. Technological uncertainty

**What was unknown going in?**

- **U-1 — Whether pooled cross-source superficial-loss detection could be computed correctly against Axiom's real data.** The CRA rule is straightforward on paper — deny the loss if replacement property is acquired within 30 days across any account held by the same taxpayer — but the data shape Axiom has is messy: on-chain transactions (hash-keyed, timestamped to block), exchange CSV imports (timezone-inconsistent, source-dependent), and AI-parsed unknown formats with confidence scores. Whether a single unified replacement-window query could actually find all the matches *and not hallucinate false ones* on this data was an open question.
- **U-2 — Whether the pro-rated partial-rebuy formula would produce CRA-defensible results at the boundaries.** The pro-rating rule is simple in the "sold 100, rebought 50" textbook example, but real cases include: sold 100 at a loss, rebought 30 on exchange A and 20 on exchange B on different days both within the window; sold 100 at a loss across two disposals a week apart, with overlapping rebuy windows; partial rebuys where the rebought lot is itself later disposed within the 30-day chain. No published reference implementation exists that handles these correctly, and the CRA's own guidance stops at the textbook case.
- **U-3 — Whether minute-level FMV with CoinGecko + Bank of Canada CAD conversion could stay both accurate and cost-bounded against real transaction volumes.** CoinGecko's `market_chart/range` endpoint rate-limits aggressively and returns gaps where no trade occurred. The "previous-period fallback" (use last 1–2 minutes) was a design hypothesis, not a validated rule — whether it produces gain/loss numbers close enough to what a specialist would defend was unknown.
- **U-4 — Whether the multi-leg disposal barter-treatment wiring onto Phase 3's transaction decomposition would produce ACB numbers that reconcile with the verification pass in Phase 5.** Phase 3 decomposes swaps into parent + sell leg + buy leg + fee leg. Phase 4 must consume that structure and treat each leg correctly — but the interaction between decomposition, classification confidence scores, and ACB replay ordering had no precedent.

**Why couldn't a competent professional have solved this with existing knowledge?**

Off-the-shelf crypto tax calculators (Koinly, Accointing, CoinTracking) either handle this poorly (the reason Aaron rejected Koinly in the first place — see [../../PROJECT.md](../../PROJECT.md) "Prior attempt"), handle it in closed-source black boxes, or don't handle it at all for multi-leg DeFi swaps with per-minute FMV and pooled cross-source superficial losses. There is no public reference implementation to copy. The CRA's guidance documents specify the *rule*, not the *algorithm against messy real data*. The novelty is in making the CRA-defensible implementation work against Axiom's actual input shape.

Supporting references:
- [04-CONTEXT.md](04-CONTEXT.md) — decisions framed 2026-03-12
- [04-RESEARCH.md](04-RESEARCH.md) — research notes
- [../../PROJECT.md](../../PROJECT.md) — "Tried Koinly but it lacks API access and misses many transactions"

---

## 3. Systematic investigation

**Hypotheses tested:**

1. **H-1 (resolves U-1):** A single SQL query against the unified `transactions` table (joined through classifications) can find all superficial-loss window matches across on-chain + exchange sources for a given user. → Tested in plan 04-02 against real vitalpointai.near data.
2. **H-2 (resolves U-2):** Pro-rating by rebought-quantity ratio produces numbers that match the textbook case *and* the boundary cases. → Tested via unit tests capturing each boundary case.
3. **H-3 (resolves U-3):** Minute-level CoinGecko prices with previous-period fallback + BoC daily CAD rates stay within specialist-acceptable tolerance. → Validated against Phase 5's balance reconciliation.
4. **H-4 (resolves U-4):** ACB replay ordered by `transaction_classifications.timestamp` (not `transactions.block_time`) gives correct results when decomposition produces legs with the same block time. → Tested via Phase 5 verification passes.

**Experimental procedure — phase structure:**

- [04-01-PLAN.md](04-01-PLAN.md) / [SUMMARY](04-01-SUMMARY.md) — ACB snapshot schema, price service extension for minute-level, BoC CAD integration
- [04-02-PLAN.md](04-02-PLAN.md) / [SUMMARY](04-02-SUMMARY.md) — Replay engine, superficial loss detection, income ledger
- [04-03-PLAN.md](04-03-PLAN.md) / [SUMMARY](04-03-SUMMARY.md) — Multi-leg disposal wiring against Phase 3 decomposition

Git history: `git log --oneline --grep="04-"`.

**Failed attempts / pivots:**

- **Rejected: reuse `engine/acb.py` as-is.** Recorded in CONTEXT "Reusable Assets" — the legacy in-memory float-based tracker had correct math but wrong precision (float, not Decimal) and wrong persistence (SQLite, not Postgres). Full rewrite was required — the old one gave wrong numbers on edge cases. *This is a documented failure: a prior implementation did not work, and the rebuild was needed to reach correctness.*
- **Rejected: daily-granularity FMV.** CONTEXT specifies minute-level "because daily was giving noticeably wrong gain/loss on fast-moving tokens." Daily was tried (it's what the `engine/prices.py` legacy fetcher used) and found insufficient for CRA-defensible numbers.
- **Deferred: affiliated-persons superficial loss detection** (e.g., spouse accounts). Recorded in "Deferred Ideas" as out of scope for Axiom's single-user case.
- **Deferred: multi-year ACB carryforward** to Phase 6.
- **Deferred: tax-loss harvesting optimization suggestions** as not-SR&ED (product feature, not R&D).
- **Stablecoin handling:** initially assumed 1:1 USD peg, then realized depeg events (USDC March 2023, UST) would produce wrong numbers — decided to make stablecoin treatment configurable per-token with a specialist flag. This is a documented pivot.

---

## 4. Technological advancement

**New knowledge generated:**

- A validated algorithm for pooled cross-source superficial loss detection with pro-rated partial rebuys and partial-rebuy-chaining, against heterogeneous (on-chain + exchange) data sources. This is the main novelty claim for this phase.
- Minute-level FMV integration pattern combining CoinGecko `market_chart/range` with previous-period fallback and Bank of Canada CAD rates, with a specialist-review flag (`price_estimated`) for transparency.
- A per-transaction ACB snapshot persistence pattern that preserves full audit-trail granularity without exploding storage, tied to replay ordering that is stable across classification changes.
- Canonical handling of multi-leg DeFi swap decomposition for CRA barter treatment, with gas/fee folding into acquisition cost — applied consistently across NEAR and EVM chains.

**How this advances beyond the baseline:**

Baseline: Koinly / Accointing / CoinTracking get cross-source superficial losses wrong on messy data (Aaron observed this firsthand, which is why the project exists). The `engine/acb.py` legacy tracker in Axiom's own codebase was float-based, in-memory, and SQLite — known incorrect on edge cases at the precision required for a CRA audit.

Post-project: Axiom has a defensible, reproducible ACB engine whose outputs a specialist can trace back to individual price lookups, individual classification decisions, and individual superficial-loss calculations — each one individually inspectable and justifiable. The verification pass in [04-VERIFICATION.md](04-VERIFICATION.md) documents what actually held.

Measurements:
- [ ] Correctness rate against Phase 5 balance reconciliation (target: 100% on test wallets)
- [ ] Superficial loss detection precision/recall against hand-traced test cases
- [ ] Per-user recalculation wall-clock time (target inherited from later Phase 15 budget)

*(Pull actual numbers from [04-VERIFICATION.md](04-VERIFICATION.md) at filing.)*

---

## 5. Supporting evidence inventory

| Evidence | Location | Date range |
|---|---|---|
| Phase CONTEXT | [04-CONTEXT.md](04-CONTEXT.md) | 2026-03-12 |
| Research notes | [04-RESEARCH.md](04-RESEARCH.md) | 2026-03-12+ |
| Execution plans (3) | `04-01-PLAN.md` … `04-03-PLAN.md` | 2026-03-12+ |
| Plan summaries | `04-01-SUMMARY.md` … `04-03-SUMMARY.md` | 2026-03-12+ |
| Verification | [04-VERIFICATION.md](04-VERIFICATION.md) | at completion |
| Validation | [04-VALIDATION.md](04-VALIDATION.md) | at completion |
| Git history | `git log --oneline --grep="(04-"` | 2026-03-12+ |
| Alembic migration | `db/migrations/versions/004_*.py` | 2026-03-12+ |

---

## 6. Labour (populated from timesheet.csv at filing)

Query: `awk -F, '$3 ~ /^04/ {sum+=$4} END {print sum}' ../sred/timesheet.csv`

| Person | Hours | Role | Notes |
|---|---|---|---|
| *(to be filled)* | | | |

---

## 7. Other expenditures (populated at filing)

- CoinGecko API usage attributable to ACB recalculation runs
- Bank of Canada API usage (free, but attributed)
- No contractor costs

---

## 8. Confidence check (self-review before filing)

- [x] Uncertainty is specific and framed at context gathering
- [x] Systematic investigation evidence exists (plans, commits, verification)
- [x] Failed-approach / pivot evidence present (legacy `engine/acb.py` rebuild, stablecoin pivot)
- [ ] **Eligibility review with SR&ED consultant** — LIKELY, not STRONG. Confirm that the novelty argument (pooled cross-source pro-rated superficial losses + minute FMV reconciliation) holds up under scrutiny. If it doesn't, drop from claim.
- [ ] Advancement numbers pulled from VERIFICATION.md at filing
- [ ] Labour hours from contemporaneous timesheet
- [x] No marketing/pitch content mixed in
