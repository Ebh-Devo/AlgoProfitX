# AlgoProfitX — Frontend Audit
> Phase 1 audit · September 2026 · Read-only analysis, no code changes

---

## 1. Framework & Build System

| Item | Detail |
|------|--------|
| Framework | React 19.2.8 (StrictMode) |
| Language | TypeScript 5.9.3 |
| Build tool | Vite 8.2.2 |
| Package manager | pnpm 11.19.0 |
| Module format | ESM (`"type": "module"`) |
| Entry point | `frontend/index.html` → `src/main.tsx` |
| Dev server | `pnpm dev` (Vite default) |
| Build command | `pnpm build` (tsc + vite build) |
| Type check | `pnpm typecheck` |
| Test runner | Vitest 4.1.11 (jsdom, globals, CSS) |
| Source maps | Disabled in production build |

---

## 2. Key Dependencies

### Runtime
| Package | Version | Purpose |
|---------|---------|---------|
| react | 19.2.8 | UI framework |
| react-dom | 19.2.8 | DOM renderer |
| react-router-dom | 7.18.2 | Client-side routing |
| @tanstack/react-query | 5.101.4 | Server state / data fetching |
| react-hook-form | 7.85.0 | Form state management |
| @hookform/resolvers | 5.9.1 | Zod integration for RHF |
| zod | 4.4.3 | Schema validation |
| recharts | ^3.10.1 | Charts (equity curve) |

### Dev
| Package | Version | Purpose |
|---------|---------|---------|
| @vitejs/plugin-react | 6.1.0 | Fast Refresh, JSX transform |
| @testing-library/react | 16.3.2 | Component testing |
| openapi-typescript | 7.13.0 | API type generation from OpenAPI spec |
| vitest | 4.1.11 | Test runner |

---

## 3. Application Entry Points

```
src/main.tsx
  └── StrictMode
      └── AppErrorBoundary      (top-level error boundary)
          └── QueryClientProvider  (React Query)
              └── AuthProvider     (auth context)
                  └── RouterProvider (react-router)
```

CSS imported in main.tsx (load order matters):
1. `styles/global.css` — base tokens, resets, shared primitives
2. `styles/creator.css` — creator feature styles
3. `styles/investor.css` — investor feature styles
4. `styles/instruments.css` — instruments feature styles
5. `styles/premium.css` — **overrides all CSS custom properties in `:root`**; loaded last intentionally

---

## 4. Route Inventory

| Route | Purpose | Auth Guard | Lazy-loaded | API Dependencies |
|-------|---------|-----------|-------------|-----------------|
| `/` | Landing / Home page | Public | No | None |
| `/login` | User login | Public | No | `POST /auth/login`, `GET /auth/me` |
| `/register` | User registration | Public | No | `POST /auth/register` |
| `/marketplace` | Public strategy listing | Public | No | `GET /marketplace/strategies` |
| `/marketplace/:slug` | Public strategy detail | Public | No | `GET /marketplace/strategies/:slug` |
| `/instruments` | Instrument explorer/list | Public | Yes | `GET /instruments` |
| `/instruments/:instrumentId` | Instrument detail | Public | Yes | `GET /instruments/:id` |
| `/app` | Authenticated dashboard | RequireAuth | No | `GET /auth/me` |
| `/account` | Account details & roles | RequireAuth | No | `GET /auth/me` |
| `/creator/enroll` | Creator role enrollment | RequireAuth | No | `POST /auth/creator/enroll` |
| `/creator/strategies` | Creator strategy list | RequireCreator | Yes | `GET /strategies` |
| `/creator/strategies/new` | Create new strategy | RequireCreator | Yes | `POST /strategies`, `GET /instruments` |
| `/creator/strategies/:strategyId` | Strategy detail + versions + lifecycle | RequireCreator | Yes | `GET /strategies/:id`, `GET /strategies/:id/versions`, lifecycle actions |
| `/creator/strategies/:strategyId/edit` | Edit strategy metadata | RequireCreator | Yes | `GET /strategies/:id`, `PATCH /strategies/:id` |
| `/creator/strategies/:strategyId/versions/:versionId` | Version detail + backtests | RequireCreator | Yes | `GET /strategies/:id/versions/:versionId`, backtest APIs |
| `/creator/strategies/:strategyId/versions/:versionId/backtests/:backtestId` | Backtest detail + analytics | RequireCreator | Yes | `GET .../backtests/:id`, `GET .../backtests/:id/analytics` |
| `/investor/allocations` | Investor allocation list | RequireInvestor | Yes | `GET /allocations`, `GET /marketplace/strategies` |
| `/investor/allocations/:allocationId` | Allocation detail + edit + delete | RequireInvestor | Yes | `GET /allocations/:id`, `PATCH /allocations/:id`, `DELETE /allocations/:id` |
| `/investor/execution-intents` | Execution intent list | RequireInvestor | Yes | `GET /execution-intents` |
| `/investor/execution-intents/:executionIntentId` | Execution intent detail + execute | RequireInvestor | Yes | `GET /execution-intents/:id`, `POST /execution-intents/:id/execute` |
| `*` | 404 Not Found | Public | No | None |

**Auth guards** (from `src/auth/guards.tsx`):
- `RequireAuth`: redirects to `/login` if unauthenticated, passes loading state
- `RequireCreator`: redirects to `/app` if user lacks `CREATOR` role
- `RequireInvestor`: redirects to `/app` if user lacks `INVESTOR` role

---

## 5. Component Inventory

### Shared / Layout

| Component | File | Description |
|-----------|------|-------------|
| `AppShell` | `components/AppShell.tsx` | Top-level layout: sticky header + `<Outlet>` |
| `AppErrorBoundary` | `components/AppErrorBoundary.tsx` | Class-based top-level error boundary |
| `LoadingState` | `components/PageState.tsx` | Spinning orbit + skeleton lines |
| `EmptyState` | `components/PageState.tsx` | Empty list/data state |
| `ErrorAlert` | `components/PageState.tsx` | Inline error alert block |

### Auth / Account Feature (`features/account/`)

| Component | File | Description |
|-----------|------|-------------|
| `LoginPage` | `AuthPages.tsx` | Email + password login form |
| `RegisterPage` | `AuthPages.tsx` | Registration form (name, email, password) |
| `AppPage` | `AccountPages.tsx` | Post-auth dashboard / workspace hub |
| `AccountPage` | `AccountPages.tsx` | User account details (email, roles, status) |
| `CreatorEnrollPage` | `AccountPages.tsx` | One-click Creator role enrollment |

### Creator Feature (`features/creator/`)

| Component | File | Description |
|-----------|------|-------------|
| `StrategyListPage` | `StrategyPages.tsx` | Table of user's strategies with lifecycle status |
| `StrategyNewPage` | `StrategyPages.tsx` | Create strategy form |
| `StrategyEditPage` | `StrategyPages.tsx` | Edit strategy metadata |
| `StrategyDetailPage` | `StrategyPages.tsx` | Strategy detail + versions list + lifecycle panel + delete zone |
| `StrategyVersionPage` | `StrategyPages.tsx` | Version detail + instrument info + JSON configs + backtests |
| `StrategyForm` (internal) | `StrategyPages.tsx` | Reusable name/slug/description form |
| `VersionCreator` (internal) | `StrategyPages.tsx` | Inline version creation form with instrument search |
| `Lifecycle` (internal) | `StrategyPages.tsx` | Lifecycle transition panel (publish/deploy/archive) |
| `VersionBacktests` | `BacktestPages.tsx` | Backtest list + create form (lazy-loaded sub-component) |
| `BacktestDetailPage` | `BacktestPages.tsx` | Backtest detail + analytics + equity chart |
| `Analytics` (internal) | `BacktestPages.tsx` | Backtest analytics: metrics grid + Recharts equity curve + table |

### Investor Feature (`features/investor/`)

| Component | File | Description |
|-----------|------|-------------|
| `AllocationListPage` | `AllocationPages.tsx` | Allocation list + inline create form |
| `AllocationDetailPage` | `AllocationPages.tsx` | Allocation detail + edit + delete + create execution intent |
| `ExecutionIntentListPage` | `ExecutionPages.tsx` | Execution intent list |
| `ExecutionIntentDetailPage` | `ExecutionPages.tsx` | Intent detail + execute + paper result display |
| `InstrumentDetails` (internal) | `ExecutionPages.tsx` | Instrument snapshot card |
| `PaperResult` (internal) | `ExecutionPages.tsx` | Paper execution result (order/fill/position) |
| `ResultBlock` (internal) | `ExecutionPages.tsx` | Generic JSON/text result card |

### Instruments Feature (`features/instruments/`)

| Component | File | Description |
|-----------|------|-------------|
| `InstrumentListPage` | `InstrumentPages.tsx` | Filterable instrument table with pagination |
| `InstrumentDetailPage` | `InstrumentPages.tsx` | Instrument detail (identity, exchange, trading metadata) |
| `InstrumentBadges` (internal) | `InstrumentPages.tsx` | Badge row for type, tradeability, active/synthetic state |

### Marketplace Feature (`features/marketplace/`)

| Component | File | Description |
|-----------|------|-------------|
| `MarketplaceListPage` | `MarketplacePages.tsx` | Public strategy discovery card grid |
| `MarketplaceDetailPage` | `MarketplacePages.tsx` | Public strategy detail page |

### Router-level (inline in `app/router.tsx`)

| Component | File | Description |
|-----------|------|-------------|
| `HomePage` | `app/router.tsx` | Full landing page (hero, workflow, feature splits, CTA) |
| `NotFoundPage` | `app/router.tsx` | 404 fallback |

---

## 6. Navigation & Header

The `AppShell` renders a single sticky top navigation bar with:

**Left:** Brand mark (`AlgoProfit X` with logo icon)  
**Center:** Primary nav links (conditional on auth/role):
- `Dashboard` (auth only)
- `Marketplace` (always)
- `Instruments` (always)
- `Strategies` (Creator role)
- `Allocations` + `Executions` (Investor role)

**Right:** Header actions:
- Unauthenticated: `Log in` + `Create account` button
- Authenticated: Role chips (Creator / Investor) + `Account` link + logout button (`↗` icon)

**No sidebar navigation exists.** All navigation is top-level horizontal. No mobile hamburger menu — nav wraps below the header at `≤820px`.

---

## 7. State Management

| Layer | Mechanism |
|-------|-----------|
| Server state / data fetching | TanStack React Query (queries + mutations) |
| Auth state | React Context (`AuthProvider`) backed by a React Query `useQuery` call |
| Form state | `react-hook-form` (auth forms) or plain `useState` (other forms) |
| Session / token | In-memory `accessToken` variable in `auth/session.ts` |
| Global client state | None (no Redux, Zustand, or equivalent) |

The access token is stored **purely in memory** (module-level variable). The refresh token is in an HttpOnly cookie (implied — the refresh endpoint uses `credentials: "include"`). Stale sessionStorage keys from a previous app name (`tradeebh`) are cleaned on module load.

---

## 8. API Client Architecture

**File:** `src/api/client.ts`

- All requests go through `apiRequest<T>(path, options)` — a typed fetch wrapper
- Base URL from `VITE_API_BASE_URL` environment variable, validated at startup
- `Authorization: Bearer <token>` header injected from in-memory session
- **Automatic token refresh:** 401 responses (on non-auth paths) trigger `refreshAccessToken()` via `POST /auth/refresh` with CSRF cookie header, then retry the original request once
- CSRF token read from `algoprofitx_csrf` cookie for logout + refresh endpoints
- Error responses parsed into `ApiError` with `status`, `message`, `fieldErrors[]`, and optional `requestId`
- Server errors (5xx) surface a reference ID to the user

---

## 9. API Endpoints — Complete Map

### Authentication (`/auth/`)
| Method | Path | Used by |
|--------|------|---------|
| POST | `/auth/register` | RegisterPage |
| POST | `/auth/login` | LoginPage via AuthContext |
| POST | `/auth/refresh` | Auto-refresh in API client |
| GET | `/auth/me` | AuthProvider (session restore) |
| POST | `/auth/logout` | AppShell logout button |
| POST | `/auth/creator/enroll` | CreatorEnrollPage |

### Strategies (`/strategies/`)
| Method | Path | Used by |
|--------|------|---------|
| GET | `/strategies` | StrategyListPage |
| POST | `/strategies` | StrategyNewPage |
| GET | `/strategies/:id` | StrategyDetailPage, StrategyEditPage, StrategyVersionPage |
| PATCH | `/strategies/:id` | StrategyEditPage |
| DELETE | `/strategies/:id` | StrategyDetailPage (danger zone) |
| POST | `/strategies/:id/publish` | Lifecycle panel |
| POST | `/strategies/:id/deploy` | Lifecycle panel |
| POST | `/strategies/:id/archive` | Lifecycle panel |
| GET | `/strategies/:id/versions` | StrategyDetailPage |
| POST | `/strategies/:id/versions` | VersionCreator |
| GET | `/strategies/:id/versions/:versionId` | StrategyVersionPage |
| GET | `/strategies/:id/versions/:versionId/backtests` | VersionBacktests |
| POST | `/strategies/:id/versions/:versionId/backtests` | VersionBacktests (create) |
| GET | `/strategies/:id/versions/:versionId/backtests/:backtestId` | BacktestDetailPage |
| POST | `/strategies/:id/versions/:versionId/backtests/:backtestId/execute` | BacktestDetailPage |
| GET | `/strategies/:id/versions/:versionId/backtests/:backtestId/analytics` | BacktestDetailPage |

### Marketplace (`/marketplace/`)
| Method | Path | Used by |
|--------|------|---------|
| GET | `/marketplace/strategies?limit&offset` | MarketplaceListPage, AllocationListPage (eligible strategies) |
| GET | `/marketplace/strategies/:slug` | MarketplaceDetailPage |

### Instruments (`/instruments/`)
| Method | Path | Used by |
|--------|------|---------|
| GET | `/instruments?limit&offset&search&exchange&instrument_type&is_tradeable&is_active` | InstrumentListPage, VersionCreator (instrument search) |
| GET | `/instruments/:id` | InstrumentDetailPage |

### Investor (`/allocations/`, `/execution-intents/`)
| Method | Path | Used by |
|--------|------|---------|
| GET | `/allocations` | AllocationListPage |
| POST | `/allocations` | AllocationListPage (create form) |
| GET | `/allocations/:id` | AllocationDetailPage |
| PATCH | `/allocations/:id` | AllocationDetailPage (edit form) |
| DELETE | `/allocations/:id` | AllocationDetailPage (danger zone) |
| POST | `/allocations/:allocationId/execution-intents` | AllocationDetailPage |
| GET | `/execution-intents` | ExecutionIntentListPage |
| GET | `/execution-intents/:id` | ExecutionIntentDetailPage |
| POST | `/execution-intents/:id/execute` | ExecutionIntentDetailPage |

---

## 10. CSS Architecture

### Organization
| File | Purpose |
|------|---------|
| `global.css` | Base CSS custom property tokens, reset, typography, shared primitives (cards, buttons, header, forms, alerts) |
| `creator.css` | Creator feature: badges, strategy tables, form stack, detail grid, version list, danger zone, backtest run list, metric cards, equity chart |
| `investor.css` | Investor feature: investor form, badge-row, result-grid, identity-meta |
| `instruments.css` | Instrument explorer: filter grid, pagination |
| `premium.css` | **Override layer** — redefines all `:root` tokens with darker/richer values, adds landing page, hero, terminal mock, workflow rail, feature splits, dashboard, marketplace, and responsive breakpoints |

### Token System (from `premium.css` — final values)
```css
/* Background scale */
--canvas: #050b12
--canvas-2: #08121d
--raised: #0b1723
--surface: #0d1a27
--surface-raised: #112333
--hover: #172e40

/* Borders */
--border: #1d3548
--border-strong: #315269

/* Text */
--text: #f4f8fb
--text-2: #c6d4df
--muted: #8ea6b8
--faint: #648094

/* Brand accent (teal-green) */
--accent: #19b995
--accent-hover: #28d0aa
--accent-soft: #0b3c35
--accent-text: #cafff2

/* Links / focus */
--link: #73c7ef
--focus: #71d7ff

/* Extended palette */
--cyan: #38aee8
--violet: #7d86ff

/* Semantic */
--success: #3ca47b / --success-bg: #123d31 / --success-text: #bdf4db
--warning: #d99d42 / --warning-bg: #453117 / --warning-text: #ffe0aa
--danger: #d46d70 / --danger-bg: #47252a / --danger-text: #ffd2d3
--info: #579bce / --info-bg: #15364f / --info-text: #cceaff
```

**Missing semantic tokens** (not currently defined): `--profit`, `--loss` (financial positive/negative), `--neutral`.

### Typography
- Body font: `IBM Plex Sans` → `Segoe UI Variable` → `Segoe UI` → `Inter` → system-ui
- Display/heading override in premium.css: `Segoe UI Variable Display` → `Aptos Display`
- Mono font: `Cascadia Mono` → `Consolas`
- Type scale: `--xs` (.75rem) → `--sm` (.875rem) → `--base` (1rem) → `--lg` (1.125rem) → `--xl` (1.4rem) → `--2xl` (clamp 1.8–2.6rem) → `--3xl` (clamp 2.45–4rem)
- Heading weights: h1 680, h2 650, h3 default (premium overrides to 720)

### Spacing Scale
`--s1` (.25rem) → `--s2` (.5rem) → `--s3` (.75rem) → `--s4` (1rem) → `--s5` (1.5rem) → `--s6` (2rem) → `--s7` (3rem) → `--s8` (4.5rem)

### Border Radius Scale
`--r1` (.5rem) → `--r2` (.75rem) → `--r3` (1.1rem) → `--r4` (1.5rem) → `--pill` (999px)

### Shadows
`--shadow-sm`: `0 8px 30px rgba(0,6,12,.18)`  
`--shadow-lg`: `0 28px 90px rgba(0,4,9,.46)`

---

## 11. Responsive Behavior

Three breakpoints in premium.css:

| Breakpoint | Changes |
|-----------|---------|
| `≤1100px` | Hero becomes single-column, workflow rail collapses to 4 cols, feature split gap reduces, dashboard grid 2-col, role cluster hides |
| `≤820px` | Header wraps (nav moves below brand), landing margin removes, terminal metrics 2x2, features stack, dashboard 1-col, disclosure stacks |
| `≤560px` | Hero h1 shrinks to 3rem, terminal metrics font shrinks, workflow 1-col, architecture grid 1-col, CTA buttons full-width, trust row 2-col |

Responsive issues noted:
- Instrument filter grid collapses to `1fr 1fr` at ≤850px and `1fr` at ≤540px
- Strategy table becomes block-layout at ≤760px (thead hidden)
- No mobile hamburger menu — nav is horizontally scrollable at mobile widths
- Run-list grid collapses at ≤760px

---

## 12. Icon / Asset Inventory

| Item | Implementation | Notes |
|------|--------------|-------|
| Icons | Unicode characters inline in JSX | ↗ (logout, empty state mark), ◎, ⌁, + |
| Brand mark | CSS bar-chart via `<i>` elements in JSX | Three `<i>` tags styled as vertical bars |
| Live dot | CSS `::before` via `.live-dot` class | Glowing circle for "live" indicators |
| Favicon | None declared | No `<link rel="icon">` in index.html |
| OG / social meta | None | Only `description` and `canonical` |
| Fonts | System fonts only | No Google Fonts, no hosted font files |
| Charts | Recharts (React) | Only on backtest equity curve |
| Hero chart | Inline SVG with CSS path animation | In router.tsx HomePage |

---

## 13. Performance Observations

- **Code splitting:** All Creator and Investor pages are lazy-loaded via `React.lazy` + dynamic `import()`. Instrument pages also lazy. Auth pages and Marketplace are NOT lazy (always eager-loaded).
- **Bundle split boundary:** `creatorPages`, `investorAllocationPages`, `investorExecutionPages`, `instrumentPages` each form their own chunk.
- **BacktestPages** is separately lazy-loaded even within the creator chunk (nested dynamic import).
- **Image payload:** None — no images loaded.
- **Third-party scripts:** None.
- **React Query caching:** `retry: 1`, `refetchOnWindowFocus: false` — conservative defaults.
- **No service worker, no PWA.**

---

## 14. Testing Infrastructure

- Framework: Vitest + jsdom + @testing-library/react
- Setup file: `src/test/setup.ts` (imports `@testing-library/jest-dom`)
- Test files exist alongside source: `*.test.tsx` / `*.test.ts`
- Tests confirmed present for: router, AppShell, AppErrorBoundary, AuthPages, AccountPages, guards, session, client, config, MarketplacePages, StrategyPages, BacktestPages, InstrumentPages, InvestorPages, productionSecurityPolicy

---

## 15. Authentication Flow Summary

1. App loads → `AuthProvider` calls `authApi.restore()` → attempts `POST /auth/refresh` (cookie-based) → if OK, calls `GET /auth/me` → stores token in memory
2. Login: `POST /auth/login` → sets access token in memory → re-fetches `/auth/me` for user data
3. Any 401 on a protected route → auto-refresh once → retry → if refresh also fails, clears session
4. Logout: `POST /auth/logout` (with CSRF header) → clears in-memory token + React Query cache
5. Creator enrollment: `POST /auth/creator/enroll` → updates React Query cache with returned user

---

## 16. Types and API Contract

All API types are generated from an OpenAPI spec via `openapi-typescript` into `src/api/generated/openapi.ts`. The `src/api/types.ts` re-exports named types from the generated file. This means the frontend type contract tracks the backend spec.

Types in use:
- `User` (UserResponse), `TokenResponse`
- `Strategy`, `StrategyCreateRequest`, `StrategyUpdateRequest`
- `StrategyVersion`, `StrategyVersionCreateRequest`
- `Backtest`, `BacktestCreateRequest`, `BacktestAnalytics`
- `MarketplaceStrategy`
- `Instrument`
- `Allocation`, `AllocationCreateRequest`, `AllocationUpdateRequest`
- `ExecutionIntent`, `ExecutionIntentCreateRequest`
- `RegisterRequest`, `LoginRequest` (local, not from OpenAPI)

---

## 17. Known Issues Identified During Audit

1. **No favicon** — `index.html` has no `<link rel="icon">`
2. **Ambiguous logout icon** — `↗` is used for both logout button and empty state indicator
3. **Semantic HTML issue** — `<i>` elements used for brand-mark bars (presentational)
4. **No mobile navigation** — horizontal scroll nav at mobile, no hamburger/drawer
5. **Mixed form patterns** — auth pages use react-hook-form; creator/investor pages use plain `useState` + `FormEvent`
6. **CSS load order coupling** — `premium.css` must be last; order is enforced only by import order in `main.tsx`
7. **premium.css redeclares all base tokens** — if premium.css fails to load, the app uses base (darker-ish) tokens; acceptable but fragile
8. **No page-level error boundaries** — only one top-level error boundary; a page crash shows a full-screen reload prompt
9. **Registration success redirects to `/login`** — user must log in again after registering (no auto-login)
10. **`RequireAuth` loading state** is a plain `<p>` not the styled `LoadingState` component
11. **`AppPage` (dashboard) has no real backend data summary** — shows static capability descriptions only
12. **AccountPage** is very sparse — only email, roles, and active status
13. **No strategy archive/restore** — lifecycle is one-way terminal
14. **No search/filter on strategy list** — no filtering across potentially large strategy sets
15. **VersionCreator search** — searches instruments on every keystroke (no debounce)
16. **Backtest status not auto-refreshed** — queued/running backtests require manual page reload to see status change
17. **`instrument_snapshot` on ExecutionIntent is cast as `Record<string, unknown> | null`** — no type safety on legacy result shapes
