---
phase: 16-post-quantum-encryption-at-rest
plan: 01
subsystem: database
tags: [post-quantum, ml-kem-768, aes-256-gcm, hmac, sqlalchemy, typedecorator, contextvars, kyber-py, cryptography]

# Dependency graph
requires:
  - phase: 07-web-ui
    provides: FastAPI dependency injection pattern for per-request context
  - phase: 11-robustness
    provides: SQLAlchemy ORM patterns used in db/models/

provides:
  - "db/crypto.py: single canonical home for all Axiom crypto primitives"
  - "EncryptedBytes TypeDecorator for transparent per-column AES-256-GCM encryption"
  - "ML-KEM-768 envelope ops: provision_user_keys, unwrap_dek_for_session, rewrap_dek_for_grantee, seal_worker_dek"
  - "ContextVar-based request-scoped DEK context: set_dek, get_dek, zero_dek"
  - "HMAC surrogates: hash_email, hash_near_account, compute_tx_dedup_hmac, compute_acb_dedup_hmac"
  - "Session DEK wrap/unwrap for session_dek_cache table (D-26)"
  - "24-test Wave 0 suite: test_crypto.py (13) + test_type_decorator.py (11)"
  - "Cross-test DEK zeroization autouse fixture in conftest.py"

affects:
  - 16-02-internal-crypto-router
  - 16-03-auth-service-key-custody
  - 16-04-migration-022
  - 16-05-orm-wiring
  - 16-06-pipeline-gating
  - 16-07-worker-key-and-cutover

# Tech tracking
tech-stack:
  added:
    - "kyber-py==1.2.0 (pure-Python ML-KEM-768 FIPS 203, Docker-safe)"
    - "cryptography (AESGCM, already in requirements.txt)"
  patterns:
    - "ContextVar DEK context — NOT threading.local (asyncio-safe, no cross-request leakage)"
    - "AES-256-GCM with os.urandom(12) nonces for every encrypt call"
    - "ML-KEM-768 envelope: kem_ct (1088) || nonce (12) || AES-GCM(shared_secret, dek)"
    - "Sealed dk: nonce (12) || AES-GCM(sealing_key, dk)"
    - "EncryptedBytes tag-byte prefix (0x01-0x04) for type round-trip fidelity"
    - "ctypes.memset zeroization + atexit.register(zero_dek) for PQE-08"

key-files:
  created:
    - db/crypto.py
    - tests/test_crypto.py
    - tests/test_type_decorator.py
  modified:
    - requirements.txt
    - tests/conftest.py

key-decisions:
  - "ContextVar (not threading.local) for DEK — asyncio-safe per plan spec and research Pitfall 1"
  - "os.urandom(12) random nonces per encryption (T-16-08) — not counter-based, no nonce reuse risk"
  - "Type-tag byte prepended to plaintext before encryption for lossless Python type round-trips"
  - "kyber-py==1.2.0 pinned exactly — pure Python, no compiler in Docker, FIPS 203 compliant"
  - "atexit.register(zero_dek) + ctypes.memset for DEK zeroization on process exit (PQE-08)"
  - "Decimal recovery via str representation — preserves exact decimal values through numeric tag"

patterns-established:
  - "Pattern: All crypto ops import from db.crypto — single auditable module"
  - "Pattern: get_dek() raises RuntimeError('No DEK in context') when unset — fail-closed by design"
  - "Pattern: zero_dek() is idempotent — safe to call even when no DEK is set"
  - "Pattern: test_crypto.py + test_type_decorator.py run after every task commit (Wave 0 contract)"

requirements-completed: [PQE-01, PQE-02, PQE-03, PQE-08]

# Metrics
duration: 115min
completed: 2026-04-12
---

# Phase 16 Plan 01: Post-Quantum Encryption Foundation Summary

**AES-256-GCM + ML-KEM-768 crypto foundation in db/crypto.py with EncryptedBytes TypeDecorator, ContextVar DEK context, ctypes zeroization, and 24 green unit tests**

## Performance

- **Duration:** ~115 min
- **Started:** 2026-04-12T19:56:47Z
- **Completed:** 2026-04-12T21:51:36Z
- **Tasks:** 3
- **Files modified:** 4 (requirements.txt, db/crypto.py, tests/test_crypto.py, tests/test_type_decorator.py, tests/conftest.py)

## Accomplishments

- Created `db/crypto.py` (553 lines) as the single canonical home for all Phase 16 crypto primitives: ML-KEM-768 envelope ops, AES-256-GCM helpers, HMAC surrogates for email/NEAR-account/tx-dedup/ACB-dedup, EncryptedBytes TypeDecorator, ContextVar DEK context with ctypes zeroization, and session DEK wrap/unwrap
- Pinned `kyber-py==1.2.0` in requirements.txt (pure-Python, Docker-safe, FIPS 203 compliant); verified keygen produces correct key lengths (ek=1184, dk=2400)
- Landed 24 green pytest unit tests (13 in test_crypto.py + 11 in test_type_decorator.py) covering ML-KEM round-trip, tamper detection, wrong-key rejection, DEK zeroization, context isolation, all HMAC surrogates, accountant rewrap, worker key round-trip, TypeDecorator type fidelity, nonce uniqueness, and fail-closed behavior

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin kyber-py 1.2.0 and add crypto module skeleton** - `4d58647` (feat)
2. **Task 2: Wave 0 test scaffolds — test_crypto.py** - `33489f3` (test)
3. **Task 3: TypeDecorator round-trip tests** - `1939e6d` (test)

## Files Created/Modified

- `db/crypto.py` - Full crypto primitives: EncryptedBytes, DEK context, ML-KEM-768 ops, HMAC surrogates (553 lines)
- `requirements.txt` - Added `kyber-py==1.2.0` in Post-quantum cryptography section
- `tests/test_crypto.py` - 13 unit tests for ML-KEM keygen, KAT, envelope round-trip, tamper, wrong-key, zeroization, context isolation, HMAC surrogates, rewrap, worker key
- `tests/test_type_decorator.py` - 11 unit tests for EncryptedBytes TypeDecorator round-trips (str/bytes/int/Decimal/dict), None passthrough, missing DEK fail-closed, ciphertext length, tamper detection, nonce uniqueness
- `tests/conftest.py` - Added `_zero_dek_between_tests` autouse fixture (placed above all existing fixtures)

## Decisions Made

- Used `ContextVar` (not `threading.local`) for DEK — asyncio-safe, no cross-request leakage in FastAPI
- Random `os.urandom(12)` nonces for every AES-256-GCM encrypt call — satisfies T-16-08; nonce uniqueness test verifies 100/100 distinct ciphertexts
- Type-tag byte (`0x01`-`0x04`) prepended to plaintext before encryption enables lossless Python type round-trips (str/bytes/numeric/JSON) through the TypeDecorator
- `kyber-py==1.2.0` pinned exactly (not `>=`) — reproducible Docker builds, no surprise upgrades
- `Decimal(str(value))` for numeric round-trips — preserves exact decimal values without float imprecision

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria passed on first run.

## Issues Encountered

None. `kyber-py` was already installed in the environment (pre-installed). All tests passed green on first run without any debugging cycles.

## User Setup Required

None — no external service configuration required for this plan. Environment variables (EMAIL_HMAC_KEY, NEAR_ACCOUNT_HMAC_KEY, TX_DEDUP_KEY, ACB_DEDUP_KEY, SESSION_DEK_WRAP_KEY) are documented in db/crypto.py module docstring and will be added to docker-compose.yml in plan 16-03.

## Known Stubs

None — db/crypto.py is a complete, fully functional implementation. All envelope operations, HMAC surrogates, and the TypeDecorator are fully implemented (not stubbed). The `seal_worker_dek`, `rewrap_dek_for_grantee`, and `unseal_worker_dek` functions are fully implemented as required by the plan spec.

## Threat Flags

None — db/crypto.py introduces no new network endpoints, auth paths, file access patterns, or schema changes. It is a pure library module with no I/O surface.

## Next Phase Readiness

- `db/crypto.py` is fully importable and exports the complete API contract listed in the plan `<interfaces>` block — plans 16-02, 16-03, 16-05 can import from it immediately
- Wave 0 test suite passes: `pytest tests/test_crypto.py tests/test_type_decorator.py -x -q` exits 0 with 24 tests
- `conftest.py` DEK zeroization fixture is in place — all future tests get cross-test isolation automatically
- Blockers for next plans: none. Plan 16-02 (internal crypto router) and 16-03 (auth-service key custody) can proceed in parallel since they only import from `db.crypto`

---
*Phase: 16-post-quantum-encryption-at-rest*
*Completed: 2026-04-12*
