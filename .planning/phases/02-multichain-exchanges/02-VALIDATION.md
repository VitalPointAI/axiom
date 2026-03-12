---
phase: 2
slug: multichain-exchanges
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing — tests/test_near_fetcher.py, tests/test_price_service.py) |
| **Config file** | none detected — Wave 0 adds pytest config |
| **Quick run command** | `pytest tests/test_evm_fetcher.py tests/test_exchange_parsers.py -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_evm_fetcher.py tests/test_exchange_parsers.py -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | DATA-04/05 | setup | `pytest tests/ --collect-only` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | DATA-04 | unit | `pytest tests/test_evm_fetcher.py -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | DATA-04 | unit | `pytest tests/test_evm_fetcher.py::test_pagination -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 1 | DATA-04 | integration | `pytest tests/test_evm_fetcher.py::test_balance_reconciliation -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 1 | DATA-05 | unit | `pytest tests/test_exchange_parsers.py::test_coinbase -x` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 1 | DATA-05 | unit | `pytest tests/test_exchange_parsers.py::test_crypto_com -x` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 1 | DATA-05 | unit | `pytest tests/test_exchange_parsers.py::test_wealthsimple -x` | ❌ W0 | ⬜ pending |
| 02-03-04 | 03 | 1 | DATA-05 | unit | `pytest tests/test_exchange_parsers.py::test_generic -x` | ❌ W0 | ⬜ pending |
| 02-03-05 | 03 | 1 | DATA-05 | unit | `pytest tests/test_exchange_parsers.py::test_import_dedup -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_evm_fetcher.py` — stubs for DATA-04 (mock Etherscan API responses, verify inserts)
- [ ] `tests/test_exchange_parsers.py` — stubs for DATA-05 (fixture CSV rows for each exchange parser)
- [ ] `tests/fixtures/` — sample CSV fixture rows for coinbase, crypto_com, wealthsimple, generic parsers
- [ ] `pyproject.toml [tool.pytest]` — add testpaths configuration

*Existing infrastructure covers framework install — pytest already available.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Calculated EVM balance matches on-chain | DATA-04 | Requires real blockchain RPC call | Compare `SUM(amount)` from DB with Etherscan balance API for test address |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
