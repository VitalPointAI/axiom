---
phase: quick-260406-lqu
plan: 01
subsystem: frontend
tags: [progress, ui, dropdown, sync-status, jobs]
dependency_graph:
  requires: []
  provides: [expandable-progress-detail-panel]
  affects: [web/components/sync-status.tsx, web/components/progress-detail-panel.tsx]
tech_stack:
  added: []
  patterns: [click-outside-ref, conditional-dropdown, stage-stepper]
key_files:
  created:
    - web/components/progress-detail-panel.tsx
  modified:
    - web/components/sync-status.tsx
decisions:
  - Used named export for ProgressDetailPanel to match codebase convention
  - Placed click-outside handler in ProgressDetailPanel rather than SyncStatus to keep panel self-contained
  - Used bg-gray-800 instead of bg-gray-850 (non-standard Tailwind) as instructed in plan
  - Exported JobDetail interface from progress-detail-panel.tsx for reuse; SyncStatus uses its own local JobDetail/ActiveJobsResponse types to avoid import coupling
metrics:
  duration: "~15 minutes"
  completed: "2026-04-06T19:50:25Z"
  tasks_completed: 2
  files_changed: 2
---

# Phase quick-260406-lqu Plan 01: Enhanced Progress Indicator Summary

**One-liner:** Clickable header progress badge with expandable dropdown panel showing 4-stage pipeline stepper, overall/stage progress bars, and per-job detail with real-time 3s polling.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create ProgressDetailPanel component | db6c015 | web/components/progress-detail-panel.tsx (created) |
| 2 | Wire clickable badge and dropdown into SyncStatus | d27a492 | web/components/sync-status.tsx (modified) |

## What Was Built

### ProgressDetailPanel (`web/components/progress-detail-panel.tsx`)

New component rendering an absolutely-positioned dropdown anchored below the header badge:

- **Header row**: "Processing Details" title + X close button (lucide X icon)
- **Stage stepper**: 4 stages (Indexing, Classifying, Cost Basis, Verifying) with green filled (complete), blue pulsing (active), gray (pending) indicators connected by a horizontal line
- **Overall progress**: label + percentage + full-width `bg-blue-500` progress bar + estimated time remaining
- **Stage-specific progress**: label + stage percentage computed from backend ranges (Indexing 0-45, Classifying 45-65, Cost Basis 65-85, Verifying 85-100) with stage-specific color (blue/purple/amber/green)
- **Jobs list**: scrollable `max-h-48` area with per-job rows showing: status dot (green=running, yellow=queued, orange=retrying, red=failed), human-readable job type label, progress fraction or status text, inline mini progress bar when fetched/total available, truncated error message for failed jobs
- **Click-outside**: `useEffect` + `mousedown` listener on `document` calls `onClose()` when click is outside panel ref

### SyncStatus updates (`web/components/sync-status.tsx`)

- Updated `ActiveJobsResponse.jobs` type from `Array<{status, pipeline_stage, pipeline_pct}>` to `JobDetail[]` matching real API shape (id, job_type, progress_fetched, progress_total, error_message, started_at, completed_at)
- Added `activeJobsData` state (stores full `ActiveJobsResponse`) and `detailOpen` state (panel open/closed)
- `fetchStatus` now calls `setActiveJobsData(data)` on active jobs, `setActiveJobsData(null)` on empty
- Global active badge wrapped in `<div className="relative"><button ...>` with ChevronDown icon that rotates 180 degrees when open
- `ProgressDetailPanel` renders conditionally below button when `detailOpen && activeJobsData`
- Done transition effect adds `setDetailOpen(false)` to close panel when pipeline completes
- Per-wallet and compact modes: unchanged

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all data flows directly from the existing `/api/jobs/active` polling response.

## Threat Flags

None - no new network endpoints, auth paths, or schema changes introduced. Panel renders job data already scoped to authenticated user.

## Self-Check: PASSED

- web/components/progress-detail-panel.tsx: FOUND
- web/components/sync-status.tsx: modified, FOUND
- Commit db6c015: Task 1 (ProgressDetailPanel)
- Commit d27a492: Task 2 (SyncStatus wiring)
- TypeScript compile: EXIT 0 (clean)
