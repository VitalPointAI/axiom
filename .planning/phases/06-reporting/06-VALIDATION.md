---
phase: 6
slug: reporting
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (used in all prior phases) |
| **Config file** | none — pytest discovered from project root |
| **Quick run command** | `python3 -m pytest tests/test_reports.py -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_reports.py -x -q`
- **After every plan wave:** Run `python3 -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | RPT-01 | unit | `pytest tests/test_reports.py::TestCapitalGainsReport -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | RPT-02 | unit | `pytest tests/test_reports.py::TestIncomeReport -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | RPT-03 | unit | `pytest tests/test_reports.py::TestLedgerReport -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | RPT-04 | unit | `pytest tests/test_reports.py::TestT1135Checker -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | RPT-05 | unit | `pytest tests/test_reports.py::TestCSVExport -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | RPT-06 | integration | `pytest tests/test_reports.py::TestPDFGeneration -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 1 | gate | unit | `pytest tests/test_reports.py::TestReportGate -x` | ❌ W0 | ⬜ pending |
| 06-03-02 | 03 | 1 | gate | unit | `pytest tests/test_reports.py::TestReportGate::test_override_generates_with_warnings -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_reports.py` — stubs for all RPT requirements + gate check
- [ ] `reports/templates/` directory with base HTML template for PDF generation
- [ ] Confirm Jinja2 installed: `pip show jinja2` — if missing, add to `requirements.txt`

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Accountant confirms package is complete | Success Criteria 5 | Human review required | Generate full tax package, have accountant review completeness |
| PDF layout is readable and professional | RPT-06 | Visual inspection | Open generated PDF, check formatting, tables, headers |
| QuickBooks/Xero/Sage import succeeds | RPT-05 | External software | Import exported files into accounting software sandbox |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
