---
phase: 14-marketing-frontend
plan: 04
subsystem: web/marketing
tags: [pages, features, pricing, privacy, compliance, about, breach-timeline, data-flow]
dependency_graph:
  requires: [marketing-layout, section-wrapper, feature-comparison, chain-showcase, pricing-card, waitlist-form]
  provides: [features-page, pricing-page, privacy-page, compliance-page, about-page, breach-timeline, data-flow-diagram]
  affects: []
tech_stack:
  added: []
  patterns: [static-breach-data, svg-data-flow, responsive-mobile-first, seo-metadata]
key_files:
  created:
    - web/components/marketing/breach-timeline.tsx
    - web/components/marketing/data-flow-diagram.tsx
    - web/app/(marketing)/features/page.tsx
    - web/app/(marketing)/pricing/page.tsx
    - web/app/(marketing)/privacy/page.tsx
    - web/app/(marketing)/compliance/page.tsx
    - web/app/(marketing)/about/page.tsx
  modified: []
  deleted: []
decisions:
  - "Breach timeline data hardcoded as static array (no API fetch) per security note in RESEARCH.md"
  - "Data flow diagram uses inline SVG with foreignObject for desktop and stacked div layout for mobile"
  - "Feature cards rendered inline on features page rather than importing FeatureCard (parallel agent builds FeatureCard in Plan 03)"
  - "All pages import Plan 03 components (FeatureComparison, ChainShowcase, PricingCard, WaitlistForm) that will resolve at merge time"
metrics:
  duration: "~9 min"
  completed: "2026-04-11"
  tasks_completed: 3
  tasks_total: 3
  files_created: 7
---

# Phase 14 Plan 04: Secondary Marketing Pages Summary

Five secondary marketing pages (features, pricing, privacy, compliance, about) plus breach timeline and data flow diagram components. All pages have SEO metadata with en_CA locale, import SectionWrapper for animations, and follow mobile-first responsive design per UI-SPEC.

## Tasks Completed

| Task | Name | Status | Files |
|------|------|--------|-------|
| 1 | Breach timeline + Data flow diagram components | DONE | breach-timeline.tsx, data-flow-diagram.tsx |
| 2 | Features + Pricing pages | DONE | features/page.tsx, pricing/page.tsx |
| 3 | Privacy + Compliance + About pages | DONE | privacy/page.tsx, compliance/page.tsx, about/page.tsx |

## Key Changes

### Task 1: Breach Timeline + Data Flow Diagram
- **breach-timeline.tsx**: 4 hardcoded breach incidents (CoinTracker Dec 2022, CoinTracker Nov 2024, Koinly Dec 2024, Waltio Jan 2025) with HaveIBeenPwned source links
  - Vertical timeline layout with destructive color date badges
  - All external links use `target="_blank" rel="noopener noreferrer"`
  - Framer Motion stagger animation (+0.1s per card)
  - useReducedMotion accessibility gate
  - Disclaimer: "Sources linked. Data from public disclosures and HaveIBeenPwned."
- **data-flow-diagram.tsx**: SVG-based architecture diagram showing data flow
  - Desktop: horizontal 3-column SVG (Your Browser, Axiom Server Toronto, External APIs) with animated connecting lines
  - Mobile: vertical stacked div layout with arrow indicators
  - Green checkmarks for local data, muted globe icons for external flows
  - Indigo accent on Axiom Server box
  - useReducedMotion gate disables path animations

### Task 2: Features + Pricing Pages
- **features/page.tsx**: SEO metadata "Features - Axiom" with en_CA locale
  - 8 feature cards (ACB compliance, superficial loss, CARF 2026, blockchain indexing, DeFi capture, AI classification, multi-chain, tax reports)
  - Automation deep-dive "They make you download CSVs. We read the blockchain directly." with 5-step numbered workflow
  - ChainShowcase and FeatureComparison component imports (from Plan 03)
  - Bottom CTA with WaitlistForm
- **pricing/page.tsx**: SEO metadata "Pricing - Axiom" with en_CA locale
  - Tagline: "One price. One tax year. No surprises."
  - PricingCard component centered
  - 4 FAQ items (What's included, Free trial, Launch date, Business use)
  - Bottom CTA with WaitlistForm

### Task 3: Privacy + Compliance + About Pages
- **privacy/page.tsx**: SEO metadata "Privacy & Security - Axiom" with en_CA locale
  - Tagline: "Your data never leaves Canada."
  - Imports BreachTimeline and DataFlowDiagram components
  - Canadian data sovereignty section (Toronto hosting, no third-party analytics, PIPEDA)
  - Future roadmap teaser (post-quantum encryption, zero-knowledge calculations, passkey-derived keys) with "planned features" disclaimer
  - Bottom CTA with WaitlistForm
- **compliance/page.tsx**: SEO metadata "CRA Compliance - Axiom" with en_CA locale
  - Tagline: "Built for Canada. CRA-ready on day one."
  - CRA ACB Method explained with inline term definitions (D-04 tone)
  - Superficial Loss Rule with proration explanation
  - CARF 2026 section explaining exchange reporting requirements
  - 6-step filing walkthrough (connect wallets -> index -> classify -> calculate -> download -> send)
  - Bottom CTA with WaitlistForm
- **about/page.tsx**: SEO metadata "About - Axiom" with en_CA locale
  - Mission statement per plan spec
  - "Built by crypto holders who got tired of broken tax tools."
  - Full roadmap (post-quantum, ZK, passkey, multi-chain expansion, exchange API, DeFi protocols)
  - Contact: hello@axiom.tax
  - Bottom CTA with WaitlistForm

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Feature cards rendered inline instead of importing FeatureCard component**
- **Found during:** Task 2
- **Issue:** FeatureCard component (from Plan 03) does not exist in this worktree since Plan 03 is built by a parallel agent
- **Fix:** Rendered feature cards inline with matching visual style (icon + title + description in bordered card). The FeatureCard import can be refactored in during merge if desired, but inline rendering is functionally complete.
- **Files modified:** web/app/(marketing)/features/page.tsx

## Blocker: Git Commit Permission

All file changes are complete and verified on disk, but git add/commit operations were systematically blocked by the sandbox permission system throughout execution. The orchestrator needs to commit these changes. This is the same issue documented in Plan 01's SUMMARY.

**Files to commit (Task 1):**
- web/components/marketing/breach-timeline.tsx
- web/components/marketing/data-flow-diagram.tsx

**Files to commit (Task 2):**
- web/app/(marketing)/features/page.tsx
- web/app/(marketing)/pricing/page.tsx

**Files to commit (Task 3):**
- web/app/(marketing)/privacy/page.tsx
- web/app/(marketing)/compliance/page.tsx
- web/app/(marketing)/about/page.tsx

## Known Stubs

None. All pages are fully implemented with real content, proper SEO metadata, and correct component imports. Pages import Plan 03 components (FeatureComparison, ChainShowcase, PricingCard, WaitlistForm) which will resolve when worktree branches are merged.

## Threat Flags

None. All changes align with the plan's threat model:
- Breach timeline data is hardcoded static content (T-14-12 mitigated)
- Data flow diagram reveals only high-level architecture, no server IPs or API keys (T-14-13 accepted)
- All breach incidents link to public HaveIBeenPwned sources (T-14-14 mitigated)
- All external links use `rel="noopener noreferrer"`

## Self-Check: PARTIAL

Cannot verify commits (git operations blocked by sandbox). File existence verified:
- web/components/marketing/breach-timeline.tsx: EXISTS (contains CoinTracker, haveibeenpwned, noopener noreferrer)
- web/components/marketing/data-flow-diagram.tsx: EXISTS (contains svg, Axiom Server, Toronto, useReducedMotion)
- web/app/(marketing)/features/page.tsx: EXISTS (metadata Features - Axiom, en_CA, FeatureComparison, ChainShowcase)
- web/app/(marketing)/pricing/page.tsx: EXISTS (metadata Pricing - Axiom, en_CA, One price, 4 FAQs)
- web/app/(marketing)/privacy/page.tsx: EXISTS (metadata Privacy & Security - Axiom, en_CA, BreachTimeline, DataFlowDiagram, post-quantum, zero-knowledge)
- web/app/(marketing)/compliance/page.tsx: EXISTS (metadata CRA Compliance - Axiom, en_CA, ACB, superficial loss, CARF)
- web/app/(marketing)/about/page.tsx: EXISTS (metadata About - Axiom, en_CA, hello@axiom.tax)
