---
phase: 4
slug: cost-basis-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (auto-discovers `tests/` directory) |
| **Config file** | none — pytest auto-discovers `tests/` directory |
| **Quick run command** | `cd /home/vitalpointai/projects/Axiom && python -m pytest tests/test_acb.py tests/test_superficial.py -x -q` |
| **Full suite command** | `cd /home/vitalpointai/projects/Axiom && python -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_acb.py tests/test_superficial.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | ACB-01 | unit | `pytest tests/test_acb.py::TestACBPool -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | ACB-01 | unit | `pytest tests/test_acb.py::TestACBPool::test_multi_acquire -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | ACB-02 | unit | `pytest tests/test_acb.py::TestACBEngine::test_cross_wallet_pool -x` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | ACB-04 | unit | `pytest tests/test_acb.py::TestACBPool::test_acquire_with_fee -x` | ❌ W0 | ⬜ pending |
| 04-01-05 | 01 | 1 | ACB-04 | unit | `pytest tests/test_acb.py::TestACBPool::test_dispose_with_fee -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | ACB-03 | unit | `pytest tests/test_price_service.py::TestMinutePriceCache -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | ACB-03 | unit | `pytest tests/test_price_service.py::TestBoCRate -x` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | ACB-03 | unit | `pytest tests/test_acb.py::TestACBEngine::test_staking_income_fmv -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 2 | ACB-05 | unit | `pytest tests/test_superficial.py::TestSuperficialLoss::test_full_rebuy_denial -x` | ❌ W0 | ⬜ pending |
| 04-03-02 | 03 | 2 | ACB-05 | unit | `pytest tests/test_superficial.py::TestSuperficialLoss::test_partial_rebuy_prorated -x` | ❌ W0 | ⬜ pending |
| 04-03-03 | 03 | 2 | ACB-05 | unit | `pytest tests/test_superficial.py::TestSuperficialLoss::test_exchange_rebuy -x` | ❌ W0 | ⬜ pending |
| 04-03-04 | 03 | 2 | ACB-05 | unit | `pytest tests/test_superficial.py::TestSuperficialLoss::test_no_rebuy_no_flag -x` | ❌ W0 | ⬜ pending |
| 04-04-01 | 04 | 2 | ACB-04 | unit | `pytest tests/test_acb.py::TestACBEngine::test_swap_fee_leg_acb -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_acb.py` — stubs for ACB-01, ACB-02, ACB-03, ACB-04; mocked psycopg2 pool
- [ ] `tests/test_superficial.py` — stubs for ACB-05; mocked pool with synthetic disposal + acquisition rows
- [ ] `tests/test_price_service.py` — new test classes: `TestMinutePriceCache`, `TestBoCRate`, `TestCoinGeckoRange` (extends existing file)

*Existing infrastructure: pytest installed, `tests/` directory present.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CoinGecko minute-level price fetch | ACB-03 | External API call; rate-limited | Mock in unit tests, verify real fetch in integration |
| Bank of Canada CAD rate fetch | ACB-03 | External API; weekend/holiday gaps | Mock in unit tests, verify real fetch in integration |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
