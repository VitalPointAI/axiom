# Phase 14: Marketing Frontend - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-10
**Phase:** 14-marketing-frontend
**Areas discussed:** Messaging Hierarchy, Page Structure, Visual Identity, Conversion Strategy, Privacy Content, Mobile Experience

---

## Messaging Hierarchy

| Option | Description | Selected |
|--------|-------------|----------|
| Privacy-first lead | "Your crypto tax data is a target. Axiom keeps it in Canada, encrypted, under your control." | |
| Automation-first lead | "Stop downloading CSVs. Axiom reads the blockchain directly." | |
| Compliance-first lead | "CRA-ready crypto taxes. ACB, superficial loss, CARF 2026 — handled." | ✓ |

**User's choice:** Compliance-first lead
**Notes:** User selected without hesitation. Compliance is the primary pain point for Canadian crypto users.

---

## Tone

| Option | Description | Selected |
|--------|-------------|----------|
| Technical credibility | Data-driven, precise language for crypto-savvy users | |
| Accessible professional | Clear, jargon-light, explains concepts as it goes | ✓ |
| Privacy-activist edge | Direct, confrontational, names breaches | |

**User's choice:** Accessible professional

---

## Competitive Positioning

| Option | Description | Selected |
|--------|-------------|----------|
| Direct comparison table | Side-by-side feature matrix naming competitors | |
| Category creation | Define new category, don't compare directly | |
| Hybrid | Category-first lead, comparison table lower on page | ✓ |

**User's choice:** Hybrid

---

## Page Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Single landing page | One long-scroll page, fastest to build | |
| Landing + 2-3 subpages | Landing plus Features, Privacy, Pricing | |
| Full marketing site | Landing, Features, Privacy, Pricing, Compliance, About | ✓ |

**User's choice:** Full marketing site

---

## Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Same Next.js app (route group) | (marketing) route group alongside (dashboard) | ✓ |
| Separate subdomain/repo | Independent deploy cycle | |

**User's choice:** Same Next.js app

---

## Visual Theme

| Option | Description | Selected |
|--------|-------------|----------|
| Dark mode default | Dark backgrounds, crypto-native feel | ✓ (with toggle) |
| Light mode default | Clean white, traditional finance feel | |
| Dark hero, light content | Mixed approach | |

**User's choice:** Dark mode default with user choice toggle for light mode
**Notes:** User specified "support user choice of dark or light mode"

---

## Brand Personality

| Option | Description | Selected |
|--------|-------------|----------|
| Fintech trust | Clean, minimal, Stripe/Wealthsimple | |
| Crypto-native | Gradients, glows, Uniswap/Phantom aesthetic | ✓ |
| Security fortress | Shield/lock motifs, 1Password/Cloudflare feel | |
| Canadian clean | Warm neutrals, Shopify-like | |

**User's choice:** Crypto-native

---

## Primary CTA

| Option | Description | Selected |
|--------|-------------|----------|
| Free sign-up | Direct to app | |
| Waitlist | Collect emails, build anticipation | ✓ |
| Free trial with pricing | Implies paid product with trial | |

**User's choice:** Waitlist

---

## Pricing Model

| Option | Description | Selected |
|--------|-------------|----------|
| Free tier + paid | Freemium conversion | |
| Flat annual fee | One price per tax year | ✓ |
| Show pricing later | Don't include yet | |

**User's choice:** Flat annual fee

---

## Analytics

| Option | Description | Selected |
|--------|-------------|----------|
| Self-hosted Plausible | Privacy-respecting, no cookies, self-hosted | ✓ |
| No analytics | Zero tracking | |
| Umami (self-hosted) | Similar to Plausible, more features | |

**User's choice:** Self-hosted Plausible

---

## Breach Timeline Presentation

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated section | Full timeline naming competitors directly | |
| Subtle reference | Mention breaches without naming companies | |
| Facts with sources | Timeline with links to public sources | ✓ |

**User's choice:** Facts with sources

---

## Transparency Table

| Option | Description | Selected |
|--------|-------------|----------|
| On privacy page only | Detailed breakdown on dedicated page | |
| On both landing and privacy | Summary on landing, full on privacy | |
| Interactive component | Visual data flow diagram | ✓ (on privacy page) |

**User's choice:** Interactive component on the privacy page
**Notes:** User specified both "on privacy page" and "interactive component"

---

## Mobile Experience

| Option | Description | Selected |
|--------|-------------|----------|
| Mobile-first design | Design mobile first, scale up | |
| Responsive desktop-led | Desktop first, ensure mobile works | |
| Mobile-first marketing, desktop-first app | Marketing optimized for mobile, app for desktop | ✓ |

**User's choice:** Mobile-first marketing, desktop-first app
**Notes:** User clarified that while app is desktop-first, it should still be fully usable friction-free on mobile.

---

## App Preview

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone marketing | No app screenshots or previews | ✓ |
| App screenshots/demos | Include screenshots and animated demos | |
| Interactive demo | Embed limited interactive demo | |

**User's choice:** Standalone marketing

---

## Claude's Discretion

- Animation library choice
- Exact color palette within crypto-native aesthetic
- Component composition and layout patterns
- SEO implementation details
- Form handling for waitlist
- Plausible integration details

## Deferred Ideas

- App screenshots/interactive demos — revisit after UI polish
- Blog/content marketing — future SEO phase
- Customer testimonials — need real users
- Client-side encryption — separate engineering phase
- Multi-jurisdiction support — future product expansion
