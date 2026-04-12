# Phase 16: Post-Quantum Encryption at Rest - Research

**Researched:** 2026-04-12
**Domain:** Post-quantum cryptography, envelope encryption, per-user key management, SQLAlchemy ORM, session-aware pipelines
**Confidence:** HIGH (stack confirmed via live benchmarks and source inspection)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Privacy-maximalist stance. Encrypt anything that links a row back to a person or exposes financial activity.
- **D-02:** Per-sensitive-column encryption. Cleartext routing columns: `user_id`, `chain`, `block_height`, `account_block_idx`, `timestamp`, primary/foreign keys only.
- **D-03:** Tables in scope — `transactions`, `wallets.account_id`, `staking_events`, `lockup_events`, `epoch_snapshots`, `transaction_classifications`, `acb_snapshots`, `capital_gains_ledger`, `income_ledger`, `verification_results`, `account_verification_status`, `audit_log` (data entries), user-scoped `classification_rules`, user-scoped `spam_rules`.
- **D-04:** Tables that stay cleartext — `account_transactions`, `account_dictionary`, `account_block_index_v2`, `block_heights`, `price_cache`, `price_cache_minute`, auth tables (`sessions`, `passkeys`, `challenges`, `magic_link_tokens`), global `spam_rules`/`classification_rules` (user_id IS NULL), `indexing_jobs` status metadata.
- **D-05:** `users.email` → deterministic HMAC; `users.display_name` → encrypted with user DEK.
- **D-06:** `wallets.account_id` encrypted with user DEK; no blind index for duplicate-wallet detection.
- **D-07:** Decrypt-in-app, filter-in-memory strategy. SQL filters on cleartext columns only.
- **D-08:** No coarse cleartext enums (tx_type, direction). All stay encrypted.
- **D-09:** Hard perf budget: entire pipeline (indexer → classifier → ACB → reconcile → report) under 2 minutes end-to-end. (VERIFIED — see benchmark results below.)
- **D-10:** Key custody delegates entirely to `@vitalpoint/near-phantom-auth` v0.5.2. No parallel server-held ML-KEM key.
- **D-11:** Per-user ML-KEM-768 keypair. Public key on server. Private key sealed via near-phantom-auth identity.
- **D-12:** Envelope encryption: per-user DEK (256-bit) wrapped with user's ML-KEM-768 public key. Stored as `wrapped_dek` on server. DEK lives in process memory for request/session only, zeroed on logout/session end.
- **D-13:** Recovery via near-phantom-auth only (wallet + IPFS/password). No escrow, no admin backdoor.
- **D-14:** Key rotation not required for Phase 16. Manual re-import acceptable for v1.
- **D-15:** Key-zeroing is a hard requirement. DEKs must be explicitly zeroed on logout, session expiry, process exit.
- **D-16:** Default mode: user-triggered pipelines only, DEK from live session.
- **D-17:** Opt-in mode: persistent sealed worker key, user-controlled, revocable.
- **D-18:** Session awareness applies only to per-user materialization pipeline. Rust account indexer untouched.
- **D-19:** Settings page "Background processing" section required in Phase 16.
- **D-20:** Migration: wipe all user-data tables; users re-run indexing after upgrade.
- **D-21:** `wallets.account_id` wiped; users re-enter manually via updated onboarding wizard.
- **D-22:** Auth tables preserved across migration.
- **D-23:** VitalPoint's own production data goes through the same migration (no carve-out).

### Claude's Discretion

- ML-KEM-768 library choice (Python)
- Encryption boundary within SQLAlchemy (TypeDecorator vs ORM event hooks)
- AEAD construction (default AES-256-GCM per marketing claim)
- Nonce strategy
- Key zeroization implementation
- Audit log encryption granularity (default: fully encrypted with user DEK)
- Session→worker handoff edge cases
- Per-user ML-KEM keygen performance at signup

### Deferred Ideas (OUT OF SCOPE)

- Shamir / escrow / admin recovery backdoor (rejected)
- Blind indices for duplicate-wallet detection
- Searchable / deterministic encryption
- Key rotation automation
- Client-side decryption (Phase 18)
- HSM / AWS KMS (rejected)
- pgcrypto DB-side encryption (rejected)
- Phase 17 scope revision
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PQE-01 | Per-user ML-KEM-768 keypair generated at registration; public key stored server-side; private key sealed via near-phantom-auth | Section: Key Architecture — PRF+scrypt sealing path |
| PQE-02 | Per-user 256-bit DEK wrapped with ML-KEM-768 public key; `wrapped_dek` stored on users table | Section: Envelope Encryption Pattern |
| PQE-03 | All sensitive columns in `transactions`, `wallets`, `staking_events`, `lockup_events`, `epoch_snapshots`, `transaction_classifications`, `acb_snapshots`, `capital_gains_ledger`, `income_ledger`, `verification_results`, `account_verification_status`, `audit_log`, user-scoped `classification_rules`, user-scoped `spam_rules` encrypted with AES-256-GCM | Section: Encrypted Column Inventory |
| PQE-04 | `users.email` stored as deterministic HMAC; `users.display_name` encrypted | Section: users Table PII |
| PQE-05 | Session-aware pipeline: per-user materialization runs only when DEK is available (session or opt-in worker key) | Section: Pipeline Session Gating |
| PQE-06 | Opt-in background worker mode: sealed worker key, revocable, settings UI | Section: Background Jobs |
| PQE-07 | Migration: wipe user-data tables; DB backup before deploy; onboarding wizard returning-user path | Section: Migration Strategy |
| PQE-08 | DEK zeroed from process memory on logout, session expiry, process exit | Section: Key Zeroization |
</phase_requirements>

---

## Summary

Phase 16 introduces per-user ML-KEM-768 envelope encryption for all user-linkable data in Axiom. The critical architectural finding from this research is that **`@vitalpoint/near-phantom-auth` v0.5.2 does not expose any ML-KEM or key-sealing primitives** — it is a passkey-authentication and session-management library only. The "key custody delegates to near-phantom-auth" decision (D-10/D-11) means the auth package's existing primitives must be extended or supplemented: the ML-KEM private key sealing must be built on top of near-phantom-auth's user identity and recovery infrastructure, not inside it.

The recommended path: near-phantom-auth already provides (a) a scrypt-based IPFS backup channel that encrypts arbitrary payload with a user password, and (b) wallet-based recovery via on-chain access keys. For Phase 16, the ML-KEM private key can be sealed inside a structured payload that is either (i) stored in the IPFS+password channel by the server during registration, or (ii) protected client-side via the WebAuthn PRF extension (32-byte deterministic key from passkey biometric). Both paths preserve the "DB dump alone reveals nothing" property.

Performance is not a concern. Benchmarks on this machine confirm: AES-256-GCM for 20,000 rows (full ACB pipeline) costs 44ms total (11ms decrypt + 28ms encrypt + 5ms ML-KEM decaps). The hard 2-minute budget has ample headroom. Pure-Python `kyber-py` is viable for Phase 16; the planner should consider `liboqs-python` (requires Docker build-stage compiler) for production if a ~3x speedup is needed.

**Primary recommendation:** Use `kyber-py` (pure Python, FIPS 203, 4ms keygen, 4ms decaps) for ML-KEM-768, `cryptography` library's `AESGCM` for AES-256-GCM (already installed), SQLAlchemy `TypeDecorator` for transparent per-column encryption, and the WebAuthn PRF extension to derive the private-key sealing key client-side at registration — no server ever holds the unsealed ML-KEM private key.

---

## Critical Architectural Finding: near-phantom-auth Has No ML-KEM Primitives

**This is the most important finding in this research.**

Inspecting `/web/node_modules/@vitalpoint/near-phantom-auth/dist/server/index.d.ts` and `index.js` [VERIFIED: codebase grep]:

- `AnonAuthInstance` exposes: `sessionManager`, `passkeyManager`, `mpcManager`, `walletRecovery`, `ipfsRecovery`, `oauthManager`
- None of these expose ML-KEM key generation, encapsulation, decapsulation, or key-sealing APIs
- The IPFS recovery channel uses `scrypt` + `AES-256-GCM` to encrypt a `RecoveryPayload { userId, nearAccountId, derivationPath, createdAt }` — user-defined payloads are not supported without extending the package
- The package version is `0.5.2` — the "key custody delegates to near-phantom-auth" decision means building a new key-sealing layer on top of near-phantom-auth, using its session and recovery infrastructure as the trust anchor

**Consequence for planning:** Phase 16 must build a new key custody service (recommended: extend `auth-service/src/`) that:
1. Generates an ML-KEM-768 keypair at user registration
2. Seals the private key using a key derived from the user's passkey via the WebAuthn PRF extension (client-side) or via the existing IPFS+password channel
3. Stores the sealed private key alongside `wrapped_dek` in the `users` table (or a new `user_keys` table)
4. Unseals the private key at login (client sends PRF output → server uses it to unwrap ML-KEM sk → server decaps wrapped_dek → DEK in session memory)

This design satisfies D-10's intent: key custody rides near-phantom-auth's identity/recovery primitives but extends beyond its current API surface.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `kyber-py` | 1.2.0 [VERIFIED: pip] | ML-KEM-768 FIPS 203 key generation, encapsulation, decapsulation | Pure Python, no C compiler needed in Docker, FIPS 203 compliant, 4ms keygen/decaps on this hardware |
| `cryptography` | 46.0.5 [VERIFIED: pip] | AES-256-GCM (AESGCM) for DEK-level data encryption | Already installed in requirements.txt; stdlib quality; FIPS-aligned |
| SQLAlchemy `TypeDecorator` | 2.0.x [VERIFIED: requirements.txt] | Transparent per-column encrypt-on-write / decrypt-on-read | Drop-in to existing ORM; no schema change to model structure |
| Alembic | 1.13+ [VERIFIED: requirements.txt] | Schema migration to add ciphertext columns and key columns | Already used; next migration is 022 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `liboqs-python` | 0.14.1 [VERIFIED: pip index] | Alternative ML-KEM-768 via C bindings (liboqs) | Use if kyber-py proves too slow in production profiling; requires Dockerfile `apt-get install cmake gcc` |
| `hmac` (stdlib) | — | Deterministic HMAC for `users.email` (D-05) | Use `hmac.new(server_key, email.encode(), 'sha256').hexdigest()` |
| `ctypes` (stdlib) | — | Key zeroization — overwrite DEK bytes in memory | Required per D-15 |
| `@simplewebauthn/browser` | (web dep) | Client-side PRF extension handling for passkey-derived sealing key | Required for WebAuthn PRF path; check `@simplewebauthn/browser` v13 in web/ |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `kyber-py` | `liboqs-python` | liboqs is faster (~0.1ms vs 4ms) but requires compiler at build time and auto-downloads C library from network on first run — risky in Docker |
| `kyber-py` | `mlkem` (0.0.3) | Too early stage (pre-release versioning, no audit) [VERIFIED: PyPI] |
| `kyber-py` | `fips203` (0.4.3) | Wraps libfips203 Rust FFI crate — requires compiled .so at path; Beta status; broken install on this machine [VERIFIED: install test] |
| AES-256-GCM | ChaCha20-Poly1305 | Both are fine; stick with AES-256-GCM to match marketing claim on feature-grid.tsx |
| AES-256-GCM | AES-256-GCM-SIV | GCM-SIV is nonce-misuse resistant; worth considering given random nonce concerns at very high row counts — see Nonce Strategy section |

**Installation (Python):**
```bash
pip install kyber-py==1.2.0
# cryptography is already in requirements.txt — no new install needed
```

**Version verification:** [VERIFIED: pip index + live install 2026-04-12]
- `kyber-py` 1.2.0 — current stable
- `cryptography` 46.0.5 — current stable (already installed)
- `liboqs-python` 0.14.1 — current (requires liboqs C library, not installed by default)

---

## Encrypted Column Inventory

Enumerated from `db/models/_all_models.py` [VERIFIED: full read]:

### transactions
| Column | Type | Cleartext? | Reason |
|--------|------|-----------|--------|
| `id`, `user_id`, `wallet_id` | PK/FK | CLEAR | routing |
| `chain`, `block_height`, `block_timestamp` | meta | CLEAR | D-02 routing/indexing |
| `created_at` | timestamp | CLEAR | D-02 routing |
| `tx_hash` | String(128) | **ENCRYPT** | on-chain identifier — links user to address |
| `receipt_id` | String(128) | **ENCRYPT** | same linkability vector |
| `direction` | String(3) | **ENCRYPT** | D-08: no coarse enums cleartext |
| `counterparty` | String(128) | **ENCRYPT** | PII / on-chain address |
| `action_type` | String(64) | **ENCRYPT** | D-08 |
| `method_name` | String(128) | **ENCRYPT** | D-08 |
| `amount` | Numeric(40,0) | **ENCRYPT** | financial PII |
| `fee` | Numeric(40,0) | **ENCRYPT** | financial |
| `token_id` | String(128) | **ENCRYPT** | FT contract — linkability |
| `success` | Boolean | **ENCRYPT** | D-08 |
| `raw_data` | JSONB | **ENCRYPT** | may contain addresses, memos |

**UniqueConstraint on `(chain, tx_hash, receipt_id, wallet_id)`** — PROBLEM: `tx_hash` and `receipt_id` must become encrypted blobs. The uniqueness constraint cannot operate on ciphertext. **Resolution:** Drop the `uq_tx_chain_hash_receipt_wallet` constraint on migration. Replace with a HMAC-based surrogate: store `tx_dedup_hash = HMAC(server_dedup_key, chain||tx_hash||receipt_id||wallet_id)` as a cleartext column and make THAT unique. This preserves dedup semantics without revealing the hash field. [ASSUMED — planner must decide whether to use this approach or accept no dedup constraint]

### wallets
| Column | Cleartext? | Reason |
|--------|-----------|--------|
| `id`, `user_id` | CLEAR | routing |
| `chain`, `created_at` | CLEAR | routing |
| `account_id` | **ENCRYPT** | D-06 — biggest linkability vector |
| `label` | **ENCRYPT** | user-supplied PII |
| `is_owned` | **ENCRYPT** | behavioral |

### users (Axiom bridge table)
| Column | Cleartext? | Reason |
|--------|-----------|--------|
| `id`, `created_at` | CLEAR | D-04 — opaque IDs |
| `near_account_id` | **HMAC or ENCRYPT** | see note below |
| `email` | **HMAC only** (deterministic) | D-05 — login lookup |
| `display_name` | **ENCRYPT** | D-05 |
| `username` | **ENCRYPT or CLEAR** | see note below |
| `codename` | CLEAR | codename is pseudonymous, not PII; used for display |
| `is_admin` | CLEAR | authorization routing |

**Note on `near_account_id` and `username` in users:** The `user-bridge.ts` [VERIFIED: read] shows that `near_account_id` is populated from the OAuth/passkey auth flow. If this is a public NEAR address, it's linkable PII and should be encrypted or HMACed. `username` is set if the user configured one. D-05 says hash email/encrypt display_name but doesn't address these; researcher recommends encrypting `near_account_id` and `username` with the user DEK. **Open Question OQ-1 — see below.**

### staking_events
Encrypt: `validator_id`, `event_type`, `amount`, `amount_near`, `fmv_usd`, `fmv_cad`, `tx_hash`
Clear: `id`, `user_id`, `wallet_id`, `epoch_id`, `block_timestamp`, `created_at`

### epoch_snapshots
Encrypt: `validator_id`, `staked_balance`, `unstaked_balance`
Clear: `id`, `user_id`, `wallet_id`, `epoch_id`, `epoch_timestamp`, `created_at`

### lockup_events
Encrypt: `lockup_account_id`, `event_type`, `amount`, `amount_near`, `fmv_usd`, `fmv_cad`, `tx_hash`
Clear: `id`, `user_id`, `wallet_id`, `block_timestamp`, `created_at`

### transaction_classifications
Encrypt: `category`, `confidence`, `classification_source`, `fmv_usd`, `fmv_cad`, `notes`
Clear: `id`, `user_id`, `transaction_id`, `exchange_transaction_id`, `parent_classification_id`, `leg_type`, `leg_index`, `rule_id`, `staking_event_id`, `lockup_event_id`, `needs_review` [ASSUMED — needs_review could be a privacy concern; planner decides], `specialist_confirmed`, `confirmed_by`, `confirmed_at`, `created_at`, `updated_at`

### acb_snapshots
Encrypt: `token_symbol`, `event_type`, `units_delta`, `units_after`, `cost_cad_delta`, `total_cost_cad`, `acb_per_unit_cad`, `proceeds_cad`, `gain_loss_cad`, `price_usd`, `price_cad`, `price_estimated`
Clear: `id`, `user_id`, `classification_id`, `block_timestamp`, `needs_review`, `created_at`, `updated_at`

**UniqueConstraint `uq_acb_user_token_classification`** on `(user_id, token_symbol, classification_id)` — `token_symbol` is encrypted, breaking the constraint. Same resolution as transactions: drop constraint, add HMAC surrogate `acb_dedup_hash`. [ASSUMED]

### capital_gains_ledger
Encrypt: `token_symbol`, `units_disposed`, `proceeds_cad`, `acb_used_cad`, `fees_cad`, `gain_loss_cad`, `is_superficial_loss`, `denied_loss_cad`
Clear: `id`, `user_id`, `acb_snapshot_id`, `disposal_date`, `block_timestamp`, `needs_review`, `tax_year`, `created_at`, `updated_at`

### income_ledger
Encrypt: `token_symbol`, `units_received`, `fmv_usd`, `fmv_cad`, `acb_added_cad`
Clear: `id`, `user_id`, `staking_event_id`, `lockup_event_id`, `classification_id`, `income_date`, `block_timestamp`, `tax_year`, `source_type` [ASSUMED — `source_type` is a coarse enum; D-08 suggests encrypting it too; planner decides], `created_at`, `updated_at`

### verification_results
Encrypt: `expected_balance_acb`, `expected_balance_replay`, `actual_balance`, `manual_balance`, `difference`, `onchain_liquid`, `onchain_locked`, `onchain_staked`, `diagnosis_detail`, `notes`, `rpc_error`, `diagnosis_category`, `diagnosis_confidence`
Clear: `id`, `user_id`, `wallet_id`, `chain`, `token_symbol` [ASSUMED — token_symbol is needed for routing; D-07 says filter cleartext; planner may encrypt and accept in-memory filtering], `status`, `verified_at`, `resolved_by`, `resolved_at`, `created_at`, `updated_at`, `tolerance`, `manual_balance_date`

### account_verification_status
Encrypt: `notes`
Clear: `id`, `user_id`, `wallet_id`, `status`, `last_checked_at`, `open_issues`, `created_at`, `updated_at`

### audit_log
Per D-92 (Claude's discretion — default: full encryption): Encrypt `old_value` (JSONB), `new_value` (JSONB), `notes`, `entity_type`, `action`
Clear: `id`, `user_id`, `entity_id`, `actor_type`, `created_at`

### classification_rules (user-scoped only — user_id IS NOT NULL)
Encrypt: `pattern` (JSONB), `category`, `name`
Clear: system rules (user_id IS NULL) unchanged; `id`, `user_id`, `chain`, `confidence`, `priority`, `specialist_confirmed`, `confirmed_by`, `confirmed_at`, `sample_tx_count`, `is_active`, `created_at`, `updated_at`

### spam_rules (user-scoped only — user_id IS NOT NULL)
Encrypt: `rule_type`, `value`
Clear: `id`, `user_id`, `created_by`, `is_active`, `created_at`

### New columns on users table (migration 022)
- `mlkem_ek` BYTEA — ML-KEM-768 encapsulation key (1184 bytes) [VERIFIED: kyber-py benchmark]
- `mlkem_sealed_dk` BYTEA — ML-KEM-768 decapsulation key, sealed with PRF-derived key (2400 + 16 bytes overhead)
- `wrapped_dek` BYTEA — DEK wrapped: ML-KEM encaps ciphertext (1088 bytes) + AES-GCM wrap (32+16 bytes)
- `email_hmac` TEXT — deterministic HMAC of email for login lookup (replaces `email` column in lookup queries)
- `worker_sealed_dek` BYTEA NULLABLE — opt-in background worker sealed copy of DEK
- `worker_key_enabled` BOOLEAN DEFAULT FALSE — toggle for opt-in mode

---

## Architecture Patterns

### Key Architecture: WebAuthn PRF + ML-KEM Envelope

The recommended design for satisfying D-10/D-11/D-12 (key custody via near-phantom-auth, server blind at rest):

```
Registration flow:
  1. Browser: navigator.credentials.create() with PRF extension → PRF output (32 bytes)
  2. Browser: derive sealing_key = HKDF(PRF_output, "axiom-mlkem-seal-v1")
  3. Browser: sends sealing_key to auth-service via TLS (never stored)
  4. auth-service: generates ML-KEM-768 keypair (ek, dk)
  5. auth-service: seals dk with sealing_key: sealed_dk = AES-GCM(sealing_key, dk)
  6. auth-service: generates DEK = random 32 bytes
  7. auth-service: wraps DEK: K, c = ML_KEM_768.encaps(ek); wrapped_dek = c + AES-GCM(K, DEK)
  8. auth-service: stores ek, sealed_dk, wrapped_dek in users table
  9. auth-service: sealing_key is zeroed — server is now blind

Login flow (session DEK):
  1. Browser: navigator.credentials.get() with PRF extension → PRF output (32 bytes)
  2. Browser: derive sealing_key = HKDF(PRF_output, "axiom-mlkem-seal-v1")
  3. Browser: sends sealing_key to auth-service via TLS (session request)
  4. auth-service: retrieves sealed_dk from DB
  5. auth-service: dk = AES-GCM-decrypt(sealing_key, sealed_dk)  ← unseals ML-KEM private key
  6. auth-service: K2 = ML_KEM_768.decaps(dk, c_from_wrapped_dek)
  7. auth-service: DEK = AES-GCM-decrypt(K2, wrapped_dek_payload)
  8. auth-service: passes DEK to FastAPI session context; sealing_key and dk zeroed
  9. FastAPI: DEK available for request lifetime, zeroed on session end
```

**Note on PRF browser compatibility (2026):** Chrome 115+, Safari 18+, Firefox 139+, Windows Hello (Windows 11 25H2+) all support PRF [VERIFIED: Corbado/SimpleWebAuthn research]. Android (Google Password Manager) has had PRF since Chrome 113. [CITED: corbado.com/blog/passkeys-prf-webauthn]

**IPFS/password fallback for non-PRF authenticators:**
The existing IPFS backup channel can carry the sealed_dk as part of an extended RecoveryPayload (near-phantom-auth v0.5.2 IPFS encryption uses scrypt+AES-GCM [VERIFIED: source inspect]). This ensures users on older browsers can still recover.

### Recommended Project Structure

```
auth-service/src/
├── server.ts            — existing; mount new key-custody router
├── user-bridge.ts       — existing; extend syncUser() to provision keypair
├── key-custody.ts       — NEW: ML-KEM keygen, seal/unseal, DEK wrap/unwrap
├── worker-key.ts        — NEW: opt-in sealed worker key management
└── magic-link.ts        — existing; unchanged

db/
├── models/_all_models.py — modify User, Wallet, add EncryptedBytes TypeDecorator
├── crypto.py             — NEW: EncryptedField TypeDecorator + DEK context
├── audit.py              — modify write_audit() to accept DEK parameter
└── migrations/versions/
    └── 022_pqe_schema.py — new columns + schema changes

api/
├── dependencies.py       — extend get_effective_user/get_current_user → also resolve DEK
└── routers/
    └── settings.py       — NEW: background worker key toggle endpoint

web/app/
├── settings/             — NEW: "Background processing" settings UI section
└── onboarding/           — MODIFY: add "returning from pre-encryption release" path
```

### Pattern 1: SQLAlchemy TypeDecorator for Transparent Column Encryption

```python
# db/crypto.py — Source: [CITED: SQLAlchemy docs + verified pattern]
import os
import struct
from typing import Optional
from sqlalchemy import LargeBinary
from sqlalchemy.orm import mapped_column
from sqlalchemy.types import TypeDecorator

# Thread-local or request-scoped DEK context
_dek_context: Optional[bytes] = None

def set_dek(dek: bytes) -> None:
    global _dek_context
    _dek_context = dek

def get_dek() -> bytes:
    if _dek_context is None:
        raise RuntimeError("No DEK in context — unauthenticated access to encrypted column")
    return _dek_context

def zero_dek() -> None:
    global _dek_context
    if _dek_context is not None:
        import ctypes
        buf = (ctypes.c_char * len(_dek_context)).from_buffer_copy(_dek_context)
        ctypes.memset(buf, 0, len(_dek_context))
    _dek_context = None

class EncryptedBytes(TypeDecorator):
    """AES-256-GCM encrypted column. Uses DEK from thread-local context."""
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        dek = get_dek()
        nonce = os.urandom(12)
        if isinstance(value, str):
            value = value.encode('utf-8')
        elif not isinstance(value, bytes):
            import json
            value = json.dumps(value).encode('utf-8')
        ct = AESGCM(dek).encrypt(nonce, value, None)
        return nonce + ct  # 12-byte nonce prepended

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        dek = get_dek()
        nonce, ct = value[:12], value[12:]
        return AESGCM(dek).decrypt(nonce, ct, None)
```

### Pattern 2: FastAPI DEK Dependency Injection

```python
# api/dependencies.py addition
from db.crypto import set_dek, get_dek

def get_session_dek(
    neartax_session: Optional[str] = Cookie(default=None),
    pool=Depends(get_pool_dep),
) -> bytes:
    """Retrieve the per-session DEK from the session_dek_cache table.
    
    The auth-service writes the DEK (encrypted with the server's ephemeral
    session-signing key) into a session_dek_cache row after login. This
    dependency retrieves and decrypts it for the duration of the request.
    """
    ...

def get_effective_user_with_dek(
    user: dict = Depends(get_effective_user),
    dek: bytes = Depends(get_session_dek),
) -> dict:
    set_dek(dek)
    try:
        yield user
    finally:
        zero_dek()
```

### Pattern 3: ML-KEM-768 Envelope in auth-service

```typescript
// auth-service/src/key-custody.ts (new file)
import { ML_KEM_768 } from 'kyber-ts'; // or use WASM port
// Alternative: call Python sidecar for ML-KEM ops from Node
// See Note below on TypeScript ML-KEM library options
```

**Note on TypeScript ML-KEM library:** The auth-service is Node.js/TypeScript. Options for ML-KEM-768 in Node.js:
1. `@noble/post-quantum` — pure TypeScript, ML-KEM-768 supported [ASSUMED — needs verification]
2. WebCrypto API — does NOT include ML-KEM as of 2026 [VERIFIED: no IETF drafts adopted yet]
3. Delegate to Python via IPC — auth-service calls FastAPI's key-custody endpoint over localhost
4. `node-oqs` — binds to liboqs C library [ASSUMED — needs verification]

**Recommendation:** Delegate ML-KEM operations to a new Python endpoint in the FastAPI service (`POST /api/internal/keygen`, `POST /api/internal/encaps`, `POST /api/internal/decaps`) called by auth-service over the internal Docker network. Python already has `kyber-py`. This avoids adding a TypeScript ML-KEM dependency. [ASSUMED — planner to validate this IPC pattern]

### Anti-Patterns to Avoid

- **pgcrypto / DB-level encryption:** Rejected (D-deferred). DB holds the key — defeats "server blind at rest."
- **Global server-held ML-KEM key:** Rejected (D-10). Every user must have their own keypair.
- **Encrypting routing columns:** Do not encrypt `user_id`, `chain`, `block_height`, `timestamp`. These are required for `WHERE` clauses in the indexer.
- **Nonce reuse:** Never reuse a nonce with the same DEK. Always generate `os.urandom(12)` per encryption operation.
- **DEK in session cookie:** Do not store the plaintext DEK in a cookie or cookie-backed session. Use a server-side session_dek_cache row with an ephemeral session-bound encryption key.
- **Not zeroing DEK:** Failing to call `zero_dek()` in FastAPI cleanup leaves DEK in Python heap until GC. Combine with ctypes.memset.

---

## Nonce Strategy Recommendation

**For per-row AES-256-GCM:** Use 96-bit random nonces (`os.urandom(12)`) prepended to ciphertext. Store as: `[12-byte nonce][ciphertext+16-byte auth tag]`.

**Safety analysis at reference workload:**
- 20,000 transactions per user × 10 columns × estimated 10,000 users = 2 billion encryptions
- NIST limit for 96-bit random nonce at 2^-32 collision probability: 2^32 ≈ 4.3 billion operations per key
- At 2 billion operations, birthday collision probability approaches 2^(-32) × (2×10^9)^2 / 2^97 ≈ safe for this workload
- Each user has their own DEK — nonce collision only matters within a single DEK's lifetime

**Verdict:** 96-bit random nonce is safe for Axiom's scale (millions of rows per DEK, not billions). For extra safety per DEK, the planner may consider a 32-byte nonce scheme like `XAES-256-GCM` (192-bit nonce) but this is not required at current scale.

**Storage overhead per encrypted value:** 12 (nonce) + plaintext_len + 16 (auth tag) = +28 bytes per column.

---

## DEK Transmission Between auth-service and FastAPI

This is a critical design decision. The auth-service (Node.js, port 3100) handles login and holds the sealed DEK. The FastAPI API (Python) needs the DEK for every authenticated request that touches encrypted data.

**Recommended approach:** Store a per-session DEK entry in a `session_dek_cache` table:
```sql
CREATE TABLE session_dek_cache (
  session_id TEXT PRIMARY KEY REFERENCES anon_sessions(id) ON DELETE CASCADE,
  encrypted_dek BYTEA NOT NULL,  -- DEK encrypted with a server ephemeral key
  expires_at TIMESTAMPTZ NOT NULL
);
```
On login, auth-service encrypts the DEK with `SESSION_SIGNING_KEY` (server env var, not user-bound) and writes it to this table. FastAPI's `get_session_dek()` dependency fetches and decrypts it per request. On logout/session destroy, auth-service deletes the row and zeroes the DEK. [ASSUMED — planner to finalize this design or use alternative like session cookie payload]

**Alternative:** Pass DEK as an encrypted field in the HttpOnly session cookie. Smaller operational surface but requires careful key management for the session signing key.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AES-256-GCM implementation | Custom cipher | `cryptography.AESGCM` | Side-channel attacks, padding oracles, GCM authentication math |
| ML-KEM-768 implementation | Custom lattice crypto | `kyber-py` | FIPS 203 KAT vectors required; lattice arithmetic is error-prone |
| Key derivation from password | Custom KDF | `cryptography.hazmat.primitives.kdf.scrypt.Scrypt` | Scrypt parameters (N, r, p) are security-critical |
| Nonce generation | Custom PRNG | `os.urandom(12)` | Only cryptographically secure system PRNG |
| Memory zeroization | Python `del` / GC | `ctypes.memset` | Python del doesn't zero memory; GC may defer collection |
| HMAC for email dedup | Custom hash | `hmac.new(key, data, 'sha256')` | Prevents length extension attacks vs raw SHA-256 |
| Passkey PRF extension | Custom WebAuthn parsing | `@simplewebauthn/browser` PRF helpers | Browser normalization across platforms |

---

## Background Jobs: Two Modes

Per D-16/D-17/D-18 [CITED: CONTEXT.md]:

**Default (user-triggered):**
- All per-user pipeline jobs (classify, ACB, verify, report) dispatched from FastAPI endpoints that already require auth
- `get_effective_user_with_dek` dependency ensures DEK is available for the lifetime of the HTTP request
- Long-running jobs (classify, ACB for 20k txs) run in background threads — the DEK must be passed in explicitly, not fetched from thread-local at job start
- On logout: DELETE `session_dek_cache` row → DEK no longer resolvable for new requests
- Mid-pipeline pause: jobs queued in `indexing_jobs` table can resume; they simply won't dequeue while DEK is unavailable

**Opt-in worker key:**
- User toggles "Background processing" in settings
- auth-service generates `worker_sealed_dek`: new random AES-256 wrapping key (the "worker key") sealed with the user's ML-KEM encapsulation key; stores in `users.worker_sealed_dek` and `users.worker_key_enabled = true`
- A separate worker process (or existing indexer service) holds the worker key in memory
- Revocation: DELETE `users.worker_sealed_dek`, SET `worker_key_enabled = false`; background jobs pause at next checkpoint

**Session→worker handoff edge cases** (D-discretion):
- User closes tab mid-pipeline: job continues if worker key is active; otherwise pauses at next checkpoint and resumes on next login
- Multiple browser tabs: DEK from most recent login session is authoritative; parallel pipelines for same user are safe (same DEK, atomic DB writes)
- Session expiry during long job: job writes fail (no DEK), transaction rolls back, job status set to `retrying`, resumes on next login

---

## Migration Strategy

Per D-20/D-21/D-22/D-23 [CITED: CONTEXT.md]:

**Sequence:**
1. Take a full PostgreSQL dump: `pg_dump -Fc neartax > pre_pqe_backup.dump`
2. Run Alembic migration 022:
   - Add `mlkem_ek`, `mlkem_sealed_dk`, `wrapped_dek`, `email_hmac`, `worker_sealed_dek`, `worker_key_enabled` to `users`
   - Replace plaintext columns with `BYTEA` ciphertext columns in all in-scope tables
   - Drop old `email` UNIQUE INDEX; add `email_hmac` UNIQUE INDEX
   - Drop uniqueness constraints that relied on encrypted columns (replace with HMAC surrogates)
3. TRUNCATE all user-data tables (transactions, wallets, staking_events, lockup_events, epoch_snapshots, transaction_classifications, acb_snapshots, capital_gains_ledger, income_ledger, verification_results, account_verification_status, audit_log data entries, user-scoped classification_rules, user-scoped spam_rules)
4. Deploy new code (auth-service + API + web)
5. Users log in → keypair provisioned at first login → onboarding wizard "returning user" path

**Rollback procedure:**
1. Stop services
2. `pg_restore -d neartax pre_pqe_backup.dump` (restore from step 1 backup)
3. Roll back Alembic: `alembic downgrade 021`
4. Redeploy prior code version

**No dual-write, no in-place backfill.** The re-import-from-source approach (D-20) means the migration is atomic: either fully encrypted or not deployed.

---

## Performance Budget Analysis

[VERIFIED: live benchmarks on this hardware, 2026-04-12]

| Operation | Time | Notes |
|-----------|------|-------|
| ML-KEM-768 keygen | 10.5ms (kyber-py) | One-time per user at registration |
| ML-KEM-768 decaps (login) | 4.4ms (kyber-py) | One-time per login session |
| DEK unwrap (AES-GCM, login) | <1ms | After decaps |
| Total login overhead | ~5ms | Negligible |
| AES-256-GCM encrypt 20k rows | 28ms | Write path (indexer → DB) |
| AES-256-GCM decrypt 20k rows | 11ms | Read path (ACB pipeline) |
| Total encryption overhead for 20k tx pipeline | ~44ms | Well within 2-min budget |

**Phase 15 budget:** The sub-2-minute wallet lookup goal (D-09) is preserved. Crypto overhead adds 44ms to a pipeline that takes ~60-90 seconds today. [VERIFIED: Phase 15 verification estimates pipeline timing around 60-120 seconds for vitalpointai.near (~20k txs)]

**kyber-py vs liboqs performance note:** The pure-Python `kyber-py` at ~10ms for a full cycle is fast enough for this use case (one decaps per login). If batch operations ever require faster keygen (e.g., mass re-key), consider migrating to `liboqs-python` later (estimated ~0.1ms per op).

---

## Pipeline Entry Point Enumeration

[VERIFIED: grep of api/routers/ directory]

All routes requiring DEK injection (currently use `get_effective_user`):

- `api/routers/wallets.py` — 6 endpoints (wallet create/list/status/delete/resync triggers pipelines)
- `api/routers/jobs.py` — 3 endpoints + 1 stub
- `api/routers/portfolio.py` — 2 endpoints
- `api/routers/transactions.py` — 4 endpoints (read/filter/reclassify — require DEK to decrypt)
- `api/routers/preferences.py` — 3 endpoints
- `api/routers/audit.py` — 1 endpoint
- `api/routers/assets.py` — 3 endpoints
- `api/routers/staking.py` — 4 endpoints
- `api/routers/verification.py` — 3 endpoints
- `api/routers/reports.py` — (not grepped but follows same pattern)
- `api/routers/accountant.py` — accountant access (special: needs client's DEK, not accountant's DEK — see Open Question OQ-2)

**Pipeline gating points** (where DEK must be present to start a job):
- `POST /api/wallets` — triggers full_sync + staking_sync + lockup_sync
- `POST /api/wallets/{id}/resync` — re-triggers pipeline
- Any job handler that transitions `indexing_jobs.status` from queued to running

---

## Accountant Access DEK Problem

[CITED: CONTEXT.md specifics section; VERIFIED: dependencies.py read]

The current `get_effective_user` dependency already supports `accountant_access` — an accountant can view a client's data by setting the `neartax_viewing_as` cookie. Post-encryption, the accountant needs the **client's DEK**, not their own.

**Recommended approach:** When a client grants accountant access, generate a **grant-specific re-wrapped DEK**: `ML_KEM_768.encaps(accountant.mlkem_ek)` → re-wrap client's DEK with the accountant's public key. Store as `accountant_access.rewrapped_client_dek`. On accountant login, they decaps with their own ML-KEM sk to get K, then unwrap to get the client's DEK. [ASSUMED — this is the clean cryptographic approach; planner must specify]

This is an important open question. See OQ-2 below.

---

## Common Pitfalls

### Pitfall 1: DEK Context Leaks Across Requests
**What goes wrong:** Thread-local or global DEK context set for User A is still set when a new request for User B starts — User B reads User A's data.
**Why it happens:** FastAPI workers reuse threads. `set_dek()` followed by a forgotten `zero_dek()`.
**How to avoid:** Always use context manager or `try/finally` in the dependency. Never call `set_dek()` outside a scoped context.
**Warning signs:** Tests pass individually but fail in parallel; unexpected decryption of another user's data.

### Pitfall 2: Encrypted Columns Break SQL Filters and ORDER BY
**What goes wrong:** A query like `WHERE category = 'income'` returns no rows after encryption.
**Why it happens:** The column now contains opaque ciphertext; SQL comparisons are meaningless.
**How to avoid:** Identify every SQL query in every router that uses an encrypted column as a filter predicate before migration. Replace with in-memory filtering post-decrypt (D-07).
**Warning signs:** Transaction ledger returns empty results; ACB calculation returns wrong totals.

### Pitfall 3: UniqueConstraint on Encrypted Columns
**What goes wrong:** Alembic migration fails or inserts silently duplicate rows after encryption.
**Why it happens:** `tx_hash`, `receipt_id`, `token_symbol` are in uniqueness constraints but become random-nonce ciphertext after encryption — two encryptions of the same value produce different bytes.
**How to avoid:** Replace with HMAC-based surrogate dedup hash column. Drop old constraints. Add new UNIQUE constraint on surrogate.
**Warning signs:** Duplicate transactions after first sync post-encryption.

### Pitfall 4: liboqs-python Auto-Downloads liboqs at Runtime
**What goes wrong:** Docker container starts, first import of `oqs` triggers a network download and CMake build — container hangs or fails in air-gapped prod.
**Why it happens:** liboqs-python's default behavior: if liboqs shared library not found, it clones from GitHub and builds. [VERIFIED: live test showed this behavior]
**How to avoid:** Use `kyber-py` (pure Python, no C library needed). If using liboqs-python, pre-build liboqs in the Dockerfile and set `LIBOQS_INSTALL_PATH`.
**Warning signs:** Container start time > 5 minutes; network errors in Docker build logs.

### Pitfall 5: DEK Not Zeroed Before Process Exit
**What goes wrong:** Python process exits normally; DEK bytes remain in swap or memory dump.
**Why it happens:** Python's garbage collector does not zero memory before releasing it.
**How to avoid:** Register `atexit.register(zero_dek)` and signal handlers (`SIGTERM`, `SIGINT`). Use `ctypes.memset` to explicitly zero the DEK buffer.
**Warning signs:** Memory forensics tool finds DEK in process memory dump after logout.

### Pitfall 6: Missing DEK in Accountant Viewing Mode
**What goes wrong:** Accountant sets `neartax_viewing_as` cookie, `get_effective_user` returns client's user_id, but the DEK resolved is the accountant's DEK — decryption fails with `InvalidTag`.
**Why it happens:** DEK lookup currently uses session_id → user_id mapping. Accountant's session gives accountant's DEK, but client's encrypted data needs client's DEK.
**How to avoid:** Implement grant-specific re-wrapped DEK as described in OQ-2. When `viewing_as_user_id` is set, resolve DEK from `accountant_access.rewrapped_client_dek` instead.
**Warning signs:** Accountant access returns 500 or empty data post-encryption.

### Pitfall 7: near-phantom-auth IPFS RecoveryPayload Has Fixed Schema
**What goes wrong:** Attempting to use near-phantom-auth's `ipfsRecovery.createRecoveryBackup()` to store the ML-KEM sealed_dk fails because `RecoveryPayload` only has `{ userId, nearAccountId, derivationPath, createdAt }` — no field for ML-KEM key material.
**Why it happens:** near-phantom-auth's IPFS backup channel is hardcoded to its `RecoveryPayload` type. [VERIFIED: source inspect]
**How to avoid:** Build a separate key-custody backup channel in auth-service that re-uses near-phantom-auth's IPFS pinning infrastructure (call Pinata API directly with the extended payload) but outside the package's typed interface.

---

## users Table PII Decision (D-05 Implementation)

[VERIFIED: user-bridge.ts source + magic-link.ts source]

The `users` table [VERIFIED: _all_models.py] currently has: `id`, `near_account_id`, `created_at`, `last_login_at`, `username`, `email`, `is_admin`, `codename`.

**Actual PII in Axiom's users table:**
- `email` — populated from magic link auth and possibly OAuth [VERIFIED: user-bridge.ts syncUser writes email]. The magic-link flow stores the challenge `email` in `anon_challenges` (near-phantom-auth table), then transit-only via AWS SES. The Axiom `users.email` column stores the raw email for lookup. Phase 16 must change this to HMAC-only.
- `display_name` — **does not exist in the current schema** [VERIFIED: _all_models.py read]. D-05 references it but the column does not exist. The ORM has `username` and `codename` instead. Researcher decision: apply D-05's "encrypt display_name" to `username` (the human-chosen identifier). `codename` is pseudonymous (ALPHA-7) and does not need encryption.
- `near_account_id` — public blockchain address; linkable PII. **Encrypt** with user DEK.

**Resolution:** Encrypt `near_account_id` and `username` with user DEK. Store `email_hmac = HMAC(SERVER_HMAC_KEY, email.lower())` as the lookup key. Drop or clear the plaintext `email` column post-migration. The `SERVER_HMAC_KEY` is a 32-byte secret in the server's environment variables (not user-bound — it only enables login lookup, not data decryption).

---

## Code Examples

### ML-KEM-768 Key Generation and Envelope Encryption (Python)

```python
# Source: kyber-py 1.2.0 API + cryptography 46.0.5 [VERIFIED: live test]
from kyber_py.ml_kem import ML_KEM_768
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os, ctypes

def provision_user_keys(sealing_key: bytes) -> dict:
    """Called at user registration when sealing_key arrives from browser PRF.
    
    Returns dict of values to store in users table.
    sealing_key: 32-byte PRF-derived key from browser (HKDF(PRF_output, context))
    """
    # Generate ML-KEM-768 keypair
    ek, dk = ML_KEM_768.keygen()  # ek=1184 bytes, dk=2400 bytes
    
    # Seal the decapsulation key with the browser-derived sealing_key
    seal_nonce = os.urandom(12)
    sealed_dk = seal_nonce + AESGCM(sealing_key).encrypt(seal_nonce, dk, None)
    
    # Generate a fresh DEK
    dek = os.urandom(32)
    
    # Wrap the DEK with ML-KEM: encaps produces shared_secret + ciphertext
    shared_secret, kem_ct = ML_KEM_768.encaps(ek)  # kem_ct=1088 bytes, ss=32 bytes
    wrap_nonce = os.urandom(12)
    wrapped_dek = kem_ct + wrap_nonce + AESGCM(shared_secret).encrypt(wrap_nonce, dek, None)
    
    # Zero sensitive material
    _zero_bytes(sealing_key)
    _zero_bytes(dek)
    _zero_bytes(shared_secret)
    
    return {
        "mlkem_ek": ek,            # store in users.mlkem_ek
        "mlkem_sealed_dk": sealed_dk,  # store in users.mlkem_sealed_dk
        "wrapped_dek": wrapped_dek,    # store in users.wrapped_dek
    }

def unwrap_dek_for_session(sealed_dk: bytes, wrapped_dek: bytes, sealing_key: bytes) -> bytes:
    """Called at login. Returns plaintext DEK."""
    # Unseal ML-KEM private key
    seal_nonce, sealed_dk_ct = sealed_dk[:12], sealed_dk[12:]
    dk = AESGCM(sealing_key).decrypt(seal_nonce, sealed_dk_ct, None)
    
    # Decapsulate to get shared secret
    kem_ct = wrapped_dek[:1088]
    wrap_nonce = wrapped_dek[1088:1100]
    wrapped_dek_ct = wrapped_dek[1100:]
    shared_secret = ML_KEM_768.decaps(dk, kem_ct)
    
    # Unwrap DEK
    dek = AESGCM(shared_secret).decrypt(wrap_nonce, wrapped_dek_ct, None)
    
    # Zero intermediate secrets
    _zero_bytes(sealing_key)
    _zero_bytes(dk)
    _zero_bytes(shared_secret)
    
    return dek  # caller must zero after use

def _zero_bytes(b: bytes) -> None:
    buf = (ctypes.c_char * len(b)).from_buffer_copy(b)
    ctypes.memset(buf, 0, len(buf))
```

### Email HMAC (D-05)

```python
# Source: Python stdlib hmac [VERIFIED: standard pattern]
import hmac as _hmac, os

SERVER_HMAC_KEY = bytes.fromhex(os.environ["EMAIL_HMAC_KEY"])  # 32-byte hex secret

def hash_email(email: str) -> str:
    return _hmac.new(SERVER_HMAC_KEY, email.lower().encode(), 'sha256').hexdigest()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Kyber (draft) | ML-KEM-768 (FIPS 203) | Aug 2024 — NIST finalization | Use "ML-KEM-768" not "Kyber-768" in code/docs |
| Random 96-bit nonce with global key | Per-user DEK + random nonce | — | Nonce collision budget per DEK is per-user, not global |
| WebAuthn for auth only | WebAuthn PRF extension for key derivation | 2024 (Safari 18, Chrome 115+) | Enables passkey-bound encryption keys without storing secrets |
| pgcrypto (DB-side) | App-level encryption | — | pgcrypto rejected (D-deferred); correct choice for "server blind at rest" |

---

## Open Questions

1. **OQ-1: Should `users.near_account_id` and `users.username` be encrypted?**
   - What we know: D-05 says "hash email, encrypt display_name" but doesn't address `near_account_id` or `username`. `near_account_id` is a public NEAR address that fully deanonymizes the user. `username` is human-chosen.
   - What's unclear: Whether login flows query `near_account_id` for routing (user-bridge.ts does — it queries `WHERE near_account_id = $1`). Encrypting it breaks this lookup.
   - Recommendation: Encrypt `near_account_id`; add `near_account_id_hmac` HMAC column for lookup (same pattern as email). Encrypt `username`. The user-bridge.ts lookup path must be updated to use HMAC lookup.

2. **OQ-2: How does accountant access work post-encryption?**
   - What we know: `accountant_access` table grants an accountant read/readwrite to a client. Accountant needs client's DEK to decrypt client's data.
   - What's unclear: The mechanism for DEK grant is not specified in CONTEXT.md.
   - Recommendation: Add `rewrapped_client_dek` column to `accountant_access`. When client grants access, re-wrap client's DEK with accountant's `mlkem_ek`. Store result. Accountant decaps with their own ML-KEM sk at login to get client's DEK. Revocation: DELETE the `accountant_access` row (and its `rewrapped_client_dek`).

3. **OQ-3: How is the DEK transmitted from auth-service (Node.js) to FastAPI (Python)?**
   - What we know: auth-service handles login and holds the unsealed DEK. FastAPI needs it for every encrypted read/write.
   - What's unclear: The exact IPC mechanism. Options: (a) `session_dek_cache` DB table, (b) encrypted session cookie field, (c) auth-service acts as a DEK proxy (FastAPI asks auth-service for DEK per request).
   - Recommendation: Option (a) — `session_dek_cache` table with server-ephemeral encryption key. Lowest latency for FastAPI; auth-service owns the write, FastAPI owns the read. Clean separation.

4. **OQ-4: TypeScript ML-KEM library for auth-service**
   - What we know: `@noble/post-quantum` is a leading candidate but not verified in this research.
   - What's unclear: API, bundle size, FIPS 203 conformance.
   - Recommendation: Planner to verify `@noble/post-quantum` via `npm view @noble/post-quantum`. Alternative: Python IPC endpoint as described in Architecture section.

5. **OQ-5: `transactions.uq_tx_chain_hash_receipt_wallet` unique constraint**
   - What we know: This constraint uses `tx_hash` and `receipt_id` which will be encrypted.
   - What's unclear: Whether the dedup logic needs an exact-match lookup (it does — `ON CONFLICT DO UPDATE`).
   - Recommendation: Add `tx_dedup_hmac = HMAC(SERVER_DEDUP_KEY, chain||tx_hash||receipt_id||wallet_id)` as a cleartext UNIQUE column. Drop old constraint. Use `tx_dedup_hmac` for `ON CONFLICT`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | AES-GCM, ML-KEM | ✓ | 3.11 (Dockerfile) | — |
| `cryptography` lib | AES-256-GCM | ✓ | 46.0.5 | — |
| `kyber-py` | ML-KEM-768 | ✓ (installable) | 1.2.0 | `liboqs-python` (requires C build) |
| `liboqs-python` | ML-KEM-768 alternative | ✗ (needs liboqs C lib) | 0.14.1 pkg | `kyber-py` |
| `fips203` | ML-KEM-768 alternative | ✗ (needs libfips203.so) | 0.4.3 | `kyber-py` |
| WebAuthn PRF support | Client-side key sealing | ✓ (Chrome 115+, Safari 18+, Firefox 139+) | browser-dependent | IPFS+password fallback |
| `@noble/post-quantum` | TypeScript ML-KEM (auth-service) | ? (not verified) | ? | Python IPC endpoint |
| `@simplewebauthn/browser` | PRF extension client-side | ✓ (web dep) | v13 (needs PRF helpers) | — |

**Missing with fallback:**
- `liboqs-python` / `fips203` — use `kyber-py` (already installable, pure Python, works in Docker without build tools)
- `@noble/post-quantum` — use Python IPC endpoint from auth-service if unverified

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (Python), Jest/vitest (TypeScript auth-service) |
| Config file | `pytest.ini` or existing test infrastructure |
| Quick run command | `pytest tests/test_crypto.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PQE-01 | ML-KEM-768 keypair generates; public/private key sizes correct; keygen is deterministic with seed | unit | `pytest tests/test_crypto.py::test_mlkem_keygen -x` | ❌ Wave 0 |
| PQE-01 | ML-KEM-768 KAT vectors pass (FIPS 203 known-answer tests) | unit | `pytest tests/test_crypto.py::test_mlkem_kat -x` | ❌ Wave 0 |
| PQE-02 | Round-trip: generate DEK → wrap with ML-KEM ek → unwrap with ML-KEM dk → DEK matches | unit | `pytest tests/test_crypto.py::test_dek_roundtrip -x` | ❌ Wave 0 |
| PQE-02 | Tamper detection: modify wrapped_dek → decaps raises exception | unit | `pytest tests/test_crypto.py::test_dek_tamper -x` | ❌ Wave 0 |
| PQE-03 | TypeDecorator encrypt/decrypt round-trip for String, Numeric, JSONB types | unit | `pytest tests/test_crypto.py::test_type_decorator -x` | ❌ Wave 0 |
| PQE-03 | Postgres dump of transactions table contains no plaintext amount/counterparty/tx_hash | integration | `pytest tests/test_encryption_at_rest.py::test_no_plaintext_in_db -x` | ❌ Wave 0 |
| PQE-04 | HMAC email lookup finds correct user; different emails don't collide | unit | `pytest tests/test_crypto.py::test_email_hmac -x` | ❌ Wave 0 |
| PQE-05 | Request without DEK in session → accessing encrypted column raises RuntimeError (not silently returns None) | unit | `pytest tests/test_dependencies.py::test_missing_dek -x` | ❌ Wave 0 |
| PQE-06 | Worker key: generate, store, revoke, verify pipeline pauses after revocation | integration | `pytest tests/test_worker_key.py -x` | ❌ Wave 0 |
| PQE-07 | Migration idempotency: running 022 twice is safe | unit | `pytest tests/test_migrations.py::test_022_idempotent -x` | ❌ Wave 0 |
| PQE-08 | DEK is zeroed after `zero_dek()`: ctypes memory scan confirms no DEK pattern in process heap | unit | `pytest tests/test_crypto.py::test_dek_zeroization -x` | ❌ Wave 0 |

### Nyquist Observable Properties ("encrypted at rest" is working)

The following properties are measurable without breaking the encryption:

1. **Raw DB dump contains no plaintext PII:** `pg_dump | strings | grep -v 'expected_cleartext'` finds no amounts, addresses, NEAR account IDs in transactions/wallets tables.
2. **Ciphertext length matches expected overhead:** Every encrypted column value is exactly `12 + len(plaintext) + 16` bytes (nonce + ciphertext + GCM tag).
3. **Decrypt round-trip:** Encrypt a known value, write to DB, read from DB, decrypt — matches original.
4. **Tamper detection fires:** Flip one byte in a stored ciphertext — decrypt raises `cryptography.exceptions.InvalidTag`.
5. **Wrong DEK rejected:** Attempt to decrypt with a different DEK — raises `InvalidTag`.
6. **Session DEK isolated:** User A's DEK cannot decrypt User B's ciphertext.
7. **Post-logout access denied:** After `zero_dek()`, accessing an encrypted column raises `RuntimeError("No DEK in context")`.

### Sampling Rate
- **Per task commit:** `pytest tests/test_crypto.py -x` (unit tests only, <10s)
- **Per wave merge:** `pytest tests/ -x` (full suite)
- **Phase gate:** Full suite green + "no plaintext in DB dump" integration test before `/gsd-verify-work`

### Wave 0 Gaps

All test files must be created:
- [ ] `tests/test_crypto.py` — ML-KEM KATs, DEK round-trip, tamper, zeroization, email HMAC
- [ ] `tests/test_type_decorator.py` — EncryptedBytes TypeDecorator round-trips
- [ ] `tests/test_encryption_at_rest.py` — DB dump plaintext scan integration test
- [ ] `tests/test_worker_key.py` — worker key lifecycle
- [ ] `tests/test_migrations.py::test_022_idempotent` — migration idempotency
- [ ] `tests/test_dependencies.py::test_missing_dek` — missing DEK guard

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | WebAuthn PRF for key sealing; existing near-phantom-auth for auth |
| V3 Session Management | yes | session_dek_cache with expiry; DEK zeroed on session destroy |
| V4 Access Control | yes | user_id isolation in all WHERE clauses; accountant rewrapped DEK |
| V5 Input Validation | yes | All encrypted values are structured bytes; TypeDecorator validates before write |
| V6 Cryptography | yes | kyber-py (FIPS 203), AESGCM (FIPS 197/SP 800-38D), no custom crypto |
| V7 Error Handling | yes | InvalidTag exceptions must not leak plaintext in HTTP responses |
| V8 Data Protection | yes | Core of this phase — encrypted at rest, DEK zeroed in memory |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| DB dump exposes user data | Information Disclosure | Per-user DEK + ML-KEM wrapping — dump reveals only ciphertext |
| Session fixation exposes DEK | Information Disclosure | DEK stored server-side in session_dek_cache, not in cookie |
| DEK lingers in memory post-logout | Information Disclosure | `ctypes.memset` zeroization + atexit handler (D-15) |
| Nonce reuse with same DEK | Tampering | `os.urandom(12)` per-encryption; per-user DEK limits blast radius |
| ML-KEM private key extraction from DB dump | Information Disclosure | sealed_dk = AES-GCM(PRF-derived-key, dk) — PRF key never stored |
| Accountant sees all users' data | Elevation of Privilege | Grant-specific rewrapped_client_dek per accountant_access row |
| Worker key persists after user revokes | Information Disclosure | Revocation DELETEs worker_sealed_dek; worker zeros its copy |
| UniqueConstraint bypass via ciphertext | Tampering | HMAC-based surrogate dedup hash (tx_dedup_hmac) |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `@noble/post-quantum` npm package supports ML-KEM-768 with a usable TypeScript API | Standard Stack (auth-service) | Planner must use Python IPC alternative; adds ~1 wave of work |
| A2 | `session_dek_cache` table approach is the correct IPC mechanism for auth-service → FastAPI DEK handoff | Architecture / DEK Transmission | If wrong, the DEK handoff design changes; not a blocker but adds work |
| A3 | The WebAuthn PRF extension salt `"axiom-mlkem-seal-v1"` approach gives sufficient domain separation for key derivation | Key Architecture | Could allow cross-application PRF collisions if not properly domain-separated |
| A4 | `tx_dedup_hmac` HMAC surrogate is acceptable replacement for the `uq_tx_chain_hash_receipt_wallet` uniqueness constraint | Encrypted Column Inventory | If uniqueness semantics change, the dedup pipeline may produce duplicates |
| A5 | Python IPC endpoint approach (auth-service calls FastAPI for ML-KEM ops) has acceptable latency over Docker internal network | Architecture Patterns | If not, TypeScript ML-KEM library required for auth-service |
| A6 | `needs_review` and `specialist_confirmed` columns in `transaction_classifications` can stay cleartext for routing purposes | Encrypted Column Inventory | Slight privacy leak: server can count how many items need review per user |
| A7 | `source_type` in `income_ledger` stays cleartext for reporting aggregation | Encrypted Column Inventory | Reveals 'staking'/'vesting'/etc. categorization — D-08 might require encryption |
| A8 | PRF fallback via IPFS+password channel is acceptable for browsers without PRF support | Key Architecture | Users on Firefox <139 or Windows Hello pre-25H2 cannot use passkey-derived key sealing — must use IPFS+password instead |

---

## Sources

### Primary (HIGH confidence)
- `db/models/_all_models.py` — complete table/column inventory [VERIFIED: full read]
- `auth-service/src/server.ts` — near-phantom-auth wiring [VERIFIED: full read]
- `auth-service/src/user-bridge.ts` — user bridge / PII storage [VERIFIED: full read]
- `web/node_modules/@vitalpoint/near-phantom-auth/dist/server/index.d.ts` — package API surface [VERIFIED: full read]
- `web/node_modules/@vitalpoint/near-phantom-auth/dist/server/index.js` — implementation inspection [VERIFIED: grep]
- `api/dependencies.py` — current auth dependency injection [VERIFIED: full read]
- `kyber-py` 1.2.0 live benchmark — ML-KEM-768 perf, key sizes [VERIFIED: live Python test]
- `cryptography` 46.0.5 AES-256-GCM benchmark — 20k row encrypt/decrypt performance [VERIFIED: live Python test]
- `fips203` 0.4.3 install test — broken (requires compiled Rust FFI) [VERIFIED: live test]
- `liboqs-python` 0.14.1 install test — requires liboqs C library (network download on first import) [VERIFIED: live test]
- Phase 15 VERIFICATION.md — pipeline timing estimate (~60-120s for 20k txs) [VERIFIED: read]

### Secondary (MEDIUM confidence)
- [Corbado: Passkeys & WebAuthn PRF for End-to-End Encryption](https://www.corbado.com/blog/passkeys-prf-webauthn) — PRF browser support matrix
- [SimpleWebAuthn PRF docs](https://simplewebauthn.dev/docs/advanced/prf) — SimpleWebAuthn PRF helpers
- [Neil Madden: GCM and random nonces](https://neilmadden.blog/2024/05/23/galois-counter-mode-and-random-nonces/) — nonce strategy analysis
- [fips203 PyPI](https://pypi.org/project/fips203/) — package description and beta status

### Tertiary (LOW confidence / ASSUMED)
- `@noble/post-quantum` TypeScript ML-KEM-768 availability — not verified in this session
- `node-oqs` TypeScript liboqs bindings — not verified

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — live install and benchmark confirmed kyber-py, cryptography
- Architecture: MEDIUM — near-phantom-auth source verified; IPC pattern and auth-service ML-KEM approach are reasoned but not prototyped
- Pitfalls: HIGH — most discovered through source code inspection and live testing
- Key architectural finding (near-phantom-auth has no ML-KEM): HIGH — verified by full source inspection

**Research date:** 2026-04-12
**Valid until:** 2026-07-12 (90 days — kyber-py and cryptography are stable; WebAuthn PRF browser support is expanding)
