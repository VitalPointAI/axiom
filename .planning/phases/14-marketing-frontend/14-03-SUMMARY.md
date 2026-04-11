---
phase: 14-marketing-frontend
plan: 03
subsystem: web/marketing
tags: [landing-page, hero, waitlist, comparison-table, pricing, chain-showcase, framer-motion]
dependency_graph:
  requires: [marketing-layout, theme-toggle, marketing-nav, marketing-footer, section-wrapper, vitest-config]
  provides: [landing-page, hero, waitlist-form, feature-card, feature-comparison, chain-showcase, pricing-card, feature-grid]
  affects: [web/app/(marketing)/page.tsx, web/app/globals.css, web/package.json]
tech_stack:
  added: []
  patterns: [server-client-boundary-split, framer-motion-stagger, zod-form-validation, reduced-motion-gate]
key_files:
  created:
    - web/components/marketing/hero.tsx
    - web/components/marketing/waitlist-form.tsx
    - web/components/marketing/feature-card.tsx
    - web/components/marketing/feature-comparison.tsx
    - web/components/marketing/chain-showcase.tsx
    - web/components/marketing/pricing-card.tsx
    - web/app/(marketing)/page.tsx
    - web/app/(marketing)/feature-grid.tsx
  modified:
    - web/app/globals.css
    - web/package.json
    - web/components/marketing/section-wrapper.tsx
    - web/app/(marketing)/layout.tsx
decisions:
  - "Created FeatureGrid client component to handle Server/Client boundary - page.tsx exports metadata (Server Component) so icon components cannot be serialized as props"
  - "Used lucide-react geometric shapes (Hexagon, Diamond, Pentagon, Circle, Triangle) for chain icons since no official chain SVGs are available in the icon library"
  - "Used $149/year as placeholder price since exact pricing was not specified in decisions"
metrics:
  duration: ~8m
  completed: "2026-04-11"
  tasks: 2
  files: 12
---

# Phase 14 Plan 03: Landing Page & Marketing Components Summary

Complete landing page with hero (gradient headline, waitlist form), 6 feature cards with Framer Motion stagger, honest 4-platform comparison table across 9 features, chain showcase (5 networks), flat-fee pricing card, privacy teaser, and final CTA.

## Tasks Completed

| Task | Name | Status | Files |
|------|------|--------|-------|
| 1 | Hero + WaitlistForm + FeatureCard components | DONE | hero.tsx, waitlist-form.tsx, feature-card.tsx, section-wrapper.tsx, globals.css, package.json, layout.tsx |
| 2 | Comparison table + Chain showcase + Pricing card + Landing page assembly | DONE | feature-comparison.tsx, chain-showcase.tsx, pricing-card.tsx, page.tsx, feature-grid.tsx |

## Key Changes

### Task 1: Hero + WaitlistForm + FeatureCard

- **waitlist-form.tsx**: Client component with react-hook-form + zod email validation. 4 status states (idle, submitting, success, duplicate, error). POSTs to /api/waitlist. Inline/standalone variants for different layouts. Button styled with bg-indigo-500 per UI-SPEC accent rules. 44px minimum touch targets.
- **hero.tsx**: Client component with gradient headline ("The first Canadian-sovereign, blockchain-native crypto tax platform."), glow-bg background, inline waitlist form, "See how Axiom works" secondary CTA. Framer Motion entrance animation (opacity 0->1, y 30->0) with useReducedMotion gate.
- **feature-card.tsx**: Client component with cardVariants for stagger animation (hidden/show states). Icon badge with bg-indigo-500/10, hover:scale-[1.02] with shadow effect. Exports cardVariants for parent container orchestration.
- **globals.css**: Added `.gradient-text` (indigo-purple-cyan gradient) and `.glow-bg` (radial indigo glow) CSS utilities.
- **package.json**: Added framer-motion, react-hook-form, @hookform/resolvers, zod dependencies.
- **section-wrapper.tsx**: Restored from Wave 1 base (prerequisite for landing page).
- **layout.tsx**: Restored from Wave 1 base (marketing route group layout).

### Task 2: Comparison + Chains + Pricing + Assembly

- **feature-comparison.tsx**: Honest comparison table: Axiom vs PrivateACB vs CoinTracker vs Koinly across 9 features (CRA ACB, Superficial Loss, CARF 2026, Direct Indexing, DeFi, AI Classification, Canadian Data, No Analytics, Breach History). Green checkmarks, red X, orange partial indicators. Axiom column highlighted with bg-indigo-500. Mobile horizontal scroll. Breach incidents in destructive color.
- **chain-showcase.tsx**: 5 blockchain icons (NEAR #00C1DE, Ethereum #627EEA, Polygon #8247E5, XRP #23292F, Akash #FF414C) with lucide-react geometric shapes. "Multi-chain support" heading with "5+ networks" subtext.
- **pricing-card.tsx**: Flat annual fee card with "Simple pricing" badge, "One price. One tax year. No surprises." headline, $149/year price display, 5 included feature bullets with check icons, "Join the waitlist" CTA that scrolls to #waitlist section.
- **page.tsx**: Server Component with metadata export (title, description, OpenGraph en_CA, Twitter card). Assembles 7 sections: Hero, Features (via FeatureGrid), Chain Showcase, Comparison, Pricing, Privacy Teaser, Final CTA. All copy matches UI-SPEC copywriting contract.
- **feature-grid.tsx**: Client component wrapping 6 FeatureCards in Framer Motion container with staggerChildren: 0.1. Contains features data with icon imports (Shield, Zap, Bot, Lock, BarChart3, Globe) to avoid Server/Client serialization issues.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Server/Client component boundary for icon props**
- **Found during:** Task 2
- **Issue:** page.tsx exports `metadata` making it a Server Component, but the plan specified defining features array with LucideIcon component references directly in page.tsx and passing them to a client FeatureGrid. React component functions cannot be serialized across the RSC boundary.
- **Fix:** Created FeatureGrid client component that owns both the features data (with icon imports) and the Framer Motion stagger container. page.tsx renders `<FeatureGrid />` with no props instead of passing the features array.
- **Files created:** web/app/(marketing)/feature-grid.tsx
- **Impact:** Same visual result, architecturally correct for Next.js App Router.

**2. [Rule 3 - Blocking] Wave 1 prerequisite files missing from worktree**
- **Found during:** Task 1 (pre-execution)
- **Issue:** This worktree was created from commit 46dfb44 (account-indexer branch) instead of eb0a348 (main with Wave 1 marketing foundation). All Wave 1 files (section-wrapper.tsx, marketing layout, globals.css utilities) were missing.
- **Fix:** Recreated section-wrapper.tsx and marketing layout.tsx from the Wave 1 base commit content (read via git show). Added gradient-text and glow-bg CSS utilities to globals.css. Added missing npm dependencies to package.json.
- **Files modified:** section-wrapper.tsx, layout.tsx, globals.css, package.json

## Blocker: Git Commit Permission

All file changes are complete and verified on disk, but `git add` and `git commit` operations were systematically blocked by the permission system throughout execution. The orchestrator needs to commit these changes. All modified/created files are listed in git status output.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| $149/year price | web/components/marketing/pricing-card.tsx | Placeholder - exact pricing not specified in D-15, will be updated when pricing is finalized |

## Threat Flags

None - all changes align with the plan's threat model. Waitlist form validates email with zod on client side (T-14-09 mitigation). Comparison data is static public information (T-14-10 accepted). Pricing is static content (T-14-11 accepted).

## Self-Check: PENDING

Cannot verify commits exist because no commits were created (permission blocked). File existence verified:
- web/components/marketing/hero.tsx: EXISTS (gradient-text, glow-bg, "The first Canadian-sovereign")
- web/components/marketing/waitlist-form.tsx: EXISTS (zodResolver, fetch /api/waitlist, 4 status states)
- web/components/marketing/feature-card.tsx: EXISTS (cardVariants hidden/show)
- web/components/marketing/feature-comparison.tsx: EXISTS (PrivateACB, CoinTracker, Koinly, bg-indigo-500, Data Breach History)
- web/components/marketing/chain-showcase.tsx: EXISTS (NEAR, Ethereum, Polygon, XRP, Akash)
- web/components/marketing/pricing-card.tsx: EXISTS ("One price. One tax year. No surprises.", "Join the waitlist")
- web/app/(marketing)/page.tsx: EXISTS (91 lines, metadata with en_CA, all component imports)
- web/app/(marketing)/feature-grid.tsx: EXISTS (CRA-Compliant, Direct Blockchain Indexing, staggerChildren)
- web/app/globals.css: EXISTS (gradient-text, glow-bg utilities added)
- web/package.json: EXISTS (framer-motion, react-hook-form, @hookform/resolvers, zod)
