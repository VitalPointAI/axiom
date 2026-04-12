# Phase 16: Post-Quantum Encryption at Rest - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 16-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-12
**Phase:** 16-post-quantum-encryption-at-rest
**Areas discussed:** Encryption scope, Query compatibility, Key custody & recovery, Migration strategy

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Encryption scope | Which tables/columns get encrypted | ✓ |
| Query compatibility | Blind indices vs cleartext whitelist vs decrypt-then-filter | ✓ |
| Key custody & recovery | Where the ML-KEM-768 server secret lives and loss handling | ✓ |
| Migration strategy | How existing production data gets encrypted | ✓ |

**User's choice:** All four starred gray areas.

---

## Encryption Scope

### Q1: How should we scope encryption across user-sensitive tables?

| Option | Description | Selected |
|--------|-------------|----------|
| Core financial only | transactions, ACBSnapshot, ledgers, verification, staking, audit | |
| Everything user-scoped | Every table with user_id FK including wallets, rules, jobs | |
| Transactions table only | Narrowest: encrypt transactions; leave derived tables cleartext | |

**User's choice (free text):** "I want anything encrypted that could possibly link back to someone — we need to ensure total privacy and anonymity unless the user decides to let someone (like their accountant) see their records and aggregated transactions, synched wallets, etc."

**Notes:** User rephrased the decision rule in terms of **linkability**, not a specific table whitelist. Captured as D-01 in CONTEXT.md. This is stronger than any of the presented options — it demands that wallets, classification metadata, and anything else that links a row to a real person also gets encrypted.

### Q2: Row-level granularity?

| Option | Description | Selected |
|--------|-------------|----------|
| Sensitive columns only | Encrypt specific columns; keep user_id/timestamp/block_height cleartext | ✓ |
| Full-row JSON blob | Serialize whole row into one encrypted blob | |
| Everything except FK/PK | Encrypt every column except primary keys and user_id | |

**User's choice:** Sensitive columns only.

**Notes:** Preserves Phase 15 indexing, gap detection, per-user query routing. D-02 in CONTEXT.md.

### Q3 (follow-up): wallets.account_id

| Option | Description | Selected |
|--------|-------------|----------|
| Encrypt account_id | Encrypt with user DEK; no cross-user address lookup | ✓ |
| Keep cleartext | Leave addresses readable on the server | |
| Encrypt + blind index | HMAC-based blind index for duplicate-wallet detection | |

**User's choice:** Encrypt account_id.

**Notes:** D-06 in CONTEXT.md. Duplicate-wallet detection deferred.

### Q4 (follow-up): users table PII

| Option | Description | Selected |
|--------|-------------|----------|
| Hash email, encrypt name | Deterministic HMAC for email; encrypt display_name | ✓ |
| Keep cleartext | Standard practice; DB dump reveals users | |
| Encrypt everything | Breaks email-based login lookup | |

**User's choice:** Hash email, encrypt name.

**Notes:** D-05 in CONTEXT.md. Researcher must verify whether Axiom's `users` table even stores email/display_name given the near-phantom-auth codename model.

---

## Query Compatibility

### Q5: Query strategy once amounts/counterparty/tx_hash are encrypted?

| Option | Description | Selected |
|--------|-------------|----------|
| Decrypt in app, filter in memory | SQL filters on cleartext only; Python filters post-decrypt | ✓ |
| Blind indices for common filters | HMAC-based blind indices for tx_type, counterparty, amount buckets | |
| Hybrid: cleartext tx_type only | Keep coarse tx_type enum cleartext, encrypt rest | |

**User's choice:** Decrypt in app, filter in memory.

**Notes:** D-07 in CONTEXT.md. Even coarse enums stay encrypted (D-08) — aggregate leakage explicitly unacceptable.

### Q6: Perf budget vs Phase 15's 2-minute wallet lookup?

| Option | Description | Selected |
|--------|-------------|----------|
| Protect the 2-min budget | Hard requirement: under 2 minutes post-encryption | ✓ |
| Accept up to 2× slowdown | Allow ~4 minutes for simpler implementation | |
| Optimize later | Ship correctness first, benchmark after | |

**User's choice:** Protect the 2-min budget.

**Notes:** D-09 in CONTEXT.md. Researcher must benchmark; failing the budget blocks planning.

---

## Key Custody & Recovery

### Q7: Where does the ML-KEM-768 server secret live?

| Option | Description | Selected |
|--------|-------------|----------|
| Mounted secret file | Docker secret / read-only bind mount | |
| Environment variable | Base64 in .env / deployment env | |
| AWS KMS / cloud HSM | Delegate wrapping to a cloud service | |
| OS keyring / systemd credential | Linux keyring or LoadCredential | |

**User's choice (free text):** "use the near-phantom-auth integration to deal with key backup and recovery via NEAR MPC"

**Notes:** User rejected the entire premise of a server-held KEM secret. Pivoted to leveraging the existing `@vitalpoint/near-phantom-auth` package. Captured as D-10.

### Q8: Recovery if the server key is lost?

| Option | Description | Selected |
|--------|-------------|----------|
| Offline backup, manual restore | You keep encrypted backup; loss of both = data gone | |
| Shamir N-of-M split | Split across trustees | |
| No recovery (pure zero-knowledge) | If key gone, data gone | |

**User's choice (free text):** "use near-phantom-auth integration to deal with key recovery"

**Notes:** Same pivot as Q7. Recovery rides on near-phantom-auth's existing wallet-link and password+IPFS recovery channels. D-13 in CONTEXT.md.

### Q9: Per-user DEK management?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-user, wrapped once at signup | Envelope encryption; cache DEK in-memory per request | |
| Per-user, rotated on every request | Strong forward secrecy but destroys perf | |
| Single global DEK | One key for all users; trivial but weak | |

**User's choice (free text):** "however that makes sense in line with near-phantom-auth integration"

**Notes:** User deferred to the integration constraints. Captured as D-11/D-12 envelope encryption model (standard shape) with the explicit note that the researcher must read near-phantom-auth source to confirm feasibility.

### Q10 (follow-up): Trust model — server-blind at rest?

| Option | Description | Selected |
|--------|-------------|----------|
| User-bound, server blind | Each user has own ML-KEM keypair; secret sealed via near-phantom-auth; server blind at rest | ✓ |
| Session-scoped server unseal | User unseals secret at login; server gets it for session duration | |
| Transitional server custody | Phase 16 keeps server-held secret; Phase 17 migrates to per-user custody | |

**User's choice:** User-bound, server blind.

**Notes:** D-11 in CONTEXT.md. This effectively collapses Phase 17 (passkey-derived keys) into Phase 16. Phase 17's scope must be re-examined after Phase 16 ships.

### Q11 (follow-up): Background jobs without an active session?

| Option | Description | Selected |
|--------|-------------|----------|
| User-triggered only | Pipelines run only while user logged in; DEK in session memory | |
| Short-lived sealed worker token | Time-boxed worker token authorized at login | |
| Opt-in persistent worker key | User explicitly opts in to let server hold sealed worker copy | |

**User's choice (free text):** "so if we allow opt-in persistent worker key, then the default is user-triggered right?"

**Notes:** User asked a clarifying question rather than picking an option. I confirmed: yes, the default is user-triggered and opt-in is an explicit user setting. Led to Q12.

### Q12: Confirm the two-mode model?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, that's the model | Default = user-triggered; opt-in = persistent sealed worker. Ship both in Phase 16. | ✓ |
| Default only for now | Ship only user-triggered; opt-in becomes its own phase | |
| Let me rethink | Reconsider alternatives | |

**User's choice:** Yes, that's the model.

**Notes:** D-16 through D-19 in CONTEXT.md. Major implication: the Phase 15 account indexer must be refactored into a session-aware dispatcher (D-18).

---

## Migration Strategy

### Q13: Existing production data transition?

| Option | Description | Selected |
|--------|-------------|----------|
| Re-import from source | Wipe user-data tables; re-run indexing post-upgrade | ✓ |
| In-place backfill (downtime) | Maintenance window; batch-encrypt existing rows | |
| Dual-write cutover | Ship encryption alongside cleartext; backfill in background | |
| Fresh start for new users only | Old accounts stay cleartext until they re-import | |

**User's choice:** Re-import from source.

**Notes:** D-20 in CONTEXT.md. Auth tables (users, passkeys, sessions, near-phantom-auth state) preserved.

### Q14: Wallets table migration?

| Option | Description | Selected |
|--------|-------------|----------|
| Re-enter on first login | Legacy cleartext column until first post-upgrade login | |
| Admin-side one-shot | Sysadmin runs migration script for all users | |
| Wipe & re-enter manually | Users re-enter wallet list via onboarding wizard | ✓ |

**User's choice:** Wipe & re-enter manually.

**Notes:** D-21 in CONTEXT.md. Onboarding wizard gets a "returning from pre-encryption release" entry path.

---

## Wrap-Up

### Q15: Ready for context?

| Option | Description | Selected |
|--------|-------------|----------|
| Ready for context | Write CONTEXT.md now | ✓ |
| Discuss library choice | Talk through ML-KEM library options | |
| Discuss audit log | Decide audit log admin-visibility | |
| Discuss encryption boundary | Choose SQLAlchemy TypeDecorator vs pgcrypto vs hooks | |

**User's choice:** Ready for context.

**Notes:** Library, audit log, and encryption boundary were left to Claude's discretion / researcher investigation.

---

## Claude's Discretion

- ML-KEM-768 library choice (pyoqs vs alternatives) — researcher + planner
- Encryption boundary within SQLAlchemy stack — planner (pgcrypto explicitly rejected)
- AEAD construction (AES-256-GCM vs GCM-SIV vs ChaCha20-Poly1305) — default AES-256-GCM
- Nonce strategy — planner
- Key zeroization implementation — planner
- Audit log encryption granularity — default to full encryption
- Session→worker handoff edge cases — researcher
- ML-KEM keygen perf at signup — planner

## Deferred Ideas

- Shamir / escrow / admin backdoor (rejected)
- Blind indices for duplicate-wallet detection
- Searchable / deterministic encryption
- Key rotation automation (acceptable to defer)
- Client-side decryption (Phase 18)
- HSM / AWS KMS (rejected)
- Audit log admin-only visibility (default to full encryption)
- pgcrypto DB-side encryption (rejected)
- Phase 17 scope revision (passkey-derived keys effectively collapsed into Phase 16)
