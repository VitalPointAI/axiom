# Phase 14: Marketing Frontend - Research

**Researched:** 2026-04-10
**Domain:** Next.js marketing site, dark mode theming, animation, waitlist capture, privacy analytics
**Confidence:** HIGH

---

## Summary

Phase 14 builds a public-facing marketing website within the existing Next.js 16 app using a `(marketing)` route group. The app already uses Tailwind CSS 4, shadcn/ui components, and a media-query-based dark mode system. The marketing site must override this to deliver dark-mode-default with a user toggle, add animation (Framer Motion or CSS), collect waitlist emails, and integrate self-hosted Plausible analytics.

The main integration challenge is dark mode: the current app uses `prefers-color-scheme` media queries exclusively, with no class-based toggle. Delivering a user-selectable dark/light toggle requires adding `next-themes` (which switches between `class` strategy and `media`), updating `tailwind.config.ts` to `darkMode: 'class'`, and migrating existing CSS overrides. This migration affects the entire app, not just marketing pages, so it requires careful scoping.

The waitlist form needs a backend endpoint. The existing `users` table has an `email` column and the project already uses AWS SES for magic links, so a minimal `POST /api/waitlist` FastAPI route storing emails is the path of least resistance — no new infrastructure needed.

**Primary recommendation:** Use the `(marketing)` route group with next-themes for dark/class mode, Framer Motion for animations, react-hook-form + Zod for the waitlist form, and next-plausible for Plausible analytics integration. Backend: add a single `POST /api/waitlist` FastAPI route with a new `waitlist_signups` table.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Messaging Hierarchy**
- D-01: Lead with CRA compliance — ACB method, superficial loss with proration, CARF 2026 readiness. This is the primary hook.
- D-02: Second layer: automation advantages — direct blockchain indexing vs CSV-only competitors, DeFi-native capture, AI-powered classification.
- D-03: Third layer: privacy and Canadian data sovereignty — Toronto-hosted, planned client-side encryption, no third-party analytics.
- D-04: Tone is accessible professional — clear, jargon-light language that explains concepts as it goes.

**Competitive Positioning**
- D-05: Hybrid positioning — lead with category creation ("The first Canadian-sovereign, blockchain-native crypto tax platform") then include a feature comparison table lower on the page.
- D-06: Comparison table covers Axiom vs PrivateACB vs CoinTracker vs Koinly with honest feature-by-feature breakdown.

**Page Structure**
- D-07: Full marketing site with dedicated pages: Landing, Features, Privacy/Security, Pricing, Compliance, About.
- D-08: Lives in the same Next.js app using a `(marketing)` route group. Routes: `/`, `/features`, `/pricing`, `/privacy`, `/compliance`, `/about`.
- D-09: Current root redirect to `/auth` replaced — landing page becomes the new root `/`.

**Visual Identity & Design**
- D-10: Dark mode default with user choice toggle for light mode. System preference detection on first visit.
- D-11: Crypto-native brand personality — gradients, glows, geometric patterns. Think Uniswap/Phantom aesthetic.
- D-12: Mobile-first marketing pages.
- D-13: Standalone marketing design — no app screenshots or interactive demos in v1.

**Conversion Strategy**
- D-14: Primary CTA is "Join the waitlist" — collect emails.
- D-15: Flat annual fee pricing model. One price per tax year. No tier complexity.
- D-16: Self-hosted Plausible for analytics on DO Toronto droplet.

**Privacy & Breach Content**
- D-17: Breach timeline included with facts and sources — dates, companies, user counts, linked to public sources.
- D-18: Interactive visual component on privacy page showing what crosses the network — data flow diagram.
- D-19: Future roadmap section: post-quantum encryption, client-side ZK calculations, passkey-derived encryption keys.

**Mobile Experience**
- D-20: Marketing pages designed mobile-first. Desktop is the scale-up.

### Claude's Discretion
- Animation library choice (Framer Motion, CSS animations, etc.)
- Exact color palette and gradient choices within the crypto-native aesthetic
- Component composition and layout patterns
- SEO meta tags, structured data, and Open Graph implementation
- Form handling for waitlist sign-up
- Plausible analytics integration details

### Deferred Ideas (OUT OF SCOPE)
- App screenshots/interactive demos — revisit after app UI is more polished
- Blog/content marketing section — future phase
- Customer testimonials/case studies — need real users first
- Client-side encryption implementation — separate engineering phase
- Multi-jurisdiction support (US/UK/AUS) — future product expansion
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MKT-01 | Hero section with clear value proposition and CTA | Landing page route, Framer Motion entry animation, waitlist form integration |
| MKT-02 | Feature comparison section — Axiom vs PrivateACB vs cloud platforms | Table component, shadcn/ui Table or custom CSS grid |
| MKT-03 | Privacy & security section with breach timeline | Static data component, external source links |
| MKT-04 | Canadian data sovereignty messaging | Copy section in landing or compliance page |
| MKT-05 | Automation showcase — blockchain indexing vs CSV-only, DeFi, AI | Feature cards or iconography section |
| MKT-06 | CRA compliance section | Dedicated `/compliance` page or landing section |
| MKT-07 | Future roadmap section | `/about` or landing section, simple list/cards |
| MKT-08 | Pricing section | `/pricing` page, flat fee display |
| MKT-09 | Trust signals — security architecture diagram, transparency table | Interactive diagram component on `/privacy` |
| MKT-10 | Multi-chain support showcase | Icon grid component (NEAR, ETH, Polygon, XRP, Akash) |
| MKT-11 | Responsive design, SEO-optimized, fast load times | next/metadata API, mobile-first Tailwind, next/image |
| MKT-12 | Analytics integration (privacy-respecting) | next-plausible 4.0.0, self-hosted Plausible on DO Toronto |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | 16.1.6 (existing) | App Router, SSR, metadata API | Already installed; App Router route groups support `(marketing)` |
| Tailwind CSS | 4.2.1 (existing) | Utility styling | Already installed; needs `darkMode: 'class'` switch |
| React | 19.2.4 (existing) | Component framework | Already installed |
| next-themes | 0.4.6 | Dark/light mode toggle with class strategy | The standard solution for Next.js class-based theming |
| framer-motion | 12.38.0 | Scroll animations, entrance effects, hover states | Industry standard for React animation; supports scroll-triggered animations |
| react-hook-form | 7.72.1 | Waitlist form handling | Minimal re-renders, excellent validation UX |
| zod | 4.3.6 | Form schema validation | Type-safe validation, pairs with react-hook-form |
| next-plausible | 4.0.0 | Plausible analytics integration | Official Next.js Plausible integration, proxies requests |
| react-intersection-observer | 10.0.3 | Scroll-into-view triggers for animations | Lightweight wrapper around IntersectionObserver API |

[VERIFIED: npm registry — all versions confirmed 2026-04-10]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| lucide-react | 0.469.0 (existing) | Icons for feature cards, CTAs | Already installed |
| clsx / tailwind-merge | 2.1.1 / 2.6.0 (existing) | Conditional class merging | Already installed |
| sharp | 0.34.5 | Next.js image optimization (next/image) | Already available via Next.js; needed for hero/section images |

[VERIFIED: npm registry — versions confirmed 2026-04-10]

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| framer-motion | CSS transitions + @keyframes | CSS is lighter (0kb JS) but far less capable for complex scroll-triggered sequences; framer-motion is appropriate for a crypto-native aesthetic site |
| framer-motion | @react-spring/web 10.0.3 | Spring physics are excellent but framer-motion has better scroll-based animation primitives (`useScroll`, `useTransform`) which this site needs |
| react-hook-form | Server Actions form | RSC Server Actions work for simple forms but RHF gives better inline validation UX for email capture |
| next-plausible | Direct Plausible script tag | next-plausible proxies analytics through the same domain, preventing ad-blockers and avoiding third-party cookie issues — consistent with privacy messaging |

**Installation:**
```bash
cd web && npm install next-themes framer-motion react-hook-form zod next-plausible react-intersection-observer
```

---

## Architecture Patterns

### Recommended Project Structure
```
web/app/
├── (marketing)/              # New route group — no auth required
│   ├── layout.tsx            # Marketing layout: nav, footer, theme provider
│   ├── page.tsx              # Landing page /
│   ├── features/
│   │   └── page.tsx          # /features
│   ├── pricing/
│   │   └── page.tsx          # /pricing
│   ├── privacy/
│   │   └── page.tsx          # /privacy — breach timeline + data flow diagram
│   ├── compliance/
│   │   └── page.tsx          # /compliance — CRA/CARF details
│   └── about/
│       └── page.tsx          # /about — team, roadmap
├── (dashboard)/              # Existing dashboard route group (UNCHANGED)
│   └── dashboard/...
├── auth/                     # Existing auth pages (UNCHANGED)
├── layout.tsx                # Root layout — updated for next-themes ThemeProvider
└── page.tsx                  # REPLACE: was redirect('/auth'), now renders (marketing) landing

web/components/
├── marketing/                # New: marketing-only components
│   ├── hero.tsx
│   ├── feature-comparison.tsx
│   ├── breach-timeline.tsx
│   ├── data-flow-diagram.tsx
│   ├── pricing-card.tsx
│   ├── chain-showcase.tsx
│   ├── waitlist-form.tsx
│   ├── marketing-nav.tsx
│   └── marketing-footer.tsx
└── ui/                       # Existing shadcn/ui (unchanged)
```

### Pattern 1: Route Group Isolation
**What:** The `(marketing)` route group creates a separate layout scope from `(dashboard)`. Marketing pages get their own nav/footer without the dashboard sidebar. Auth middleware must explicitly allow all marketing routes.
**When to use:** Always — this is the Next.js App Router pattern for page groups with shared layout but separate concerns.

**Example:**
```typescript
// web/app/(marketing)/layout.tsx
// Source: Next.js App Router docs — route groups
import { ThemeProvider } from 'next-themes'
import MarketingNav from '@/components/marketing/marketing-nav'
import MarketingFooter from '@/components/marketing/marketing-footer'

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
      <MarketingNav />
      <main>{children}</main>
      <MarketingFooter />
    </ThemeProvider>
  )
}
```

### Pattern 2: Class-Based Dark Mode (Critical Migration)
**What:** The current app uses `darkMode: 'media'` in `tailwind.config.ts`. D-10 requires user-selectable dark/light toggle, which requires `darkMode: 'class'`. `next-themes` adds a `dark` class to `<html>` when dark mode is active.
**When to use:** Required — this is the only way to support a user toggle.

**Migration steps:**
1. Change `tailwind.config.ts`: `darkMode: ['class']`  (Tailwind 4 syntax is `darkMode: 'class'`)
2. Replace CSS `@media (prefers-color-scheme: dark)` overrides in `globals.css` with `.dark` class prefixes or Tailwind `dark:` utilities
3. Add `ThemeProvider` from `next-themes` to root `layout.tsx` with `attribute="class" defaultTheme="dark" enableSystem`
4. Add theme toggle component using `useTheme()` hook from `next-themes`

**Impact on existing app:** Existing dashboard dark mode CSS overrides (the `@media (prefers-color-scheme: dark)` blocks in `globals.css`) will stop working. They must be converted to `.dark` class selectors. This is a required migration — all globals.css media overrides need converting.

**Example:**
```typescript
// Before (globals.css)
@media (prefers-color-scheme: dark) {
  .bg-white { background-color: #1e293b !important; }
}

// After (globals.css)
.dark .bg-white { background-color: #1e293b !important; }
// OR — better approach: use Tailwind dark: utilities in component markup
// <div className="bg-white dark:bg-slate-800">
```

### Pattern 3: Scroll-Triggered Animations
**What:** Framer Motion `useScroll` + `useInView` to trigger entrance animations as sections scroll into view.
**When to use:** Hero entrance, feature cards, comparison table rows.

**Example:**
```typescript
// Source: Framer Motion docs — scroll animations
'use client'
import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'

export function FeatureCard({ title, description }: { title: string; description: string }) {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 20 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
    >
      <h3>{title}</h3>
      <p>{description}</p>
    </motion.div>
  )
}
```

### Pattern 4: Waitlist Form with Server Action
**What:** react-hook-form client form POSTing to a Next.js API route (`/api/waitlist`), which proxies to the FastAPI backend.
**When to use:** Waitlist CTA form (D-14).

**Example:**
```typescript
// web/app/api/waitlist/route.ts — Next.js API route proxying to FastAPI
export async function POST(request: Request) {
  const { email } = await request.json()
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/waitlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  const data = await res.json()
  return Response.json(data, { status: res.status })
}
```

### Pattern 5: SEO with Next.js Metadata API
**What:** Use `export const metadata: Metadata` in each page.tsx for static metadata. Use `generateMetadata` for dynamic.
**When to use:** All marketing pages — critical for SEO (MKT-11).

**Example:**
```typescript
// web/app/(marketing)/page.tsx
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Axiom — The First Canadian-Sovereign Crypto Tax Platform',
  description: 'CRA-compliant crypto tax reporting. ACB method, superficial loss, CARF 2026. Blockchain-native. Canadian-hosted. Privacy-first.',
  openGraph: {
    title: 'Axiom — Canadian Crypto Tax',
    description: 'The first Canadian-sovereign, blockchain-native crypto tax platform.',
    type: 'website',
    locale: 'en_CA',
  },
  twitter: { card: 'summary_large_image' },
}
```

### Pattern 6: Interactive Data Flow Diagram (D-18)
**What:** SVG-based or CSS-based flow diagram showing "what stays on Axiom server" vs "what goes to external APIs." Animated with Framer Motion or CSS transitions on hover/scroll.
**When to use:** Privacy page (MKT-09).
**Approach:** Build as a custom SVG component with motion.path or animated connection lines. No third-party diagram library needed — keeping it simple and lightweight.

### Anti-Patterns to Avoid
- **Using `@media (prefers-color-scheme: dark)` CSS after next-themes migration:** next-themes applies the `dark` class to `<html>`. Media queries for color scheme will conflict with user toggle. Convert all dark mode CSS to `.dark` class selectors.
- **Importing Framer Motion in Server Components:** All Framer Motion components require `'use client'`. Wrap only the animated sections, not entire pages.
- **Third-party analytics scripts:** No Google Analytics, Mixpanel, Hotjar, or similar. Plausible only (D-16).
- **Using `redirect()` in `(marketing)/layout.tsx`:** Marketing pages must be publicly accessible. The middleware must explicitly list marketing paths as public routes.
- **Blocking the entire layout with AuthProvider:** The root `layout.tsx` wraps everything in `AuthProvider`. Marketing pages don't need auth — `AuthProvider` doesn't redirect but it does make API calls. Verify it doesn't fire unauthenticated API requests.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dark/light mode toggle | Custom localStorage + class management | next-themes | Handles SSR hydration mismatch, system preference sync, flash-of-wrong-theme prevention |
| Scroll-triggered animations | IntersectionObserver + manual CSS class toggling | framer-motion useInView | Handles exit animations, stagger effects, reduced-motion accessibility |
| Form validation | Manual `onChange` state + regex | react-hook-form + zod | Error message coordination, touched/dirty state, async validation |
| Analytics without cookies | Hand-rolling a privacy-safe beacon | next-plausible + self-hosted Plausible | Plausible is open-source, cookieless by design, GDPR-compliant |
| Open Graph image generation | Static PNG exports | next/og (Next.js built-in) or static OG image | next/og generates dynamic OG images from JSX via Edge Runtime |

**Key insight:** Dark mode with user toggle is surprisingly complex in SSR apps — next-themes exists precisely because React hydration mismatches cause flash-of-wrong-theme bugs. Do not hand-roll.

---

## Common Pitfalls

### Pitfall 1: Flash of Wrong Theme (FOWT)
**What goes wrong:** On first page load, SSR renders with the wrong theme before React hydrates, causing a white flash on a dark-mode-default site.
**Why it happens:** The server doesn't know the user's preference; it renders the default. The client then applies the correct theme after hydration.
**How to avoid:** `next-themes` with `suppressHydrationWarning` on `<html>` and the `disableTransitionOnChange` prop during theme switch. The root `layout.tsx` already has `suppressHydrationWarning` — keep it.
**Warning signs:** Brief white flash on page load, especially on first visit.

### Pitfall 2: Middleware Blocking Marketing Routes
**What goes wrong:** The current `middleware.ts` has a hardcoded list of `publicPaths`. Marketing routes (`/features`, `/pricing`, `/privacy`, `/compliance`, `/about`) aren't in this list. The middleware currently passes them through (no session check), but future changes could accidentally redirect users to `/auth`.
**Why it happens:** The middleware explicitly checks `/dashboard` for session — all other routes pass through. But the `publicPaths` whitelist is easy to accidentally tighten.
**How to avoid:** Add marketing paths to the `publicPaths` array explicitly in `middleware.ts`. Also confirm that root `/` is public after removing the `redirect('/auth')` from `page.tsx`.

### Pitfall 3: AuthProvider Making Unauthorized API Calls
**What goes wrong:** `web/components/auth-provider.tsx` wraps all pages via root layout. If it fires API calls on mount (e.g., `GET /api/auth/me`) for every page load, marketing page visitors will generate 401s from the FastAPI backend.
**Why it happens:** Auth providers typically check session on mount.
**How to avoid:** Read `auth-provider.tsx` before implementing. If it makes API calls unconditionally, the marketing layout should either not inherit it, or use a conditional render. The route group layout CAN override — `(marketing)/layout.tsx` does not need to include `AuthProvider`.
**Warning signs:** Network errors in browser console on marketing page load.

### Pitfall 4: Tailwind v4 darkMode Syntax
**What goes wrong:** Tailwind CSS v4 changed some configuration API. The `darkMode` config key may behave differently.
**Why it happens:** The project uses Tailwind CSS 4.2.1 — released ~2025. Some online docs still show v3 syntax.
**How to avoid:** The existing `tailwind.config.ts` already uses `darkMode: 'media'` successfully in v4 syntax. Changing to `darkMode: ['class']` or `darkMode: 'class'` is the v4-compatible approach. Verify with Tailwind v4 docs. [ASSUMED — verify Tailwind v4 class-mode syntax]

### Pitfall 5: Framer Motion Bundle Size
**What goes wrong:** Importing all of `framer-motion` significantly inflates the JS bundle — the full library is ~100KB gzipped.
**Why it happens:** framer-motion v12 ships as `motion` package with tree-shaking support.
**How to avoid:** Use `motion` (the renamed package alias) with named imports. All animated components must be `'use client'` — colocate them to minimize SSR overhead. Use `LazyMotion` with `domAnimation` feature bundle for marketing pages.

### Pitfall 6: next-plausible Self-Hosted Configuration
**What goes wrong:** next-plausible defaults to sending analytics to `plausible.io`. For self-hosted Plausible, you must configure `domain` and `customDomain`.
**Why it happens:** Configuration is per-instance.
**How to avoid:** 
```typescript
// web/app/(marketing)/layout.tsx
import PlausibleProvider from 'next-plausible'

<PlausibleProvider domain="axiom.tax" customDomain="https://analytics.axiom.tax">
  {children}
</PlausibleProvider>
```
The `customDomain` must point to the self-hosted Plausible instance on DO Toronto. [ASSUMED — Plausible must be running on DO droplet before this integration will report data]

### Pitfall 7: Cache-Control Headers Break Marketing SEO
**What goes wrong:** The existing `next.config.mjs` sets `Cache-Control: no-store, must-revalidate` on ALL routes. This is catastrophic for marketing page performance and SEO — it disables all browser and CDN caching.
**Why it happens:** Was added as a workaround for auth cache issues (comment in config: "Force cache busting for the auth fix").
**How to avoid:** Override cache headers for marketing pages to allow caching (e.g., `s-maxage=3600, stale-while-revalidate`). This requires path-conditional headers in `next.config.mjs`:
```javascript
async headers() {
  return [
    {
      source: '/(features|pricing|privacy|compliance|about|)',
      headers: [{ key: 'Cache-Control', value: 's-maxage=3600, stale-while-revalidate=86400' }],
    },
    {
      source: '/:path*',  // everything else stays no-store
      headers: [{ key: 'Cache-Control', value: 'no-store, must-revalidate' }],
    },
  ]
}
```
[VERIFIED: codebase — `next.config.mjs` confirmed to have blanket no-store header]

---

## Code Examples

### Dark Mode Toggle Component
```typescript
// Source: next-themes docs + shadcn/ui pattern
'use client'
import { useTheme } from 'next-themes'
import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      aria-label="Toggle theme"
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  )
}
```

### Waitlist Form Component
```typescript
// Source: react-hook-form docs + zod docs
'use client'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const waitlistSchema = z.object({
  email: z.string().email('Enter a valid email address'),
})

type WaitlistInput = z.infer<typeof waitlistSchema>

export function WaitlistForm() {
  const { register, handleSubmit, formState: { errors, isSubmitting }, reset } = useForm<WaitlistInput>({
    resolver: zodResolver(waitlistSchema),
  })

  const onSubmit = async (data: WaitlistInput) => {
    const res = await fetch('/api/waitlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (res.ok) reset()
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <input {...register('email')} type="email" placeholder="your@email.com" />
      {errors.email && <span>{errors.email.message}</span>}
      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Joining...' : 'Join the waitlist'}
      </button>
    </form>
  )
}
```

### Staggered Feature Cards (Framer Motion)
```typescript
// Source: Framer Motion docs — stagger children
'use client'
import { motion } from 'framer-motion'

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
}

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

export function FeatureGrid({ features }: { features: { title: string; desc: string }[] }) {
  return (
    <motion.div
      variants={container}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true }}
      className="grid grid-cols-1 md:grid-cols-3 gap-6"
    >
      {features.map((f) => (
        <motion.div key={f.title} variants={item} className="...">
          <h3>{f.title}</h3>
          <p>{f.desc}</p>
        </motion.div>
      ))}
    </motion.div>
  )
}
```

### Crypto-Native Gradient CSS Pattern
```css
/* Uniswap/Phantom-inspired gradient approach — verified by visual inspection of those sites */
/* Place in globals.css or as Tailwind @layer utilities */
.gradient-text {
  background: linear-gradient(135deg, #7c3aed 0%, #2563eb 50%, #0ea5e9 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.glow-border {
  border: 1px solid transparent;
  background: linear-gradient(#0f172a, #0f172a) padding-box,
              linear-gradient(135deg, #7c3aed, #2563eb) border-box;
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `darkMode: 'class'` with manual toggle | `next-themes` library | ~2022 | Solves SSR hydration flash, system preference detection built-in |
| Manual IntersectionObserver | `framer-motion` `useInView` / `whileInView` | Framer Motion v6+ | Declarative, handles reduced-motion, exit animations |
| Custom analytics with cookies | Self-hosted Plausible / cookieless analytics | ~2021 | GDPR-compliant, no consent banner needed |
| `export default` metadata object | Next.js `metadata` API / `generateMetadata` | Next.js 13+ (App Router) | Type-safe, per-page/layout metadata, automatic OG tag injection |
| `<Head>` component (pages router) | `export const metadata` in layout/page | Next.js 13+ | Pages Router is deprecated for new projects |

**Deprecated/outdated:**
- `next/head` (Pages Router): Not used in App Router. Use `metadata` exports instead.
- `darkMode: 'media'` (current): Must be replaced with `darkMode: 'class'` to support user toggle (D-10).
- `@media (prefers-color-scheme: dark)` CSS blocks in `globals.css`: 60+ lines of overrides that must be converted to `.dark` class selectors after the dark mode migration.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Tailwind CSS v4 `darkMode: 'class'` syntax works the same as v3 | Architecture Patterns, Pattern 2 | If v4 changed syntax, dark mode migration may produce unexpected results |
| A2 | Self-hosted Plausible is already running on DO Toronto droplet (D-16) | Environment Availability | next-plausible will silently send data nowhere if Plausible isn't deployed |
| A3 | A new `waitlist_signups` table is needed in PostgreSQL | Architecture Patterns, Pattern 4 | If the existing `users` table is used instead, migration script is different |
| A4 | `AuthProvider` in root layout does not make unconditional API calls that 401 on marketing pages | Common Pitfalls | If it does, all marketing page loads generate backend errors |

---

## Open Questions

1. **Is Plausible already deployed on the DO Toronto droplet?**
   - What we know: D-16 specifies self-hosted Plausible on DO Toronto droplet.
   - What's unclear: No docker-compose service for Plausible found in production config. May need a separate deployment step.
   - Recommendation: Plan a Wave 0 task to verify/deploy Plausible before the analytics integration task. Analytics can be wired up with a placeholder domain and activated when Plausible is live.

2. **Does waitlist storage go in the existing `users` table or a new `waitlist_signups` table?**
   - What we know: `users` table has an `email` column. The product isn't fully public — waitlist emails are pre-signup.
   - What's unclear: Whether waitlist emails become user accounts automatically or remain a separate list.
   - Recommendation: Use a separate `waitlist_signups` table (email, created_at, source). Keeps separation of concerns; no user account is created until the user actually signs up.

3. **Does the dark mode migration break existing dashboard styling?**
   - What we know: `globals.css` has ~60+ lines of `@media (prefers-color-scheme: dark)` overrides using `!important` for Tailwind class overrides. These will stop working after switching to `darkMode: 'class'`.
   - What's unclear: How many dashboard components rely on these media query overrides vs Tailwind `dark:` utilities.
   - Recommendation: Convert all `@media (prefers-color-scheme: dark)` blocks in `globals.css` to `.dark` class selectors in the same migration. This is a single-file change but must be tested in the dashboard.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Frontend build | ✓ (WSL system) | v12.22.9 (system) — Docker uses Node 20 | Build runs in Docker container, not host |
| Docker | Build + deployment | ✓ | 29.2.1 | — |
| Next.js | Marketing pages | ✓ | 16.1.6 (in web/package.json) | — |
| Tailwind CSS | Styling | ✓ | 4.2.1 (in web/package.json) | — |
| framer-motion | Animations | ✗ | Not installed | npm install in Wave 0 |
| next-themes | Dark mode toggle | ✗ | Not installed | npm install in Wave 0 |
| react-hook-form | Waitlist form | ✗ | Not installed | npm install in Wave 0 |
| zod | Form validation | ✗ | Not installed | npm install in Wave 0 |
| next-plausible | Analytics | ✗ | Not installed | npm install in Wave 0 |
| react-intersection-observer | Scroll triggers | ✗ | Not installed | npm install in Wave 0 |
| Plausible instance (DO Toronto) | Analytics reporting | Unknown | — | Wire up, activate when deployed |
| AWS SES | Waitlist confirmation email (optional) | ✓ | Already configured in FastAPI | Omit confirmation email if not needed |

[VERIFIED: codebase — package.json confirmed for existing deps; npm registry confirmed for new dep versions]

**Missing dependencies with no fallback:**
- All new npm packages (framer-motion, next-themes, react-hook-form, zod, next-plausible, react-intersection-observer) — all installable via `npm install`, no blockers.

**Missing dependencies with fallback:**
- Plausible instance — analytics calls will 404 until deployed. Not blocking for frontend build.

---

## Validation Architecture

`workflow.nyquist_validation` is absent from config.json — treated as enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | No frontend test framework detected in web/ |
| Config file | None — Wave 0 must establish if tests are required |
| Quick run command | `cd web && npm run lint` (lint is the only automated check) |
| Full suite command | `cd web && npm run build` (build validation) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MKT-01 | Hero renders with CTA | visual/manual | `npm run build` (build-time check) | ❌ Wave 0 |
| MKT-08 | Pricing page renders | smoke | `npm run build` | ❌ Wave 0 |
| MKT-11 | SEO metadata present | manual/lint | `npm run build` (TypeScript type check) | ❌ Wave 0 |
| MKT-12 | Analytics script loads | manual | Browser DevTools | N/A |
| Waitlist form | Email validation | unit | No test infra | ❌ Wave 0 |

**Note:** The web/ directory has no `*.test.ts` or `*.spec.ts` files and no Jest/Vitest config. Marketing pages are primarily visual — the build (`npm run build`) and lint (`npm run lint`) serve as the automated quality gate. Manual browser testing covers the visual/interactive requirements.

### Sampling Rate
- **Per task commit:** `cd web && npm run lint`
- **Per wave merge:** `cd web && npm run build`
- **Phase gate:** Full build green + manual browser check before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `npm install` of new dependencies in `web/` — required before any marketing component can be built
- [ ] `tailwind.config.ts` updated: `darkMode: 'class'`
- [ ] `globals.css` migrated: all `@media (prefers-color-scheme: dark)` blocks converted to `.dark` class selectors
- [ ] Root `layout.tsx` updated: add `ThemeProvider` from next-themes
- [ ] `middleware.ts` updated: add marketing routes to `publicPaths`
- [ ] `web/app/page.tsx` updated: replace `redirect('/auth')` with marketing landing page
- [ ] FastAPI `POST /api/waitlist` endpoint created
- [ ] Alembic migration for `waitlist_signups` table

---

## Security Domain

`security_enforcement` is absent from config.json — treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Marketing pages are public — no auth |
| V3 Session Management | No | Marketing pages have no sessions |
| V4 Access Control | Yes | Middleware must not accidentally protect marketing routes |
| V5 Input Validation | Yes | Waitlist email: zod schema validation on client + FastAPI Pydantic on server |
| V6 Cryptography | No | No crypto operations on marketing pages |

### Known Threat Patterns for Marketing + Waitlist Form

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Waitlist spam / email harvesting abuse | Spoofing | Rate limit `POST /api/waitlist` with slowapi (already installed in FastAPI) |
| Email injection in waitlist form | Tampering | Pydantic `EmailStr` validation on FastAPI endpoint; zod on client |
| Open redirect via marketing CTA | Spoofing | CTAs link to `/auth` (same domain) — no external redirect |
| Analytics fingerprinting | Privacy | Plausible is cookieless and IP-anonymized by default |
| XSS via breach timeline content | Tampering | Breach timeline is static hardcoded data, not user-generated — no XSS risk |

**Security note on breach timeline (D-17):** The breach timeline section must be static hardcoded data (not fetched from an API or CMS) to avoid any injection surface. All source links must use `rel="noopener noreferrer"`.

---

## Sources

### Primary (HIGH confidence)
- Codebase — `web/package.json`, `web/tailwind.config.ts`, `web/app/globals.css`, `web/middleware.ts`, `web/next.config.mjs` — direct file inspection
- npm registry (via curl) — confirmed versions: framer-motion 12.38.0, next-themes 0.4.6, react-hook-form 7.72.1, zod 4.3.6, next-plausible 4.0.0, react-intersection-observer 10.0.3
- Codebase — `db/migrations/versions/006_auth_schema.py` — users table email column confirmed

### Secondary (MEDIUM confidence)
- Next.js App Router documentation pattern — route groups `(marketing)` follow established App Router conventions [ASSUMED training knowledge, standard Next.js pattern]
- next-themes documentation — `ThemeProvider attribute="class"` pattern is the documented approach for class-based dark mode

### Tertiary (LOW confidence)
- Tailwind CSS v4 `darkMode: 'class'` syntax — assumed same as v3 based on training knowledge; v4 docs should be confirmed before implementation [A1]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions npm-registry-verified
- Architecture: HIGH — based on direct codebase inspection + established Next.js patterns
- Pitfalls: HIGH for FOWT, cache headers, middleware (all verified in codebase); MEDIUM for Tailwind v4 dark mode syntax (not verified against v4 docs)
- Waitlist backend: HIGH — SES + Pydantic + Alembic patterns all confirmed in existing codebase

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (npm packages stable; Next.js / framer-motion move fast but 30 days is safe for planning)
