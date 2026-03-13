---
phase: 7
slug: web-ui
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (backend) + vitest (frontend) |
| **Config file** | `pytest.ini` / `web/vitest.config.ts` (Wave 0 installs if missing) |
| **Quick run command** | `pytest tests/api/ -x -q` |
| **Full suite command** | `pytest tests/api/ && cd web && npx vitest run` |
| **Estimated runtime** | ~45 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/api/ -x -q`
- **After every plan wave:** Run `pytest tests/api/ && cd web && npx vitest run`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | UI-08 | unit | `pytest tests/api/test_auth.py` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | UI-01 | unit | `pytest tests/api/test_auth.py::test_passkey_flow` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | UI-02 | integration | `pytest tests/api/test_dashboard.py` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | UI-03 | integration | `pytest tests/api/test_wallets.py` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | UI-04 | integration | `pytest tests/api/test_transactions.py` | ❌ W0 | ⬜ pending |
| 07-03-02 | 03 | 2 | UI-05 | integration | `pytest tests/api/test_classification.py` | ❌ W0 | ⬜ pending |
| 07-04-01 | 04 | 2 | UI-06 | integration | `pytest tests/api/test_reports.py` | ❌ W0 | ⬜ pending |
| 07-04-02 | 04 | 2 | UI-07 | integration | `pytest tests/api/test_verification.py` | ❌ W0 | ⬜ pending |
| 07-05-01 | 05 | 3 | UI-03 | e2e | `cd web && npx vitest run src/__tests__/sync.test.ts` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/api/conftest.py` — shared fixtures (test DB, auth helpers, mock user)
- [ ] `tests/api/test_auth.py` — auth endpoint stubs for UI-01, UI-08
- [ ] `tests/api/test_dashboard.py` — dashboard endpoint stubs for UI-02
- [ ] `tests/api/test_wallets.py` — wallet management stubs for UI-03
- [ ] `tests/api/test_transactions.py` — transaction ledger stubs for UI-04, UI-05
- [ ] `tests/api/test_reports.py` — report generation stubs for UI-06
- [ ] `tests/api/test_verification.py` — verification dashboard stubs for UI-07
- [ ] `pip install pytest-asyncio httpx` — async test support for FastAPI

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WebAuthn passkey registration/login | UI-01 | Requires browser authenticator API | Register passkey in Chrome, verify login flow end-to-end |
| Stage progress bar animation | UI-03 | Visual UX verification | Add wallet, watch pipeline stages animate through completion |
| Report PDF visual correctness | UI-06 | PDF layout verification | Generate tax package, open PDF, verify formatting |
| Accountant client-switching UX | UI-08 | Multi-user browser session | Login as accountant, switch to client view, verify amber banner |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
