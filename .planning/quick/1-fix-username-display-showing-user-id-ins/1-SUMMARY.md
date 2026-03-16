---
phase: quick
plan: 1
subsystem: frontend-auth
tags: [bug-fix, ux, auth-provider, dashboard]
dependency_graph:
  requires: []
  provides: [display_name-guarantee, username-display-fix]
  affects: [web/components/auth-provider.tsx, web/app/dashboard/layout.tsx, web/app/dashboard/page.tsx, web/components/login-buttons.tsx]
tech_stack:
  added: []
  patterns: [fallback-chain, display-name-guarantee]
key_files:
  created: []
  modified:
    - web/components/auth-provider.tsx
    - web/app/dashboard/layout.tsx
    - web/app/dashboard/page.tsx
    - web/components/login-buttons.tsx
decisions:
  - "display_name fallback chain: codename > username > email > near_account_id > 'User' — guarantees non-numeric string"
  - "nearAccountId fallback chain now includes username before String(user_id)"
  - "login-buttons.tsx uses display_name first (already includes codename), nearAccountId truncation as fallback for NEAR-wallet-only users"
metrics:
  duration: "2 minutes"
  completed_date: "2026-03-16"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 4
---

# Quick Fix 1: Fix Username Display Showing User ID Summary

**One-liner:** Fixed all welcome/greeting locations to use a `display_name` fallback chain (codename > username > email > near_account_id > 'User') instead of the numeric database user ID.

## What Was Built

The dashboard was displaying the raw numeric database user ID (e.g., "Welcome, 3") because `display_name` was only populated as `u.codename || u.username` (both nullable), and all three display locations fell back to `user.nearAccountId` which itself fell back to `String(u.user_id)`.

Two-task fix:

1. **auth-provider.tsx** — Enriched both fallback chains at the session-mapping boundary so display_name is always a meaningful string.
2. **dashboard layout, page, login-buttons** — Three welcome/greeting locations now use `user.display_name` instead of `user.nearAccountId`.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Fix auth-provider display_name + nearAccountId fallback chains | 7d99097 |
| 2 | Update dashboard layout, page, login-buttons to use display_name | 69c2f27 |

## Key Changes

**`web/components/auth-provider.tsx`**
- `display_name`: `u.codename || u.username || u.email || u.near_account_id || 'User'`
- `nearAccountId`: `u.near_account_id || u.username || u.email || u.codename || String(u.user_id)`

**`web/app/dashboard/layout.tsx`** (line 118)
- Header: `user.nearAccountId` → `user.display_name`

**`web/app/dashboard/page.tsx`** (line 40)
- Page: `user?.nearAccountId` → `user?.display_name`

**`web/components/login-buttons.tsx`** (lines 22-24)
- `user.codename || ...` → `user.display_name || ...` (display_name already includes codename in chain)

## Deviations from Plan

None — plan executed exactly as written.

## Success Criteria Verification

- Dashboard header shows "Welcome, [name]" where [name] is codename/username/email/NEAR address — never numeric ID: PASS
- Dashboard page shows "Welcome back, [name]" with same logic: PASS
- Login buttons show user's display name: PASS
- TypeScript compiles without errors in modified files: PASS (pre-existing unrelated errors in app/auth/page.tsx are out of scope)

## Self-Check: PASSED

Files exist:
- web/components/auth-provider.tsx: FOUND
- web/app/dashboard/layout.tsx: FOUND
- web/app/dashboard/page.tsx: FOUND
- web/components/login-buttons.tsx: FOUND

Commits exist:
- 7d99097: FOUND
- 69c2f27: FOUND
