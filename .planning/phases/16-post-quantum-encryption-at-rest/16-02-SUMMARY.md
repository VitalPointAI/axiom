---
phase: 16-post-quantum-encryption-at-rest
plan: 02
subsystem: api
tags: [post-quantum, ml-kem-768, fastapi, internal-router, dek-context, session-dek, hmac, loopback, psycopg2]

# Dependency graph
requires:
  - phase: 16
    plan: 01
    provides: "db/crypto.py — provision_user_keys, unwrap_dek_for_session, wrap_session_dek, unwrap_session_dek, rewrap_dek_for_grantee, set_dek, zero_dek, _zero_bytes"

provides:
  - "POST /internal/crypto/keygen — ML-KEM-768 keygen + DEK provisioning via IPC (D-27)"
  - "POST /internal/crypto/unwrap-session-dek — DEK unsealing + session re-wrap for session_dek_cache"
  - "POST /internal/crypto/rewrap-dek — DEK re-encapsulation for accountant access (D-25)"
  - "get_session_dek: async FastAPI dependency — reads session_dek_cache, injects DEK into ContextVar, zeroes on teardown"
  - "get_effective_user_with_dek: combines get_effective_user + get_session_dek; 501 guard for accountant mode"
  - "19 passing tests + 1 xfail documenting migration 022 dependency"

affects:
  - 16-03-auth-service-key-custody
  - 16-04-migration-022
  - 16-05-orm-wiring
  - 16-06-pipeline-gating

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Async generator dependency for get_session_dek — ensures set_dek() runs in asyncio task context, not threadpool"
    - "run_in_threadpool() wraps psycopg2 pool operations inside async dependency"
    - "hmac.compare_digest for constant-time token comparison (T-16-10)"
    - "try/finally DEK zeroing in endpoint bodies (_zero_bytes) and dependency teardown (zero_dek)"
    - "include_in_schema=False hides /internal/crypto/* from OpenAPI docs"
    - "AXIOM_ENV=production gate for IP loopback enforcement"

key-files:
  created:
    - api/schemas/internal_crypto.py
    - api/routers/internal_crypto.py
    - tests/test_internal_crypto.py
    - tests/test_dependencies_dek.py
  modified:
    - api/main.py
    - api/dependencies.py

decisions:
  - "get_session_dek is an async generator (not sync) so that set_dek() and zero_dek() run in the asyncio task context — ContextVars are task-scoped; a sync threadpool dependency would set the ContextVar in the wrong context"
  - "psycopg2 pool operations inside get_session_dek are wrapped in run_in_threadpool() to avoid blocking the event loop"
  - "get_effective_user_with_dek is a sync dependency (no await) that combines two other dependencies — FastAPI supports mixed sync/async dependency trees"
  - "Loopback guard is bypassed in dev/test (AXIOM_ENV != production) so TestClient tests work without needing to spoof client host"
  - "test_get_session_dek_against_real_db is xfail — migration 022 (plan 16-04) must land before this can pass"

# Metrics
duration: 65min
completed: 2026-04-12
---

# Phase 16 Plan 02: Internal Crypto Router + DEK Dependencies Summary

**Loopback-only FastAPI IPC router (three ML-KEM endpoints) plus async get_session_dek dependency with contextvar injection and teardown zeroing — 19 tests green**

## Performance

- **Duration:** ~65 min
- **Started:** 2026-04-12T21:56:34Z
- **Completed:** 2026-04-12T22:52:00Z
- **Tasks:** 3
- **Files modified:** 6 (api/main.py, api/dependencies.py, api/schemas/internal_crypto.py, api/routers/internal_crypto.py, tests/test_internal_crypto.py, tests/test_dependencies_dek.py)

## Accomplishments

- Created `api/schemas/internal_crypto.py` — Pydantic v2 request/response models for three IPC endpoints with Field validators (hex length, pattern)
- Created `api/routers/internal_crypto.py` — loopback-only internal crypto router:
  - Three endpoints: keygen, unwrap-session-dek, rewrap-dek
  - Token guard: `hmac.compare_digest` on `X-Internal-Service-Token` header (T-16-10)
  - IP guard: rejects non-loopback source IPs when `AXIOM_ENV=production` (T-16-10)
  - `include_in_schema=False` — hidden from OpenAPI docs
  - All crypto primitives imported from `db.crypto` — no duplication
  - Plaintext sealing_key and DEK zeroed in `finally` blocks before response returns (T-16-11)
- Registered `internal_crypto.router` in `api/main.py`
- Extended `api/dependencies.py` with two new dependencies (existing functions preserved untouched):
  - `get_session_dek`: async generator that reads `session_dek_cache`, decrypts DEK via `db.crypto.unwrap_session_dek`, sets in ContextVar via `db.crypto.set_dek`, yields, and calls `db.crypto.zero_dek()` in `finally` (D-15, T-16-15)
  - `get_effective_user_with_dek`: combines `get_effective_user` + `get_session_dek`; raises HTTP 501 for accountant viewing mode (plan 16-06 hook)
- Landed 19 passing tests + 1 xfail:
  - `tests/test_internal_crypto.py` (13 tests): keygen happy path, token guards (missing/wrong/unconfigured), input validation, unwrap-session-dek round-trip, rewrap-dek round-trip (two-user), loopback guard in production/dev
  - `tests/test_dependencies_dek.py` (6 pass + 1 xfail): missing cookie, no row, expired row, happy path with DEK verification, zero-after-request, accountant 501, xfail for real-DB integration (pending plan 16-04)

## Task Commits

1. **Task 1: Internal crypto router + Pydantic schemas** — `1fb30ab`
2. **Task 2: FastAPI get_session_dek dependency + teardown** — `8e59c6e`
3. **Task 3: Integration tests + async dependency fix** — `a52fd78`

## Files Created/Modified

- `api/schemas/internal_crypto.py` — 6 Pydantic v2 models: KeygenRequest/Response, UnwrapSessionDekRequest/Response, RewrapDekRequest/Response (103 lines)
- `api/routers/internal_crypto.py` — Three IPC endpoints with token/loopback guards and DEK zeroing (181 lines)
- `api/main.py` — Added `internal_crypto.router` registration
- `api/dependencies.py` — Added `get_session_dek` (async) + `get_effective_user_with_dek` (sync); existing functions untouched
- `tests/test_internal_crypto.py` — 13 end-to-end router tests (no DB required)
- `tests/test_dependencies_dek.py` — 7 dependency tests (6 pass, 1 xfail for migration 022)

## Internal Crypto IPC Contract (for plan 16-03)

### POST /internal/crypto/keygen
**Headers:** `X-Internal-Service-Token: ${INTERNAL_SERVICE_TOKEN}`
**Body:** `{"sealing_key_hex": "<64 hex chars>"}`
**Response:** `{"mlkem_ek_hex": "<2368>", "mlkem_sealed_dk_hex": "<4856>", "wrapped_dek_hex": "<2296>"}`

### POST /internal/crypto/unwrap-session-dek
**Body:** `{"sealing_key_hex": "...", "mlkem_sealed_dk_hex": "...", "wrapped_dek_hex": "..."}`
**Response:** `{"session_dek_wrapped_hex": "..."}` (store directly in session_dek_cache.encrypted_dek)

### POST /internal/crypto/rewrap-dek
**Body:** `{"session_dek_wrapped_hex": "...", "grantee_mlkem_ek_hex": "..."}`
**Response:** `{"rewrapped_dek_hex": "..."}` (store in accountant_access.rewrapped_client_dek)

## Environment Variables Required at Runtime

| Variable | Description | Format |
|----------|-------------|--------|
| `INTERNAL_SERVICE_TOKEN` | Shared secret for auth-service → FastAPI IPC | Any string (≥32 chars recommended) |
| `SESSION_DEK_WRAP_KEY` | AES-256-GCM key for session_dek_cache row encryption | 64 hex chars (32 bytes) |
| `EMAIL_HMAC_KEY` | HMAC key for email hashing | 64 hex chars |
| `NEAR_ACCOUNT_HMAC_KEY` | HMAC key for NEAR account ID hashing | 64 hex chars |
| `TX_DEDUP_KEY` | HMAC key for transaction dedup | 64 hex chars |
| `ACB_DEDUP_KEY` | HMAC key for ACB snapshot dedup | 64 hex chars |
| `AXIOM_ENV` | Set to `production` to enable IP loopback enforcement | `production` or unset |

All env vars (except `INTERNAL_SERVICE_TOKEN`) are added to `docker-compose.yml` in plan 16-03.

## Decisions Made

- `get_session_dek` is an **async generator**, not sync: ContextVars are asyncio-task-scoped; calling `set_dek()` from a sync threadpool thread would not propagate the value to the endpoint handler running in the asyncio event loop. Async generator ensures `set_dek()` runs in the correct context.
- `run_in_threadpool()` wraps the psycopg2 `pool.getconn()` / `cur.execute()` / `pool.putconn()` calls inside the async generator — keeps the event loop unblocked while preserving ContextVar correctness.
- Loopback guard is **bypass-in-dev** (`AXIOM_ENV != production`): allows TestClient (127.0.0.1) and local development without mock surgery.
- `get_effective_user_with_dek` returns **HTTP 501** (not 404) when `viewing_as_user_id` is set — makes the "not implemented yet" state explicit and traceable, so no route silently operates with the wrong DEK.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] get_session_dek changed from sync to async generator**
- **Found during:** Task 3 (test_get_session_dek_happy_path failed with RuntimeError: No DEK in context)
- **Issue:** The plan template showed a sync generator (`def get_session_dek`). When FastAPI runs a sync generator dependency, it wraps it with `contextmanager_in_threadpool`, executing `__enter__` and `__exit__` in a threadpool thread. The `set_dek()` call sets the ContextVar in the threadpool thread's context, which does NOT propagate to the asyncio task where the endpoint handler runs — ContextVars are asyncio-task-scoped (the exact "Pitfall 1" documented in db/crypto.py and 16-CONTEXT.md).
- **Fix:** Converted to `async def get_session_dek()` (async generator) with `run_in_threadpool()` wrapping the sync pool calls. This ensures `set_dek()` and `zero_dek()` execute in the asyncio task context where the ContextVar propagates correctly to the endpoint.
- **Files modified:** `api/dependencies.py`
- **Commit:** `a52fd78` (included with Task 3)

## Known Stubs

- `get_effective_user_with_dek`: raises HTTP 501 for accountant viewing mode (`viewing_as_user_id` set). This is intentional — plan 16-06 will replace the 501 with the real DEK resolution path via `accountant_access.rewrapped_client_dek`. Not a functional stub; the 501 is the correct behavior until plan 16-06 ships.
- `session_dek_cache` table: referenced by `get_session_dek` but does not exist until migration 022 (plan 16-04). Until then, every call to `get_session_dek` that reaches the DB query will receive no row → HTTP 401. This is fail-closed behavior, not a bug.

## Threat Flags

None — no new network surfaces introduced beyond those documented in the plan's threat model. The `/internal/crypto/*` endpoints are already in the threat register (T-16-10 through T-16-15).

## Handoff to Plan 16-03

Plan 16-03 (auth-service key custody) has a concrete IPC contract:
1. On user registration: call `POST /internal/crypto/keygen` with the sealing_key derived from near-phantom-auth passkey material; store the three blobs in `users.mlkem_ek`, `users.mlkem_sealed_dk`, `users.wrapped_dek`.
2. On login: call `POST /internal/crypto/unwrap-session-dek` with sealing_key + user's DB blobs; store the returned `session_dek_wrapped_hex` in `session_dek_cache.encrypted_dek` with expiry matching the session TTL.
3. On accountant grant: call `POST /internal/crypto/rewrap-dek` with client's session-wrapped DEK and grantee's ek; store `rewrapped_dek_hex` in `accountant_access.rewrapped_client_dek`.

All three calls require `X-Internal-Service-Token: ${INTERNAL_SERVICE_TOKEN}` header over loopback network only (Docker internal network / nginx ACL in plan 16-07).

## Self-Check

---
## Self-Check: PASSED

Files exist:
- FOUND: api/schemas/internal_crypto.py
- FOUND: api/routers/internal_crypto.py
- FOUND: tests/test_internal_crypto.py
- FOUND: tests/test_dependencies_dek.py
- FOUND: api/main.py (modified)
- FOUND: api/dependencies.py (modified)

Commits exist:
- FOUND: 1fb30ab (Task 1)
- FOUND: 8e59c6e (Task 2)
- FOUND: a52fd78 (Task 3)

Tests: 19 passed, 1 xfailed — all green
