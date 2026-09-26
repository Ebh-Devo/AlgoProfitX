# AlgoProfitX — Frontend Redesign Plan
> Phase 1 plan · September 2026 · Review before implementation

---

## Guiding Constraints

1. **Do not change backend contracts.** All API endpoints, request shapes, and response shapes are frozen. Only the presentation layer changes.
2. **Do not remove working functionality.** Every action a user can currently take must remain available after redesign.
3. **Do not auto-login after registration** — the backend currently returns a 201 with user data (not a token), so the redirect to `/login` is correct behavior.
4. **The registration smoke-test failure is a backend/deployment concern** — the redesign must surface backend errors clearly, not hide them.
5. **Paper/synthetic disclaimers must remain prominent** — they are a trust and compliance concern.

---

## Priority Tiers

| Priority | Rationale |
|---------|-----------|
| P0 — Critical | Broken UX, missing functionality, trust/compliance issue |
| P1 — High | Major UX improvement, heavily-used pages |
| P2 — Medium | Polish, consistency, secondary-use pages |
| P3 — Low | Nice-to-have, minor improvements |

---

## Implementation Sequence

### Phase A — Foundation (do first, no visible product changes)
1. Design token consolidation (merge global.css + premium.css tokens into one file)
2. Add Lucide React icon library
3. Create shared component library (Button, Badge, Alert, LoadingState, EmptyState improvements)
4. Fix mobile navigation (hamburger / drawer)

### Phase B — High-traffic pages
5. Landing page (HomePage) — refine and optimize
6. Login + Register pages
7. Dashboard (AppPage)
8. Marketplace list + detail

### Phase C — Creator workspace
9. Strategy list
10. Strategy detail + lifecycle
11. Strategy version detail
12. Backtest detail + analytics

### Phase D — Investor workspace
13. Allocation list + detail
14. Execution intent list + detail

### Phase E — Secondary pages
15. Instrument list + detail
16. Account page (expand capabilities)
17. Creator enrollment page

---

## Page-by-Page Redesign Plan

---

### Page 1 — Landing / Home (`/`)
**Priority: P1**

#### Current State
Well-structured landing page with hero, workflow section, feature splits, architecture band, disclosure, and CTA. The terminal mockup with equity chart is a strong visual anchor. The page is long and dense but follows a logical structure.

#### Problems
- Hero headline text is already very large — at some viewports the font renders too aggressively (6.15rem)
- The "trust-row" at the bottom of the hero copy uses `✓` Unicode checkmarks — replace with icons
- CTA section references `www.algoprofitx.com` as the domain, which may or may not match the deployed URL — verify before shipping
- Navigation at mobile is the horizontal scroll strip — not discoverable
- The `NotFoundPage` linked from `*` has no styling at all
- No `<footer>` element — CTA section effectively acts as footer but has no copyright, legal links, or contact

#### New Design Direction
- Keep the overall page structure — it is sound
- Refine the hero: tighten line-height on display text, add more breathing room between sections
- Add a proper `<footer>` with: copyright, disclaimer link, GitHub link (if public), version
- Replace `✓` Unicode with Lucide `Check` icon
- The hero terminal mockup is excellent — keep it, refine spacing inside
- Add `rel="noopener noreferrer"` to any external links

#### Components Required
- `Footer` (new)
- `Icon` wrapper (Lucide)
- No structural component changes needed

#### API Dependencies
None (landing page is fully static)

#### Responsive Considerations
- Current breakpoints are well-structured — keep them
- Hero two-column → single-column at 1100px is correct
- Mobile hero needs more vertical rhythm

#### Priority: P1

---

### Page 2 — Login (`/login`)
**Priority: P0**

#### Current State
Simple card with email/password form. Backend errors surfaced via `ErrorAlert`. Field-level errors displayed inline. Redirect to `/app` (or saved location) on success.

#### Problems
- The `auth-card` max-width is 30rem — acceptable for a form
- The form has no password visibility toggle
- After successful registration, user must navigate to `/login` separately — this friction will drive drop-offs
- No "Forgot password" flow exists (link could be added pointing to a future endpoint)
- The login card sits on a plain canvas — no visual framing
- Error text (`<small>`) uses danger color only — needs an icon or ARIA `role="alert"`

#### New Design Direction
- Keep the card-centered layout
- Add password visibility toggle (eye icon via Lucide)
- Surface error state more prominently — icon + styled error message
- Add placeholder "Forgot password?" text link (grayed out if not yet implemented, or pointing to a `/forgot-password` route that can be wired later)
- Slightly improve the background: add a subtle gradient or panel behind the card to visually separate it from the canvas

#### Components Required
- Improved `AuthCard` layout
- `PasswordInput` (toggle visibility)
- `FormError` (icon + message)

#### API Dependencies
- `POST /auth/login` (unchanged)
- `GET /auth/me` (unchanged — via AuthContext)

#### Responsive Considerations
- Card is already 100% width on small screens — acceptable

#### Priority: P0

---

### Page 3 — Register (`/register`)
**Priority: P0**

#### Current State
Three-field form (name, email, password). On success redirects to `/login`.

#### Problems
- **Post-registration redirect to `/login` creates unnecessary friction** — the backend should be queried about whether auto-login is possible, but currently it is not. The redirect must stay but should be clear ("Account created. Please log in.") with a persistent success message on the login page.
- No password strength indicator
- No confirmation that what the user typed will actually work (no real-time validation)
- Field error rendering uses bare `<small>` elements — improve to icons + ARIA

#### New Design Direction
- Add a "success" state: when registration succeeds, show a brief confirmation panel before redirecting
- Pass a state flag to the login page so it can show "Account created successfully" at the top
- Add a password strength meter (client-side only — does not affect the backend password policy)
- Add clear field descriptions: "Password must be at least 8 characters"

#### Components Required
- `PasswordStrengthMeter` (optional, new)
- Improved `FormError` (same as login)
- Router state for success flash message on login page

#### API Dependencies
- `POST /auth/register` (unchanged)

#### Responsive Considerations
- Same as login — card is narrow, stacks fine

#### Priority: P0

---

### Page 4 — Dashboard / AppPage (`/app`)
**Priority: P1**

#### Current State
Post-auth workspace hub. Shows 4 capability stat tiles and 3 feature cards. No real backend data is shown — all content is static/hardcoded.

#### Problems
- Dashboard shows no real user data — capabilities are described but nothing is "live"
- 4-column stat strip is not connected to any API
- The "Creator mode: Available" is not actually actionable from the stat strip — it just describes the state
- Dashboard feature cards are marketing copy, not operational tools
- No overview of active strategies, allocations, or recent executions
- No quick-action shortcuts to high-frequency tasks

#### New Design Direction
The dashboard should be the **command center** — a single screen that surfaces what the user most needs to see:

```
Authenticated Dashboard — Proposed Layout

[ Greeting + Quick Actions (+ New Strategy | Discover) ]

[ Stats strip: Creator/Investor role state | Key metric if available ]

[ Creator workspace card | Investor workspace card | Instrument Explorer card ]

[ Disclosure / disclaimer banner ]
```

For now (given existing backend), the stat strip shows roles and capabilities (current behavior is acceptable), and the feature cards link to the correct sections. The main improvement is making the layout feel more like a cockpit and less like a marketing page. Future iterations can wire real data (recent strategies count, active allocations count) when those summary API endpoints are available.

**Do not invent API calls that don't exist.** Keep the current data sources.

#### Components Required
- `DashboardHeader` (greeting + actions, improved)
- `StatTile` (reusable stat cell)
- `WorkspaceCard` (improved feature card)

#### API Dependencies
- `GET /auth/me` (unchanged — roles from auth context)
- No new API calls

#### Responsive Considerations
- Stats strip: 4-col → 2x2 at ≤820px → 1-col at ≤560px (current behavior is correct)
- Feature cards: 3-col → 2-col at ≤1100px → 1-col at ≤820px

#### Priority: P1

---

### Page 5 — Marketplace List (`/marketplace`)
**Priority: P1**

#### Current State
Card grid of public strategies. Each card shows strategy name, monogram, status badge, description, published date, and current version. Clean and functional.

#### Problems
- Card grid minimum width (310px) means only 1 card per row on narrow viewports
- No search or filter on marketplace (must scroll through all strategies)
- The "strategy monogram" (first 2 letters) is a good pattern — keep it
- `MarketplaceDetailPage` is very sparse — mostly disclaimers

#### New Design Direction
- Add a search/filter bar (client-side filter on loaded strategies — no new API endpoint needed)
- Improve card layout: clearer visual hierarchy, instrument/version info if available
- Marketplace detail: add more visual structure, make the disclaimer panel less dominant (it's honest, but it currently dominates the page)

#### Components Required
- `StrategyCard` (improved)
- `MarketplaceFilters` (client-side, new)

#### API Dependencies
- `GET /marketplace/strategies?limit=20&offset=0` (unchanged)
- `GET /marketplace/strategies/:slug` (unchanged)

#### Responsive Considerations
- Card grid: `auto-fit minmax(300px, 1fr)` is acceptable

#### Priority: P1

---

### Page 6 — Strategy List (`/creator/strategies`)
**Priority: P1**

#### Current State
Full-width table with strategy metadata, status badge, version info, timestamps, and action links.

#### Problems
- Table has no search, filter, or sort
- Strategy description in the table row can be truncated in narrow columns
- The table collapses to block layout at ≤760px — but the block layout has no visual hierarchy
- "Current Version" column shows "Selected" / "—" — not very informative (why not "Version 3"?)

#### New Design Direction
- Add a search bar (client-side filter on strategy name/slug/status — no new API)
- Status filter: All / Draft / Published / Deployed / Archived
- Show current version number instead of "Selected"
- The table layout is appropriate for desktop — keep it
- Mobile block layout needs labels added (e.g., "Status:", "Version:")

#### Components Required
- `StrategyTable` (improved)
- `StatusFilter` (new, client-side)

#### API Dependencies
- `GET /strategies` (unchanged)

#### Responsive Considerations
- Mobile block layout needs improvement

#### Priority: P1

---

### Page 7 — Strategy Detail (`/creator/strategies/:id`)
**Priority: P1**

#### Current State
Rich page: metadata card, lifecycle panel, versions list, version creator form, danger zone. All functional.

#### Problems
- `VersionCreator` instrument search fires on every keystroke — add a 300ms debounce
- The lifecycle panel could be clearer — what state comes after current? Show a state diagram or arrow sequence
- `Lifecycle` component shows all possible actions but doesn't explain constraints (e.g., "Must create a Version before publishing")
- Delete confirm flow is correct — keep it
- Danger zone appears immediately below versions — very easy to accidentally see

#### New Design Direction
- Add a state progression indicator to the Lifecycle card (e.g., `Draft → Published → Deployed → Archived`)
- Add debounce to instrument search
- Move danger zone to a separate collapsible section at the very bottom

#### Components Required
- `LifecycleProgress` (new, shows state trail)
- `InstrumentSearch` with debounce (refactor)

#### API Dependencies
- All current endpoints unchanged

#### Responsive Considerations
- Detail grid (2-col) stacks to 1-col at ≤760px — acceptable

#### Priority: P1

---

### Page 8 — Strategy Version Detail (`/creator/strategies/:id/versions/:versionId`)
**Priority: P2**

#### Current State
Shows instrument info, read-only JSON config blocks, and the VersionBacktests section.

#### Problems
- JSON blocks (`<pre>`) are read-only but have no copy button — JSON can be long
- The `json-view` style is a dark `<pre>` block — acceptable but could be improved with syntax highlighting for readability
- "Legacy/unresolved" instrument message is clear but could be more helpful

#### New Design Direction
- Add a "Copy" button to JSON blocks
- Consider a basic JSON syntax highlighting solution (a minimal CSS-based approach, not a full library, to avoid bundle increase)
- Keep the rest — it is clear and functional

#### Priority: P2

---

### Page 9 — Backtest Detail (`/creator/strategies/.../backtests/:backtestId`)
**Priority: P1**

#### Current State
The most data-rich page. Run timeline, execution identity, instrument snapshot, provenance, analytics with equity chart and metrics grid.

#### Problems
- **No auto-refresh for queued/running status** — user must manually reload. This is a significant UX problem for a workflow that requires waiting.
- Metric grid uses auto-fit with 10rem minimum — on desktop this can create awkward 5-3 or 7-2 column layouts
- The equity chart Y-axis domain uses `["auto", "auto"]` — on a flat equity curve this can make a 0.01% variation look like a crash
- `Analytics` component mixes multiple sections without visual grouping — feels like a wall of content
- Equity table is behind a `<details>` — good pattern, but hidden by default means users may not notice it

#### New Design Direction
- Add **polling** for queued/running backtests: poll `GET /strategies/.../backtests/:id` every 5s when status is `queued` or `running` (React Query `refetchInterval` option — no backend change needed)
- Improve metric grid: fix to 3-column on desktop
- Add Y-axis baseline: clamp domain to show at least a ±5% range
- Group analytics into sections: Overview Metrics | Equity Curve | Trade Statistics | Provenance
- Keep the `<details>` table but add a summary count ("X equity points")

#### Components Required
- `BacktestMetricGrid` (improved, fixed columns)
- `EquityChart` (improved, better Y-axis)
- React Query `refetchInterval` for polling (implementation-level, not new component)

#### API Dependencies
- `GET .../backtests/:id` with polling — same endpoint, just called repeatedly
- `GET .../analytics` — unchanged

#### Responsive Considerations
- Metric grid: 3-col → 2-col at ≤768px → 1-col at ≤480px
- Equity chart: height should be responsive (current 20rem at ≤760px is acceptable)

#### Priority: P1

---

### Page 10 — Allocation List (`/investor/allocations`)
**Priority: P2**

#### Current State
List of allocations with inline create form. Clean functional layout.

#### Problems
- The create form appears inline (not in a modal/drawer) — for a short form this is acceptable, but the inline form pushes content
- The allocation list uses `run-list` CSS class (borrowed from backtest) — not semantic
- "Deployed strategy" dropdown fetches 100 strategies — if there are no deployed strategies, the dropdown is confusingly empty

#### New Design Direction
- Keep inline form (acceptable pattern)
- Add empty state for "no deployed strategies" in the dropdown with a helpful message and link to marketplace
- Add a dedicated CSS class for the allocation list (not reusing `run-list`)

#### Priority: P2

---

### Page 11 — Allocation Detail (`/investor/allocations/:id`)
**Priority: P2**

#### Current State
Detail card + inline edit form + danger zone. Clean.

#### Problems
- "Create Execution Intent" button triggers a POST immediately without a confirmation step — acceptable for a paper action but could benefit from a summary ("Paper execute Version 3 of Momentum Alpha?")
- Edit form shows amount and currency — that's all that's editable. Clear.
- Danger zone: "Allocations with execution history cannot be deleted." — this error comes from the API, not validated client-side. When a delete fails for this reason, the current error flow shows a generic error alert. The error message should match the API's explanation.

#### Priority: P2

---

### Page 12 — Execution Intent Detail (`/investor/execution-intents/:id`)
**Priority: P2**

#### Current State
Full paper execution detail: intent snapshots, timeline, instrument detail, execution button, and paper result display.

#### Problems
- **No auto-refresh for `running` or `pending` intents** — same polling gap as backtests
- `PaperResult` renders a large `dl` list of all paper result fields — overwhelming for the user's primary concern (did it fill or not?)
- The "Order / Fill / Position" result blocks are raw JSON dumps (`ResultBlock`) — hard to read
- The disclaimer banner is prominent but repeats on multiple places on the page

#### New Design Direction
- Add polling for `pending` and `running` intents (React Query `refetchInterval` — no backend change)
- Lead with the outcome summary (filled / no-fill / failed) as the primary visual element
- Collapse the detailed field list under a disclosure
- Format Order/Fill/Position blocks as structured cards, not raw JSON (the fields are documented in the type)
- Keep the disclaimer banner — but show it once, not in multiple places

#### Priority: P2

---

### Page 13 — Instrument List (`/instruments`)
**Priority: P2**

#### Current State
Filterable table with search, type, tradeability, and exchange filters. Pagination.

#### Problems
- Filter grid is 5-column on desktop (search + type + tradeability + exchange + search button) — cramped
- The "Search" button is needed to apply the search field — but type/tradeability/exchange filter immediately on change. Inconsistent UX.
- Pagination is previous/next with "Page N" — no indicator of total results
- Table shows `Not available` for null lot/tick values — `—` would be more legible

#### New Design Direction
- Make search also fire on input (debounced) rather than requiring a button press
- Or: remove the search button and apply all filters on change (consistent)
- Show result count in the heading area ("47 instruments match")
- Replace `Not available` with `—` in technical value cells

#### Priority: P2

---

### Page 14 — Instrument Detail (`/instruments/:id`)
**Priority: P3**

#### Current State
Three cards: Identity, Exchange, Trading metadata. Clean.

#### Problems
- No back button back to the filtered state — clicking `← Instruments` resets filters
- Sessions/calendar information not shown (the exchange has timezone, but no trading session hours)

#### Priority: P3

---

### Page 15 — Account Page (`/account`)
**Priority: P3**

#### Current State
Extremely sparse. Shows email, roles, and active status only. No ability to change anything.

#### Problems
- No way to change password, name, or email
- No ability to see or revoke sessions
- No audit trail of recent actions
- The page exists but adds minimal value

#### New Design Direction
Until the backend supports update-account endpoints, the account page can be improved to:
- Show a better-formatted user profile section
- Add a "Copy email" utility
- Show account age (member since)
- Show active roles with descriptions of what each role allows
- Add a placeholder "Change password" section that links to an endpoint when it becomes available

**Do not invent backend functionality** — make the most of what exists.

#### Priority: P3

---

### Page 16 — Creator Enrollment (`/creator/enroll`)
**Priority: P3**

#### Current State
Single-action page with explanation and enroll button.

#### Problems
- Very sparse — the explanation is minimal
- No indication of what Creator access unlocks beyond what's already shown on the dashboard

#### New Design Direction
- Show a brief feature list: "Creator mode unlocks: strategy creation, version management, backtesting, lifecycle control, marketplace publishing"
- Keep the single-action pattern — it's appropriate for this page

#### Priority: P3

---

### Page 17 — Not Found (`*`)
**Priority: P2**

#### Current State
`<section><h1>Page not found</h1></section>` — completely unstyled.

#### New Design Direction
- Style to match AppShell (already inside AppShell)
- Add navigation suggestions: "Go home", "Go to marketplace"
- Keep it simple

#### Priority: P2

---

## Navigation Redesign

### Current Issues
- No mobile hamburger menu
- Horizontal scroll at ≤820px is invisible to most users
- Role cluster is hidden at ≤1100px (no way to see roles)
- Logout icon (`↗`) is confusing

### Proposed Changes

**Desktop (unchanged except logout icon):**
- Replace `↗` logout button with `LogOut` Lucide icon
- Keep role cluster visible until ≤820px (current ≤1100px breakpoint is too aggressive)

**Mobile (≤820px):**
- Add hamburger button (right side of header)
- Off-canvas drawer or bottom sheet with full nav links + role display + account link + logout
- Close on route change, close on backdrop click, ESC to close
- Focus trapped when open

---

## Component Unification Opportunities

| Duplication | Current | Proposed |
|------------|---------|----------|
| Status badge | `badge badge-{status}` classes scattered everywhere | Centralized `<StatusBadge status="deployed" />` component |
| Loading state | `LoadingState` + inline `<p>Loading…>` in guards | All loading → `LoadingState` component |
| Error display | `ErrorAlert` + ad-hoc `ApiError.message` inline text | All errors → `ErrorAlert` component |
| Dates | `date()` function defined separately in 4+ files | Shared `src/lib/format.ts` |
| Error extraction | `errorMessage(error, fallback)` in creator/investor | Shared utility |
| Form input styling | `auth-card input` vs `form-stack input` vs `instrument-filters input` | Unified `<Input>` component |
| Run lists | `run-list` used for backtests, allocations, execution intents | Context-specific CSS or `<RunList>` component |
