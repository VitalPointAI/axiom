---
phase: 11
plan: "05"
title: Audit Wiring, History API & Offline Mode
status: complete
started: 2026-03-14
completed: 2026-03-14
---

## What was built

write_audit() wired into all mutation points, audit history API endpoint, and offline/cached mode for indexer service.

## Key files

### Modified
- `engine/classifier/writer.py` — write_audit_log() now delegates to unified write_audit()
- `verify/duplicates.py` — Audit on duplicate auto-merge
- `api/routers/transactions.py` — Audit on manual classification edit (actor_type='user')
- `api/routers/verification.py` — Audit on verification resolution
- `reports/generate.py` — Audit after report manifest written
- `api/main.py` — Registered audit router
- `api/routers/__init__.py` — Added audit router import
- `config.py` — Added OFFLINE_MODE, NETWORK_JOB_TYPES config
- `indexers/service.py` — Added _detect_offline_mode(), _requeue_for_offline(), health/status offline exposure

### Created
- `api/routers/audit.py` — GET /api/audit/history with entity_type/entity_id/limit filters
- `tests/test_api_audit.py` — 6 tests for audit history endpoint
- `tests/test_offline_mode.py` — 6 tests for offline mode detection and API exposure

## Commits
- `86ff6e0` feat(11-05): wire write_audit() into all mutation points
- `445ec54` feat(11-05): add audit history API endpoint
- `9f75958` feat(11-05): implement offline/cached mode for indexer service

## Deviations
- `engine/acb/engine_acb.py` audit wiring was done per-token after replay rather than per-snapshot, to avoid excessive audit rows during normal operation.

## Self-Check: PASSED
- write_audit() wired into classifier, duplicates, transactions, verification, reports: ✓
- Audit history API with user isolation and filters: ✓
- Offline mode with auto-detection and job requeuing: ✓
- Health/status endpoints expose offline state: ✓
