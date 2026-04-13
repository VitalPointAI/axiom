# Phase 16 Migration 022 Runbook

**Migration:** 022_pqe_schema — Post-Quantum Encryption at Rest schema cutover  
**Risk level:** HIGH — TRUNCATEs all user-data tables (D-20). Data is unrecoverable without the backup.  
**Estimated duration:** 5-15 minutes (depending on DB size; TRUNCATE is fast on empty-ish dev DB)  
**Rollback window:** Up to 24 hours post-deploy (before new encrypted data is written and relied upon)

---

## Pre-Flight Checklist

Complete ALL items before running `alembic upgrade 022`. No exceptions.

- [ ] **Run pre_pqe_backup.sh** and confirm dump exists in `backups/` dir
- [ ] **Verify dump file size** is non-zero (`du -h backups/pre_pqe_*.dump`)
- [ ] **Test restore on a throwaway DB** (optional but recommended for production)
- [ ] **All required env vars are set** (see section below)
- [ ] **No active sessions** — notify users of planned maintenance window
- [ ] **Rust account indexer** (systemd) is NOT stopped — it writes to `account_transactions` which is untouched
- [ ] **alembic current** shows revision 021 before starting
- [ ] **Dev/test dry-run completed** (see Task 4 checkpoint requirement)

---

## Required Environment Variables

All 6 variables must be set in the shell that runs `alembic upgrade 022` and in
`docker-compose.prod.yml` before deploying the Phase 16 application code.

Generate values with `openssl rand -hex 32` — each must be a 64-character hex string (32 bytes).

```bash
export EMAIL_HMAC_KEY="<64 hex chars>"         # HMAC key for email address hashing (D-05)
export NEAR_ACCOUNT_HMAC_KEY="<64 hex chars>"  # HMAC key for NEAR account ID hashing (D-24)
export TX_DEDUP_KEY="<64 hex chars>"           # HMAC key for transaction dedup (D-28)
export ACB_DEDUP_KEY="<64 hex chars>"          # HMAC key for ACB snapshot dedup (D-28)
export SESSION_DEK_WRAP_KEY="<64 hex chars>"   # AES-256-GCM key for session_dek_cache (D-26)
export INTERNAL_SERVICE_TOKEN="<any string>"   # auth-service → FastAPI IPC token (≥32 chars)
```

**IMPORTANT:** Store these values in your secrets manager (AWS SSM, 1Password, etc.) immediately.
If EMAIL_HMAC_KEY or NEAR_ACCOUNT_HMAC_KEY are lost, existing HMAC lookups will fail and users
cannot be resolved pre-session. These keys are rotation-sensitive — treat like root credentials.

---

## Step 1: Pre-Migration Backup (D-23)

```bash
export DATABASE_URL="postgres://neartax:<password>@localhost:5432/neartax"
./scripts/pre_pqe_backup.sh
```

Verify the output shows:
```
[pre_pqe_backup] SUCCESS
[pre_pqe_backup] Dump file: .planning/phases/16-post-quantum-encryption-at-rest/backups/pre_pqe_YYYYMMDD_HHMMSS.dump
[pre_pqe_backup] File size: <non-zero size>
```

**Record the dump file path** — you will need it for rollback:
```
BACKUP_PATH=".planning/phases/16-post-quantum-encryption-at-rest/backups/pre_pqe_YYYYMMDD_HHMMSS.dump"
```

---

## Step 2: Verify Current Schema State

```bash
alembic current
# Expected output: 021 (head)

psql $DATABASE_URL -c "SELECT COUNT(*) FROM users;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM transactions;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM wallets;"
```

Record row counts for post-migration verification:
- users count (should be preserved post-migration): ____
- transactions count (should be 0 post-migration): ____
- wallets count (should be 0 post-migration): ____

---

## Step 3: Set Environment Variables

```bash
export EMAIL_HMAC_KEY="<from secrets manager>"
export NEAR_ACCOUNT_HMAC_KEY="<from secrets manager>"
export TX_DEDUP_KEY="<from secrets manager>"
export ACB_DEDUP_KEY="<from secrets manager>"
export SESSION_DEK_WRAP_KEY="<from secrets manager>"
```

If any key is missing, the migration will FAIL with a RuntimeError before modifying any data.
This fail-safe prevents running a partial migration with an unknown HMAC key.

---

## Step 4: Run Migration 022

```bash
alembic upgrade 022
```

Expected output includes (in order):
1. `Running upgrade 021 -> 022`
2. HMAC backfill log messages for user rows
3. TRUNCATE execution for 13 tables
4. Column swap operations across all per-user tables
5. `Done.`

If the migration fails mid-way, Alembic runs everything inside a single transaction by default.
Postgres will roll back ALL DDL changes automatically — the schema returns to revision 021.
The backup is still intact. Diagnose the error and retry.

---

## Step 5: Post-Migration Sanity Checks

Run these immediately after `alembic upgrade 022` exits 0:

```bash
# 1. Alembic reports 022 as current
alembic current
# Expected: 022 (head)

# 2. users count preserved (D-22)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM users;"
# Expected: same count as pre-migration

# 3. transactions TRUNCATEd (D-20)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM transactions;"
# Expected: 0

# 4. wallets TRUNCATEd (D-21)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM wallets;"
# Expected: 0

# 5. HMAC columns populated on existing users
psql $DATABASE_URL -c "SELECT id, email_hmac, near_account_id_hmac FROM users LIMIT 5;"
# Expected: email_hmac = 64-char hex string for users who had email; near_account_id_hmac same

# 6. session_dek_cache table exists and is empty
psql $DATABASE_URL -c "\d session_dek_cache"
# Expected: table definition with session_id, encrypted_dek, expires_at, created_at

# 7. accountant_access has rewrapped_client_dek column
psql $DATABASE_URL -c "\d accountant_access"
# Expected: rewrapped_client_dek BYTEA in column list

# 8. transactions has tx_dedup_hmac column
psql $DATABASE_URL -c "\d transactions" | grep tx_dedup_hmac
# Expected: tx_dedup_hmac | bytea

# 9. auth tables are PRESERVED (D-22)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM passkeys;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM sessions;"
# Expected: same counts as pre-migration

# 10. Public data plane is UNTOUCHED (D-04)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM account_transactions;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM block_heights;"
# Expected: same counts as pre-migration
```

If any check fails: **DO NOT DEPLOY the new code.** Run rollback immediately (Step 8).

---

## Step 6: Deploy Updated Application Code

Deploy in this order to minimize service disruption:

```bash
# 1. Auth-service first (handles new session_dek_cache writes on login)
docker compose -f docker-compose.prod.yml up -d auth-service

# 2. FastAPI API (handles get_session_dek dependency, internal crypto router)
docker compose -f docker-compose.prod.yml up -d api

# 3. Web frontend (Next.js — picks up new onboarding UI for re-entry)
docker compose -f docker-compose.prod.yml up -d web

# 4. Indexer stays running (systemd-managed; public data plane is untouched)
# DO NOT restart or stop the Rust account indexer — it has been running continuously

# 5. Run health check
./scripts/healthcheck.sh
```

---

## Step 7: Smoke Test — Login and DEK Provisioning

1. Open the app in a browser
2. Log in with an existing passkey (user account is preserved — passkeys untouched)
3. Verify:
   - Session is established (no 401 errors)
   - `session_dek_cache` has a row for this session:
     ```sql
     SELECT session_id, expires_at FROM session_dek_cache;
     ```
   - Dashboard shows "no wallets" / empty state (expected — wallets were TRUNCATEd per D-21)
   - Onboarding wizard loads (guiding user to re-enter wallets)
   - ML-KEM columns are populated on the user row:
     ```sql
     SELECT id, mlkem_ek IS NOT NULL, wrapped_dek IS NOT NULL FROM users WHERE id = <your_user_id>;
     ```

---

## Step 8: User Communication

After a successful deploy, notify users:

> "We've completed a major security upgrade (post-quantum encryption at rest). Your account and
> login credentials are preserved. However, your wallet list and indexed transaction data have
> been reset — please log in and re-enter your wallets through the onboarding wizard.
> Your transaction data will be re-indexed automatically after you add your wallets.
> We apologize for the inconvenience. This was a one-time migration required to deliver
> end-to-end encryption of your financial data."

---

## Rollback: When and How

### Trigger Conditions

Roll back if ANY of the following:
- `alembic upgrade 022` fails with an error that is not automatically rolled back
- Post-migration sanity checks show unexpected data loss (e.g., users count is 0)
- auth-service fails to write to `session_dek_cache` after login (HTTP 500 on login)
- FastAPI `get_session_dek` returns 500/401 for all users post-deploy
- Critical regression detected in smoke test

### Rollback Command

```bash
export DATABASE_URL="postgres://neartax:<password>@localhost:5432/neartax"
./scripts/pqe_rollback.sh "$BACKUP_PATH"
```

The rollback script:
1. Stops api, auth-service, indexer containers
2. Runs `alembic downgrade 021` (schema column-shape restore)
3. Runs `pg_restore --clean --if-exists` from the backup dump (data restore)
4. Restarts services

After rollback, verify:
```bash
alembic current         # should show: 021
psql $DATABASE_URL -c "SELECT COUNT(*) FROM transactions;"   # should match pre-migration count
```

**Note:** Data written between the backup and the rollback (any new transactions, sessions, etc.)
will be lost. The rollback restores the DB to the exact snapshot taken by pre_pqe_backup.sh.

---

## Diagnostics: What Can Go Wrong

| Symptom | Likely Cause | Diagnosis Command | Fix |
|---------|-------------|-------------------|-----|
| `RuntimeError: EMAIL_HMAC_KEY not set` | Env var missing | `echo $EMAIL_HMAC_KEY` | Set env var, retry migration (no schema change has occurred) |
| `psycopg2.errors.DependentObjectsStillExist` | FK constraint prevents DROP | Check alembic output for which constraint | Add explicit `op.drop_constraint` before drop_column |
| `alembic upgrade 022` hangs | Lock contention from active connections | `SELECT * FROM pg_stat_activity WHERE wait_event IS NOT NULL;` | Kill idle connections: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle';` |
| users count is 0 post-migration | Unexpected TRUNCATE on users | This should never happen — check migration output | Roll back immediately |
| `session_dek_cache` table not found after upgrade | Migration did not complete | `alembic current` shows 021? | Retry `alembic upgrade 022` |
| Login returns 401 post-deploy | `session_dek_cache` not being written | Check auth-service logs for IPC errors | Verify `INTERNAL_SERVICE_TOKEN` matches between auth-service and FastAPI env |
| Login returns 500 | FastAPI can't find session_dek_cache row | Check FastAPI logs for `get_session_dek` | Verify `SESSION_DEK_WRAP_KEY` is set and matches auth-service env |
| Rust indexer stopped | Restart triggered by deploy | `systemctl status axiom-indexer` | `systemctl start axiom-indexer` — indexer is independent of migration |
| pg_restore fails with auth errors | DATABASE_URL credentials wrong | `psql $DATABASE_URL -c "\l"` | Fix DATABASE_URL and retry rollback |

---

*Runbook version: 1.0*  
*Phase: 16-post-quantum-encryption-at-rest*  
*Plan: 16-04 — Alembic migration 022*  
*Created: 2026-04-12*
