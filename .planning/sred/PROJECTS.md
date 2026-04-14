# SR&ED Project Register

**Purpose:** Which Axiom phases are SR&ED-eligible, with one-paragraph technical narratives suitable for T661 Part 2.

**Legend:**
- **STRONG** — Clear technological uncertainty + advancement, should claim
- **LIKELY** — Probably eligible, needs brief review before filing
- **WEAK** — Mostly integration or standard practice, likely not claimable
- **NO** — Pure business logic, UX polish, or routine work
- **TBD** — Not yet assessed

Update this file: when a new phase is added (Claude fills TBD), at phase completion (refine the narrative against what actually happened), and before filing (confirm the STRONG set).

---

## Fiscal Year 2025 (Jan 1 – Dec 31, 2025)

| Phase | Eligibility | Claim-worthy? | One-line uncertainty |
|---|---|---|---|
| 01 — NEAR Indexer | WEAK | Probably not | Mostly integration against existing NEAR RPC / validator APIs |
| 02 — Multi-chain + Exchanges | LIKELY | Review | AI-powered unknown-format file ingestion with confidence scoring is non-trivial |
| 03 — Transaction Classification | LIKELY | Review | Multi-leg decomposition of arbitrary DeFi contracts (NEAR + EVM) with rule+AI hybrid classification and cross-source dedup |
| 04 — Cost Basis Engine | LIKELY | Review | CRA-defensible ACB with pooled superficial-loss detection across wallets + exchanges + pro-rated partial rebuys |
| 05 — Verification | WEAK | Probably not | Balance reconciliation against on-chain state — mostly arithmetic |
| 06 — Reporting | NO | No | Report generation — standard practice |
| 07 — Web UI | NO | No | UI work is explicitly excluded by CRA unless it solves a technical uncertainty |
| 08 — CI/CD Deployment | NO | No | Standard DevOps |
| 09 — Code Quality & Hardening | NO | No | Refactoring |
| 10 — Remaining Concerns Remediation | NO | No | Bug-fix / robustness |
| 11 — Robustness & Audit Log | WEAK | Probably not | Mostly engineering discipline |
| 12 — User Onboarding | NO | No | UX flow |

**FY2025 claim-worthy shortlist (after review):** 02, 03, 04 (pending narrative review)

---

## Fiscal Year 2026 (Jan 1 – Dec 31, 2026)

| Phase | Eligibility | Claim-worthy? | One-line uncertainty |
|---|---|---|---|
| 13 — Reliable Indexing | WEAK | Probably not | Primarily tool evaluation (TheGraph vs SubQuery vs self-hosted) + cost research + standard integration work; outcome was predictable from documentation review. CRA excludes "research to select commercial products." NEAR Lake cost optimization could be a narrow carve-out if experimentation was substantial. |
| 14 — Marketing Frontend | NO | No | Marketing site |
| 15 — Account Block Index Integer Encoding | STRONG | Yes | ~5x storage reduction target via novel combination of dictionary-encoded integer IDs + segment-based indexing, with a hard <2-minute wallet-lookup perf budget and 500GB disk ceiling constraint — outcome unknown until benchmarked |
| 16 — Post-Quantum Encryption at Rest | STRONG | Yes | First-in-class application of NIST FIPS 203 ML-KEM-768 lattice crypto to a blind-server per-user envelope encryption model, riding passkey-derived key custody, with a hard sub-2-minute end-to-end pipeline budget under full-column encryption — performance and correctness of the session→DEK→per-user-pipeline handoff was unknown going in |

**FY2026 claim-worthy shortlist:** 15, 16 (both STRONG — do not skip). Phase 13 downgraded to WEAK on 2026-04-14.

---

## Technical narratives (T661 Part 2 drafts)

Full narratives live in each phase's `{N}-SRED.md` file. This section holds one-paragraph summaries refined from those briefs at filing time.

### Phase 2 — Multi-Chain + Exchanges (narrow claim: plans 02-05, 02-06 only)
Draft brief: [02-SRED.md](../phases/02-multichain-exchanges/02-SRED.md) — **narrow the claim** to the AI-powered file ingestion agent and cross-source deduplication components. Do not claim the EVM fetcher, standard CSV parsers, or plugin ABC scaffolding.

### Phase 3 — Transaction Classification (narrow claim)
Draft brief: [03-SRED.md](../phases/03-transaction-classification/03-SRED.md) — narrow claim around hybrid rule+AI classification with specialist-gated sample review, global spam intelligence, and wallet-discovery graph analysis. Do not claim audit log plumbing or rules-engine framework.

### Phase 4 — Cost Basis Engine
Draft brief: [04-SRED.md](../phases/04-cost-basis-engine/04-SRED.md) — claim rests on pooled cross-source pro-rated superficial loss detection and minute-level multi-provider FMV reconciliation. Baseline ACB math is a known specification and is not SR&ED on its own.

### Phase 15 — Account Block Index Integer Encoding
Draft brief: [15-SRED.md](../phases/15-account-block-index-integer-encoding/15-SRED.md) — STRONG. Combined integer-encoding + segment-indexing with empirical measurement against real NEAR chain data, under a hard 500 GB disk constraint.

### Phase 16 — Post-Quantum Encryption at Rest
Draft brief: [16-SRED.md](../phases/16-post-quantum-encryption-at-rest/16-SRED.md) — STRONG. NIST FIPS 203 ML-KEM-768 integration with passkey-based key custody, session-DEK IPC, accountant-grant DEK rewrapping, HMAC surrogates for pre-session lookup, under a hard sub-2-minute pipeline budget.

---

## Change log

- **2026-04-14** — Register created. Phase 15 and 16 assessed as STRONG; phases 02/03/04 flagged LIKELY pending narrative review at FY2025 filing prep.
- **2026-04-14** — Backfilled draft SRED briefs for phases 02, 03, 04, 15, 16. Phase 13 assessed as WEAK (primarily tool evaluation + standard integration; CRA excludes commercial product research).
