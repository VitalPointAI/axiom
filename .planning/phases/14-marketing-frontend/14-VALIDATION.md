---
phase: 14
slug: marketing-frontend
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-10
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest + @testing-library/react (installed in Plan 01 Task 1) |
| **Config file** | `web/vitest.config.ts` (created in Plan 01 Task 1) |
| **Quick run command** | `cd web && npx vitest run --reporter=verbose` |
| **Full suite command** | `cd web && npx vitest run` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd web && npx vitest run --reporter=verbose`
- **After every plan wave:** Run `cd web && npx vitest run`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | MKT-11 | — | N/A | config | `cd web && npx next build` | N/A (config) | pending |
| 14-01-02 | 01 | 1 | MKT-11 | — | N/A | config | `cd web && npx next build` | N/A (config) | pending |
| 14-01-03 | 01 | 1 | MKT-11 | — | N/A | render | `cd web && npx vitest run` | Plan 01 T1 | pending |
| 14-02-01 | 02 | 1 | MKT-01 | — | N/A | render | `cd web && npx vitest run` | Plan 01 T1 | pending |
| 14-03-01 | 03 | 2 | MKT-02,MKT-03 | — | N/A | render | `cd web && npx vitest run` | Plan 01 T1 | pending |
| 14-04-01 | 04 | 2 | MKT-08 | — | N/A | render | `cd web && npx vitest run` | Plan 01 T1 | pending |
| 14-05-01 | 05 | 3 | MKT-11,MKT-12 | — | N/A | integration | `cd web && npx vitest run` | Plan 01 T1 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [x] `web/vitest.config.ts` — created in Plan 01 Task 1
- [x] `web/__tests__/marketing/` — test directory created in Plan 01 Task 1
- [x] vitest + @testing-library/react + jsdom installed in Plan 01 Task 1

*Wave 0 is folded into Plan 01 Task 1's dependency install step.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Page loads < 2s on mobile | MKT-11 | Requires Lighthouse/network throttling | Run Lighthouse audit on deployed page |
| Responsive layout across breakpoints | MKT-11 | Visual verification needed | Check mobile/tablet/desktop viewports |
| Dark/light mode toggle | D-10 | Visual state change | Toggle theme, verify all sections render correctly |
| Breach timeline accuracy | MKT-03 | Content verification | Cross-reference dates/sources with linked articles |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (Wave 0 folded into Plan 01 Task 1)
