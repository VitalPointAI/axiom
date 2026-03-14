---
phase: 09-code-quality-hardening
plan: "01"
subsystem: ci-infrastructure
tags: [ci, ruff, legacy-cleanup, stubs]
dependency_graph:
  requires: []
  provides: [ci-quality-gates, ruff-config, legacy-archive]
  affects: [.github/workflows/ci.yml, .github/workflows/deploy.yml, pyproject.toml, _archive/]
tech_stack:
  added: [ruff, pytest-cov]
  patterns: [workflow-run-dependency, archive-not-delete]
key_files:
  created:
    - .github/workflows/ci.yml
    - pyproject.toml
    - _archive/README.md
    - _archive/engine_prices.py
    - _archive/hybrid_indexer.py
    - _archive/ft_indexer.py
  modified:
    - .github/workflows/deploy.yml
    - api/routers/portfolio.py
decisions:
  - "Archive legacy SQLite modules to _archive/ rather than deleting — preserves history"
  - "Generous ruff ignores (E501, E402, W291-293, E711-712) for existing codebase"
  - "Deploy workflow uses workflow_run trigger to gate on CI passing"
metrics:
  duration_minutes: 15
  tasks_completed: 2
  files_modified: 8
  completed_date: "2026-03-14"
requirements: [QH-01, QH-08, QH-12]
---

# Phase 9 Plan 01: CI Quality Gates & Legacy Cleanup Summary

**One-liner:** CI pipeline with pytest+ruff gates deploy workflow; legacy SQLite modules archived; stub endpoints return 501.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | CI quality gates workflow + ruff config | 47688dc | .github/workflows/ci.yml, pyproject.toml, .github/workflows/deploy.yml |
| 2 | Archive legacy SQLite modules + document stubs | e4aea73 | _archive/*, api/routers/portfolio.py |

## What Was Built

### Task 1: CI Quality Gates
- `.github/workflows/ci.yml` with pytest, ruff lint, and coverage steps
- `pyproject.toml` with ruff configuration (line-length=120, py311, generous ignores)
- `.github/workflows/deploy.yml` updated with `workflow_run` trigger — deploy only after CI passes

### Task 2: Legacy Cleanup & Stub Documentation
- Archived `engine/prices.py`, `indexers/hybrid_indexer.py`, `indexers/ft_indexer.py` to `_archive/`
- `api/routers/portfolio.py` stub endpoint updated to return `HTTPException(501)`
- `_archive/README.md` documents archival purpose

## Deviations from Plan

- `indexers/xrp_fetcher.py` and `indexers/akash_fetcher.py` stub documentation deferred (no changes needed — these are functional fetchers with known limitations already logged)
- Test files from 09-02 (test_rate_limiting.py, test_config_validation.py) included in Task 2 commit due to staging overlap

## Self-Check: PASSED

- .github/workflows/ci.yml: FOUND
- pyproject.toml: FOUND
- _archive/engine_prices.py: FOUND
- _archive/hybrid_indexer.py: FOUND
- _archive/ft_indexer.py: FOUND
- Commit 47688dc: FOUND
- Commit e4aea73: FOUND
