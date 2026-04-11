# Phase 14 — Image Asset Specifications

> Detailed specs for each image asset needed for the Axiom marketing site.
> Provide each spec below to an AI image generator to produce the asset.

---

## Brand Context (include with every prompt)

**Axiom** is a Canadian-sovereign, blockchain-native crypto tax platform. The brand aesthetic is crypto-native (think Uniswap, Phantom Wallet) — dark-first, gradient accents, clean and modern. The primary accent is an indigo-to-purple-to-cyan gradient (`#6366f1 → #8b5cf6 → #06b6d4`). Typography is Inter. The tone is professional but approachable — not corporate, not meme-y.

---

## 1. Axiom Logomark (Icon)

**Filename:** `axiom-logomark.svg` (also export as `axiom-logomark-512.png` at 512x512)
**Usage:** Favicon, app icon, social avatar, nav bar (small sizes)

### Prompt

Create a minimal, geometric logomark for "Axiom", a Canadian crypto tax platform. The mark should work at sizes from 16x16 to 512x512.

**Design direction:**
- Abstract geometric shape — NOT a literal letter "A", NOT a maple leaf, NOT a cryptocurrency coin
- Inspired by the concept of an "axiom" (a self-evident truth, a foundational principle) — consider: intersecting planes, a crystalline structure, converging lines that suggest precision and certainty
- Should feel like it belongs alongside Uniswap's unicorn, Phantom's ghost, or Stripe's forward slash — simple, ownable, immediately recognizable
- Single shape, not a wordmark — must be legible as a 16x16 favicon

**Colors:**
- Primary version: indigo-to-purple gradient fill (`#6366f1` to `#8b5cf6`)
- Monochrome version: solid white (for dark backgrounds) and solid `#1a1a2e` (for light backgrounds)

**Style:**
- Flat design, no 3D effects, no drop shadows, no skeuomorphism
- Clean vector lines, geometric precision
- Should feel mathematical/precise, not organic/handdrawn
- Rounded corners optional but subtle (2-4px radius at 512px scale)

**Deliverables:** SVG (vector), PNG at 512x512, PNG at 192x192, PNG at 32x32, ICO at 16x16

---

## 2. Axiom Wordmark (Logo + Text)

**Filename:** `axiom-logo-full.svg`
**Usage:** Nav bar (desktop), footer, email headers, documentation

### Prompt

Create a horizontal wordmark for "Axiom" that pairs with the logomark from spec #1.

**Design direction:**
- The logomark icon sits to the left, "Axiom" text to the right — horizontal lockup
- Text is set in Inter Bold (700 weight), tracking slightly tightened (-0.02em)
- The "x" in Axiom may optionally use the accent gradient as a subtle brand element (the cross of the x picks up the indigo-to-purple gradient), but only if it doesn't look forced — solid color is fine too
- Total aspect ratio approximately 4:1 (wide and short)

**Colors:**
- Dark background version: white text + gradient logomark
- Light background version: near-black (`#0f172a`) text + gradient logomark
- Monochrome versions of each

**Size:** Design at 400x100 canvas, ensure it's sharp at 200x50 minimum

**Deliverables:** SVG (vector), PNG at 400x100 (2x for retina: 800x200)

---

## 3. Open Graph / Social Share Image

**Filename:** `og-default.png`
**Usage:** Default OG image for all pages when shared on Twitter/LinkedIn/Facebook/Slack. Referenced by `twitter: { card: 'summary_large_image' }` meta tag.

### Prompt

Create an Open Graph social share image for Axiom, a Canadian crypto tax platform.

**Dimensions:** 1200x630 pixels (standard OG image size)

**Layout:**
- Dark background matching the site's dominant color: near-black navy (`hsl(222.2, 84%, 4.9%)` ≈ `#020817`)
- Axiom logomark + wordmark centered in the upper-third of the image
- Below the logo: the tagline "The first Canadian-sovereign, blockchain-native crypto tax platform." in white Inter Bold, 32-40px, centered
- Subtle background elements: the brand gradient glow (indigo/purple, `rgba(99, 102, 241, 0.15)`) as a soft radial wash behind the text — ambient, not overwhelming
- Optional: faint geometric grid pattern at 5% opacity in the background for crypto-native texture
- Bottom of image: small "axiom.tax" URL in muted text (`hsl(215, 20%, 65%)`)

**Style:**
- Clean, high contrast text on dark background
- Professional but crypto-native — this will appear in Twitter/LinkedIn previews
- No photos, no stock imagery, no illustrations of people
- Text must be large enough to read in a small Twitter card preview (~400px wide)

**Deliverables:** PNG at 1200x630

---

## 4. Hero Background Pattern (Optional Texture)

**Filename:** `hero-pattern.svg`
**Usage:** Subtle background texture behind the hero section, rendered at 5-10% opacity

### Prompt

Create a seamless, tileable geometric pattern for the background of a crypto tax platform's hero section.

**Design direction:**
- Geometric grid/mesh pattern — think: isometric grid, blockchain-node network, or subtle hexagonal tessellation
- Lines and nodes, not filled shapes — wireframe aesthetic
- Should feel like "the structure behind data" or "a network of connected calculations"
- NOT literal blockchain imagery (no chain links, no Bitcoin symbols)
- Pattern tile size: 200x200px, seamlessly repeating

**Colors:**
- Single color: white (`#ffffff`) — the component will apply opacity (5-10%) and the dark/light theme handles contrast
- Stroke weight: 0.5-1px at the 200x200 tile size

**Style:**
- Minimal, precise, mathematical
- Low visual density — more negative space than pattern
- Must not distract from overlaid text at any opacity from 3-15%

**Deliverables:** SVG (tileable), PNG at 200x200 (tileable)

---

## 5. Chain Logo Set (Blockchain Icons)

**Filename:** `chains/near.svg`, `chains/ethereum.svg`, `chains/polygon.svg`, `chains/xrp.svg`, `chains/akash.svg`
**Usage:** Chain showcase section on landing page and features page

### Important Note

These are official blockchain brand assets. **Do NOT generate these with AI.** Instead, download official logos from:

- **NEAR:** https://near.org/brand — official N mark
- **Ethereum:** https://ethereum.org/en/assets/ — diamond mark
- **Polygon:** https://polygon.technology/brand-kit — purple mark
- **XRP (Ripple):** https://ripple.com/brand-assets/ — XRP mark
- **Akash:** https://akash.network — red cloud mark

Download SVG versions from official sources. If SVG not available, use high-res PNG (minimum 128x128) and run through an SVG tracer.

**Sizing:** Normalize all to 48x48 viewBox with consistent padding. Monochrome versions (white for dark theme) are also needed.

---

## 6. Favicon Set (Multi-size)

**Filename:** `favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`, `apple-touch-icon.png`, `android-chrome-192x192.png`, `android-chrome-512x512.png`
**Usage:** Browser tabs, bookmarks, mobile home screen icons

### Prompt

Use the logomark from Spec #1 and export at the following sizes:

| File | Size | Notes |
|------|------|-------|
| `favicon.ico` | 16x16, 32x32 (multi-size ICO) | For legacy browser tabs |
| `favicon-16x16.png` | 16x16 | Modern browsers |
| `favicon-32x32.png` | 32x32 | Retina browser tabs |
| `apple-touch-icon.png` | 180x180 | iOS home screen — add 20px padding, solid dark background (`#020817`) |
| `android-chrome-192x192.png` | 192x192 | Android home screen — solid dark background |
| `android-chrome-512x512.png` | 512x512 | Android splash — solid dark background |

**Background:** For apple-touch-icon and android-chrome sizes, place the logomark on a solid dark navy background (`#020817`) with the gradient-colored logomark centered. Do NOT use a transparent background for these — mobile OSes render transparent poorly.

**Deliverables:** All files listed above. Also generate a `site.webmanifest`:
```json
{
  "name": "Axiom",
  "short_name": "Axiom",
  "icons": [
    { "src": "/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png" }
  ],
  "theme_color": "#020817",
  "background_color": "#020817",
  "display": "standalone"
}
```

---

## 7. Page-Specific OG Images (Optional, High-Value)

These are optional but significantly improve social sharing. Each follows the same template as Spec #3 but with page-specific text.

### 7a. Features OG Image
**Filename:** `og-features.png` (1200x630)
**Text:** "Direct blockchain indexing. AI-powered classification. Multi-chain support." below the Axiom logo

### 7b. Privacy OG Image
**Filename:** `og-privacy.png` (1200x630)
**Text:** "Your crypto tax data stays in Canada." below the Axiom logo
**Optional accent:** A subtle shield or lock icon in the gradient color, placed beside the text

### 7c. Pricing OG Image
**Filename:** `og-pricing.png` (1200x630)
**Text:** "One price. One tax year. No surprises." below the Axiom logo

### 7d. Compliance OG Image
**Filename:** `og-compliance.png` (1200x630)
**Text:** "Built for Canada. CRA-ready on day one." below the Axiom logo

### 7e. About OG Image
**Filename:** `og-about.png` (1200x630)
**Text:** "Building the first Canadian-sovereign, blockchain-native crypto tax platform." below the Axiom logo

---

## Summary: All Assets Needed

| # | Asset | Priority | AI-Generate? | Sizes |
|---|-------|----------|-------------|-------|
| 1 | Logomark | **Critical** | Yes | SVG, 512/192/32/16 PNG, ICO |
| 2 | Wordmark | **Critical** | Yes | SVG, 800x200 PNG |
| 3 | Default OG image | **High** | Yes | 1200x630 PNG |
| 4 | Hero background pattern | Low | Yes | SVG 200x200 tile |
| 5 | Chain logos | **High** | **No** — download official | SVG, 48x48 |
| 6 | Favicon set | **Critical** | Derived from #1 | Multiple sizes |
| 7a-e | Page OG images | Low | Yes | 1200x630 PNG each |

### File Placement
All assets go in `web/public/`:
```
web/public/
  axiom-logomark.svg
  axiom-logo-full.svg
  og-default.png
  og-features.png       (optional)
  og-privacy.png        (optional)
  og-pricing.png        (optional)
  og-compliance.png     (optional)
  og-about.png          (optional)
  hero-pattern.svg      (optional)
  favicon.ico
  favicon-16x16.png
  favicon-32x32.png
  apple-touch-icon.png
  android-chrome-192x192.png
  android-chrome-512x512.png
  site.webmanifest
  chains/
    near.svg
    ethereum.svg
    polygon.svg
    xrp.svg
    akash.svg
```
