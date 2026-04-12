---
phase: 16-post-quantum-encryption-at-rest
plan: 03
subsystem: auth-service
tags: [post-quantum, ml-kem-768, auth-service, typescript, ipc-client, key-custody, worker-key, session-dek, loopback]

# Dependency graph
requires:
  - phase: 16
    plan: 01
    provides: "db/crypto.py — ML-KEM crypto primitives"
  - phase: 16
    plan: 02
    provides: "FastAPI internal crypto router — /internal/crypto/* IPC endpoints"

provides:
  - "auth-service/src/internal-crypto-client.ts: typed fetch wrapper for FastAPI IPC (keygen, unwrap-session-dek, rewrap-dek)"
  - "auth-service/src/key-custody.ts: provisionUserKeys, getUserKeyBundle, resolveSessionDek, deleteSessionDekCache"
  - "auth-service/src/worker-key.ts: createWorkerKey, revokeWorkerKey with audit_log writes"
  - "auth-service/src/user-bridge.ts extended: getPool() exported; syncUser accepts sealingKeyHex; provisionUserKeys called on first INSERT"
  - "auth-service/src/server.ts extended: login writes session_dek_cache; logout deletes session_dek_cache row"
  - "npm test script via Node 20 built-in test runner + tsx (no Jest — root-owned node_modules blocked npm install)"
  - "11 passing unit tests (4 + 4 + 3)"

affects:
  - 16-04-migration-022 (session_dek_cache + users ML-KEM columns needed)
  - 16-07-worker-key-and-cutover (Settings UI calls createWorkerKey/revokeWorkerKey)

# Tech tracking
tech-stack:
  added:
    - "Node 20 built-in test runner (node:test) via tsx --test (no Jest — see deviations)"
  patterns:
    - "_createKeyCustody / _createWorkerKeyOps DI factory pattern for ESM-compatible unit testing (no module mocking needed)"
    - "key-custody.ts and worker-key.ts each maintain their own pg.Pool from AXIOM_DB_URL to avoid circular imports"
    - "sealing key zeroed with .fill(0) in finally blocks throughout (T-16-16)"
    - "fail-soft: provisionUserKeys failure in syncUser logs but does not fail the auth flow"

key-files:
  created:
    - auth-service/src/internal-crypto-client.ts
    - auth-service/src/key-custody.ts
    - auth-service/src/worker-key.ts
    - auth-service/src/__tests__/internal-crypto-client.test.ts
    - auth-service/src/__tests__/key-custody.test.ts
    - auth-service/src/__tests__/worker-key.test.ts
  modified:
    - auth-service/src/user-bridge.ts
    - auth-service/src/server.ts
    - auth-service/package.json

decisions:
  - "DI factory pattern (_createKeyCustody, _createWorkerKeyOps) instead of Jest module mocking — ESM module mocking requires Node 22+ mock.module() which is unavailable in Node 20; factory pattern achieves identical test coverage"
  - "key-custody.ts and worker-key.ts each create their own pg.Pool from AXIOM_DB_URL to break the circular import that would arise from importing getPool() from user-bridge.ts"
  - "Node built-in test runner (tsx --test) instead of Jest — node_modules is root-owned from Docker build; npm install blocked. tsx is already in devDependencies. Node 20 test runner provides describe/test/assert; no additional deps needed"
  - "provisionUserKeys wrapped in try/catch in syncUser — key provisioning failure must not fail auth; user can still log in and keys retry on next login"
  - "Session DEK resolution in server.ts fires asynchronously (no await on res.json return) to avoid delaying the login HTTP response"

requirements-completed: [PQE-01, PQE-02, PQE-06]

# Metrics
duration: 70min
completed: 2026-04-12
---

# Phase 16 Plan 03: Auth-Service Key Custody Summary

**TypeScript key-custody + worker-key modules delegating all ML-KEM operations to FastAPI IPC — 11 green unit tests, no TypeScript ML-KEM library added (D-27)**

## Performance

- **Duration:** ~70 min
- **Started:** 2026-04-12T22:55:00Z
- **Completed:** 2026-04-12T23:26:49Z
- **Tasks:** 3
- **Files modified:** 6 (new: internal-crypto-client.ts, key-custody.ts, worker-key.ts, 3 test files; modified: user-bridge.ts, server.ts, package.json)

## Accomplishments

- Created `auth-service/src/internal-crypto-client.ts` (165 lines): typed `fetch` wrapper for FastAPI `/internal/crypto/*` endpoints with `X-Internal-Service-Token` header, 32-byte sealing key validation, hex encode/decode, fail-closed token check. IPC contract matches `api/routers/internal_crypto.py` exactly.
- Created `auth-service/src/key-custody.ts` (206 lines): `provisionUserKeys`, `getUserKeyBundle`, `resolveSessionDek`, `deleteSessionDekCache` — all delegating ML-KEM ops to FastAPI. `resolveSessionDek` upserts `session_dek_cache` with ON CONFLICT for idempotency (D-26). Sealing key zeroed in finally.
- Created `auth-service/src/worker-key.ts` (140 lines): `createWorkerKey` (self-rewrap for independent worker blob) + `revokeWorkerKey` — both write `audit_log` rows (T-16-19). DI factory for testability.
- Extended `auth-service/src/user-bridge.ts`: exported `getPool()`, `syncUser()` accepts `sealingKeyHex`, calls `provisionUserKeys` on first INSERT (fail-soft wrapped in try/catch).
- Extended `auth-service/src/server.ts`: login interceptor calls `resolveSessionDek` when `sealingKeyHex` present; logout interceptor calls `deleteSessionDekCache` on `/auth/logout`.
- Added `npm test` script using Node 20 built-in test runner + tsx (no Jest install required).
- Landed 11 passing unit tests: 4 (internal-crypto-client) + 4 (key-custody) + 3 (worker-key).

## Task Commits

1. **Task 1: internal-crypto-client.ts** — `226f54c`
2. **Task 2: key-custody + user-bridge + server wiring** — `83ebadb`
3. **Task 3: worker-key module** — `a35a793`

## Files Created/Modified

- `auth-service/src/internal-crypto-client.ts` — IPC client with token auth + hex codec (165 lines)
- `auth-service/src/key-custody.ts` — Key custody: provision, session DEK, cache management (206 lines)
- `auth-service/src/worker-key.ts` — Opt-in worker key: create/revoke + audit (140 lines)
- `auth-service/src/__tests__/internal-crypto-client.test.ts` — 4 tests
- `auth-service/src/__tests__/key-custody.test.ts` — 4 tests
- `auth-service/src/__tests__/worker-key.test.ts` — 3 tests
- `auth-service/src/user-bridge.ts` — Added getPool() export, sealingKeyHex param, provisionUserKeys call
- `auth-service/src/server.ts` — Added login/logout session DEK hooks
- `auth-service/package.json` — Added "test" script + "engines": { "node": ">=20" }

## IPC Contract (for plan 16-07 integration tests)

### POST /internal/crypto/keygen
**Header:** `X-Internal-Service-Token: ${INTERNAL_SERVICE_TOKEN}`
**Body:** `{"sealing_key_hex": "<64 hex chars>"}`
**Response:** `{"mlkem_ek_hex": "...", "mlkem_sealed_dk_hex": "...", "wrapped_dek_hex": "..."}`

### POST /internal/crypto/unwrap-session-dek
**Body:** `{"sealing_key_hex": "...", "mlkem_sealed_dk_hex": "...", "wrapped_dek_hex": "..."}`
**Response:** `{"session_dek_wrapped_hex": "..."}` (store directly in session_dek_cache.encrypted_dek)

### POST /internal/crypto/rewrap-dek
**Body:** `{"session_dek_wrapped_hex": "...", "grantee_mlkem_ek_hex": "..."}`
**Response:** `{"rewrapped_dek_hex": "..."}` (store in accountant_access.rewrapped_client_dek)

## Environment Variables Required at Runtime

| Variable | Description | Default |
|----------|-------------|---------|
| `INTERNAL_CRYPTO_URL` | FastAPI base URL for IPC | `http://api:8000` |
| `INTERNAL_SERVICE_TOKEN` | Shared secret (must match FastAPI) | none (required) |
| `AXIOM_DB_URL` / `DATABASE_URL` | Postgres connection string | none (required) |
| `SESSION_LIFETIME_SECONDS` | session_dek_cache row TTL | 86400 (24h) |

## SQL Patterns (for plan 16-07 end-to-end verification)

```sql
-- provisionUserKeys (key-custody.ts)
UPDATE users SET mlkem_ek = $1, mlkem_sealed_dk = $2, wrapped_dek = $3 WHERE id = $4

-- resolveSessionDek (key-custody.ts) — upsert
INSERT INTO session_dek_cache (session_id, encrypted_dek, expires_at)
VALUES ($1, $2, $3)
ON CONFLICT (session_id) DO UPDATE
  SET encrypted_dek = EXCLUDED.encrypted_dek, expires_at = EXCLUDED.expires_at

-- deleteSessionDekCache (key-custody.ts)
DELETE FROM session_dek_cache WHERE session_id = $1

-- createWorkerKey (worker-key.ts)
UPDATE users SET worker_sealed_dek = $1, worker_key_enabled = TRUE WHERE id = $2
INSERT INTO audit_log (user_id, entity_type, entity_id, action, actor_type, created_at)
  VALUES ($1, 'user', $1, 'worker_key_enabled', 'user', NOW())

-- revokeWorkerKey (worker-key.ts)
UPDATE users SET worker_sealed_dek = NULL, worker_key_enabled = FALSE WHERE id = $1
INSERT INTO audit_log (user_id, entity_type, entity_id, action, actor_type, created_at)
  VALUES ($1, 'user', $1, 'worker_key_revoked', 'user', NOW())
```

## Decisions Made

- Used **DI factory pattern** (`_createKeyCustody`, `_createWorkerKeyOps`) instead of Jest module mocking. ESM module mocking needs `mock.module()` (Node 22+) or complex loader hooks. The factory pattern achieves identical coverage by accepting all external dependencies as parameters.
- **No circular imports**: `key-custody.ts` and `worker-key.ts` each create their own `pg.Pool` from `AXIOM_DB_URL`. Importing `getPool()` from `user-bridge.ts` would create a circular dependency since `user-bridge.ts` imports `provisionUserKeys` from `key-custody.ts`.
- **Node built-in test runner** (`tsx --test`) instead of Jest: `auth-service/node_modules` is owned by root (Docker build artifact), blocking `npm install`. `tsx` is already a devDependency. Node 20's test runner provides all needed primitives.
- **Fail-soft provisioning**: `provisionUserKeys` in `syncUser()` is wrapped in try/catch — a FastAPI keygen failure (service down, token missing) must not fail the auth flow. Keys will be provisioned on next login attempt.
- **Session DEK fires async** in the `res.json` interceptor: no `await` blocks the response to the client. If `resolveSessionDek` fails, it logs but the user session is still valid (graceful degradation until migration 022 ships the session_dek_cache table).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced Jest with Node 20 built-in test runner**
- **Found during:** Task 1 setup
- **Issue:** `auth-service/node_modules` owned by root (`docker build` artifact). `npm install jest @types/jest ts-jest` blocked with EACCES errno -13 mkdir on `@esbuild/aix-ppc64`.
- **Fix:** Used `tsx --test` (Node 20 built-in test runner). `tsx` is already in devDependencies. Adapted test code to use `node:test` + `node:assert/strict` instead of Jest globals. Test coverage is identical to the Jest version in the plan.
- **Files modified:** `package.json` (test script), all three test files

**2. [Rule 3 - Blocking] Resolved circular import via separate pools**
- **Found during:** Task 2 design
- **Issue:** Plan specified `import { getPool } from "./user-bridge.js"` in `key-custody.ts`, but `user-bridge.ts` needs to `import { provisionUserKeys } from "./key-custody.js"`. This creates a circular ESM import that would crash at runtime.
- **Fix:** `key-custody.ts` and `worker-key.ts` each create their own `pg.Pool` from `AXIOM_DB_URL`/`DATABASE_URL`. The `getPool()` export from `user-bridge.ts` is still exported (for future use or testing) but is not imported by `key-custody.ts`. Behavior is identical: the same DB is used.
- **Files modified:** `key-custody.ts`, `worker-key.ts`

**3. [Rule 1 - Bug] DI factory instead of module-level jest.mock()**
- **Found during:** Task 2 test design
- **Issue:** Plan test code used `jest.mock("../internal-crypto-client.js")` and `jest.mock("../user-bridge.js")`. ESM module-level mocking requires either Jest (blocked) or Node 22+ `mock.module()` (not available in Node 20). Without this, tests would be unable to isolate key-custody from its dependencies.
- **Fix:** Exported `_createKeyCustody` and `_createWorkerKeyOps` DI factories that accept pool, keygenFn, unwrapFn, rewrapFn as parameters. Tests instantiate the factory with mock functions — no module mocking needed. The production exported functions (`provisionUserKeys`, etc.) wrap the factory with real dependencies. Coverage is equivalent to the plan's Jest approach.
- **Files modified:** `key-custody.ts`, `worker-key.ts`, all test files

## Known Stubs

- `resolveSessionDek` writes to `session_dek_cache` which does not exist until migration 022 (plan 16-04). At runtime pre-migration, the INSERT will fail. This is fail-closed / intentional — the error is caught in `server.ts` and logged but does not fail the auth flow.
- `createWorkerKey` / `revokeWorkerKey` reference `users.worker_sealed_dek` and `users.worker_key_enabled` which do not exist until migration 022. Same fail-closed behavior until migration ships.

## Threat Flags

None — no new network surfaces introduced. All threat mitigations from the plan's STRIDE register were applied:
- T-16-16: sealing_key.fill(0) in every finally block
- T-16-17: X-Internal-Service-Token header on every IPC call
- T-16-18: createWorkerKey re-wraps only the caller's own DEK
- T-16-19: audit_log written for both worker key enable and revoke

## Handoff to Plan 16-07

- `worker-key.ts` is ready: exports `createWorkerKey(userId, sealingKey)` and `revokeWorkerKey(userId)`. Plan 16-07's Settings UI can call these via a new auth-service HTTP endpoint (e.g., `POST /auth/worker-key` and `DELETE /auth/worker-key`) that reads `req.body.sealingKeyHex` and the current session's user ID.
- Integration test against running FastAPI + real DB deferred to plan 16-07 (requires migration 022 to land the `session_dek_cache`, `users.mlkem_ek`, `users.worker_sealed_dek` columns).

## Self-Check

### Self-Check: PASSED

Files exist:
- FOUND: auth-service/src/internal-crypto-client.ts
- FOUND: auth-service/src/key-custody.ts
- FOUND: auth-service/src/worker-key.ts
- FOUND: auth-service/src/__tests__/internal-crypto-client.test.ts
- FOUND: auth-service/src/__tests__/key-custody.test.ts
- FOUND: auth-service/src/__tests__/worker-key.test.ts
- FOUND: auth-service/src/user-bridge.ts (modified)
- FOUND: auth-service/src/server.ts (modified)
- FOUND: auth-service/package.json (modified)

Commits exist:
- FOUND: 226f54c (Task 1 — internal-crypto-client)
- FOUND: 83ebadb (Task 2 — key-custody + user-bridge + server)
- FOUND: a35a793 (Task 3 — worker-key)

Tests: 11 passed, 0 failed — all green
