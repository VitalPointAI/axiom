---
phase: 09-code-quality-hardening
plan: "02"
subsystem: api-hardening
tags: [rate-limiting, env-validation, sql-safety, rollback]
dependency_graph:
  requires: []
  provides: [slowapi-rate-limiting, env-validation, sql-whitelist, rollback-consistency]
  affects: [api/main.py, api/rate_limit.py, api/auth, api/routers/, config.py, indexers/classifier_handler.py]
tech_stack:
  added: [slowapi]
  patterns: [shared-limiter-instance, env-validation-on-startup, field-whitelist]
key_files:
  created:
    - api/rate_limit.py
    - tests/test_rate_limiting.py
    - tests/test_config_validation.py
  modified:
    - api/main.py
    - api/auth/router.py
    - api/routers/wallets.py
    - api/routers/reports.py
    - api/routers/transactions.py
    - config.py
    - indexers/classifier_handler.py
decisions:
  - "slowapi with get_remote_address key function for rate limiting"
  - "Auth endpoints: 10/min, job triggers: 5/min, data endpoints: 60/min"
  - "validate_env() raises RuntimeError on missing DATABASE_URL"
  - "ALLOWED_UPDATE_FIELDS whitelist prevents SQL injection via field names"
metrics:
  duration_minutes: 12
  tasks_completed: 2
  files_modified: 10
  completed_date: "2026-03-14"
requirements: [QH-04, QH-05, QH-06, QH-07]
---

# Phase 9 Plan 02: API Hardening Summary

**One-liner:** slowapi rate limiting on auth/job/data endpoints, env validation at startup, SQL field whitelist, and consistent rollback patterns in handlers.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wire slowapi rate limiting + env validation + SQL whitelist | dc6c3b6 | api/rate_limit.py, api/main.py, api/auth/router.py, api/routers/*, config.py |
| 2 | Standardize transaction rollback + tests | fff17c9, e4aea73 | indexers/classifier_handler.py, tests/test_rate_limiting.py, tests/test_config_validation.py |

## What Was Built

### Task 1: Rate Limiting + Env Validation
- `api/rate_limit.py` — shared slowapi limiter instance
- slowapi wired into FastAPI app with exception handler
- Rate limits applied: auth (10/min), wallet creation (5/min), reports (5/min), transactions (60/min)
- `config.validate_env()` called in lifespan — fails fast on missing DATABASE_URL
- `ALLOWED_UPDATE_FIELDS` whitelist in transactions.py for dynamic SQL UPDATE

### Task 2: Rollback Consistency + Tests
- `classifier_handler._ensure_rules_seeded()` now has proper except/rollback/raise + cur.close()
- `file_handler.py` already had correct rollback pattern (verified, no changes needed)
- `tests/test_rate_limiting.py` verifies limiter is registered on app
- `tests/test_config_validation.py` verifies fail-fast on missing DATABASE_URL

## Deviations from Plan

- file_handler.py already had correct rollback pattern — no changes needed
- Test files committed with 09-01 Task 2 due to staging overlap (functionally correct)

## Self-Check: PASSED

- api/rate_limit.py: FOUND
- tests/test_rate_limiting.py: FOUND
- tests/test_config_validation.py: FOUND
- Commit dc6c3b6: FOUND
- Commit fff17c9: FOUND
