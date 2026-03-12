---
phase: 3
slug: transaction-classification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already in use — see `tests/` directory) |
| **Config file** | none — tests run via `pytest tests/` from project root |
| **Quick run command** | `pytest tests/test_classifier.py tests/test_wallet_graph.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_classifier.py tests/test_wallet_graph.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | CLASS-01 | unit | `pytest tests/test_classifier.py::TestNearClassification -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | CLASS-01 | unit | `pytest tests/test_classifier.py::TestExchangeClassification -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | CLASS-01 | unit | `pytest tests/test_classifier.py::TestEVMClassification -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | CLASS-01 | unit | `pytest tests/test_classifier.py::TestMultiLegDecomposition -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | CLASS-02 | unit | `pytest tests/test_wallet_graph.py::TestInternalTransferDetection -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | CLASS-02 | unit | `pytest tests/test_wallet_graph.py::TestCrossChainMatching -x` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 1 | CLASS-02 | unit | `pytest tests/test_wallet_graph.py::TestFalsePositivePrevention -x` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 1 | CLASS-03 | unit | `pytest tests/test_classifier.py::TestStakingRewardLinkage -x` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 1 | CLASS-04 | unit | `pytest tests/test_classifier.py::TestLockupVestLinkage -x` | ❌ W0 | ⬜ pending |
| 03-05-01 | 05 | 1 | CLASS-05 | unit | `pytest tests/test_classifier.py::TestSwapDecomposition -x` | ❌ W0 | ⬜ pending |
| 03-05-02 | 05 | 1 | CLASS-05 | unit | `pytest tests/test_evm_decoder.py::TestSwapDetection -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_classifier.py` — stubs for CLASS-01, CLASS-03, CLASS-04, CLASS-05
- [ ] `tests/test_wallet_graph.py` — stubs for CLASS-02
- [ ] `tests/test_evm_decoder.py` — stubs for CLASS-05 EVM path
- [ ] `tests/test_spam_detector.py` — stubs for spam detection logic

*Existing test infrastructure covers all other handlers but not classifier.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Specialist confirmation UI workflow | CLASS-01 | UI interaction requires human review | Confirm rule, verify audit trail record created |
| Spam tagging propagation | CLASS-01 | Cross-account global propagation needs live multi-user data | Tag spam tx, verify similar txs flagged across accounts |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
