---
phase: 13
slug: reliable-indexing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-17
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | `pyproject.toml [tool.pytest]` |
| **Quick run command** | `pytest tests/test_indexers.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_indexers.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | neardata.xyz block fetch | unit (mock HTTP) | `pytest tests/test_near_stream_fetcher.py -x` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | EVM WebSocket reconnect | unit (mock websocket) | `pytest tests/test_evm_stream_fetcher.py::test_reconnect -x` | ❌ W0 | ⬜ pending |
| 13-02-01 | 02 | 1 | Cost tracker writes | unit | `pytest tests/test_cost_tracker.py -x` | ❌ W0 | ⬜ pending |
| 13-02-02 | 02 | 1 | Chain registry loads fetcher | unit | `pytest tests/test_chain_registry.py -x` | ❌ W0 | ⬜ pending |
| 13-03-01 | 03 | 2 | Balance mismatch re-index | integration | `pytest tests/test_gap_detection.py -x` | ❌ W0 | ⬜ pending |
| 13-03-02 | 03 | 2 | Migration creates tables | integration | `pytest tests/test_migrations.py::test_011 -x` | ❌ W0 | ⬜ pending |
| 13-04-01 | 04 | 2 | SSE sends on pg_notify | integration | `pytest tests/test_streaming_api.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_near_stream_fetcher.py` — stubs for neardata.xyz block extraction
- [ ] `tests/test_evm_stream_fetcher.py` — stubs for WebSocket reconnect + historical sync
- [ ] `tests/test_cost_tracker.py` — stubs for api_cost_log writes
- [ ] `tests/test_chain_registry.py` — stubs for plugin registry DB config
- [ ] `tests/test_gap_detection.py` — stubs for balance mismatch re-index
- [ ] `tests/test_streaming_api.py` — stubs for SSE pg_notify
- [ ] Framework: existing pytest sufficient, no new installation needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-time WebSocket streaming under load | Data freshness <5min | Requires live chain connection | Connect wallet, send test tx, verify appears in UI within 5 min |
| neardata.xyz failover to NEAR Lake | Reliability | Requires simulating service outage | Block neardata.xyz host, verify NEAR Lake picks up |
| Cost dashboard accuracy | Budget monitoring | Requires accumulated real API usage | Run indexer for 1hr, compare dashboard totals to provider dashboards |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
