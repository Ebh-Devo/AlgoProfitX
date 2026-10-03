# Frontend Revamp

Status: **Milestone 1 complete** (design foundation, application shell, landing page). Later phases pending review.

## 1. Product design direction

AlgoProfitX is a systematic-strategy research workspace for Indian markets: versioned strategies, reference backtests, a discovery marketplace, version-pinned allocations and **paper** execution. The UI should read as a calm, precise analytical instrument — closer to institutional fintech than to a consumer trading app — and must never imply capabilities the product lacks (no broker orders, no funded capital, no live performance).

## 2. Visual principles

- Typography-led; flat surfaces separated by hairline borders, not glow or gradients.
- One brand accent. Green/red are **reserved for market state** (profit/loss, success/danger) so brand colour never competes with P&L meaning.
- Elevation expresses layering (canvas → surface → raised → overlay); shadows only on floating layers (menus, dialogs, drawers).
- Density suited to data work; generous whitespace only on marketing surfaces.
- Honest labelling: simulated data is always marked; unsupported capability is shown as "Coming soon", not faked.

## 3. Typography

- **Inter Variable** for UI and headings (self-hosted via `@fontsource-variable/inter`; CSP `font-src 'self'` compatible). Tight tracking on headings (−0.02 to −0.045em).
- **JetBrains Mono Variable** for identifiers, code, and numeric table columns (`.num`, `.mono`).
- Scale: `--text-xs` 12 / `sm` 14 / `base` 16 / `lg` 18 / `xl` 22 / `2xl` fluid page title / `3xl` fluid display.
- Numbers use tabular figures everywhere (`font-variant-numeric: tabular-nums`).

## 4. Colour system (`src/styles/tokens.css`)

| Role | Tokens |
| --- | --- |
| Surfaces | `--color-canvas` `#0a0c10`, `-canvas-subtle`, `-surface`, `-surface-raised`, `-overlay`, `-hover` |
| Borders | `--color-border`, `--color-border-strong` |
| Text | `--color-text-primary / secondary / muted / faint` (all ≥ 4.5:1 on canvas) |
| Brand | `--color-accent` signal blue `#4f6ef7`, `-accent-hover`, `-accent-subtle`, `-accent-text`, `--color-link`, `--color-focus` |
| Status | `--color-success / warning / danger / info` each with `-subtle` and `-text` |
| Market | `--color-profit`, `--color-loss` (+ subtle/text) — P&L only, always paired with a sign |
| Charts | `--chart-1…5`, `--chart-grid`, `--chart-axis` |

Legacy aliases (`--canvas`, `--s4`, `--r2`, `--accent-soft`…) are retained so un-migrated pages inherit the new look automatically. Dark-first; no light theme yet.

Spacing: 4-px scale `--space-1…8`. Radius: 4 / 6 / 10 / 14 (controls 6, panels 10, dialogs 14). Motion: `--dur-fast/base/slow` (120/180/260 ms) with one easing curve; all motion is disabled under `prefers-reduced-motion`.

## 5. Component / design-system principles

- Tokens → primitives (`components.css`) → shells (`shell.css`) → page CSS. Pages compose primitives; no page-specific colour or radius values.
- React primitives in `src/components/ui`: `Button`, `Badge`, `Alert`, `Card`, `Input`, plus new `PageHeader`, `Stat`/`StatGrid`, `Tabs`, `Dialog`. CSS-only primitives: `.data-table` (+ `.num` right-aligned mono columns, `.table-wrap` for overflow), `.skeleton`, `.empty-state`, `.loading-state`, form field/error/hint classes.
- `Dialog` uses native `<dialog>` (focus trap, Esc, inert background). `Tabs` implements roving tabindex with arrow/Home/End keys.
- Flat surfaces: `.card` has no gradient or hover lift; `.card-interactive` changes border/background only.

## 6. Application shell principles

- **Workspace shell** (`DashboardShell`): fixed sidebar grouped by intent (Overview / Build / Invest / Discover / Coming soon), topbar with route-derived breadcrumbs, a persistent **Simulated · Paper** environment chip, and an accessible account menu (roles, settings, log out). Role-gated items are unchanged.
- **Public shell** (`AppShell`): sticky header, mobile drawer, shared footer carrying the simulation disclosure.
- Shared pieces live in `src/components/layout` (`Brand`, `AccountMenu`, `useDrawer`, `buildCrumbs`, `SiteFooter`).
- The previous sidebar's second "Backtesting" link pointed at the strategies list; it was removed (backtests live under a strategy version).

## 7. Responsive principles

- Breakpoints: 1100 (laptop), 960 (sidebar → drawer), 820 (tablet → phone chrome), 520/560 (small phone).
- Below 960 px the sidebar becomes an off-canvas dialog drawer; breadcrumbs collapse to root + current; the environment chip moves into the topbar.
- Wide tables scroll inside `.table-wrap` today; Phase 3+ will replace this with card-style row representations on phones for key trading tables.

## 8. Accessibility principles

- Skip link and focusable `<main>` on both shells; visible 2-px focus ring on every interactive element.
- Drawers: `role="dialog"`/`aria-modal` when open, `aria-hidden` + `visibility:hidden` when closed, focus trap, Esc, focus restore, `preventScroll` on focus.
- Account menu: `aria-haspopup`, `aria-expanded`, `role="menu"`, arrow-key navigation, Esc returns focus.
- Breadcrumb `<nav>` with `aria-current="page"`; nav groups labelled; decorative icons `aria-hidden`.
- Status is never colour-only (badges carry text, financial values carry signs).
- Reduced motion honoured globally.

## 9. Completed — Milestone 1

- New token system, typography (self-hosted Inter / JetBrains Mono), flat component primitives.
- New workspace shell and public shell (responsive, accessible).
- New primitives: `PageHeader`, `Stat`, `Tabs`, `Dialog`, data-table styles.
- Fully redesigned landing page (hero with a **no-data layout preview**, positioning, audience, capabilities, workflow, transparency/boundaries, CTA, footer). All copy reflects shipped functionality; no figures, testimonials or compliance claims.
- Legacy page CSS (`premium.css`, `dashboard.css`) stripped of gradients/glow and mapped to the new tokens; shell/landing rules removed from them.
- Tests updated for the new shell/landing and added for breadcrumbs, account menu and tabs.

## 10. Remaining phases

1. Dashboard — rework information hierarchy around current system state.
2. Strategies — list/create/edit/detail with grouped, progressively disclosed forms and confirmations.
3. Backtesting workspace — results, metrics, trade table, shared chart language (Recharts theme using `--chart-*`).
4. Execution / allocations / intents — clear state language, failure surfaces, confirmation dialogs.
5. Marketplace + instruments — migrate off legacy CSS; table sorting/filter/pagination patterns; mobile row cards.
6. Auth + onboarding, then Settings/Account.
7. Responsive + accessibility audit pass (axe, keyboard walk-through, contrast) across all screens; remove remaining legacy CSS.

## 11. Known limitations

- Pages not yet migrated still use legacy class names; they inherit the new tokens but not the new layouts.
- No ESLint config exists in the repo, so there is no lint step; checks run are `typecheck`, `test`, `build`.
- Dark theme only. The workspace shell was visually verified through a temporary harness (no backend was reachable); authenticated pages were not exercised against a live API.
- Bundle: two self-hosted variable fonts add ~175 kB of font files (latin + latin-ext); consider dropping latin-ext if not needed.

## 12. Future product decisions / missing APIs

The brief calls for portfolio, positions, P&L, broker status and notifications. The current API client (`src/api`) exposes only auth, strategies/versions/backtests, marketplace, instruments, allocations and execution intents. These are **not** invented in the UI; they are future dependencies:

- Portfolio / holdings / positions / P&L endpoints
- Broker connection and broker status endpoints (no broker integration exists)
- Notification / activity feed endpoint
- Profile, security, preferences and subscription endpoints beyond login/enroll
- Strategy activation/deactivation controls beyond the existing lifecycle states

Decisions needed: whether a light theme is in scope; whether a command palette is wanted once there is enough searchable content.
