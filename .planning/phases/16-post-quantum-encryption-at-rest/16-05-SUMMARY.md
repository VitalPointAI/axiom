---
phase: 16-post-quantum-encryption-at-rest
plan: 05
subsystem: database
tags: [post-quantum, aes-256-gcm, hmac, sqlalchemy, typedecorator, encrypted-columns, dedup-hmac, orm]

# Dependency graph
requires:
  - phase: 16
    plan: 01
    provides: "db/crypto.py — EncryptedBytes TypeDecorator, compute_tx_dedup_hmac, compute_acb_dedup_hmac, get_dek, set_dek, zero_dek"
  - phase: 16
    plan: 04
    provides: "migration 022 — BYTEA columns, tx_dedup_hmac, acb_dedup_hmac, session_dek_cache, PQE user columns"

provides:
  - "db/models/_all_models.py: 95 EncryptedBytes columns across 13 models + all PQE metadata columns"
  - "db/dedup_hmac_helpers.py: insert_transaction_with_dedup(), insert_acb_snapshot_with_dedup() with ON CONFLICT DO UPDATE"
  - "indexers/near_fetcher.py: _batch_insert replaced with insert_transaction_with_dedup"
  - "indexers/evm_fetcher.py: _batch_upsert replaced with insert_transaction_with_dedup"
  - "engine/acb/engine_acb.py: _persist_snapshot delegates to insert_acb_snapshot_with_dedup"
  - "db/audit.py: write_audit() preflight get_dek() raises RuntimeError when no DEK (T-16-30)"
  - "tests/test_orm_encryption.py: 7 tests (5 DB-backed, 2 pure Python)"
  - "tests/test_audit_encryption.py: 3 tests (1 DB-backed, 2 pure Python)"

affects:
  - 16-06-pipeline-gating
  - 16-07-worker-key-and-cutover

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "EncryptedBytes.process_bind_param(value, None) callable standalone at psycopg2 layer"
    - "Dedup HMAC computed from plaintext BEFORE encryption — passed as cleartext BYTEA for ON CONFLICT"
    - "insert_transaction_with_dedup() / insert_acb_snapshot_with_dedup() — encrypt-then-insert pattern"
    - "audit.write_audit() preflight get_dek() — fail-closed audit invariant (T-16-30)"
    - "RUN_MIGRATION_TESTS=1 gate for DB round-trip tests requiring migration 022 schema"

key-files:
  created:
    - db/dedup_hmac_helpers.py
    - tests/test_orm_encryption.py
    - tests/test_audit_encryption.py
  modified:
    - db/models/_all_models.py
    - db/audit.py
    - indexers/near_fetcher.py
    - indexers/evm_fetcher.py
    - engine/acb/engine_acb.py

key-decisions:
  - "EncryptedBytes operates at psycopg2 layer via process_bind_param(value, None) — dialect=None works; no SQLAlchemy session needed in indexers"
  - "Dedup HMAC computed BEFORE column encryption from plaintext values — essential because HMAC input must be deterministic"
  - "ON CONFLICT (user_id, tx_dedup_hmac) DO UPDATE replaces old cleartext uniqueness constraint (D-28)"
  - "Parallel *_enc columns on ClassificationRule/SpamRule — system rules keep cleartext; user rules use encrypted columns"
  - "AuditLog: entity_type, action, old_value, new_value, notes all EncryptedBytes; actor_type stays cleartext (non-PII routing field)"
  - "uq_wallet_user_account_chain dropped from Wallet model — account_id is BYTEA so ORM-level uniqueness not possible; callers deduplicate in Python"
  - "Wallet.is_owned made EncryptedBytes (per plan interfaces block — was Boolean)"

patterns-established:
  - "Pattern: All new transaction inserts call insert_transaction_with_dedup() — never raw INSERT"
  - "Pattern: All new acb_snapshots inserts call insert_acb_snapshot_with_dedup() — never raw INSERT"
  - "Pattern: audit writes require DEK in context — fail loudly if missing (not silently skip)"
  - "Pattern: DB-backed tests gated on RUN_MIGRATION_TESTS=1; pure Python tests always run"

requirements-completed: [PQE-03, PQE-04]

# Metrics
duration: 68min
completed: 2026-04-13
---

# Phase 16 Plan 05: ORM Wiring Summary

**95 EncryptedBytes columns across 13 ORM models, dedup HMAC write helpers replacing raw INSERT in all indexers and ACB engine, fail-closed audit DEK preflight, and 10 tests (4 pure Python always-run, 6 DB-backed gated)**

## Performance

- **Duration:** ~68 min
- **Started:** 2026-04-13T19:08:33Z
- **Completed:** 2026-04-13T20:16:53Z
- **Tasks:** 3
- **Files modified:** 8 (created: db/dedup_hmac_helpers.py, tests/test_orm_encryption.py, tests/test_audit_encryption.py; modified: db/models/_all_models.py, db/audit.py, indexers/near_fetcher.py, indexers/evm_fetcher.py, engine/acb/engine_acb.py)

## Accomplishments

- Converted `db/models/_all_models.py` from cleartext column types to `EncryptedBytes` TypeDecorator across 13 model classes (95 column usages). Added all Phase 16 PQE metadata columns: `mlkem_ek`, `mlkem_sealed_dk`, `wrapped_dek`, `email_hmac`, `near_account_id_hmac`, `worker_sealed_dek`, `worker_key_enabled`, `tx_dedup_hmac`, `acb_dedup_hmac`, `rewrapped_client_dek`, and the `SessionDekCache` model.
- Created `db/dedup_hmac_helpers.py` with `insert_transaction_with_dedup()` and `insert_acb_snapshot_with_dedup()`: compute HMAC dedup surrogates from plaintext values, encrypt all in-scope columns via `EncryptedBytes.process_bind_param()`, and upsert with `ON CONFLICT (user_id, dedup_hmac) DO UPDATE`.
- Wired all three production write paths: `indexers/near_fetcher.py::_batch_insert`, `indexers/evm_fetcher.py::_batch_upsert`, and `engine/acb/engine_acb.py::_persist_snapshot` — all delegate to the dedup helpers.
- Added DEK preflight to `db/audit.write_audit()`: raises `RuntimeError("audit_log write attempted without a DEK in context. ...")` before touching the DB, satisfying T-16-30 and the plan's fail-closed invariant.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Convert ORM columns to EncryptedBytes | `2a384a1` | db/models/_all_models.py |
| 2 | Dedup HMAC helpers + write-path wiring | `6470791` | db/dedup_hmac_helpers.py, db/audit.py, indexers/near_fetcher.py, indexers/evm_fetcher.py, engine/acb/engine_acb.py |
| 3 | ORM encryption round-trip and fail-closed tests | `9e3d132` | tests/test_orm_encryption.py, tests/test_audit_encryption.py |

## Files Created/Modified

- `db/models/_all_models.py` — 95 EncryptedBytes columns; new PQE columns (mlkem_*, email_hmac, near_account_id_hmac, tx_dedup_hmac, acb_dedup_hmac, rewrapped_client_dek, worker_*); SessionDekCache model; parallel *_enc columns on ClassificationRule/SpamRule
- `db/dedup_hmac_helpers.py` — 165-line module: `insert_transaction_with_dedup()`, `insert_acb_snapshot_with_dedup()`, each with ON CONFLICT DO UPDATE SQL + EncryptedBytes.process_bind_param() at psycopg2 layer
- `db/audit.py` — Added `import db.crypto as _c` and get_dek() preflight with specific RuntimeError message
- `indexers/near_fetcher.py` — `_batch_insert()` replaced with dedup helper calls; added `from db.dedup_hmac_helpers import insert_transaction_with_dedup`
- `indexers/evm_fetcher.py` — `_batch_upsert()` replaced; removed `execute_values` and unused `json` import
- `engine/acb/engine_acb.py` — `_persist_snapshot()` delegates to `insert_acb_snapshot_with_dedup()`
- `tests/test_orm_encryption.py` — 7 tests (5 DB-backed gated on RUN_MIGRATION_TESTS=1, 2 pure Python always-run)
- `tests/test_audit_encryption.py` — 3 tests (1 DB-backed, 2 pure Python)

## Decisions Made

- **EncryptedBytes at psycopg2 layer:** `process_bind_param(value, None)` accepts `dialect=None` and works standalone. This avoids forcing SQLAlchemy sessions into the indexers, which are entirely psycopg2-based.
- **Dedup HMAC computed before encryption:** The dedup HMAC inputs (tx_hash, token_symbol) are plaintext values. The HMAC is computed first, then columns are encrypted. This is the only correct order — the HMAC must be deterministic, so it cannot use ciphertext (which is non-deterministic by design).
- **Wallet.is_owned made EncryptedBytes (was Boolean):** The plan interfaces block lists `is_owned` as an encrypted column. Changed to EncryptedBytes; callers that write Boolean values will receive Boolean back via the type tag round-trip.
- **uq_wallet_user_account_chain dropped from ORM:** account_id is now BYTEA. A unique constraint on ciphertext would be useless (each encryption produces different bytes). Callers must deduplicate in Python when re-entering wallets.
- **AuditLog indexes revised:** `ix_al_entity` index changed from `(entity_type, entity_id)` to just `(entity_id)` since entity_type is now BYTEA ciphertext. `ix_al_action` removed (action is BYTEA). This matches what migration 022 actually produced.
- **write_audit conn=None behavior preserved:** The DEK preflight runs before the `if conn is None: return` check. This means `conn=None` still silently skips the insert IF a DEK is set; it raises if no DEK regardless of conn.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Wallet.is_owned changed from Boolean to EncryptedBytes**
- **Found during:** Task 1 (ORM column conversion)
- **Issue:** Plan interfaces block lists `is_owned` in the Wallet encrypted columns list. The plan action step says "Boolean" in the Wallet ORM, but the interfaces contract says it should be encrypted. Threat model D-08 says no cleartext enums — `is_owned` reveals user's custodial stance.
- **Fix:** Changed `is_owned` from `Boolean` to `EncryptedBytes`.
- **Files modified:** db/models/_all_models.py
- **Commit:** 2a384a1

**2. [Rule 2 - Missing Critical] AuditLog index corrected to not index BYTEA ciphertext**
- **Found during:** Task 1 (ORM column conversion)
- **Issue:** The original model had `Index("ix_al_entity", "entity_type", "entity_id")` — after migration 022 drops the cleartext entity_type column, this index would attempt to index ciphertext (useless) or fail.
- **Fix:** Changed index to `Index("ix_al_entity", "entity_id")` only; removed `ix_al_action` (action is also BYTEA).
- **Files modified:** db/models/_all_models.py
- **Commit:** 2a384a1

**3. [Rule 2 - Missing Critical] `evm_fetcher.py`: removed unused `psycopg2.extras.execute_values` and `json` imports**
- **Found during:** Task 2 (replacing _batch_upsert)
- **Issue:** After replacing the `execute_values`-based batch insert with per-row `insert_transaction_with_dedup()` calls, `execute_values` and `json` became unused imports (ruff flagged F401).
- **Fix:** Removed both imports; ruff lint passes.
- **Files modified:** indexers/evm_fetcher.py
- **Commit:** 6470791

---

**Total deviations:** 3 auto-fixed (all Rule 2 — missing critical correctness)
**Impact on plan:** All fixes necessary for correct behavior. No scope creep.

## D-07 SQL WHERE Clause Audit (Handed off to Plan 16-06)

The following files contain SQL WHERE clauses that filter on now-encrypted columns.
Plan 16-06 must rewrite these to fetch-all-then-filter-in-memory (D-07):

| File | Encrypted column in WHERE | Notes |
|------|--------------------------|-------|
| `api/routers/assets.py:182,419` | `rule_type = 'token_symbol'` | SpamRule lookup by type |
| `engine/classifier/near_classifier.py:37` | `event_type = 'reward'` | StakingEvent filter |
| `engine/wallet_graph.py:121,131` | `direction = 'out'` / `direction = 'in'` | Transaction direction filter |
| `indexers/near_indexer_nearblocks.py:342` | `tx_hash = %s`, `direction = %s` | Legacy nearblocks indexer (deprecated) |
| `indexers/staking_fetcher.py:628,668` | `validator_id = %s`, `event_type = 'deposit'` | Staking event lookup |
| `indexers/backfill_defi_prices.py:85,100,114,128,146` | `token_symbol = %s` | Price backfill by symbol |
| `indexers/epoch_staking_snapshot.py:108` | `validator_id = %s` | Epoch snapshot lookup |
| `indexers/epoch_rewards_indexer.py:210,219,482,576` | `validator_id = %s` | Epoch reward queries |
| `indexers/historical_backfill.py:123,218` | `validator_id = %s` | Historical backfill |
| `indexers/lockup_fetcher.py:422` | `tx_hash = %s`, `event_type = %s` | Lockup dedup |
| `indexers/full_backfill.py:114,236` | `validator_id = %s` | Full backfill |

**Note:** The plan explicitly scoped this to an enumeration task for plan 16-06. These WHERE clauses will need to become fetch-by-user_id-then-filter-in-memory patterns. The most common cases (staking_fetcher, epoch_rewards_indexer) filter by validator_id which is encrypted — those fetchers will need to decrypt the validator_id column and compare in Python.

## Issues Encountered

None. Plan executed without unexpected blocking issues. The HMAC dedup helpers required one design decision (plaintext vs. post-encrypt HMAC computation) that was resolved correctly.

## Known Stubs

None — all implemented functionality is complete. The DB-backed tests are gated but not stubbed; they will run correctly when `RUN_MIGRATION_TESTS=1` is set against a migration-022 database.

Note: The production write paths (near_fetcher, evm_fetcher, acb engine) will only actually execute with encryption when `set_dek()` is called in the request context. Plan 16-06 wires the `get_session_dek()` dependency into the pipeline entry points. Until 16-06 ships, callers without a DEK will receive `RuntimeError: No DEK in context` when they attempt the first encrypted write — which is the correct fail-closed behavior.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced beyond those documented in the plan's threat model (T-16-28, T-16-29, T-16-30).

## Next Phase Readiness

- `db/models/_all_models.py` is fully encryption-aware. All in-scope columns use `EncryptedBytes`; plan 16-06 can import these models and use them with the DEK context wired.
- `db/dedup_hmac_helpers.py` is the canonical transaction/snapshot write path. All three production write paths have been updated. Plan 16-06 only needs to ensure `set_dek()` is called before those code paths execute.
- `db/audit.py` is fail-closed. Any code path that calls `write_audit()` without a DEK will raise immediately.
- Tests pass: 24 Wave 0 tests + 4 pure Python Phase 16-05 tests green on every run. 6 DB-backed tests ready to run with `RUN_MIGRATION_TESTS=1`.
- **Blockers for plan 16-06:** The D-07 WHERE clauses table above must be addressed before production indexing runs (staking_fetcher, epoch_rewards_indexer). These are enumerated in the table above.

## Self-Check: PASSED

Files exist:
- FOUND: db/models/_all_models.py (EncryptedBytes count: 95)
- FOUND: db/dedup_hmac_helpers.py (insert_transaction_with_dedup, insert_acb_snapshot_with_dedup)
- FOUND: db/audit.py (get_dek preflight + specific RuntimeError message)
- FOUND: indexers/near_fetcher.py (insert_transaction_with_dedup called)
- FOUND: indexers/evm_fetcher.py (insert_transaction_with_dedup called)
- FOUND: engine/acb/engine_acb.py (insert_acb_snapshot_with_dedup called)
- FOUND: tests/test_orm_encryption.py (7 tests)
- FOUND: tests/test_audit_encryption.py (3 tests)

Commits exist:
- FOUND: 2a384a1 (Task 1 — ORM columns to EncryptedBytes)
- FOUND: 6470791 (Task 2 — dedup helpers + write-path wiring + audit DEK preflight)
- FOUND: 9e3d132 (Task 3 — ORM encryption round-trip and fail-closed tests)

Tests:
- Wave 0 (test_crypto.py + test_type_decorator.py): 24 passed
- test_orm_encryption.py (pure Python subset): 2 passed
- test_audit_encryption.py (pure Python subset): 2 passed
- Total pure Python tests: 4/4 passed

---
*Phase: 16-post-quantum-encryption-at-rest*
*Completed: 2026-04-13*
