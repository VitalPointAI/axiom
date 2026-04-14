# Phase 2 — SR&ED Brief

**Phase:** 2 — Multi-Chain + Exchanges
**Fiscal year:** 2025
**Eligibility:** LIKELY — requires review before filing
**Status:** DRAFT
**Last updated:** 2026-04-14

> ⚠️ **Eligibility caveat:** Most of this phase is standard integration work (Etherscan V2 pagination, Coinbase CSV parsing, plugin ABCs, job queue wiring) and is *not* SR&ED. What *may* qualify is specifically the **AI-powered universal file ingestion agent** — parsing arbitrary unknown exchange export formats (CSV/PDF/XLSX/DOC) via a Claude-API-driven extraction agent with confidence-scored auto-commit, handling formats with no prior parser support — and the **cross-source deduplication algorithm** that links matching on-chain and exchange records at tolerance-bounded amount/time windows. Frame the claim narrowly around those two components. Do not claim the EVM fetcher, CSV parser framework, or plugin ABCs.

---

## 1. Project summary

Phase 2 extends Axiom's ingest layer beyond Phase 1 (NEAR only) to cover EVM chains (ETH, Polygon, Optimism, Cronos), Cosmos SDK chains (Akash), XRP Ledger, Sweat (NEAR subnet), and the full set of centralized exchanges via both API connectors and file imports. It establishes two plugin systems — one for chains, one for exchanges — and unifies everything into PostgreSQL with job queue integration, cross-source deduplication, and multi-user isolation.

The novel component, and the one this brief focuses on, is the **AI-powered file ingestion agent**. Every crypto user ends up with a folder of export files from exchanges that no longer exist, exchanges with undocumented CSV formats, exchanges that only produce PDFs, and one-off CSV files they edited manually before forgetting. Traditional CSV parsers handle ~4–5 known vendors; the long tail is where users lose data. Axiom's AI agent accepts *any* file format, extracts transactions via Claude API with a confidence score, auto-commits high-confidence rows, and flags lower-confidence rows for specialist review — never blocking the user on unknown formats, never losing data.

The second partially-novel component is **cross-source deduplication**: detecting when the same real-world transaction appears from multiple ingest sources (e.g., a Coinbase withdrawal showing up in both the Coinbase CSV and the ETH on-chain receive) and linking them into a single canonical record without double-counting.

---

## 2. Technological uncertainty

**What was unknown going in?**

- **U-1 — Whether an AI agent can reliably extract transactions from arbitrary unknown formats with actionable confidence scores.** Claude-API file ingestion is not a published reference pattern for crypto tax data. Whether the agent could handle the heterogeneity of real exchange exports (PDFs with scanned tables, CSVs with localized number formats, XLSX with multiple sheets, exports where the same exchange has 3 different format versions) was an open question. And critically: whether the confidence score would correlate with actual correctness tightly enough that the "auto-commit above threshold" strategy would not lose money.
- **U-2 — Smart routing between traditional parsers and the AI agent.** CONTEXT specifies "traditional parsers handle known simple formats, AI agent handles unknown/complex formats" — but how to *detect* which category a given file falls into, without already knowing the format, was undetermined. A mis-routing (sending a known format to the AI agent) wastes API cost; a mis-routing the other direction produces garbage or a hard failure.
- **U-3 — Cross-source deduplication tolerance bands.** The design is "similar amount (within fee tolerance), close timestamps (within 30 min), compatible asset." But gas fees, exchange withdrawal fees, and timezone-stamped CSV rows vs UTC-stamped chain rows all conspire to make naive matching unreliable. The specific tolerance parameters had to be empirically tuned.
- **U-4 — EVM contract decoding for classification purposes from within the ingest layer.** Phase 3 owns classification, but Phase 2 needs to preserve enough of the raw transaction structure that Phase 3 can decompose later. Which fields to capture, at what level of raw-vs-cooked, required experimentation against real DeFi interactions.
- **U-5 — Parallel processing of multiple exchange files while maintaining global chronological correctness.** The requirement was "parallel is desirable but only if the end result is chronologically correct across all sources." Whether a naive map-reduce over parallel parser workers could produce correct ordering, or whether a serializing step was required, was unknown.

**Why couldn't a competent professional have solved this with existing knowledge?**

For U-1 specifically: there is no published reference for AI-driven crypto-tax file ingestion with confidence-gated auto-commit. This is genuinely novel territory at the time the project started. For U-3, cross-source deduplication of financial transactions is a known *problem* (it appears in accounting software) but the *specific* parameter space for crypto transactions — gas fees, dust, timezone inconsistency, decimal precision mismatches — has no published solution.

The rest of the phase (plugin ABCs, Etherscan V2 pagination, standard CSV parsers) is standard engineering and is *not* SR&ED. Only the AI agent and cross-source dedup are being claimed here.

Supporting references:
- [02-CONTEXT.md](02-CONTEXT.md) — decisions framed 2026-03-12, including the explicit "smart cost routing" and "AI agent extraction team" requirements
- [02-RESEARCH.md](02-RESEARCH.md)

---

## 3. Systematic investigation

**Hypotheses tested (novelty-relevant only):**

1. **H-1 (resolves U-1):** A Claude-API agent with structured extraction output + confidence scoring can handle arbitrary unknown crypto-exchange exports well enough that auto-commit above 85% (or similar threshold) does not produce material errors. → Tested in plan 02-05 against real export files from VitalPoint's exchange accounts.
2. **H-2 (resolves U-2):** File-format detection can be done cheaply (hash of first few rows, extension, MIME) before invoking the AI agent, routing known formats to traditional parsers. → Implemented as a pre-check in the file handler.
3. **H-3 (resolves U-3):** A tolerance band of (amount ± fee-upper-bound, timestamp ± 30min, compatible asset) catches real cross-source duplicates with <1% false positives against VitalPoint's actual cross-source data. → Tested and tuned via plan 02-06.
4. **H-4 (resolves U-5):** Parallel parser workers with a final sort-merge step produce chronologically correct unified output without correctness loss. → Validated in plan 02-06 integration.

**Experimental procedure — phase structure:**

- [02-01-PLAN.md](02-01-PLAN.md) / [SUMMARY](02-01-SUMMARY.md) — Alembic migration + chain/exchange plugin ABCs
- [02-02-PLAN.md](02-02-PLAN.md) / [SUMMARY](02-02-SUMMARY.md) — EVMFetcher (standard integration, **not novel**)
- [02-03-PLAN.md](02-03-PLAN.md) / [SUMMARY](02-03-SUMMARY.md) — Exchange parser PostgreSQL migration (not novel)
- [02-04-PLAN.md](02-04-PLAN.md) / [SUMMARY](02-04-SUMMARY.md) — Service wiring + upload API (not novel)
- [02-05-PLAN.md](02-05-PLAN.md) / [SUMMARY](02-05-SUMMARY.md) — **AI-powered file ingestion agent** (claim-worthy)
- [02-06-PLAN.md](02-06-PLAN.md) / [SUMMARY](02-06-SUMMARY.md) — **Cross-source dedup** + final integration (claim-worthy)
- [02-07-PLAN.md](02-07-PLAN.md) / [SUMMARY](02-07-SUMMARY.md) — Gap closure fixes (not novel)

Git history: `git log --oneline --grep="02-"`. Plans 05 and 06 are the SR&ED-relevant commits.

**Failed attempts / pivots:**

- **Rejected: build CSV parsers for every exchange.** CONTEXT shows `coinbase.py`, `crypto_com.py`, `wealthsimple.py`, `generic.py` existed as partial implementations — the plan was to stop building more parsers per-vendor and instead build the AI agent to handle the long tail. *This is a documented strategic pivot: traditional-per-vendor approach was tried and found to not scale, and the AI approach was adopted as a result.*
- **Rejected: block on unknown formats** (classic parser behavior: "Unsupported file type, please convert to CSV"). Explicitly rejected in CONTEXT — "never lose data, never block on user input."
- **Deferred: email/notification alerts for sync failures** → out of scope for R&D claim, standard ops.
- **Deferred: Coinbase Pro margin trades and exchange-specific advanced features** → out of scope.
- **Deferred: NFT valuation beyond transfer tracking** → future phase.

---

## 4. Technological advancement

**New knowledge generated (narrow claim):**

- A working AI-agent pattern for crypto-tax file ingestion across arbitrary formats with confidence-scored auto-commit and review-flag routing. Reusable beyond Axiom.
- Empirical calibration of Claude-API confidence scores against actual extraction correctness for crypto exchange exports — what threshold corresponds to what error rate. This data did not exist publicly.
- A cross-source deduplication algorithm with empirically tuned tolerance bands that correctly identifies real duplicates across heterogeneous on-chain and exchange data without double-counting.
- A parallel-then-sort-merge ingest pipeline that preserves chronological correctness across mixed ingest sources.

**How this advances beyond the baseline:**

Baseline: crypto tax tools either support only a fixed list of known vendors (Koinly etc.) or require users to manually convert unknown formats — users lose data on the long tail. Cross-source deduplication in existing tools either fails silently or requires manual merging.

Post-project: Axiom ingests arbitrary files with non-zero recovery rate even for formats it's never seen, and automatically identifies cross-source duplicates at configurable tolerance.

Measurements (pull from [02-VERIFICATION.md](02-VERIFICATION.md) at filing):
- [ ] AI agent extraction success rate across test corpus of unknown formats
- [ ] Confidence-score calibration curve
- [ ] Cross-source dedup precision/recall

---

## 5. Supporting evidence inventory

| Evidence | Location | Date range |
|---|---|---|
| Phase CONTEXT | [02-CONTEXT.md](02-CONTEXT.md) | 2026-03-12 |
| Research notes | [02-RESEARCH.md](02-RESEARCH.md) | 2026-03-12+ |
| Execution plans (7) | `02-01-PLAN.md` … `02-07-PLAN.md` | 2026-03-12+ |
| **Claim-worthy plan summaries** | [02-05-SUMMARY.md](02-05-SUMMARY.md), [02-06-SUMMARY.md](02-06-SUMMARY.md) | 2026-03-12+ |
| Other plan summaries | (supporting context only, not claim surface) | 2026-03-12+ |
| Verification | [02-VERIFICATION.md](02-VERIFICATION.md) | at completion |
| Validation | [02-VALIDATION.md](02-VALIDATION.md) | at completion |
| Git history | `git log --oneline --grep="(02-05\|02-06"` | 2026-03-12+ |
| Alembic migration 002 | `db/migrations/versions/002_*.py` | 2026-03-12+ |

---

## 6. Labour (populated from timesheet.csv at filing)

⚠️ **Important:** only log hours spent on plans 02-05 and 02-06 (AI agent, dedup) against phase 02 in the timesheet. Hours spent on plans 02-01 through 02-04 and 02-07 are standard engineering and are NOT SR&ED. Use notes column to distinguish: e.g. `2026-03-15,Aaron Luhning,02.05,3.0,AI agent confidence threshold tuning`.

Query (claim-worthy hours only): `awk -F, '$3 ~ /^02\.(05|06)$/ {sum+=$4} END {print sum}' ../sred/timesheet.csv`

| Person | Hours | Role | Notes |
|---|---|---|---|
| *(to be filled — only 02-05 and 02-06 work)* | | | |

---

## 7. Other expenditures (populated at filing)

- Claude API usage attributable to AI agent development + production runs (separate from classification in Phase 3)
- Not claim-worthy: Etherscan V2 API, exchange APIs — these are standard integration costs

---

## 8. Confidence check (self-review before filing)

- [x] Uncertainty is specific and framed at context gathering
- [x] Systematic investigation evidence exists for the claim-worthy components
- [x] Pivot evidence present (abandoned per-vendor parser approach)
- [ ] **Eligibility review with SR&ED consultant** — LIKELY, not STRONG. **Narrow the claim** to plans 02-05 and 02-06 only. Claiming the whole phase will dilute the strong parts and invite challenge on the weak parts.
- [ ] Advancement numbers pulled from VERIFICATION.md at filing
- [ ] Labour hours from contemporaneous timesheet — and **only the claim-worthy sub-plans**
- [x] No marketing/pitch content mixed in
