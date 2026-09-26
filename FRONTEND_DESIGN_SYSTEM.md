# AlgoProfitX — Proposed Design System
> Phase 1 design proposal · September 2026 · For review before implementation

---

## Design Intent

AlgoProfitX is a **systematic trading research platform**. The visual language must communicate:

> **Precision · Trust · Intelligence · Performance**

This is not a consumer fintech app or a SaaS landing page tool. The target user is methodical — they care about accuracy, explainability, and control. The design should feel like a **professional analytical instrument**, not a polished startup product.

**Tone:**
- Restrained, not flashy
- Data-dense but readable, not cluttered
- Dark-first (trading UIs live in dark environments)
- Typography-led, not graphic-led
- Honest about simulation boundaries (no misleading visual prominence for unverified data)

---

## 1. Color System

### Philosophy
Use a single accent hue (the existing teal-green) as the brand's only saturated color. All other UI color is derived from a single neutral dark blue-grey base. Financial state (profit/loss) uses green/red only in clearly scoped contexts.

### Base Palette (CSS Custom Properties)

```css
/* Dark canvas — core backgrounds */
--color-canvas:           #050b12;   /* Page background */
--color-canvas-subtle:    #08121d;   /* Slightly lighter bg */
--color-surface:          #0d1a27;   /* Card, panel background */
--color-surface-raised:   #112333;   /* Elevated card */
--color-overlay:          #0b1723;   /* Raised elements, nav bg */
--color-hover:            #172e40;   /* Hover state on interactive surfaces */

/* Borders */
--color-border:           #1d3548;   /* Default border */
--color-border-strong:    #315269;   /* Emphasized border, focus rings */

/* Text */
--color-text-primary:     #f4f8fb;   /* Headlines, values, primary content */
--color-text-secondary:   #c6d4df;   /* Body copy, descriptions */
--color-text-muted:       #8ea6b8;   /* Labels, meta, secondary info */
--color-text-faint:       #648094;   /* Disabled, placeholder, decorative */

/* Brand accent — teal-green */
--color-accent:           #19b995;   /* Primary interactive, active states */
--color-accent-hover:     #28d0aa;   /* Hover state for accent elements */
--color-accent-subtle:    #0b3c35;   /* Accent background for badges, chips */
--color-accent-text:      #cafff2;   /* Text on accent backgrounds */

/* Links and focus */
--color-link:             #73c7ef;   /* Hyperlinks */
--color-focus:            #71d7ff;   /* Focus ring color */

/* Semantic — status */
--color-success:          #3ca47b;
--color-success-subtle:   #123d31;
--color-success-text:     #bdf4db;

--color-warning:          #d99d42;
--color-warning-subtle:   #453117;
--color-warning-text:     #ffe0aa;

--color-danger:           #d46d70;
--color-danger-subtle:    #47252a;
--color-danger-text:      #ffd2d3;

--color-info:             #579bce;
--color-info-subtle:      #15364f;
--color-info-text:        #cceaff;

/* Financial state — ADD THESE (currently missing) */
--color-profit:           #4fd4a0;   /* Positive P&L, positive returns */
--color-profit-subtle:    #0f3528;
--color-profit-text:      #c8ffe8;

--color-loss:             #e07070;   /* Negative P&L, drawdown */
--color-loss-subtle:      #4a1c1c;
--color-loss-text:        #ffd0d0;

--color-neutral:          #8ea6b8;   /* Flat / unchanged financial state */
```

### Semantic Token Aliases (component-level)

```css
/* Backgrounds */
--bg-page:        var(--color-canvas);
--bg-card:        var(--color-surface);
--bg-card-raised: var(--color-surface-raised);
--bg-overlay:     var(--color-overlay);

/* Interactive */
--interactive-primary:       var(--color-accent);
--interactive-primary-hover: var(--color-accent-hover);
--interactive-secondary:     transparent;
--interactive-danger:        var(--color-danger-subtle);

/* Text aliases */
--text:    var(--color-text-primary);
--text-2:  var(--color-text-secondary);
--muted:   var(--color-text-muted);
--faint:   var(--color-text-faint);

/* Borders */
--border:        var(--color-border);
--border-strong: var(--color-border-strong);

/* Financial */
--profit:        var(--color-profit);
--loss:          var(--color-loss);
--neutral-value: var(--color-neutral);
```

### Usage Rules
- Use `--profit` / `--loss` exclusively for financial P&L values — never for success/error UI state
- Do NOT use color alone to communicate financial state — always pair with a sign symbol (+ / −) or label
- Teal accent (`--color-accent`) is reserved for the AlgoProfitX brand and primary actions — do not repurpose it as a "success" color
- Destructive actions (Delete, Archive) always use `--color-danger` — never use teal for destructive

---

## 2. Typography

### Font Stack

```css
/* Display / Headings */
--font-display: "Segoe UI Variable Display", "Aptos Display", "SF Pro Display", system-ui, sans-serif;

/* Body / UI */
--font-sans: "IBM Plex Sans", "Segoe UI Variable", "Segoe UI", Inter, system-ui, sans-serif;

/* Monospace — code, JSON, financial numbers, IDs */
--font-mono: "Cascadia Mono", "JetBrains Mono", Consolas, monospace;

/* Numeric — trading values, prices, quantities */
/* Use font-variant-numeric: tabular-nums on all financial figures */
```

**Future improvement:** Add IBM Plex Mono via self-hosting or a CDN (free, aligns with IBM Plex Sans, excellent tabular numerals for trading data).

### Type Scale

| Token | Size | Weight | Line height | Use |
|-------|------|--------|-------------|-----|
| `--text-display` | clamp(3.25rem, 6vw, 6.15rem) | 720 | 0.97 | Hero headline |
| `--text-h1` | clamp(2.2rem, 4vw, 3.5rem) | 720 | 1.1 | Page titles |
| `--text-h2` | clamp(1.6rem, 2.5vw, 2.2rem) | 700 | 1.2 | Section headings |
| `--text-h3` | 1.125rem | 650 | 1.3 | Card headings, subsection headings |
| `--text-body-lg` | 1.125rem | 400 | 1.75 | Lead paragraphs |
| `--text-body` | 1rem | 400 | 1.6 | Body copy |
| `--text-body-sm` | 0.875rem | 400 | 1.5 | Secondary text, descriptions |
| `--text-caption` | 0.75rem | 500 | 1.4 | Labels, captions, eyebrows |
| `--text-label` | 0.75rem | 700 | 1 | Form labels, table headers |
| `--text-mono` | 0.875rem | 400 | 1.5 | Code, JSON, IDs |
| `--text-data` | 1rem | 600 | 1 | Financial values (tabular-nums) |
| `--text-data-lg` | 1.4rem | 650 | 1 | Metric cards, prominent values |
| `--text-data-xl` | 1.8rem | 720 | 1 | Dashboard headline numbers |

### Trading Number Conventions
- All financial numbers: `font-variant-numeric: tabular-nums`
- Positive values: prefix `+`, color `--profit`
- Negative values: prefix `−` (minus sign, not hyphen), color `--loss`
- Currency: always include currency code (INR, USD) or symbol
- Percentages: include `%` suffix
- Null / unavailable: render `—` (em dash), never `null` or `undefined`

---

## 3. Spacing System

Retain the existing 8-point grid.

```css
--space-1:  0.25rem;  /*  4px */
--space-2:  0.5rem;   /*  8px */
--space-3:  0.75rem;  /* 12px */
--space-4:  1rem;     /* 16px */
--space-5:  1.5rem;   /* 24px */
--space-6:  2rem;     /* 32px */
--space-7:  3rem;     /* 48px */
--space-8:  4.5rem;   /* 72px */
--space-9:  6rem;     /* 96px */
--space-10: 8rem;     /* 128px */

/* Layout */
--page-max-width:    1280px;
--page-gutter:       max(1.25rem, calc((100vw - 1280px) / 2));
--section-gap:       var(--space-8);
--card-pad:          var(--space-5);
--card-pad-sm:       var(--space-4);
```

---

## 4. Border Radius System

```css
--radius-sm:   0.375rem;  /* Small inputs, chips */
--radius-md:   0.625rem;  /* Buttons, form inputs */
--radius-lg:   1rem;      /* Cards */
--radius-xl:   1.5rem;    /* Hero terminal, large panels */
--radius-pill: 999px;     /* Badges, live dots, pill buttons */
```

---

## 5. Shadow & Elevation

```css
--shadow-none: none;
--shadow-sm:   0 1px 3px rgba(0, 6, 12, 0.3), 0 1px 2px rgba(0, 0, 0, 0.2);
--shadow-md:   0 8px 30px rgba(0, 6, 12, 0.25);
--shadow-lg:   0 28px 90px rgba(0, 4, 9, 0.46);
--shadow-glow: 0 0 24px rgba(25, 185, 149, 0.24);  /* Accent glow, used sparingly */
```

**Elevation rule:** Cards float on the canvas. Modals/drawers float above cards. Tooltips float above modals. Use shadows to reinforce layering — never use elevation to decorate.

---

## 6. Component System

### 6.1 Buttons

```
Primary   — filled teal gradient, white text
Secondary — transparent, border, light text
Ghost     — no border, no fill, link-colored text (for in-content actions)
Danger    — danger-subtle fill, danger-text color
```

**States all buttons must have:** default, hover, active (press), focus-visible, disabled  
**Sizes:** sm (min-height 2rem), md (default, min-height 2.5rem), lg (min-height 3.15rem)

**Iconography rule:** Buttons may include a leading or trailing icon. Use proper icon library (Lucide recommended — lightweight, consistent stroke weight) rather than Unicode characters.

---

### 6.2 Form Inputs

All inputs share a consistent spec:
- Background: `--color-canvas` (darker than surface, creates inset feel)
- Border: `--color-border-strong`
- Focus: border `--color-accent`, box-shadow `0 0 0 3px rgba(25,185,149,.12)`
- Error state: border `--color-danger`, helper text `--color-danger-text`
- Label: always visible above field (no floating labels)
- Helper/hint text: below field, `--text-muted`, `--text-caption`

**Types needed:** Text, Email, Password, Number (financial), Search, Textarea, Select, Checkbox, Radio group

**Financial number inputs** — right-align the value. Show currency unit clearly. Use step/precision appropriate to the currency.

---

### 6.3 Cards

```
Default card:
  background: --color-surface
  border: 1px solid --color-border
  border-radius: --radius-lg
  padding: --card-pad
  
Elevated card:
  background: --color-surface-raised
  box-shadow: --shadow-md
  
Interactive card (clickable):
  + cursor: pointer
  + hover: border --color-border-strong, transform: translateY(-2px)
  + focus-visible: ring
```

---

### 6.4 Badges / Status Indicators

Badges convey state. Current badge classes cover the main strategy lifecycle states. The complete set needed:

| Badge type | Token colors | States |
|-----------|-------------|--------|
| Lifecycle | success/info/warning/neutral | draft, published, deployed, archived |
| Backtest | warning/info/success/danger | queued, running, completed, failed |
| Execution | warning/info/success/danger | pending, running, completed, failed |
| Role | accent-subtle | Creator, Investor |
| Data | accent-subtle | paper, synthetic |
| Instrument | typed | equity, index, tradeable, non-tradeable |

**Rule:** Always pair color with text. Never use a color badge alone to convey status.

---

### 6.5 Tables

**Data tables** (strategy list, instrument list, equity curve table):
- Fixed thead, sticky if needed
- Row hover: `--color-hover` background
- Mobile: collapse to card/list layout (current creator.css approach is correct)
- Numeric columns: right-align, `font-variant-numeric: tabular-nums`
- Status columns: badge cell, no text overflow
- Empty state: full-width empty state row, not hidden table

---

### 6.6 Charts

The only chart currently present is the Recharts equity curve on the Backtest detail page. The homepage hero shows a decorative SVG chart.

**Proposed chart palette:**
```css
--chart-line:       #28d0aa;   /* Primary equity line */
--chart-fill:       rgba(25, 185, 149, 0.12);  /* Area fill under line */
--chart-grid:       rgba(100, 151, 175, 0.1);  /* Gridlines */
--chart-axis:       var(--color-text-muted);
--chart-tooltip-bg: var(--color-surface-raised);
--chart-tooltip-border: var(--color-border-strong);
```

**Chart rules:**
- Equity curves: always use monotone interpolation, suppress dots for large series
- Drawdown: use a separate fill zone, color `--color-loss-subtle`
- All axes must be labeled with unit (%, INR, date)
- Tooltips must show absolute values, not just relative
- Charts must be responsive (ResponsiveContainer)
- Must remain readable at 320px width
- All charts must have an ARIA label

---

### 6.7 Alerts / Notifications

```
alert-info    — blue, for informational context and disclaimers
alert-success — green, for completed positive outcomes
alert-warning — amber, for cautionary states
alert-error   — red, for errors and failures
alert-disclosure — amber-tinted, for synthetic/paper data disclaimers (existing pattern)
```

**Important:** "Paper" and "Synthetic" disclaimers must always be visible when displaying simulated data. Do not de-emphasize these — they are a compliance and trust concern.

---

### 6.8 Loading States

Three tiers:
1. **Page loading** — centered spinner + skeleton lines (existing `LoadingState` component, acceptable)
2. **Section loading** — inline spinner within the section, not full page takeover
3. **Skeleton screens** — for known-structure content (strategy list, metric grid) — more informative than a generic spinner

---

### 6.9 Empty States

Current `EmptyState` is a simple icon + text. Improve to context-specific empty states with:
- Clear heading explaining what's empty
- Why it's empty (no items created yet, filters applied, etc.)
- A primary action (e.g., "Create your first strategy")

---

### 6.10 Navigation

**Desktop (≥820px):**
- Sticky top header: brand + centered nav + actions
- Nav links: subtle hover, active underline indicator
- Role chips: minimal pill badges showing active roles

**Mobile (≤820px) — proposed redesign:**
- Header: brand + hamburger icon (right)
- Mobile drawer slides from left (or bottom sheet) with full nav + role info
- Do NOT use horizontal scroll nav at mobile — it is invisible and unusable

---

## 7. Icon System

**Current problem:** Unicode characters used for icons (↗, ◎, ⌁, +) are inconsistent, confusing, and inaccessible.

**Proposed solution:** Adopt **Lucide React** (MIT licensed, ~2.5KB per icon via tree-shaking, SVG, consistent 24px stroke-based design).

Key icons needed:
| Use | Icon |
|-----|------|
| Dashboard | `LayoutDashboard` |
| Strategies | `GitBranch` or `Layers` |
| Marketplace | `Store` or `ShoppingBag` |
| Instruments | `BarChart2` |
| Allocations | `PieChart` or `Wallet` |
| Executions | `Zap` or `Play` |
| Account | `User` |
| Logout | `LogOut` (not `↗`) |
| Create / Add | `Plus` |
| Delete | `Trash2` |
| Edit | `Pencil` |
| View detail | `ArrowRight` or `ExternalLink` |
| Back | `ArrowLeft` |
| Success | `CheckCircle` |
| Warning | `AlertTriangle` |
| Error | `XCircle` |
| Info | `Info` |
| Loading | CSS spinner (no icon) |
| Empty | `Inbox` or context-specific |
| Chart / Analytics | `TrendingUp` |
| Version | `Tag` or `GitCommit` |
| Backtest | `FlaskConical` or `Activity` |

---

## 8. Motion & Animation

**Principles:**
- Use motion to communicate state change, not to decorate
- Always respect `prefers-reduced-motion` (existing `@media (prefers-reduced-motion: reduce)` is good — keep it)
- No animation that delays user interaction

**Approved uses:**
| Use case | Recommended animation |
|---------|----------------------|
| Loading spinner | CSS keyframe rotate, 0.8s linear infinite |
| Skeleton shimmer | CSS gradient background-position animation |
| Card hover | translateY(-2px), 0.18s ease |
| Button hover | translateY(-2px), 0.18s ease |
| Modal open | scale(0.96) → scale(1), fade-in, 0.18s ease-out |
| Page transition | Minimal — fade only if router supports it |
| Status badge change | Background-color transition, 0.2s ease |
| Chart appear | Recharts default animation (draw-in), reduce for accessibility |

**Avoid:**
- Continuous animations on visible UI elements (other than a spinner)
- Parallax
- Scroll-triggered animations (no JS animation library needed)
- Transform animations on data tables

---

## 9. Layout Architecture

### Page Structure

```
┌─────────────────────────────────────────────────────┐
│ SiteHeader (sticky, ~4.75rem)                       │
├─────────────────────────────────────────────────────┤
│                                                     │
│  PageContainer (max-width: 1280px, centered)        │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  PageHeading                                │   │
│  │  (eyebrow + h1 + description + action)      │   │
│  ├─────────────────────────────────────────────┤   │
│  │                                             │   │
│  │  Page content                               │   │
│  │                                             │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Content Grid Patterns

```
Detail page (two-panel):     1fr 1fr  → stack at ≤768px
Stats row (four cells):      repeat(4, 1fr) → 2x2 at ≤820px → 1fr at ≤560px
Card grid (marketplace):     repeat(auto-fit, minmax(300px, 1fr))
Metric grid (analytics):     repeat(auto-fit, minmax(160px, 1fr))
Form page (centered):        max-width: 44rem, centered
Auth page (card):            max-width: 30rem, centered, card-wrapped
```

---

## 10. Accessibility Requirements

| Requirement | Current State | Action Needed |
|------------|--------------|--------------|
| Keyboard navigation | Mostly OK via browser defaults | Add focus-visible styles to all interactive elements |
| Focus ring | Defined in global.css | Ensure it applies to all custom interactive elements |
| Color contrast | Text-primary on canvas: ~14:1 ✓ | Verify muted text meets AA (4.5:1) |
| Screen reader — icons | Unicode chars in buttons have aria-labels | Replace Unicode with proper icon library + aria-label |
| Screen reader — charts | Hero SVG has aria-label ✓; equity chart has no aria | Add aria-label to all charts |
| Form labels | Labels present ✓ | Ensure error messages are announced live |
| Status badges | Color + text ✓ | Acceptable |
| Financial state | Color + sign ✓ | Do not regress — keep both color AND symbol |
| Reduced motion | `prefers-reduced-motion` in premium.css ✓ | Keep, expand to all new animations |
| Semantic HTML | `<i>` for brand mark bars ✗ | Use `<span>` or CSS pseudo-elements |
| Live regions | LoadingState has `role="status" aria-live="polite"` ✓ | Apply to all async loading states |
| Error alerts | ErrorAlert has `role="alert"` ✓ | Keep |

---

## 11. Design Token Consolidation Plan

Currently tokens are split across two `:root` blocks in two files (global.css and premium.css), with premium.css acting as a full override. This creates a fragile dependency on load order.

**Proposed:** Collapse into a single design token source. Either:
1. Keep as CSS — combine into one `tokens.css` file imported first, with a clear semantic layer above raw primitives
2. Generate from a JS/TS token file if the build system supports it

This does not require a Tailwind or CSS-in-JS migration — pure CSS custom properties are sufficient.
