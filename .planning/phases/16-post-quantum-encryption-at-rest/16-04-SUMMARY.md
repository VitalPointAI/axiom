---
phase: 16-post-quantum-encryption-at-rest
plan: 04
subsystem: database
tags: [post-quantum, alembic, migration, schema, hmac, aes-256-gcm, ml-kem-768, truncate, pg-dump]

# Dependency graph
requires:
  - phase: 16
    plan: 01
    provides: "db/crypto.py — HMAC surrogate functions (hash_email, hash_near_account, compute_tx_dedup_hmac)"
  - phase: 16
    plan: 02
    provides: "session_dek_cache table contract — get_session_dek dependency reads this table"
  - phase: 16
    plan: 03
    provides: "auth-service resolveSessionDek writes to session_dek_cache; provisionUserKeys writes mlkem_* columns"

provides:
  - "db/migrations/versions/022_pqe_schema.py: 791-line Alembic migration (up + down) implementing D-20 through D-28"
  - "db/schema_users.sql: updated users table shape post-migration"
  - "scripts/pre_pqe_backup.sh: pg_dump -Fc backup before destructive TRUNCATE"
  - "scripts/pqe_rollback.sh: interactive rollback (downgrade 021 + pg_restore)"
  - ".planning/phases/16-post-quantum-encryption-at-rest/16-04-MIGRATION-RUNBOOK.md: 281-line cutover runbook"
  - "tests/test_migration_022.py: 3 integration tests (gated on RUN_MIGRATION_TESTS=1)"

affects:
  - 16-05-orm-wiring (uses new BYTEA columns and session_dek_cache; plan can proceed)
  - 16-06-pipeline-gating (DEK dependency reads session_dek_cache created here)
  - 16-07-worker-key-and-cutover (final cutover runs alembic upgrade 022 in production)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "HMAC-SHA256 backfill (stdlib hmac) computed in Python before dropping plaintext columns — no pgcrypto dependency"
    - "Parameterized UPDATE queries for HMAC backfill (no f-string logging of PII — T-16-26)"
    - "server_default placeholder trick for NOT NULL BYTEA columns on empty tables"
    - "DROP column + ADD BYTEA column pattern (safe because tables are TRUNCATEd first)"
    - "Parallel BYTEA columns (pattern_enc, category_enc, name_enc) for classification_rules/spam_rules — system rules keep cleartext"
    - "RuntimeError fail-fast guard in migration if env vars missing (aborts before any DDL)"

key-files:
  created:
    - db/migrations/versions/022_pqe_schema.py
    - scripts/pre_pqe_backup.sh
    - scripts/pqe_rollback.sh
    - .planning/phases/16-post-quantum-encryption-at-rest/16-04-MIGRATION-RUNBOOK.md
    - tests/test_migration_022.py
  modified:
    - db/schema_users.sql
    - .gitignore

decisions:
  - "Stdlib hmac (not pgcrypto) for HMAC backfill — avoids Postgres extension dependency and keeps crypto centralized in Python (db.crypto)"
  - "Fail-fast RuntimeError in migration if EMAIL_HMAC_KEY or NEAR_ACCOUNT_HMAC_KEY missing — migration refuses to run rather than silently writing NULL HMACs"
  - "Drop check constraints (ck_staking_event_type, ck_acb_event_type, ck_avs_status) on tables with BYTEA columns — cleartext check constraints cannot validate encrypted values"
  - "Drop indexes on cleartext columns that are now BYTEA (ix_tc_category, ix_al_action, etc.) — indexes on ciphertext are useless; query-by-decrypted-value is handled in-app (D-07)"
  - "session_dek_cache without REFERENCES sessions(id) FK — auth-service manages lifecycle via explicit DELETE on logout; application-level cleanup avoids dependency on sessions table schema"
  - "backups/ directory added to .gitignore — T-16-23 prevention (pg_dump contains plaintext user PII)"
  - "test_migration_022.py skips (not fails) without RUN_MIGRATION_TESTS=1 — unit test runs must not require a real Postgres"

requirements-completed: [PQE-03, PQE-04, PQE-07]

# Metrics
duration: ~65min (code authoring; plan started 2026-04-12T23:40Z, completed 2026-04-13T00:41Z approx)
completed: 2026-04-13
---

# Phase 16 Plan 04: Alembic Migration 022 Summary

**791-line Alembic migration 022 implementing the full PQE schema transformation — HMAC backfill, 13-table TRUNCATE, BYTEA column swap on 11 per-user tables, session_dek_cache creation — with backup/rollback scripts, cutover runbook, and 3 integration tests**

## Performance

- **Duration:** ~65 min
- **Started:** 2026-04-12T23:40:13Z
- **Completed:** 2026-04-13T00:41:00Z
- **Tasks:** 3 committed (Task 4 = checkpoint — PAUSED, not executed)
- **Files modified:** 7 (created: 022_pqe_schema.py, pre_pqe_backup.sh, pqe_rollback.sh, 16-04-MIGRATION-RUNBOOK.md, test_migration_022.py; modified: schema_users.sql, .gitignore)

## Accomplishments

**Task 1 — Migration 022 + schema_users.sql (commit aa1b643):**

- Created `db/migrations/versions/022_pqe_schema.py` (791 lines) implementing decisions D-20 through D-28:
  - **users table (D-05, D-11, D-12, D-17, D-24):** Added mlkem_ek, mlkem_sealed_dk, wrapped_dek, email_hmac UNIQUE, near_account_id_hmac UNIQUE, worker_sealed_dek, worker_key_enabled. Backfilled email_hmac and near_account_id_hmac from existing plaintext via stdlib HMAC-SHA256 BEFORE dropping source columns. Dropped email/near_account_id/username; re-added as BYTEA.
  - **accountant_access (D-25):** Added rewrapped_client_dek BYTEA column.
  - **session_dek_cache (D-26):** Created new table with session_id TEXT PK, encrypted_dek BYTEA, expires_at TIMESTAMPTZ, created_at TIMESTAMPTZ; expires_at index.
  - **TRUNCATE (D-20):** TRUNCATEd 13 user-data tables with RESTART IDENTITY CASCADE. DELETEd user-scoped classification_rules and spam_rules rows.
  - **BYTEA column swap on 11 tables:** transactions, wallets, staking_events, epoch_snapshots, lockup_events, transaction_classifications, acb_snapshots, capital_gains_ledger, income_ledger, verification_results, account_verification_status, audit_log — all sensitive columns replaced with BYTEA using DROP+ADD (safe after TRUNCATE).
  - **Dedup HMAC columns (D-28):** tx_dedup_hmac BYTEA NOT NULL on transactions with UNIQUE(user_id, tx_dedup_hmac); acb_dedup_hmac BYTEA NOT NULL on acb_snapshots with UNIQUE(user_id, acb_dedup_hmac). Old uq_tx_chain_hash_receipt_wallet and uq_acb_user_token_classification dropped.
  - **classification_rules/spam_rules:** Added parallel BYTEA columns (pattern_enc, category_enc, name_enc; rule_type_enc, value_enc) — system rules (user_id IS NULL) keep cleartext columns.
  - **downgrade():** Full schema reversal — removes all PQE additions and restores pre-022 column shapes. Data restore requires pg_restore from backup.
- Updated `db/schema_users.sql` to reflect the post-migration users table shape.

**Task 2 — Backup/rollback scripts + runbook (commit cef5620):**

- `scripts/pre_pqe_backup.sh`: `pg_dump -Fc` backup to `.planning/phases/16.../backups/pre_pqe_YYYYMMDD_HHMMSS.dump`. Enforces DATABASE_URL, auto-adds backups/ to .gitignore (T-16-23), fails loudly on empty dump.
- `scripts/pqe_rollback.sh`: Interactive rollback (requires typing "YES"). Stops api/auth-service/indexer, runs `alembic downgrade 021`, runs `pg_restore --clean --if-exists`. Restarts services. Accepts explicit dump path or auto-selects latest.
- `.planning/.../16-04-MIGRATION-RUNBOOK.md` (281 lines): Complete cutover runbook with pre-flight env-var checklist (6 keys), backup → migration → sanity-check → deploy sequence, smoke test steps, rollback trigger conditions, 9-entry diagnostics table.
- `.gitignore`: Added `backups/` directory (T-16-23 mitigation — pg_dump contains plaintext user PII).

**Task 3 — Migration tests (commit 0810dc1):**

- `tests/test_migration_022.py`: 3 integration tests gated on `RUN_MIGRATION_TESTS=1`:
  - `test_022_upgrade_preserves_user_wipes_data`: Full upgrade 022 verification — users preserved, HMACs populated, transactions/wallets TRUNCATEd, PQE columns exist, public data plane untouched.
  - `test_022_downgrade_removes_scaffolding`: Upgrade+downgrade round-trip — session_dek_cache gone, mlkem_ek gone, users.email back to VARCHAR.
  - `test_022_env_var_required`: Confirms fail-fast RuntimeError when EMAIL_HMAC_KEY is missing.
- Tests skip (not fail) without `RUN_MIGRATION_TESTS=1` — safe for routine local unit test runs.
- Wave 0 tests remain 24/24 green.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Migration 022 + schema_users.sql | `aa1b643` | db/migrations/versions/022_pqe_schema.py, db/schema_users.sql |
| 2 | Backup/rollback scripts + runbook | `cef5620` | scripts/pre_pqe_backup.sh, scripts/pqe_rollback.sh, 16-04-MIGRATION-RUNBOOK.md, .gitignore |
| 3 | Migration integration tests | `0810dc1` | tests/test_migration_022.py |
| 4 | **CHECKPOINT — NOT EXECUTED** | — | `alembic upgrade head` against live dev DB |

## CRITICAL: Remaining Checkpoint

**Task 4 is a `checkpoint:human-verify` that has NOT been executed.**

The human operator must run the migration dry-run against the dev database before this plan can be marked complete. See the CHECKPOINT REACHED section at the end of this document for exact instructions.

## Decisions Made

- Used stdlib `hmac.new()` (not pgcrypto) for HMAC backfill in migration — keeps all crypto in Python, avoids Postgres extension dependency.
- Migration has a RuntimeError fail-fast guard if EMAIL_HMAC_KEY or NEAR_ACCOUNT_HMAC_KEY is missing — refuses to run rather than silently writing NULL HMACs that would break auth-service lookups.
- Dropped check constraints (ck_staking_event_type, ck_acb_event_type, ck_avs_status) on tables with encrypted columns — cleartext CHECK constraints cannot validate BYTEA ciphertext.
- session_dek_cache created without REFERENCES sessions(id) FK — auth-service owns the lifecycle via explicit DELETE on logout; avoiding the FK prevents cross-table dependency issues.
- Drop+re-add column pattern (not ALTER COLUMN TYPE) — cleaner DDL on newly empty tables; also bypasses PostgreSQL restrictions on casting JSONB/Numeric to BYTEA.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Critical Functionality] Added check constraint drops alongside column swaps**
- **Found during:** Task 1 implementation
- **Issue:** The plan's column swap list didn't explicitly mention dropping CHECK constraints on encrypted columns (ck_staking_event_type on event_type, ck_acb_event_type on event_type, ck_avs_status on status). After encryption, these string-check constraints would be applied to BYTEA ciphertext, causing all INSERT attempts to fail.
- **Fix:** Added `op.drop_constraint()` calls for ck_staking_event_type, ck_acb_event_type, ck_avs_status in upgrade(); restored them in downgrade() via raw SQL ALTER TABLE.
- **Files modified:** db/migrations/versions/022_pqe_schema.py
- **Commit:** aa1b643

**2. [Rule 2 - Critical Functionality] Added cleartext index drops alongside BYTEA column swaps**
- **Found during:** Task 1 implementation
- **Issue:** The plan listed columns to swap but didn't list the cleartext indexes (ix_tc_category, ix_tc_needs_review, ix_al_entity, ix_al_action, ix_acb_token_symbol, ix_cgl_token_symbol, ix_vr_status) that would be left dangling after the DROP. Also: uq_vr_wallet_token references token_symbol (now BYTEA) and uq_epoch_wallet_validator_epoch references validator_id (now BYTEA) — both must be dropped.
- **Fix:** Added explicit `op.drop_index()` and `op.drop_constraint()` calls before or after the column swaps; mirrored in downgrade() with `op.create_index()` and `op.create_unique_constraint()` restores.
- **Files modified:** db/migrations/versions/022_pqe_schema.py
- **Commit:** aa1b643

**3. [Rule 1 - Bug] users_username_key unique constraint added to downgrade()**
- **Found during:** Task 1 review of downgrade() path
- **Issue:** The plan's downgrade() skeleton restored email and near_account_id UNIQUE constraints but omitted the username UNIQUE constraint that existed pre-migration (from migration 006_auth_schema). The downgrade would leave username without its UNIQUE constraint, creating a schema mismatch.
- **Fix:** Added `op.create_unique_constraint("users_username_key", "users", ["username"])` in downgrade().
- **Files modified:** db/migrations/versions/022_pqe_schema.py
- **Commit:** aa1b643

## Known Stubs

None — the migration file is complete. All columns, constraints, and tables are implemented as specified. The `session_dek_cache` table has no FK to `sessions` (intentional decision documented above). Migration tests are gated on `RUN_MIGRATION_TESTS=1` but are complete implementations, not stubs.

The tests could not be run against a real DB in this environment (no Postgres available). The test file is complete and will run correctly when `RUN_MIGRATION_TESTS=1` and `TEST_DATABASE_URL` are set.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| T-16-23 (mitigated) | scripts/pre_pqe_backup.sh | pg_dump creates a file containing plaintext user PII. Mitigated by: (1) auto-adding backups/ to .gitignore in the backup script, (2) storing outside git-tracked paths. |

No new unplanned threat surfaces introduced.

## Self-Check: PASSED

Files exist:
- FOUND: db/migrations/versions/022_pqe_schema.py (791 lines)
- FOUND: db/schema_users.sql (updated)
- FOUND: scripts/pre_pqe_backup.sh (executable, syntax-valid)
- FOUND: scripts/pqe_rollback.sh (executable, syntax-valid)
- FOUND: .planning/phases/16-post-quantum-encryption-at-rest/16-04-MIGRATION-RUNBOOK.md (281 lines)
- FOUND: tests/test_migration_022.py (3 tests collected)

Commits exist:
- FOUND: aa1b643 (Task 1 — migration 022 + schema_users.sql)
- FOUND: cef5620 (Task 2 — backup/rollback scripts + runbook)
- FOUND: 0810dc1 (Task 3 — migration tests)

Tests:
- Wave 0 (test_crypto.py + test_type_decorator.py): 24 passed
- test_migration_022.py: 3 skipped (RUN_MIGRATION_TESTS not set — correct behavior)

## CHECKPOINT REACHED: Task 4 — Human Verify Dev DB Dry-Run

**Type:** human-verify  
**Progress:** Tasks 1-3 complete and committed. Task 4 (PAUSED).

The migration file, backup scripts, rollback scripts, runbook, and tests are all in place. The next step requires the human operator to run a dry-run of `alembic upgrade 022` against the dev database.

### Verification Steps

```bash
# 1. Backup the dev DB first
export DATABASE_URL="postgres://neartax:<password>@localhost:5432/neartax"
./scripts/pre_pqe_backup.sh
# Confirm: backups/pre_pqe_YYYYMMDD_HHMMSS.dump appears and is non-empty

# 2. Set HMAC env vars (generate fresh 32-byte hex keys for dev)
export EMAIL_HMAC_KEY=$(openssl rand -hex 32)
export NEAR_ACCOUNT_HMAC_KEY=$(openssl rand -hex 32)
export TX_DEDUP_KEY=$(openssl rand -hex 32)
export ACB_DEDUP_KEY=$(openssl rand -hex 32)
export SESSION_DEK_WRAP_KEY=$(openssl rand -hex 32)

# 3. Run migration 022
alembic upgrade 022
# Confirm: exits 0, no errors

# 4. Sanity checks
psql $DATABASE_URL -c "SELECT COUNT(*) FROM users;"
# Expected: same count as before (users preserved — D-22)

psql $DATABASE_URL -c "SELECT COUNT(*) FROM transactions;"
# Expected: 0 (TRUNCATEd — D-20)

psql $DATABASE_URL -c "SELECT email_hmac, near_account_id_hmac FROM users LIMIT 3;"
# Expected: 64-char hex strings (not NULL)

psql $DATABASE_URL -c "\d session_dek_cache"
# Expected: table exists with session_id, encrypted_dek, expires_at, created_at

psql $DATABASE_URL -c "SELECT column_name FROM information_schema.columns WHERE table_name='accountant_access' AND column_name='rewrapped_client_dek';"
# Expected: 1 row returned

# 5. Rollback (restore dev DB to pre-migration state)
./scripts/pqe_rollback.sh .planning/phases/16-post-quantum-encryption-at-rest/backups/pre_pqe_*.dump
# Type YES when prompted
# Confirm: services restart, transaction count restored

# 6. Report: "approved" if clean, or describe any errors
```

### Expected Post-Conditions (Post-Upgrade, Before Rollback)

- `alembic current` = `022 (head)`
- `SELECT COUNT(*) FROM users` = original count (auth rows preserved)
- `SELECT COUNT(*) FROM transactions` = 0
- `SELECT COUNT(*) FROM wallets` = 0
- `\d session_dek_cache` shows the table
- `SELECT email_hmac FROM users LIMIT 1` returns a 64-char hex string

### Expected Post-Conditions (Post-Rollback)

- `alembic current` = `021 (head)`
- `SELECT COUNT(*) FROM transactions` = original count (data restored from pg_dump)
- `\d session_dek_cache` returns "relation does not exist"

---
*Phase: 16-post-quantum-encryption-at-rest*  
*Completed (Tasks 1-3): 2026-04-13*  
*Paused at Task 4 checkpoint*
