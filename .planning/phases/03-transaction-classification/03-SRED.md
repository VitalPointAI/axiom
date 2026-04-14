# Phase 3 — SR&ED Brief

**Phase:** 3 — Transaction Classification
**Fiscal year:** 2025
**Eligibility:** LIKELY — requires review before filing
**Status:** DRAFT
**Last updated:** 2026-04-14

> ⚠️ **Eligibility caveat:** Parts of this phase are clearly in the "standard engineering" bucket (rule-based classifier, audit log plumbing, specialist review UI plumbing). What *may* qualify as SR&ED is the **rule+AI hybrid classification** approach with confidence-triaged specialist review, the **multi-leg decomposition of arbitrary EVM DeFi contracts** via AI-powered contract-source discovery, the **global spam intelligence pattern** that propagates from one flagged transaction to similar ones across users, and the **wallet-discovery graph analysis** for same-owner detection. Frame the claim narrowly around those specific components — do not claim the whole phase as R&D. Before filing, confirm with a SR&ED consultant which carve-outs hold up.

---

## 1. Project summary

Phase 3 is Axiom's transaction classification engine. For every transaction ingested by Phase 1 (NEAR) and Phase 2 (EVM + exchanges), the engine must determine: what tax category does this transaction fall into (one of 35+ fine-grained Koinly-compatible categories extended for full Canadian compliance), is it spam, is it an internal transfer between the user's own wallets, should it be decomposed into multiple legs (e.g., a DEX swap = sell leg + buy leg + fee leg), and what confidence does the engine have in its classification. Every classification must be auditable under CRA scrutiny and every specialist review must be traceable.

The core engineering problem is that the classification space is combinatorial and partially observable: Axiom cannot enumerate every possible DeFi contract a user might interact with, and rule-based classification alone cannot keep up with the long tail. The solution hybridizes deterministic rules (which handle the well-known 80%+ of transactions like simple transfers, known staking pools, major DEX routers) with AI-assisted classification for the ambiguous long tail, gates every classification behind specialist review before it affects tax numbers, and maintains a confirmable-rule data model where a specialist can review a *sample* of transactions a proposed rule would affect *before* confirming it globally.

---

## 2. Technological uncertainty

**What was unknown going in?**

- **U-1 — Whether a rule+AI hybrid classifier could stay CRA-defensible when specialist review is the only gate.** The "excruciating detail under the hood, friendly summarized view on top" requirement (from CONTEXT "Specifics") means the engine must capture *why* it classified a transaction the way it did, at a level a specialist can trace. Whether Claude-API-generated classifications could produce reasoning traces that hold up under audit — and whether specialists could confirm them efficiently — was unknown.
- **U-2 — Whether multi-leg decomposition could be computed reliably for arbitrary EVM DeFi contracts.** ABI/method-signature decoding handles known contracts; for unknown contracts the plan was "AI-powered decoding — find contract source, understand how transactions are built." Whether that actually works across the DeFi long tail (forks of Uniswap, bespoke Aave forks, novel LP primitives) was unknown at planning time.
- **U-3 — Whether global spam intelligence could propagate safely.** The design is: one user tags one transaction as spam → system searches for similar transactions across *all* user accounts and marks them too. The technical uncertainty is the similarity function — false positives here mean silently hiding legitimate transactions from other users' tax reports. No published similarity function for "spam-like crypto transactions" exists that Axiom could adopt as-is.
- **U-4 — Whether wallet-discovery graph analysis could reliably identify same-owner wallets across chains without false positives.** The existing `engine/wallet_graph.py` had a pattern-matching starting point using interaction frequency/volume, but whether it could scale to the heterogeneous data Phase 2 produces — and produce suggestions specific enough to trust — was an open question.
- **U-5 — Whether confidence-triaged specialist review (high → quick, medium → closer look, low → deep investigation) could be calibrated such that specialists actually catch errors at each tier.** The design splits specialist effort by AI confidence, but whether the confidence score correlates with actual error rate at each tier required empirical measurement.

**Why couldn't a competent professional have solved this with existing knowledge?**

Off-the-shelf crypto tax tools use opaque classification engines (Koinly et al.) whose accuracy Aaron found insufficient — that's the origin of the project. There is no published reference design for a hybrid deterministic+AI classifier with specialist-gated sample-review, wallet-discovery, and global spam intelligence, where all classifications are auditable at CRA-defensible granularity. The individual techniques exist in isolation (Claude API classification is standard; graph analysis for wallet discovery exists as research papers), but composing them into a CRA-defensible specialist workflow with rule-as-data versioning was not precedented.

Supporting references:
- [03-CONTEXT.md](03-CONTEXT.md) — decisions framed 2026-03-12
- [03-RESEARCH.md](03-RESEARCH.md)
- [../../PROJECT.md](../../PROJECT.md) — "Tried Koinly but it misses many transactions" — the baseline explicitly named as insufficient

---

## 3. Systematic investigation

**Hypotheses tested:**

1. **H-1 (resolves U-1):** Claude API classification with structured reasoning output produces traces a specialist can confirm or reject efficiently. → Tested in plan 03-02 with real ambiguous transactions from VitalPoint's history.
2. **H-2 (resolves U-2):** AI-powered contract-source discovery + decomposition handles the EVM DeFi long tail well enough that the fallback ("flag for review, don't auto-classify") is rare. → Tested against real user data; failure rate measured in VERIFICATION.
3. **H-3 (resolves U-3):** A spam-similarity function based on contract address, token metadata, dust thresholds, and unsolicited-airdrop heuristics propagates safely without false positives on legitimate transactions. → Tested via specialist-confirmation sampling; rule requires sample review before global application, which bounds the blast radius of false positives.
4. **H-4 (resolves U-4):** The wallet-graph owned-wallet detection produces suggestions a specialist trusts at ≥X% acceptance rate. → Validated against VitalPoint's known wallet inventory (64 NEAR accounts are a known-ground-truth test set).
5. **H-5 (resolves U-5):** AI confidence scores are calibrated well enough that the three triage tiers (90%+ / 70–89% / <70%) correlate with actual error rates. → Measured empirically; tier thresholds may be adjusted based on observed precision.

**Experimental procedure — phase structure:**

- [03-01-PLAN.md](03-01-PLAN.md) / [SUMMARY](03-01-SUMMARY.md)
- [03-02-PLAN.md](03-02-PLAN.md) / [SUMMARY](03-02-SUMMARY.md)
- [03-03-PLAN.md](03-03-PLAN.md) / [SUMMARY](03-03-SUMMARY.md)
- [03-04-PLAN.md](03-04-PLAN.md) / [SUMMARY](03-04-SUMMARY.md)
- [03-05-PLAN.md](03-05-PLAN.md) / [SUMMARY](03-05-SUMMARY.md)

Git history: `git log --oneline --grep="03-"`.

**Failed attempts / pivots:**

- **Rejected: auto-confirm high-confidence classifications.** CONTEXT explicitly says "Nothing is auto-confirmed — every classification goes through specialist review." This is a documented design decision to *not* trust the AI beyond triage — i.e. an experiment (auto-confirm) was considered and rejected based on the defensibility argument.
- **Rejected: reuse the legacy `engine/classifier.py` as-is.** CONTEXT notes it was SQLite-based and needed PostgreSQL rewrite; implicit in the plan is that the logic patterns were reusable but the implementation was not. A full rewrite was performed.
- **Rejected: auto-add suggested wallets.** CONTEXT says wallet discovery *suggests* auto-adding, not performs it — specialist review is the gate. An auto-add approach was considered and rejected.
- **Deferred: network visualization / forensic analysis** for wallet relationships → Phase 7 UI.
- **Deferred: tax specialist/auditor UI section** → Phase 7 UI, but data model lives in Phase 3 so the boundary had to be designed carefully.
- **Pivot: classification rules in database vs code.** Initially the path would have been hardcoded rules (simpler), but the requirement for "new rules can be added without code deploys" and specialist-confirmation workflow forced the rules-as-data design.

---

## 4. Technological advancement

**New knowledge generated:**

- A reference pattern for hybrid deterministic + AI-assisted classification with sample-based specialist confirmation, versioned rules-as-data, and CRA-defensible audit trails for every classification.
- An empirically-validated spam similarity function and propagation model with bounded blast-radius (sample review before global application).
- A multi-leg decomposition pattern for DeFi swaps that unifies NEAR and EVM under one data model (`parent + sell_leg + buy_leg + fee_leg`) feeding a downstream ACB engine that treats each leg independently.
- Calibration data for Claude-API confidence scoring on crypto transaction classification — what confidence threshold actually corresponds to what error rate. Reusable beyond this phase.
- A wallet-ownership graph analysis refinement for cross-chain same-owner detection, building on and improving the legacy `wallet_graph.py`.

**How this advances beyond the baseline:**

Baseline: Koinly-style opaque classification that Aaron verified was insufficient ("misses many transactions"). Internal legacy classifier in `engine/classifier.py` was SQLite/float-based, couldn't handle multi-chain, couldn't decompose multi-leg swaps, and had no specialist gate.

Post-project: Axiom has a classification engine that a specialist can audit end-to-end, where every classification links back to either a confirmed rule (with the sample the specialist reviewed when confirming it), or an AI classification (with the reasoning trace), or both. This is generalizable beyond Axiom's own use case.

Measurements (pull from [03-VERIFICATION.md](03-VERIFICATION.md) at filing):
- [ ] Classification accuracy against hand-labeled test set
- [ ] Confidence score calibration by tier
- [ ] Spam false-positive rate
- [ ] Multi-leg decomposition failure rate for unknown EVM contracts

---

## 5. Supporting evidence inventory

| Evidence | Location | Date range |
|---|---|---|
| Phase CONTEXT | [03-CONTEXT.md](03-CONTEXT.md) | 2026-03-12 |
| Research notes | [03-RESEARCH.md](03-RESEARCH.md) | 2026-03-12+ |
| Execution plans (5) | `03-01-PLAN.md` … `03-05-PLAN.md` | 2026-03-12+ |
| Plan summaries | `03-01-SUMMARY.md` … `03-05-SUMMARY.md` | 2026-03-12+ |
| Verification | [03-VERIFICATION.md](03-VERIFICATION.md) | at completion |
| Validation | [03-VALIDATION.md](03-VALIDATION.md) | at completion |
| Git history | `git log --oneline --grep="(03-"` | 2026-03-12+ |
| Alembic migration | `db/migrations/versions/003_*.py` | 2026-03-12+ |

---

## 6. Labour (populated from timesheet.csv at filing)

Query: `awk -F, '$3 ~ /^03/ {sum+=$4} END {print sum}' ../sred/timesheet.csv`

| Person | Hours | Role | Notes |
|---|---|---|---|
| *(to be filled)* | | | |

---

## 7. Other expenditures (populated at filing)

- Claude API usage attributable to classification runs (track usage per job type in cost dashboard)
- CoinGecko / CryptoCompare API usage for classification-time FMV lookups
- No contractor costs

---

## 8. Confidence check (self-review before filing)

- [x] Uncertainty is specific and framed at context gathering
- [x] Systematic investigation evidence exists
- [x] Rejected / pivot evidence present (auto-confirm rejected, legacy classifier rewrite)
- [ ] **Eligibility review with SR&ED consultant** — LIKELY, not STRONG. Narrow the claim to the hybrid classifier + spam-intelligence + wallet-discovery components; do *not* claim generic audit log / rules-engine plumbing as R&D.
- [ ] Advancement numbers pulled from VERIFICATION.md at filing
- [ ] Labour hours from contemporaneous timesheet
- [x] No marketing/pitch content mixed in
