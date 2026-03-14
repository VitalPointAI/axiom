---
phase: 10
slug: remaining-concerns-remediation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed, 400 tests currently) |
| **Config file** | none — run from project root |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | RC-01 | unit (import check) | `python -c "from engine.classifier import TransactionClassifier; from engine.acb import ACBPool; from db.models import User"` | ✅ | ⬜ pending |
| 10-02-01 | 02 | 1 | RC-02 | migration | `alembic upgrade head` | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 1 | RC-03 | unit | `pytest tests/test_reports.py -k streaming -x` | ❌ W0 | ⬜ pending |
| 10-04-01 | 04 | 1 | RC-04 | unit | `pytest tests/test_near_fetcher.py -k backfill -x` | ❌ W0 | ⬜ pending |
| 10-05-01 | 05 | 1 | RC-05 | unit | `pytest tests/test_near_fetcher.py -k cache -x` | ❌ W0 | ⬜ pending |
| 10-06-01 | 06 | 1 | RC-06 | unit | `pytest tests/test_config_validation.py -k pool -x` | ❌ W0 | ⬜ pending |
| 10-07-01 | 07 | 1 | RC-07 | unit | `pytest tests/test_config_validation.py -k sanitize -x` | ❌ W0 | ⬜ pending |
| 10-08-01 | 08 | 1 | RC-08 | unit | `pytest tests/ -k stub -x` | ❌ W0 | ⬜ pending |
| 10-09-01 | 09 | 1 | RC-09 | manual | `python -c "import tomllib; d=tomllib.loads(open('pyproject.toml').read()); assert d['project']['requires-python']"` | ✅ | ⬜ pending |
| 10-10-01 | 10 | 2 | RC-10 | unit | `pytest tests/test_classifier.py -k priority -x` | ❌ W0 | ⬜ pending |
| 10-11-01 | 11 | 2 | RC-11 | unit | `pytest tests/test_acb.py -k missing_price -x` | ❌ W0 | ⬜ pending |
| 10-12-01 | 12 | 2 | RC-12 | unit | `pytest tests/test_classifier.py -k idempotent -x` | ❌ W0 | ⬜ pending |
| 10-13-01 | 13 | 2 | RC-13 | unit | `pytest tests/ -k coinbase_pro -x` | ❌ W0 | ⬜ pending |
| 10-14-01 | 14 | 2 | RC-14 | manual | `grep -ri sqlite docs/` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `db/migrations/versions/007_price_cache_index.py` — covers RC-02
- [ ] Tests for RC-03 streaming in `tests/test_reports.py`
- [ ] Tests for RC-04 backfill batching in `tests/test_near_fetcher.py`
- [ ] Tests for RC-05 NearBlocks cache in `tests/test_near_fetcher.py`
- [ ] Tests for RC-06 pool config in `tests/test_config_validation.py`
- [ ] Tests for RC-07 sanitize_for_log in `tests/test_config_validation.py`
- [ ] Tests for RC-10 rule priority in `tests/test_classifier.py`
- [ ] Tests for RC-11 missing price/gap in `tests/test_acb.py`
- [ ] Tests for RC-12 idempotent classify in `tests/test_classifier.py`
- [ ] Tests for RC-13 DeprecationWarning in `tests/test_coinbase_pro_deprecation.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Module split preserves imports | RC-01 | Import check validates at module level | Run import command post-split; verify no ImportError |
| pyproject.toml has python_requires | RC-09 | One-time config edit | Run tomllib assertion post-edit |
| No SQLite references in docs | RC-14 | Grep-based check | Run `grep -ri sqlite docs/` — expect no output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
