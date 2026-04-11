---
phase: 14-marketing-frontend
plan: 01
subsystem: web/marketing
tags: [foundation, dark-mode, route-group, ui-components, test-infra]
dependency_graph:
  requires: []
  provides: [marketing-layout, theme-toggle, marketing-nav, marketing-footer, section-wrapper, vitest-config]
  affects: [web/app/layout.tsx, web/app/dashboard/layout.tsx, web/middleware.ts, web/next.config.mjs]
tech_stack:
  added: [next-themes@0.4.6, framer-motion@12.38.0, react-hook-form@7.72.1, "@hookform/resolvers", zod@4.3.6, next-plausible@4.0.0, react-intersection-observer@10.0.3, vitest, "@testing-library/react", "@testing-library/jest-dom", jsdom, "@vitejs/plugin-react"]
  patterns: [class-based-dark-mode, route-group-layout, AuthProvider-scoping]
key_files:
  created:
    - web/vitest.config.ts
    - web/__tests__/marketing/.gitkeep
    - web/app/(marketing)/layout.tsx
    - web/app/(marketing)/page.tsx
    - web/components/marketing/theme-toggle.tsx
    - web/components/marketing/marketing-nav.tsx
    - web/components/marketing/marketing-footer.tsx
    - web/components/marketing/section-wrapper.tsx
  modified:
    - web/package.json
    - web/package-lock.json
    - web/tailwind.config.ts
    - web/app/globals.css
    - web/app/layout.tsx
    - web/app/dashboard/layout.tsx
    - web/middleware.ts
    - web/next.config.mjs
  deleted:
    - web/app/page.tsx
decisions:
  - "Used exact-match for marketing routes in middleware to prevent '/' prefix matching all paths"
  - "Wrapped existing DashboardLayout inner content with AuthProvider wrapper pattern (DashboardLayoutInner + DashboardLayout export)"
  - "Used CSS nesting (.dark { .bg-white { } }) for dark mode overrides since Tailwind v4 supports it natively"
metrics:
  completed: "2026-04-10"
---

# Phase 14 Plan 01: Marketing Site Foundation Summary

Class-based dark mode via next-themes, (marketing) route group with nav/footer layout, AuthProvider scoped to dashboard only, vitest test infrastructure, and 7 new npm packages installed.

## Tasks Completed

| Task | Name | Status | Files |
|------|------|--------|-------|
| 1 | Install dependencies + test infrastructure + dark mode migration + AuthProvider restructure | DONE | package.json, tailwind.config.ts, globals.css, layout.tsx, dashboard/layout.tsx, vitest.config.ts |
| 2 | Marketing route group + middleware + cache headers | DONE | (marketing)/layout.tsx, (marketing)/page.tsx, middleware.ts, next.config.mjs |
| 3 | UI components - nav, footer, theme-toggle, section-wrapper | DONE | marketing-nav.tsx, marketing-footer.tsx, theme-toggle.tsx, section-wrapper.tsx |

## Key Changes

### Task 1: Foundation
- Installed 7 production deps: next-themes, framer-motion, react-hook-form, @hookform/resolvers, zod, next-plausible, react-intersection-observer
- Added 5 dev deps: vitest, @testing-library/react, @testing-library/jest-dom, jsdom, @vitejs/plugin-react
- Changed `darkMode: 'media'` to `darkMode: 'class'` in tailwind.config.ts
- Converted all 4 `@media (prefers-color-scheme: dark)` blocks to `.dark {}` selectors in globals.css
- Added `.gradient-text` and `.glow-bg` marketing CSS utilities
- Removed AuthProvider from root layout, added ThemeProvider (next-themes) with `attribute="class" defaultTheme="dark" enableSystem`
- Restructured dashboard layout to wrap with AuthProvider (DashboardLayoutInner pattern)
- Created vitest.config.ts with jsdom environment and @ path alias

### Task 2: Route Group + Middleware
- Created `web/app/(marketing)/layout.tsx` with MarketingNav + main + MarketingFooter
- Created `web/app/(marketing)/page.tsx` as landing page placeholder
- Deleted `web/app/page.tsx` (old redirect to /auth per D-09)
- Updated middleware with exact-match public paths for marketing routes (/, /features, /pricing, /privacy, /compliance, /about) and prefix-match for /auth, /_next, /api/waitlist
- Replaced blanket no-store cache header with route-specific headers: s-maxage=3600 for marketing, no-store for dashboard/auth/api

### Task 3: UI Components
- **theme-toggle.tsx**: Client component with useTheme hook, Sun/Moon icons with rotation animation, ghost button variant, aria-label
- **marketing-nav.tsx**: Fixed sticky nav (h-16, z-50), scroll-triggered blur backdrop, desktop nav links, mobile hamburger with 44px touch targets, "Join the waitlist" CTA
- **marketing-footer.tsx**: 3-column grid (brand/tagline, quick links, CTA/contact), semantic footer element, hello@axiom.tax contact
- **section-wrapper.tsx**: Framer Motion scroll animation (opacity 0->1, y 20->0), useReducedMotion accessibility gate, max-w-[1200px] container

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Middleware '/' prefix match**
- **Found during:** Task 2
- **Issue:** Using `pathname.startsWith('/')` in the publicPaths array would match ALL routes since every path starts with '/'
- **Fix:** Split publicPaths into `publicExactPaths` (exact match with `includes()`) and `publicPrefixPaths` (prefix match with `startsWith()`)
- **Files modified:** web/middleware.ts

**2. [Rule 3 - Blocking] Test dev dependencies not saved to package.json**
- **Found during:** Task 1
- **Issue:** Background npm install --save-dev completed but did not update package.json (race condition with background execution)
- **Fix:** Manually added vitest, @testing-library/react, @testing-library/jest-dom, jsdom, @vitejs/plugin-react to devDependencies in package.json
- **Files modified:** web/package.json

## Blocker: Git Commit Permission

All file changes are complete and verified on disk, but git add/commit operations were systematically blocked by the permission system throughout execution. The orchestrator needs to commit these changes. All modified/created/deleted files are listed in git status output.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| Landing page placeholder | web/app/(marketing)/page.tsx | Intentional - Plan 02 (landing page) will replace with full hero/sections |

## Threat Flags

None - all changes align with the plan's threat model. Marketing routes are explicitly listed in middleware publicPaths. AuthProvider is scoped to dashboard only. Cache headers differentiate public (cacheable) from authenticated (no-store) routes.

## Self-Check: PENDING

Cannot verify commits exist because no commits were created (permission blocked). File existence verified via Read/Grep tools:
- web/vitest.config.ts: EXISTS
- web/__tests__/marketing/.gitkeep: EXISTS
- web/app/(marketing)/layout.tsx: EXISTS
- web/app/(marketing)/page.tsx: EXISTS
- web/components/marketing/theme-toggle.tsx: EXISTS (contains useTheme)
- web/components/marketing/marketing-nav.tsx: EXISTS (contains /features, /pricing, etc.)
- web/components/marketing/marketing-footer.tsx: EXISTS (contains "Canadian crypto taxes, done right.")
- web/components/marketing/section-wrapper.tsx: EXISTS (contains useReducedMotion)
- web/tailwind.config.ts: VERIFIED (darkMode: 'class')
- web/app/globals.css: VERIFIED (zero prefers-color-scheme, has .dark selectors)
- web/app/layout.tsx: VERIFIED (ThemeProvider, no AuthProvider)
- web/app/page.tsx: DELETED
