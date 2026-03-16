---
phase: 12
slug: user-onboarding
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pyproject.toml, tests/ directory) |
| **Config file** | pyproject.toml `[tool.ruff]` for lint; pytest discovers tests/ automatically |
| **Quick run command** | `pytest tests/test_api_preferences.py tests/test_api_wallets.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_api_preferences.py tests/test_api_wallets.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | ONBOARD-01 | unit | `pytest tests/test_api_preferences.py -x -q` | W0 | pending |
| 12-02-01 | 02 | 2 | ONBOARD-02 | type-check | `cd web && npx tsc --noEmit` | N/A | pending |
| 12-02-02 | 02 | 2 | ONBOARD-01 | type-check | `cd web && npx tsc --noEmit` | N/A | pending |
| 12-03-01 | 03 | 2 | ONBOARD-03 | type-check | `cd web && npx tsc --noEmit` | N/A | pending |
| 12-03-02 | 03 | 2 | ONBOARD-05,06,07 | type-check | `cd web && npx tsc --noEmit` | N/A | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_api_preferences.py` — stubs for ONBOARD-01, ONBOARD-05, ONBOARD-06 (GET/POST/PATCH preferences endpoints, JSONB merge, idempotent completion)

*Note: `tests/test_migration_009.py` removed from Wave 0 — migration 010 uses `IF NOT EXISTS` / `DROP COLUMN IF EXISTS` SQL syntax which is inherently idempotent. A dedicated migration test adds no value beyond what the integration tests already cover.*

*Existing infrastructure covers ONBOARD-02, ONBOARD-03, ONBOARD-07 via `tests/test_api_wallets.py` and `tests/test_api_verification.py`.*

---

## Frontend Verification Note

Frontend plans (12-02, 12-03) use `npx tsc --noEmit` as the primary fast verify command (~5-10 seconds) instead of `npx next build` (which can exceed 30 seconds). A full `npx next build` should be run as a wave-level gate after all frontend tasks in a wave are complete.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Report orientation links correct in Step 5 | ONBOARD-04 | UI copy and link correctness — requires visual inspection | Navigate to Step 5 of onboarding wizard, verify all report type links point to correct dashboard pages |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
