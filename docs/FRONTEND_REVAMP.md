# Frontend Revamp

Status: **Milestone 1 complete** (design foundation, shell, landing page). **Milestone 2 in review** (Dashboard + Strategies). Later phases pending.

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

1. ~~Dashboard~~ — done in Milestone 2.
2. ~~Strategies~~ — done in Milestone 2.
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

## 13. Milestone 2 — Dashboard + Strategies

Branch `feat/frontend-dashboard-strategies`. No backend, API-contract or auth changes; all data comes from the existing clients (`strategiesApi`, `investorApi`).

### Dashboard design decisions
- Answers "what is happening right now?" top-down: page header (title, one-line context, primary action) → status summaries → strategy/execution panels with recent activity and quick actions alongside → a single slim simulation note (replaces the old capability strip, platform-status strip and disclosure block).
- Metrics are only counts derivable from the list endpoints: strategies by status (total / deployed / published / drafts, archived as a hint) and, for investors, active allocations and execution intents by status (total / completed / failed). Nothing is invented; unavailable values show "—".
- **Recent activity** is derived client-side from timestamps the API really returns (strategy `created_at` / `published_at` / `deployed_at`, allocation `created_at`, execution intent `created_at` / `started_at` / `completed_at` + `status`). It is not a backend activity feed.
- Each section loads and fails independently: skeletons while loading, a friendly `ErrorPanel` with **Try again** on failure (raw backend text is never shown), and first-use empty states with a CTA (create first strategy / go to allocations / enroll).
- Role gating is unchanged (creator and investor sections, enroll CTA for users without a role). The old Explore tiles, capability strip and platform-status strip were removed; marketplace and instruments remain reachable via Quick actions and the sidebar.

### Strategy UX decisions
- **List**: a data table (not cards) — Strategy (name, slug, description), Status, Visibility, Version, Updated, actions — with search (name/slug), status filter chips with counts, and sort (recently updated / newest / name). The result count is an `aria-live` status; "no match" and "no strategies" are distinct empty states. Row actions: **Edit** plus an action menu (Open details, View in Marketplace for public published/deployed strategies).
- **Create / edit**: grouped form ("Strategy identity" — the only capability the create endpoint supports) with field-level meaning/hints, live description counter, slug auto-derived from the name until edited, API field errors mapped to fields, and a "What happens next" guide (create) or lifecycle progress (edit). Edit warns that changing the slug changes the Marketplace URL.
- **Detail** is a workspace: header (name, status, **one primary action for the current state** — Publish for draft, Deploy for published — plus Edit metadata and a **More** menu holding Archive and Delete), Versions panel (create-Version flow in grouped sections: Instrument → Algorithm configuration → Backtest configuration), Overview, and a Lifecycle stepper using the real `published_at` / `deployed_at`. A draft without Versions gets an inline hint; Publish is still attempted so the backend rule stays authoritative.
- **Confirmations**: Archive and Delete use a `ConfirmDialog` (safe action first, pending state, errors shown in the dialog). Publish/Deploy are routine and not confirmed.
- **Version page** uses the same header/panel language; backtest content (`VersionBacktests`) is untouched until Milestone 3.
- Status language (`StatusBadge`): text label + icon + semantic colour — Draft, Published, Deployed, Archived (strategies) and Pending / Queued / Running / Completed / Failed (execution/backtest). Only states that exist in the API enums are shown.

### Reusable components introduced / extended
`SectionHeader`, `Skeleton` / `SkeletonGroup` / `SkeletonRows` / `SkeletonStats`, `ConfirmDialog` (on `Dialog`), `ActionMenu` (reuses `.menu` styles; arrow/Home/End/Escape), `FilterChips`, `ActivityFeed` (+ `relativeTime`), `ErrorPanel` and a richer `EmptyState` (icon / action / compact) in `PageState`. Extended: `StatusBadge` (icons, queued/running), `Button` (`aria-disabled`), `Input` (`aria-describedby` references only the element that exists). Shared CSS lives in the new `src/styles/workspace.css` (panels, toolbar, stacked tables, stepper, key/value lists, form sections); `dashboard.css` was rewritten to the small set of dashboard-only rules.

### Responsive decisions
- Dashboard: two columns (main + 22 rem side) at ≥ 1100 px, single column below; stat grids reflow to 2-up on phones.
- The strategy table **becomes stacked cards at ≤ 720 px** (labels via `data-label`, visually-hidden header kept for assistive tech); filter chips scroll horizontally; search is full width; page-header actions go full width; the More menu becomes a full-width trigger/panel so it never clips.
- Create/edit and detail collapse to one column at ≤ 1000 px (the lifecycle guide moves above the form).
- Verified in the browser pane at 1360, 820 and 375 px.

### Accessibility work
- Status is text + icon + colour; filter chips use `aria-pressed` in a labelled group; the list result count is a polite live region; skeleton groups expose one `role="status"` message; errors use `role="alert"`.
- The table has a hidden caption and column headers; icon-only buttons carry names ("Actions for <strategy>"); decorative icons are `aria-hidden`.
- Dialogs are native `<dialog>` (focus trap, Esc); action menus follow the account-menu pattern (roving focus, Esc restores focus to the trigger).
- Form fields keep label/hint/error wiring (`aria-describedby`, `aria-invalid`); the version form uses fieldsets with hidden legends.
- Reduced motion is honoured (the spinning status icon is disabled).

### Unsupported / future capabilities found
- The strategy list/detail API has no **strategy type**, **backtest state**, **last-run/last-activity** field or **performance metrics**; none are shown. Backtests exist only per Version (`/versions/{id}/backtests`), so a dashboard "latest backtest" would need N+1 requests or a new aggregate endpoint.
- No activity/history endpoint: activity is derived from timestamps and cannot show configuration changes, archive time or deletions.
- No activate/deactivate/pause strategy control — the lifecycle is Draft → Published → Deployed → Archived only. No paper-execution "stop".
- "Run a backtest" is only reachable from a Version, so the dashboard links to strategies rather than faking a one-click action.
- Marketplace/discovery lives in `MarketplacePages` and is left for Milestone 5 (only a link from the action menu was added).

### Known limitations
- No ESLint config in the repo, so there is no lint step (typecheck, test and build were run).
- Dashboard activity and counts are computed from full list responses (the API clients expose no pagination for strategies/allocations/intents).
- Dashboard, list, detail and create flows were verified visually against a local mock API (no backend reachable); filter/sort/dialog flows are covered by unit tests.
- The Version page still shows the unmigrated backtest panels (`BacktestPages`, Milestone 3).
- Unrelated observation, not changed: the strategy tests are tightly coupled to DOM text, so redesigns require test edits.
