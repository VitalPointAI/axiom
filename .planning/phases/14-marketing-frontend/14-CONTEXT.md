# Phase 14: Marketing Frontend - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a full public-facing marketing website within the existing Next.js app that positions Axiom as the first Canadian-sovereign, blockchain-native crypto tax platform. Drive waitlist sign-ups through compliance-first messaging, privacy differentiation, and automation showcases.

</domain>

<decisions>
## Implementation Decisions

### Messaging Hierarchy
- **D-01:** Lead with CRA compliance — ACB method, superficial loss with proration, CARF 2026 readiness. This is the primary hook.
- **D-02:** Second layer: automation advantages — direct blockchain indexing vs CSV-only competitors, DeFi-native capture, AI-powered classification.
- **D-03:** Third layer: privacy and Canadian data sovereignty — Toronto-hosted, planned client-side encryption, no third-party analytics.
- **D-04:** Tone is accessible professional — clear, jargon-light language that explains concepts as it goes. Appeals to anyone who owns crypto and needs to file taxes in Canada.

### Competitive Positioning
- **D-05:** Hybrid positioning — lead with category creation ("The first Canadian-sovereign, blockchain-native crypto tax platform") then include a feature comparison table lower on the page for users who want specifics.
- **D-06:** Comparison table covers Axiom vs PrivateACB vs CoinTracker vs Koinly with honest feature-by-feature breakdown.

### Page Structure
- **D-07:** Full marketing site with dedicated pages: Landing, Features, Privacy/Security, Pricing, Compliance, About.
- **D-08:** Lives in the same Next.js app as the dashboard using a `(marketing)` route group. Marketing pages serve from `/`, `/features`, `/pricing`, `/privacy`, `/compliance`, `/about`.
- **D-09:** Current root redirect to `/auth` replaced — landing page becomes the new root `/`.

### Visual Identity & Design
- **D-10:** Dark mode default with user choice toggle for light mode. System preference detection on first visit.
- **D-11:** Crypto-native brand personality — gradients, glows, geometric patterns. Think Uniswap/Phantom aesthetic. Feels cutting-edge and modern.
- **D-12:** Mobile-first marketing pages (people browse on phones from crypto community links). The app itself is desktop-first but must be fully usable friction-free on mobile.
- **D-13:** Standalone marketing design — no app screenshots or interactive demos in v1. Sells the vision and benefits. Users discover the app after sign-up.

### Conversion Strategy
- **D-14:** Primary CTA is "Join the waitlist" — collect emails, build anticipation. Product isn't fully public-ready yet.
- **D-15:** Flat annual fee pricing model displayed on the pricing page. One price per tax year. Simple, no tiers complexity.
- **D-16:** Self-hosted Plausible for analytics. Privacy-respecting, GDPR-compliant, no cookies. Consistent with privacy messaging. Deployed on the DO Toronto droplet.

### Privacy & Breach Content
- **D-17:** Breach timeline included with facts and sources — dates, companies, user counts, linked to public sources (Have I Been Pwned, news articles). Factual and defensible, not aggressive.
- **D-18:** "What crosses the network" transparency displayed as an interactive visual component on the privacy page — data flow diagram showing what stays on server, what goes to price APIs, what user controls.
- **D-19:** Future roadmap section highlights planned post-quantum encryption, client-side zero-knowledge calculations, passkey-derived encryption keys.

### Mobile Experience
- **D-20:** Marketing pages designed mobile-first. Desktop is the scale-up, not the other way around. Crypto community traffic comes from Twitter/X, Discord, Telegram — all mobile.

### Claude's Discretion
- Animation library choice (Framer Motion, CSS animations, etc.)
- Exact color palette and gradient choices within the crypto-native aesthetic
- Component composition and layout patterns
- SEO meta tags, structured data, and Open Graph implementation
- Form handling for waitlist sign-up
- Plausible analytics integration details

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing App Structure
- `web/app/layout.tsx` — Root layout, theme provider, font loading
- `web/app/page.tsx` — Current root redirect (will be replaced)
- `web/components/ui/` — Existing shadcn/ui components (card, button, badge, input, label)
- `web/app/globals.css` — Tailwind CSS config, custom properties, theme variables

### Stack & Conventions
- `.planning/codebase/STACK.md` — Next.js 16, Tailwind CSS 4, shadcn/ui
- `.planning/codebase/CONVENTIONS.md` — Code patterns and style guide
- `.planning/codebase/STRUCTURE.md` — Project file organization

### Phase Requirements
- `.planning/ROADMAP.md` §Phase 14 — Full requirements list (MKT-01 through MKT-12)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `web/components/ui/card.tsx` — Card component with shadow/rounded variants
- `web/components/ui/button.tsx` — Button with variants (default, outline, ghost, etc.)
- `web/components/ui/badge.tsx` — Badge for labels and tags
- `web/components/auth-provider.tsx` — Auth context (marketing pages won't need this but layout shares it)

### Established Patterns
- App Router with route groups: `(dashboard)` exists, `(marketing)` follows same pattern
- Tailwind CSS 4 with CSS custom properties for theming
- shadcn/ui component library for base UI elements

### Integration Points
- `web/app/layout.tsx` — Root layout wraps all route groups
- `web/app/auth/` — Auth flow that waitlist CTA should link to
- Nginx proxy on port 3003 — serves all routes through Docker compose

</code_context>

<specifics>
## Specific Ideas

- PrivateACB breach timeline (CoinTracker Dec 2022 + Nov 2025, Koinly Dec 2025, Waltio Jan 2026, French tax office 2025-2026) as a factual, sourced section
- "The first Canadian-sovereign, blockchain-native crypto tax platform" as category-defining tagline
- Interactive data flow diagram showing what stays local vs what crosses the network
- Competitor comparison: "They make you download CSVs. We read the blockchain directly."
- Future roadmap teaser: post-quantum encryption, zero-knowledge tax calculations, passkey-derived keys

</specifics>

<deferred>
## Deferred Ideas

- App screenshots/interactive demos — revisit after the app UI is more polished
- Blog/content marketing section — future phase for SEO content strategy
- Customer testimonials/case studies — need real users first
- Client-side encryption implementation — separate engineering phase (discussed in conversation, not marketing-phase scope)
- Multi-jurisdiction support (US/UK/AUS) — future product expansion

</deferred>

---

*Phase: 14-marketing-frontend*
*Context gathered: 2026-04-10*
