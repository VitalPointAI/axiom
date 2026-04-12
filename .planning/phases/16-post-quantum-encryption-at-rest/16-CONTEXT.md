# Phase 16: Post-Quantum Encryption at Rest - Context

**Gathered:** 2026-04-12
**Status:** Ready for research & planning

<domain>
## Phase Boundary

Deliver end-to-end post-quantum encryption at rest for every piece of user-sensitive or user-linkable data the Axiom server stores. Each user holds their own ML-KEM-768 keypair; the server is blind at rest and can only decrypt during an active authenticated session (or via an explicit opt-in background-worker key the user granted). Key custody, backup, and recovery piggyback on the existing `@vitalpoint/near-phantom-auth` integration — no parallel server-side KEM-secret system.

This phase delivers on the "Post-Quantum Encrypted" marketing claim already live on [web/app/(marketing)/feature-grid.tsx:28](web/app/(marketing)/feature-grid.tsx#L28) and [web/app/(marketing)/privacy/page.tsx:43](web/app/(marketing)/privacy/page.tsx#L43), and collapses what was originally Phase 17 (passkey-derived key custody) into this phase.

**Not in scope:**
- Client-side ZK computation (that's Phase 18)
- Encrypting data in transit beyond existing TLS (already handled)
- Encrypting the `price_cache` or `price_cache_minute` tables (public market data, no user link)
- Encrypting CI/CD secrets or deployment config (handled outside the data plane)

</domain>

<decisions>
## Implementation Decisions

### Encryption Scope (D-01 — D-06)

- **D-01:** Encrypt anything that can link a row back to a person or expose their financial activity. Privacy-maximalist stance. The only cleartext data on the server at rest should be (a) public market data, (b) the minimum metadata needed for routing/indexing/reconciliation queries, and (c) per-user auth lookup hooks (see D-05).
- **D-02:** Encryption granularity is **per-sensitive-column**, not full-row blobs. Cleartext columns that MUST stay cleartext to preserve Phase 15 indexing, gap detection, and per-user query routing: `user_id`, `chain`, `block_height`, `account_block_idx`, `timestamp`, and primary/foreign keys. Every other column carrying PII, financial values, or on-chain identifiers gets encrypted. The exact column list is for the researcher/planner to enumerate against [db/models/_all_models.py](db/models/_all_models.py), but the decision rule is fixed.
- **D-03:** Tables in scope for encryption (non-exhaustive; researcher must enumerate all columns):
  - `transactions` — amounts, counterparty, tx_hash, method, direction, metadata, memo, all financial fields
  - `wallets.account_id` — this is the single biggest linkability vector (public on-chain addresses fully deanonymize the user); MUST be encrypted
  - `staking_events`, `lockup_events`, `epoch_snapshots` — amounts, account refs
  - `transaction_classifications` — classification metadata, counterparty info, reviewer notes
  - `acb_snapshots`, `capital_gains_ledger`, `income_ledger` — all financial columns
  - `verification_results`, `account_verification_status` — balance snapshots, discrepancy details
  - `audit_log` — entity references, before/after diffs, anything linking a user to a change
  - `classification_rules` (user-scoped rules only; global system rules stay cleartext)
  - `spam_rules` (user-scoped only)
- **D-04:** Tables that stay cleartext (not user-linkable or required for pre-auth routing):
  - **Public blockchain cache — the entire Phase 15 public data plane:** `account_transactions`, `account_dictionary`, `account_block_index_v2`, `block_heights`, and any other tables written by the Rust account indexer. These are keyed by public NEAR account IDs (not `user_id`) and mirror already-public on-chain data. Zero linkability risk; encrypting them would kneecap the shared indexer for no privacy gain.
  - `price_cache`, `price_cache_minute` (public market data)
  - `users.id`, `users.created_at` (opaque internal ID and timestamp — no linkability on their own)
  - `sessions`, `passkeys`, `challenges`, `magic_link_tokens` (auth plumbing; already managed by `@vitalpoint/near-phantom-auth` — do not touch; that package's own data model is the source of truth)
  - `indexing_jobs` status metadata (job state, not data content) — but any per-user payload fields get encrypted
  - Global `spam_rules` and system `classification_rules` (user_id IS NULL)
- **D-05:** `users` table PII handling: **hash email, encrypt display_name**.
  - `email` → stored only as a deterministic HMAC (server-key keyed) so login/magic-link lookup works. Raw email is never written to disk.
  - `display_name` → encrypted with a server-held key (not the user DEK, because we need to render it pre-session or for admin). Or better: also encrypted with user DEK and simply not shown pre-session. Researcher to decide which path keeps the login UX coherent.
  - Note: the `auth-service` / near-phantom-auth data model is already "anonymous by design" (codename-based; no email/phone/name stored by near-phantom-auth itself). The `users` table here is Axiom's own bridge table — the email/display_name fields may originate from the OAuth bridge. Researcher must verify what actually lives where and may collapse this decision if near-phantom-auth's codename model already eliminates the PII columns.
- **D-06:** `wallets.account_id` is encrypted with the user's DEK. No blind index on addresses. If duplicate-wallet detection ("this address is already claimed by another user") is required by product, it's a new gray area for a later phase — Phase 16 does not ship blind indices for wallets.

### Query Compatibility (D-07 — D-09)

- **D-07:** **Decrypt-in-app, filter-in-memory** is the sanctioned strategy. SQL queries only filter on cleartext columns (`user_id`, `timestamp`, `chain`, `block_height`). Every other predicate — by category, by counterparty, by amount threshold — is executed in Python after decrypting the user's slice. No blind indices, no deterministic encryption, no searchable encryption. This aligns with "server is blind" and keeps the attack surface minimal.
- **D-08:** No coarse cleartext enums either (tx_type, direction). Those stay encrypted. Aggregate leakage (e.g. "user has N swaps") is explicitly not acceptable.
- **D-09:** **Hard perf budget: protect Phase 15's sub-2-minute wallet lookup.** For the reference workload of vitalpointai.near (~20k transactions), the full pipeline (indexer → classifier → ACB → reconcile → report) must still complete under 2 minutes end-to-end post-encryption. Researcher must benchmark and, if needed, identify a faster batch-decrypt / cached-DEK / process-local key handling path before planning. If the budget cannot be met, that is a blocker for this phase and must surface before planning.

### Key Custody & Recovery (D-10 — D-15)

- **D-10:** **Key custody delegates to `@vitalpoint/near-phantom-auth` (v0.5.2)**, which is already wired into [auth-service/src/server.ts](auth-service/src/server.ts). Do NOT invent a parallel server-held KEM-secret system. Every custody, recovery, backup, and rotation concern must ride the primitives that package already exposes (passkey, NEAR MPC account, wallet recovery via on-chain access key, password+IPFS recovery).
- **D-11:** **User-bound ML-KEM-768 keypair.** Each Axiom user has their own ML-KEM-768 keypair. The public key lives on the server (used to wrap that user's DEK on write). The private key is sealed with material derived from their near-phantom-auth identity (passkey assertion and/or the IPFS+password recovery channel) and unsealed only during an authenticated session. A DB dump alone — even of the Axiom DB + the auth-service DB — must reveal no user data and no key that unlocks user data.
- **D-12:** **Envelope encryption:** per-user DEK, 256-bit, generated at registration, wrapped with the user's ML-KEM-768 public key, stored server-side as wrapped ciphertext. On session establishment, the client's unsealed ML-KEM secret decapsulates the DEK; the DEK lives in process memory for the duration of the request/session and is zeroed on logout or session end. Researcher/planner must read the near-phantom-auth source and figure out the exact sealing/unsealing primitives available — this is the MOST IMPORTANT research task in this phase.
- **D-13:** **Recovery is whatever near-phantom-auth already provides** — namely (a) linked NEAR wallet via on-chain access key (not stored in our DB) and (b) password + IPFS encrypted backup. If the user loses all recovery material, data is unrecoverable. This is honest and is the same guarantee near-phantom-auth already makes for account recovery. Do NOT add a recovery escrow, Shamir split, or admin backdoor. The honest threat model is the whole point.
- **D-14:** **Rotation:** researcher to determine whether near-phantom-auth supports key rotation out of the box. Rotation is NOT a blocker for Phase 16 — a "re-import and re-encrypt" path is acceptable for the first release. Planner may defer rotation automation to a later phase if it adds significant complexity.
- **D-15:** **Key-zeroing:** DEKs held in process memory must be explicitly zeroed on logout, session expiry, and process exit. This is a hard requirement, not a nice-to-have. Use `ctypes` / `memoryview` / whatever the chosen crypto lib supports. Researcher to pick the exact mechanism.

### Background Jobs — Two Modes (D-16 — D-19)

- **D-16:** **Default mode: user-triggered pipelines only.** The account indexer, classifier, ACB recompute, gap reindex, verifier, and report generators only run while the user is actively logged in. The live session holds the unwrapped DEK in memory and dispatches pipeline jobs using that key. On logout or session expiry, the key is zeroed and pipelines for that user pause mid-run (must resume gracefully on next login). This is what every new user gets out of the box and what the privacy page can truthfully claim by default.
- **D-17:** **Opt-in mode: persistent sealed worker key.** A user can explicitly flip a settings toggle — labeled in the UI as "Let Axiom keep indexing my wallets in the background (less private, more convenient)" — which generates a sealed worker copy of the DEK bound to a server-side worker process. The worker can then run background indexing/ACB/report jobs without the user being logged in. The user can revoke the worker key at any time from settings; revocation zeros the worker key and pauses all background jobs for that user.
- **D-18:** **Session awareness applies to the per-user materialization pipeline, NOT the Rust account indexer.** The two must stay cleanly separated:
  - **Unchanged (public data plane):** The Rust account indexer ([indexers/account-indexer-rs/](indexers/account-indexer-rs/), systemd-managed) keeps running exactly as Phase 15 shipped it. It ingests public NEAR blocks into `account_transactions`, `account_dictionary`, `account_block_index_v2`, `block_heights`, `price_cache*`. These tables carry zero linkability — they're a shared public-blockchain cache keyed by public account IDs, not by `user_id`. Leave them cleartext. Do not touch the indexer's invocation model.
  - **Session- or worker-key-aware (per-user plane):** The per-user materialization pipeline — wallet sync → classifier → ACB → verifier → ledgers → reports — is what runs only when a DEK is available. On login, the session-unwrapped DEK decrypts the user's `wallets.account_id` list, the pipeline reads the public `account_transactions` cache for each address (fast, no decryption), runs classify/ACB/verify/report in memory, and writes the encrypted results into the user's `transactions`, `transaction_classifications`, `acb_snapshots`, `capital_gains_ledger`, `income_ledger`, `verification_results`, etc.
  - Users without a live session and without an opt-in worker key simply don't have their per-user data refreshed until next login. A "last synced at X" timestamp in the UI is enough; no "paused" banner needed.
  - The privacy win is two-fold: (a) the server can't enumerate which public addresses belong to which users because `wallets.account_id` is encrypted, and (b) the server can't read any user's derived/classified/tax-relevant data at rest. The public blockchain cache keeps cooking in the background uninterrupted.
  - Researcher/planner must locate where the FastAPI API currently triggers per-user pipelines (classifier → ACB → verifier → report-gen) and gate those entry points on DEK availability — not touch the Rust indexer.
- **D-19:** **Worker-key UX surface:** the settings page needs a new section "Background processing" with (a) clear explanation of the privacy tradeoff, (b) toggle, (c) status indicator ("Worker active", "Last run", "Revoke"), (d) audit trail entry on every toggle. Scope this as part of Phase 16 deliverables — not deferred.

### Migration Strategy (D-20 — D-23)

- **D-20:** **Re-import from source.** On Phase 16 deploy, wipe all user-data tables (`transactions`, `transaction_classifications`, `acb_snapshots`, `capital_gains_ledger`, `income_ledger`, `verification_results`, `account_verification_status`, `staking_events`, `lockup_events`, `epoch_snapshots`, `audit_log` for data-mutation entries, any derived reports). Users re-run indexing for their wallets after logging in post-upgrade. Clean-slate test of the encrypted path end-to-end. No in-place backfill. No dual-write. No cleartext legacy column ever touches encrypted code.
- **D-21:** **Wallets: wipe and re-enter manually.** `wallets.account_id` cannot be regenerated from source, so users (including VitalPoint) must re-enter their wallet list through the onboarding wizard after the Phase 16 upgrade. Onboarding wizard needs an "I'm returning from the pre-encryption release" path that pre-fills a welcome message and guides the user into re-entering wallets.
- **D-22:** **Auth tables are preserved** across the migration. `users` (Axiom bridge), `passkeys`, `sessions`, `magic_link_tokens`, `challenges`, `accountant_access`, and the near-phantom-auth tables (under the auth-service schema) all remain intact. Users do NOT lose their accounts or passkeys — they just lose indexed data and must re-import. This is important for UX: the user logs in with their existing passkey, sees an empty dashboard, and is guided to re-enter wallets.
- **D-23:** **The VitalPoint production data goes through the migration too** — no exception carved out for the dev/admin account. This guarantees the migration path is actually tested against real data and not just a dev-account happy path. Take a DB backup before the deploy; researcher must document the rollback procedure in the plan.

### Claude's Discretion

- **ML-KEM-768 library choice** — Researcher to evaluate `pyoqs` / `liboqs-python` (C bindings, mature, Docker-friendly), `pqcrypto`, `kyber-py`, or a Rust-wrapped option. Selection criteria: FIPS 203 conformance, maintenance cadence, cross-platform Docker build cost, perf on the Phase 15 workload. Planner picks.
- **Encryption boundary** — SQLAlchemy `TypeDecorator` per column vs ORM event hooks vs a small app-layer encryption service. Planner picks based on how invasive each is against [db/models/_all_models.py](db/models/_all_models.py). pgcrypto (DB-layer) is ruled out because it defeats "server is blind at rest" — the DB would hold the key.
- **AEAD construction** — Whether to use raw AES-256-GCM, AES-256-GCM-SIV (nonce-misuse resistant), or ChaCha20-Poly1305. Default to AES-256-GCM to match the marketing claim on [feature-grid.tsx:28](web/app/(marketing)/feature-grid.tsx#L28); researcher can flag if a better option emerges.
- **Nonce strategy** — 96-bit random nonces vs deterministic counter-based vs per-row domain-separated. Planner picks; must be safe against nonce reuse at write volume.
- **Key zeroization implementation** — `ctypes.memset`, `cryptography`'s `SecureBuffer`, or equivalent. Planner picks.
- **Audit log — admin visibility vs full encryption** — Researcher should decide: either encrypt audit_log with the user's DEK (admin can't read it — consistent with the privacy story) or keep per-row event type cleartext while encrypting the diff payload. Default to full encryption unless there's a specific compliance reason to expose something.
- **Session→worker handoff edge cases** — What happens if the user closes the tab mid-pipeline? Session refresh? Multiple tabs? Researcher to propose a model; planner to specify.
- **Per-user ML-KEM key generation performance cost at signup** — ML-KEM-768 keygen is fast but may need an async path. Planner picks.

### Folded Todos

None. No todos matched this phase in cross-reference.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing auth & key management
- [auth-service/src/server.ts](auth-service/src/server.ts) — Current near-phantom-auth wiring, `createAnonAuth` config. This is the integration point for all key-custody work.
- [auth-service/src/user-bridge.ts](auth-service/src/user-bridge.ts) — How near-phantom-auth users get mapped into the Axiom `users` table. Affects the `users.email` / `users.display_name` decision.
- [auth-service/src/magic-link.ts](auth-service/src/magic-link.ts) — Magic-link auth flow. Researcher must confirm whether email even lands in the Axiom DB or only transits through AWS SES.
- [auth-service/package.json](auth-service/package.json) — Pins `@vitalpoint/near-phantom-auth` ^0.5.2.
- [web/node_modules/@vitalpoint/near-phantom-auth/README.md](web/node_modules/@vitalpoint/near-phantom-auth/README.md) — Full feature reference for the near-phantom-auth package (anonymous passkey + NEAR MPC + IPFS/wallet recovery). READ IN FULL before planning. Key-custody, recovery, and session-sealing primitives all live here.
- [web/node_modules/@vitalpoint/near-phantom-auth/dist/](web/node_modules/@vitalpoint/near-phantom-auth/dist/) — Compiled source. Researcher must inspect `server/` and `client/` sub-exports to discover exactly which sealing/unsealing primitives are available for deriving an ML-KEM secret-key-sealing key from the passkey/recovery flow. This is the MOST important piece of research for the phase.

### Data model (what gets encrypted)
- [db/models/_all_models.py](db/models/_all_models.py) — Canonical source of every table and column. Researcher must enumerate every user-linkable column for the encrypted-columns whitelist.
- [db/schema.sql](db/schema.sql), [db/schema_evm.sql](db/schema_evm.sql), [db/schema_exchanges.sql](db/schema_exchanges.sql), [db/schema_users.sql](db/schema_users.sql) — Raw SQL schemas for sanity-check against the ORM models.
- [db/migrations/versions/](db/migrations/versions/) — Migration history. Phase 16 will add a new migration adding `wrapped_dek`, ML-KEM public key column on users, and replacing cleartext columns with ciphertext columns on every in-scope table. Planner to sequence.

### Phase 15 performance budget
- [.planning/phases/15-account-block-index-integer-encoding/15-CONTEXT.md](.planning/phases/15-account-block-index-integer-encoding/15-CONTEXT.md) — Phase 15 context, source of the sub-2-minute budget claim.
- [.planning/phases/15-account-block-index-integer-encoding/15-VERIFICATION.md](.planning/phases/15-account-block-index-integer-encoding/15-VERIFICATION.md) — Actual delivered perf numbers that Phase 16 must not regress.
- [indexers/account-indexer-rs/](indexers/account-indexer-rs/) — The Rust account indexer that D-18 requires refactoring into a session-aware dispatcher.
- [scripts/run_account_indexer.sh](scripts/run_account_indexer.sh) — Current systemd-managed indexer entrypoint; refactor surface for D-18.

### Marketing claims to deliver
- [web/app/(marketing)/feature-grid.tsx:28](web/app/(marketing)/feature-grid.tsx#L28) — "Post-Quantum Encrypted" feature card.
- [web/app/(marketing)/privacy/page.tsx:43](web/app/(marketing)/privacy/page.tsx#L43) — Encryption architecture section of privacy page. Text here and on feature-grid must still be literally true after Phase 16 ships.

### External specs (researcher: add full paths when you fetch these)
- NIST FIPS 203 (ML-KEM / Module-Lattice-based Key Encapsulation Mechanism) — the standard behind the "Post-Quantum" claim.
- NIST SP 800-38D (GCM mode) — for the AES-256-GCM data-key layer.
- RFC 9180 (HPKE) may inform the envelope design; not required reading but worth scanning.

### Prior phase context (for conventions and prior decisions)
- [.planning/PROJECT.md](.planning/PROJECT.md) — Core value: accurate tax reporting. Privacy is now a peer goal.
- [.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md) — No prior security requirements; PQE-01..08 to be derived during planning from this CONTEXT.
- [.planning/phases/07-web-ui/07-CONTEXT.md](.planning/phases/07-web-ui/07-CONTEXT.md) — auth system design baseline.
- [.planning/phases/12-user-onboarding/12-CONTEXT.md](.planning/phases/12-user-onboarding/12-CONTEXT.md) — the wizard Phase 16 will extend for post-migration re-entry.
- [.planning/phases/13-reliable-indexing/13-CONTEXT.md](.planning/phases/13-reliable-indexing/13-CONTEXT.md) — indexing architecture Phase 16 must not break.
- [.planning/codebase/ARCHITECTURE.md](.planning/codebase/ARCHITECTURE.md), [.planning/codebase/STACK.md](.planning/codebase/STACK.md), [.planning/codebase/INTEGRATIONS.md](.planning/codebase/INTEGRATIONS.md) — codebase maps.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- **`@vitalpoint/near-phantom-auth`** — Already installed and wired. Provides passkey auth, NEAR MPC accounts, IPFS+password recovery, wallet recovery. Phase 16's entire key custody story rides on this package.
- **`auth-service` microservice** — Express service on :3100 proxied via nginx. Already holds all auth state. Phase 16 adds key-sealing endpoints here, not in the FastAPI API, to keep crypto material on one side of the fence.
- **`users` bridge table** — [auth-service/src/user-bridge.ts](auth-service/src/user-bridge.ts) keeps auth-service identities in sync with Axiom's `users` row. Phase 16 extends this to provision the user's ML-KEM keypair at first sync.
- **Existing onboarding wizard** — Phase 12 delivered a wallet-entry flow that Phase 16 will reuse for post-migration re-entry (D-21). No new wizard needed; just a new entry path.

### Established patterns
- **SQLAlchemy ORM with typed mapped_columns** — [db/models/_all_models.py](db/models/_all_models.py). Per-column `TypeDecorator` would drop in cleanly here.
- **Alembic migrations, numbered sequentially** — [db/migrations/versions/](db/migrations/versions/). Current highest is 021. Phase 16's migration would be 022+.
- **Multi-service Docker Compose with PostgreSQL shared** — API (FastAPI), auth-service (Express), indexer (systemd), web (Next.js). Crypto libs must build cleanly in each container that touches user data — this rules out any library that needs a compiler toolchain at runtime.
- **FastAPI dependency injection for auth** — [api/dependencies.py](api/dependencies.py) resolves the current user per request. Phase 16 extends this to also resolve the unwrapped session DEK and pass it down.

### Integration points
- **Session→DEK lifecycle** — wherever a FastAPI request dependency resolves the user, Phase 16 also resolves the unwrapped DEK and exposes it to ORM decoders. This is the narrowest integration seam.
- **Account indexer (systemd, Rust)** — [indexers/account-indexer-rs/](indexers/account-indexer-rs/) — UNCHANGED. Keeps writing the public blockchain cache. Do not add session awareness here.
- **Per-user pipeline entry points (FastAPI)** — classifier handler, ACB handler, verifier handler, report generator, wallet-sync handler. These are the actual gating points for DEK availability. Researcher must enumerate them in [api/routers/](api/routers/) and wherever the job queue dispatches pipeline work.
- **Report generation (PackageBuilder)** — currently runs in-process; needs to hold the DEK only for the duration of the generate-and-download cycle.
- **Audit log writer** — [db/audit.py](db/audit.py) — wrap every write in a DEK-aware encoder.

### Creative options the architecture enables
- Because auth-service is a separate Node process, the ML-KEM sealing logic can live there and the Python API never sees raw secret-key material. The API only ever holds short-lived unwrapped DEKs passed from auth-service over a local IPC (Unix socket, nginx upstream, or a sealed envelope in the session cookie). Researcher to evaluate.

</code_context>

<specifics>
## Specific Ideas

- **"Total privacy and anonymity unless the user decides to let someone (like their accountant) see their records"** — user's own framing, direct quote. This is the north star for every ambiguous call.
- **Background processing setting must explicitly name the tradeoff** — the UI copy needs to say something like "Less private, more convenient" so users understand what they're opting into. Don't hide the tradeoff behind vague wording.
- **No parallel server-KEM-secret system.** User explicitly rejected that approach in favor of near-phantom-auth. If a researcher or planner feels tempted to "just add a server env var for the ML-KEM key," stop and re-read D-10.
- **The marketing copy on `feature-grid.tsx` and `privacy/page.tsx` is already live.** Phase 16 must deliver on those words as written, not rewrite the marketing page to match a weaker implementation.
- **VitalPoint's own 2025 tax data goes through the same migration as everyone else** (D-23). No carve-out.
- **Accountant access** (`accountant_access` table) is the only legitimate path for a second party to see a user's data. How accountants actually decrypt data granted to them is a Phase-16 design question the researcher must answer — probably via a grant-specific re-wrapped DEK.

</specifics>

<deferred>
## Deferred Ideas

- **Shamir N-of-M server-key escrow / admin recovery backdoor** — explicitly rejected. Do not revisit.
- **Blind indices for duplicate-wallet detection** (D-06) — if product needs "this address is already claimed by another user," that's a follow-up phase with its own threat model discussion.
- **Searchable encryption / deterministic encryption for filter predicates** — rejected in favor of decrypt-in-app (D-07). Revisit only if perf forces it and researcher has a concrete proposal.
- **Key rotation automation** (D-14) — acceptable to ship Phase 16 without automatic rotation; a manual re-import-and-re-encrypt path is fine for v1. Can become a future phase.
- **Client-side computation / browser-side decryption** — that's Phase 18 (was originally planned); Phase 16 is server-side-with-session-key. Phase 17 as originally written (passkey-derived keys) is effectively subsumed by D-11/D-12 of this phase, so Phase 17's scope may need to be revisited after Phase 16 ships.
- **HSM / AWS KMS integration** — rejected. Adds a cloud dependency and doesn't fit the "server is blind" model.
- **Audit log admin-only visibility** — deferred to Claude's discretion in decisions; default to full encryption.
- **pgcrypto database-side encryption** — rejected (defeats "server is blind at rest"; the DB would hold the key).

### Reviewed Todos (not folded)

None — no pending todos matched this phase.

</deferred>

---

*Phase: 16-post-quantum-encryption-at-rest*
*Context gathered: 2026-04-12*
