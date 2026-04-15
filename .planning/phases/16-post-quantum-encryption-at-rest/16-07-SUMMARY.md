---
phase: 16-post-quantum-encryption-at-rest
plan: "07"
subsystem: pqe-cutover
tags: [pqe, encryption, worker-key, onboarding, nginx, integration-test, deployment]
dependency_graph:
  requires:
    - phase: 16-01
      provides: "db/crypto.py seal_worker_dek / unseal_worker_dek (corrected in this plan)"
    - phase: 16-03
      provides: "auth-service key-custody, worker-key.ts (corrected in this plan)"
    - phase: 16-05
      provides: "ORM EncryptedBytes columns, dedup helpers"
    - phase: 16-06
      provides: "Pipeline DEK gating, accountant rewrap, session_client_dek_cache"
  provides:
    - "AES-256-GCM worker key sealing (WORKER_KEY_WRAP_KEY) — replaces ML-KEM worker path"
    - "POST/DELETE /internal/crypto/seal-worker-dek + unseal-worker-dek endpoints"
    - "auth-service worker-key.ts rewritten with sessionId-based workflow"
    - "auth-service worker-process.ts: 60s loop, sequential dispatch, graceful shutdown"
    - "auth-service logout deletes session_client_dek_cache (T-16-37 closure)"
    - "GET /api/users/me with mlkem_ek_provisioned for returning-user detection (D-21)"
    - "POST/DELETE/GET /api/settings/worker-key — Background Processing API"
    - "POST /api/internal/run-pipeline — internal pipeline dispatch for worker process"
    - "web/app/settings/background-processing/page.tsx — D-19 UI with full explanatory copy"
    - "web/app/onboarding/returning/page.tsx — returning-from-pre-encryption path (D-21)"
    - "nginx ACL for /internal/crypto/* in nginx/default.conf + deploy/nginx/internal-crypto.conf"
    - "docker-compose.prod.yml api+indexer services with all Phase 16 env vars"
    - "tests/integration/test_pqe_end_to_end.py — full pipeline happy path (gated on RUN_MIGRATION_TESTS=1)"
  affects:
    - "Production cutover (D-23) — human-verify checkpoint pending"
    - "auth-service deploy — worker-process.ts requires WORKER_PROCESS_ENABLED=1 to activate"
tech-stack:
  added: []
  patterns:
    - "Worker key uses AES-256-GCM with WORKER_KEY_WRAP_KEY (NOT ML-KEM) — worker can unseal without user session"
    - "auth-service worker-process.ts: sequential user loop (T-16-44 DoS mitigation)"
    - "sessionId passed to createWorkerKey instead of sealingKey — cleaner IPC boundary"
    - "session_client_dek_cache deleted on logout via deleteSessionClientDekCache (T-16-37)"
key-files:
  created:
    - db/crypto.py (seal_worker_dek / unseal_worker_dek corrected)
    - api/schemas/internal_crypto.py (SealWorkerDek / UnsealWorkerDek schemas added)
    - api/routers/settings.py
    - api/routers/internal_pipeline.py
    - auth-service/src/worker-process.ts
    - deploy/nginx/internal-crypto.conf
    - web/app/settings/layout.tsx
    - web/app/settings/background-processing/page.tsx
    - web/app/onboarding/returning/page.tsx
    - tests/integration/__init__.py
    - tests/integration/conftest.py
    - tests/integration/test_pqe_end_to_end.py
    - tests/test_worker_key_api.py
    - tests/test_onboarding_returning.py
  modified:
    - api/routers/internal_crypto.py (seal/unseal-worker-dek endpoints added)
    - api/routers/__init__.py (settings_router, internal_pipeline_router registered)
    - api/main.py (settings_router, internal_pipeline_router mounted)
    - auth-service/src/server.ts (worker-key routes, logout T-16-37 fix, imports)
    - auth-service/src/worker-key.ts (rewritten: sessionId workflow, AES-GCM sealing)
    - auth-service/src/internal-crypto-client.ts (internalSealWorkerDek / internalUnsealWorkerDek)
    - auth-service/src/key-custody.ts (deleteSessionClientDekCache added)
    - web/app/onboarding/page.tsx (returning-user detection + redirect)
    - nginx/default.conf (/internal/crypto/ ACL location block)
    - docker-compose.prod.yml (Phase 16 env vars for api + indexer services)
    - tests/test_crypto.py (worker roundtrip uses worker_wrap_key; 3 new tests)
key-decisions:
  - "Worker key uses AES-256-GCM with WORKER_KEY_WRAP_KEY (plan 16-07 architectural correction to plan 16-03's ML-KEM approach)"
  - "createWorkerKey takes sessionId not sealingKey — auth-service reads session_dek_cache internally"
  - "GET /api/users/me added to settings router (no separate users router needed)"
  - "nginx ACL added directly to nginx/default.conf in addition to deploy/nginx/internal-crypto.conf reference file"
  - "docker-compose.prod.yml api+indexer services now forward all Phase 16 env vars"
requirements-completed: [PQE-05, PQE-06, PQE-07]
duration: 651min
completed: "2026-04-15"
---

# Phase 16 Plan 07: Worker Key + Cutover Summary

**Corrected worker key from ML-KEM to AES-256-GCM (WORKER_KEY_WRAP_KEY), delivered Background Processing settings UI, returning-user onboarding path, nginx ACL, auth-service logout cleanup (T-16-37), and a full E2E integration test — paused at production cutover checkpoint (D-23).**

## Performance

- **Duration:** ~11 hours (batch across session boundary)
- **Started:** 2026-04-14T00:00:00Z
- **Completed:** 2026-04-15 (checkpoint, not yet production-cutover)
- **Tasks:** 3 of 4 complete (Task 4 = human-verify checkpoint)
- **Files modified:** 20+

## Accomplishments

- Corrected the architectural error in plan 16-03: `seal_worker_dek` / `unseal_worker_dek` now use AES-256-GCM with `WORKER_KEY_WRAP_KEY` (server env var) rather than ML-KEM, so the worker process can decrypt without any active user session
- Delivered `/api/settings/worker-key` endpoints (POST/DELETE/GET) with auth-service forwarding and full test coverage; rewrote `auth-service/src/worker-key.ts` to take `sessionId` and read `session_dek_cache` directly
- Created `auth-service/src/worker-process.ts`: 60-second sequential loop, graceful SIGTERM/SIGINT shutdown, per-user DEK zeroing after each pipeline dispatch
- Closed T-16-37: auth-service logout now also deletes `session_client_dek_cache` rows via `deleteSessionClientDekCache`
- Settings UI at `/settings/background-processing` with full D-19 copy ("less private, more convenient"), toggle, status indicator, revoke button; returning-user onboarding page with expandable explanation and wallet re-entry CTA
- nginx ACL added to `nginx/default.conf` restricting `/internal/crypto/*` to loopback + Docker bridge (T-16-10 defense in depth)
- `docker-compose.prod.yml` api and indexer services now forward all Phase 16 env vars (EMAIL_HMAC_KEY, NEAR_ACCOUNT_HMAC_KEY, TX_DEDUP_KEY, ACB_DEDUP_KEY, SESSION_DEK_WRAP_KEY, WORKER_KEY_WRAP_KEY, INTERNAL_SERVICE_TOKEN, AXIOM_ENV)
- Full E2E integration test at `tests/integration/test_pqe_end_to_end.py` (gated on `RUN_MIGRATION_TESTS=1`): provision → login → wallet CRUD (ciphertext check) → logout 401 → worker key → accountant grant

## Task Commits

1. **Task 1: Worker key API + worker process + plan 16-03 correction** — `007b030` (feat)
2. **Task 2: Settings UI + returning-user onboarding + nginx ACL** — `fc7757c` (feat)
3. **Task 3: E2E integration test + docker-compose env vars** — `33b72a8` (feat)
4. **Task 4: Production cutover (D-23)** — PAUSED at checkpoint (human-verify)

## Files Created/Modified

### Python backend

- `db/crypto.py` — `seal_worker_dek(dek, worker_wrap_key)` and `unseal_worker_dek(sealed, worker_wrap_key)` corrected to AES-256-GCM
- `api/schemas/internal_crypto.py` — `SealWorkerDekRequest/Response`, `UnsealWorkerDekRequest/Response` schemas
- `api/routers/internal_crypto.py` — `/seal-worker-dek` and `/unseal-worker-dek` endpoints
- `api/routers/settings.py` — `GET /api/users/me`, `POST/DELETE/GET /api/settings/worker-key`
- `api/routers/internal_pipeline.py` — `POST /api/internal/run-pipeline` (token-guarded, not in OpenAPI)
- `api/routers/__init__.py` — settings_router, internal_pipeline_router
- `api/main.py` — mounts settings_router, internal_pipeline_router

### Auth service (TypeScript)

- `auth-service/src/worker-key.ts` — rewritten: takes `sessionId`, calls `internalSealWorkerDek`, audit log
- `auth-service/src/worker-process.ts` — 60s loop, sequential dispatch, SIGTERM shutdown, DEK zeroing
- `auth-service/src/internal-crypto-client.ts` — `internalSealWorkerDek`, `internalUnsealWorkerDek`
- `auth-service/src/key-custody.ts` — `deleteSessionClientDekCache` added
- `auth-service/src/server.ts` — worker-key routes, T-16-37 logout fix

### Frontend (Next.js)

- `web/app/settings/layout.tsx` — auth-protected settings layout
- `web/app/settings/background-processing/page.tsx` — D-19 UI (120+ lines)
- `web/app/onboarding/returning/page.tsx` — returning-user page (D-21)
- `web/app/onboarding/page.tsx` — detection logic for returning users + redirect

### Infrastructure

- `deploy/nginx/internal-crypto.conf` — canonical ACL reference config
- `nginx/default.conf` — /internal/crypto/ location block with allow/deny
- `docker-compose.prod.yml` — Phase 16 env vars for api + indexer

### Tests

- `tests/test_crypto.py` — worker roundtrip uses `worker_wrap_key`; 3 new tests
- `tests/test_worker_key_api.py` — 6 tests for settings endpoints
- `tests/test_onboarding_returning.py` — 6 tests for /api/users/me
- `tests/integration/test_pqe_end_to_end.py` — full E2E happy path (gated)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Worker key used ML-KEM instead of AES-256-GCM**
- **Found during:** Task 1 reading plan interfaces block
- **Issue:** `db/crypto.py` `seal_worker_dek` / `unseal_worker_dek` used ML-KEM (same as accountant rewrap), but D-17 and the plan interfaces block require AES-256-GCM with `WORKER_KEY_WRAP_KEY` so the worker process can unseal without any user session
- **Fix:** Replaced ML-KEM encaps/decaps with `_aes_encrypt(worker_wrap_key, dek)` / `_aes_decrypt(worker_wrap_key, sealed)`; updated test accordingly
- **Files modified:** db/crypto.py, tests/test_crypto.py
- **Commit:** 007b030

**2. [Rule 2 - Missing] `createWorkerKey` took `sealingKey` but plan requires `sessionId`**
- **Found during:** Task 1 (plan step 4 specifies sessionId, auth-service reads session_dek_cache internally)
- **Issue:** The plan interfaces block explicitly describes auth-service reading `session_dek_cache` by `session_id` in `createWorkerKey` — cleaner IPC than passing sealingKey
- **Fix:** Rewrote `worker-key.ts` to take `sessionId`, look up `encrypted_dek` from `session_dek_cache`, then call `internalSealWorkerDek`
- **Files modified:** auth-service/src/worker-key.ts
- **Commit:** 007b030

**3. [Rule 2 - Missing] `deleteSessionClientDekCache` not in key-custody.ts**
- **Found during:** Task 1 (T-16-37 handoff from plan 16-06)
- **Issue:** Plan 16-06 handoff note said auth-service logout must `DELETE FROM session_client_dek_cache WHERE session_id = $1` — function didn't exist in key-custody.ts yet
- **Fix:** Added `deleteSessionClientDekCache(sessionId)` to key-custody.ts; imported and called it in server.ts logout handler
- **Files modified:** auth-service/src/key-custody.ts, auth-service/src/server.ts
- **Commit:** 007b030

**4. [Rule 2 - Missing] docker-compose.prod.yml api/indexer missing Phase 16 env vars**
- **Found during:** Task 3 (per guardrails: "waves 5-6 left this undone for migrate only")
- **Issue:** The `api` service had no EMAIL_HMAC_KEY, SESSION_DEK_WRAP_KEY, INTERNAL_SERVICE_TOKEN, WORKER_KEY_WRAP_KEY, AXIOM_ENV, AUTH_SERVICE_URL; `indexer` had no HMAC keys
- **Fix:** Added all Phase 16 env vars to api service; added HMAC keys to indexer service
- **Files modified:** docker-compose.prod.yml
- **Commit:** 33b72a8

**5. [Rule 2 - Missing] GET /api/users/me endpoint didn't exist**
- **Found during:** Task 2 (onboarding/page.tsx detection logic needs this)
- **Issue:** The plan spec says onboarding detection calls `/api/users/me` which returns `mlkem_ek_provisioned`, `wallet_count`, `onboarding_completed_at` — no such endpoint existed
- **Fix:** Added `GET /api/users/me` to settings.py router using `get_effective_user` (no DEK required)
- **Files modified:** api/routers/settings.py
- **Commit:** fc7757c

## Known Stubs

None — all functionality from the plan is implemented. `POST /api/internal/run-pipeline` is a real implementation (not a stub) that queues indexing jobs for all of a user's wallets.

The human-verify checkpoint (Task 4) is the final gate before production cutover.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: new-internal-endpoint | api/routers/internal_pipeline.py | POST /api/internal/run-pipeline — new internal endpoint; guarded by X-Internal-Service-Token and include_in_schema=False but not by nginx ACL (only reachable from worker-process container on Docker network) |
| threat_flag: new-auth-routes | auth-service/src/server.ts | /auth/worker-key/enable and DELETE /auth/worker-key — new routes accessible through nginx /auth/ proxy; gated on session cookie only |

Both are documented in the plan's threat model (T-16-39, T-16-40, T-16-41, T-16-44).

## Self-Check: PASSED

Files confirmed present:
- `db/crypto.py` — FOUND (seal_worker_dek uses AES-256-GCM)
- `api/routers/settings.py` — FOUND
- `api/routers/internal_pipeline.py` — FOUND
- `auth-service/src/worker-process.ts` — FOUND
- `auth-service/src/worker-key.ts` — FOUND (rewritten)
- `deploy/nginx/internal-crypto.conf` — FOUND
- `web/app/settings/background-processing/page.tsx` — FOUND (124 lines)
- `web/app/onboarding/returning/page.tsx` — FOUND (88 lines)
- `tests/integration/test_pqe_end_to_end.py` — FOUND (collects 1 test)
- `tests/test_worker_key_api.py` — FOUND (6 tests, all pass)
- `tests/test_onboarding_returning.py` — FOUND (6 tests, all pass)

Commits confirmed present: 007b030, fc7757c, 33b72a8

Test suite: 658 passed, 10 skipped, 1 xfailed (no regressions from plans 16-01 through 16-06)
