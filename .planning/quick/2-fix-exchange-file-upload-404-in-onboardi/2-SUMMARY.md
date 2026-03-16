---
phase: quick-2
plan: "01"
subsystem: web/onboarding
tags: [bug-fix, file-upload, onboarding, frontend]
dependency_graph:
  requires: []
  provides: [working-exchange-file-upload-in-onboarding]
  affects: [web/app/onboarding/steps/import.tsx]
tech_stack:
  added: []
  patterns: [API_URL prefix for cross-origin fetch, raw fetch() for FormData uploads]
key_files:
  created: []
  modified:
    - web/app/onboarding/steps/import.tsx
decisions:
  - "Use raw fetch() with API_URL prefix instead of apiClient — apiClient hardcodes Content-Type: application/json which breaks multipart FormData uploads"
metrics:
  duration: "3 minutes"
  completed: "2026-03-16"
---

# Quick Task 2: Fix Exchange File Upload 404 in Onboarding Summary

**One-liner:** Fixed onboarding wizard step 3 file upload by correcting the fetch URL from non-existent `/api/upload-file` to `${API_URL}/api/exchanges/import` (the actual FastAPI endpoint).

## What Was Done

Changed two things in `web/app/onboarding/steps/import.tsx`:

1. Added `import { API_URL } from '@/lib/api'` to the imports.
2. Changed the fetch call from:
   ```
   fetch('/api/upload-file', ...)
   ```
   to:
   ```
   fetch(`${API_URL}/api/exchanges/import`, ...)
   ```

The old URL `/api/upload-file` was the original Next.js API route from Phase 2 Plan 02-04 before the 07-07 Docker/API migration removed all 75 Next.js API routes. The actual FastAPI endpoint is `POST /api/exchanges/import` defined in `api/routers/reports.py` under `exchanges_router`.

The `API_URL` prefix ensures the fetch targets the FastAPI service correctly in both local dev (`http://localhost:8000`) and production (empty string for relative proxied paths).

## Verification

- `grep -n "api/exchanges/import" web/app/onboarding/steps/import.tsx` — confirmed at line 40
- `grep -n "API_URL" web/app/onboarding/steps/import.tsx` — confirmed import at line 5, usage at line 40
- `grep -rn "upload-file" web/` (excluding node_modules) — zero source matches

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Hash | Message |
|------|---------|
| 2a6c3d6 | fix(quick-2): fix exchange file upload 404 in onboarding wizard |

## Self-Check: PASSED

- [x] `web/app/onboarding/steps/import.tsx` modified with correct fetch URL and API_URL import
- [x] Commit 2a6c3d6 exists in git log
- [x] No references to `/api/upload-file` remain in source files
