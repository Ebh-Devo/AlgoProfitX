# AlgoProfitX — Frontend Technical Debt
> Phase 1 audit · September 2026

---

## Classification

| Severity | Label | Definition |
|---------|-------|-----------|
| High | `[H]` | Likely to cause bugs, accessibility failures, or user confusion in production |
| Medium | `[M]` | Causes maintenance friction or sub-optimal UX — no immediate failure |
| Low | `[L]` | Code quality, polish, or future-proofing |

---

## 1. CSS Architecture

### [H] Token override fragility — `premium.css` must be loaded last

**File:** `src/main.tsx` (import order)  
**Detail:** The entire design token system in `global.css` is completely overridden by `premium.css`. If `premium.css` fails to parse (e.g., a syntax error) or is loaded out of order, the app renders with the wrong background palette, wrong accent colors, and wrong typography. The cascade dependency is invisible to anyone reading either file in isolation.  
**Fix:** Consolidate all CSS custom property tokens into a single `tokens.css` file. Remove the duplicate `:root` block from `global.css`. `premium.css` becomes only overrides and additions (landing page styles, hero, etc.) rather than a complete token reset.

---

### [M] Minified CSS in source

**File:** `src/styles/global.css`, `src/styles/premium.css`  
**Detail:** The CSS files are written as single minified lines. This makes them extremely hard to read, diff, debug, and review. Vite minifies CSS at build time — there is no need to hand-minify the source.  
**Fix:** Format all CSS files as readable source with standard indentation. Vite's build step will minify for production.

---

### [M] Feature CSS styles bleed between features

**File:** `src/styles/creator.css`  
**Detail:** `creator.css` defines `.run-list`, `.metric-grid`, `.metric-card`, `.chart-card`, and `.equity-chart` — but these are also used in investor and backtest pages. The styling is coupled to a feature-named file but used globally. If an investor page ever needs a different `.run-list` style, there will be a conflict.  
**Fix:** Move shared styles (run-list, metric-grid, alert patterns) to `global.css` or a new `shared.css`. Feature CSS files should only contain styles exclusive to that feature.

---

### [L] Hardcoded color literals in premium.css

**File:** `src/styles/premium.css`  
**Detail:** Despite a token system existing, many CSS rules in `premium.css` use literal color values (`rgba(23,80,105,.3)`, `#1ad3a7`, `#097a82`, etc.) instead of referencing `--color-*` tokens. This means changing the brand accent color requires hunting through all CSS files.  
**Fix:** Define all unique color values as tokens, then reference only tokens in property rules.

---

## 2. JavaScript / TypeScript

### [H] Instrument search fires on every keystroke — no debounce

**File:** `src/features/creator/StrategyPages.tsx:42`  
**Detail:** `VersionCreator` passes `search` state directly as a React Query query key, triggering a new `GET /instruments?search=...` API call on every character typed. On slow connections this creates a waterfall of requests and may display stale results.  
**Fix:** Add a 300ms debounce to the search state update. `use-debounce` is a common pattern, or implement with a `useRef`/`setTimeout` approach without adding a dependency.

---

### [H] No polling for queued/running backtests or execution intents

**Files:**  
- `src/features/creator/BacktestPages.tsx:35`  
- `src/features/investor/ExecutionPages.tsx:174`  
**Detail:** When a Backtest is `queued` or `running`, the user sees an informational alert but the page never updates automatically. The user must manually reload to see status changes. This breaks the workflow — the user executes a backtest and then stares at a stale page.  
**Fix:** Add `refetchInterval: 5000` to the React Query `useQuery` for Backtest and ExecutionIntent when `status === "queued" || status === "running"`. Stop polling when status changes to `completed` or `failed`. No backend changes needed.

---

### [M] Mixed form management patterns

**Detail:** Authentication forms (`LoginPage`, `RegisterPage`) use `react-hook-form` with Zod validation. Creator and investor forms use plain `useState` + `FormEvent` handlers. This inconsistency means different code paths for error handling, field validation, accessibility, and submission state.  
**Files:**  
- `src/features/account/AuthPages.tsx` — uses RHF
- `src/features/creator/StrategyPages.tsx` — uses useState  
- `src/features/investor/AllocationPages.tsx` — uses useState  
**Fix:** Standardize on `react-hook-form` with Zod for all forms, or accept the mixed pattern if the simpler forms truly don't need schema validation. Document the rule.

---

### [M] Duplicate date formatting functions defined across multiple files

**Detail:** A local `date()` or `displayDate()` function is defined in at least 5 separate files:
- `MarketplacePages.tsx` → `displayDate()`
- `StrategyPages.tsx` → `date()`
- `BacktestPages.tsx` → `displayDate()`
- `AllocationPages.tsx` → `date()`
- `ExecutionPages.tsx` → `date()`

Each has slightly different type signatures (`string | null | undefined`), format options, and fallback values.  
**Fix:** Create `src/lib/format.ts` with `formatDate(value, options?)` and `formatDateTime(value)` utilities. Import from there.

---

### [M] Duplicate `errorMessage()` helper defined in multiple files

**Detail:** `const errorMessage = (error: unknown, fallback: string) => error instanceof ApiError ? error.message : fallback` is defined identically in `StrategyPages.tsx` and `BacktestPages.tsx`, with a slightly different name (`message`) in the investor files.  
**Fix:** Move to `src/lib/errors.ts` or `src/api/client.ts` and export it.

---

### [M] `RequireAuth` loading state uses unstyled `<p>` element

**File:** `src/auth/guards.tsx:9`  
**Detail:** While the `LoadingState` component exists and is used everywhere else, the auth guard renders `<p className="page-state">Loading your account…</p>`. The `page-state` class is not defined anywhere in the CSS. This renders as unstyled plain text during session restore, which can cause a brief flash of unstyled content on every page load.  
**Fix:** Replace with `<LoadingState label="Loading your account…" />`.

---

### [M] Registration success has no success feedback

**File:** `src/features/account/AuthPages.tsx:76`  
**Detail:** Successful registration silently redirects to `/login`. The user has no confirmation that their account was created. If the redirect is delayed or interrupted, the user may re-submit the form.  
**Fix:** After successful registration, pass a success flag via router state (`navigate("/login", { state: { registered: true } })`). On the login page, check for this flag and show a "Account created successfully. Please log in." message.

---

### [M] No favicon declared

**File:** `frontend/index.html`  
**Detail:** The `<head>` has no `<link rel="icon">`. Browsers will request `/favicon.ico` and receive a 404. This appears in browser developer tools and affects browser tab appearance.  
**Fix:** Create a simple favicon and add `<link rel="icon" type="image/svg+xml" href="/favicon.svg">`.

---

### [M] Session expiry does not redirect to login

**File:** `src/api/client.ts:64`  
**Detail:** When a token refresh fails mid-session, `clearSession()` is called and an `ApiError(401)` is thrown. This error propagates to the page's React Query error state, which shows a generic `ErrorAlert`. The user is not redirected to `/login` and must manually navigate. The header nav does update (via React Query invalidation) but the page content remains broken.  
**Fix:** In the auth context or a React Query error handler, detect `ApiError` with `status === 401` and redirect to `/login`. Or add a `subscribeToSession` listener in the router that triggers navigation on session clear.

---

### [L] `<i>` elements used for brand mark bars

**File:** `src/components/AppShell.tsx:20`  
**Detail:** `<i /><i /><i />` are used as decorative bars in the brand mark logo. `<i>` is a semantic HTML element for italic text — using it for purely decorative visual elements is incorrect. These should be `<span aria-hidden="true">` elements.  
**Fix:** Change to `<span aria-hidden="true" />` (with a className for styling).

---

### [L] `↗` used as logout button icon

**File:** `src/components/AppShell.tsx:33`  
**Detail:** The logout button uses `↗` (northeast arrow) as its icon — this is a conventional "open in new tab" or "navigate away" symbol, not a logout symbol. The button has `aria-label="Log out"` which saves screen reader users, but sighted users may be confused.  
**Fix:** Replace with a proper logout icon (e.g., Lucide `LogOut`).

---

### [L] `↗` used as EmptyState indicator

**File:** `src/components/PageState.tsx:8`  
**Detail:** Same symbol `↗` is used as the empty state icon, creating visual confusion with the logout button.  
**Fix:** Use `Inbox` or a context-appropriate icon from Lucide.

---

### [L] OpenAPI-generated types not committed or checked

**File:** `frontend/src/api/generated/openapi.ts`  
**Detail:** The file is generated by `pnpm generate:api-types` from the backend OpenAPI spec. If the spec changes and the types are not regenerated, the frontend TypeScript types silently diverge from the actual API contract.  
**Fix:** Either commit the generated file and regenerate in CI, or add a CI check that runs generation and fails if the file changed.

---

### [L] No Social/OG meta tags in `index.html`

**File:** `frontend/index.html`  
**Detail:** The page has a description and canonical URL but no `og:title`, `og:description`, `og:image`, `twitter:card`, etc. Links to AlgoProfitX pages will render poorly when shared on Slack, Twitter, or LinkedIn.  
**Fix:** Add standard Open Graph meta tags. These are static in `index.html` for an SPA (not page-specific, but a branded fallback is better than nothing).

---

### [L] No error boundary at the feature/page level

**File:** `src/components/AppErrorBoundary.tsx`  
**Detail:** The only error boundary wraps the entire application. A runtime JS error in (for example) the `Analytics` component on the Backtest Detail page will unmount the entire application and show the full-screen fatal error screen. The user loses all navigation context.  
**Fix:** Add per-page or per-section error boundaries, especially around the `Analytics` component and chart rendering (which has external data dependencies). React 18+ allows `<ErrorBoundary>` at any level in the tree.

---

### [L] `useQueryClient` dependency warning potential — `enrollCreator` in AuthContext

**File:** `src/auth/auth-context.tsx:34`  
**Detail:** The `useMemo` for `value` depends on `meQuery.data`, `meQuery.isLoading`, and `queryClient`. If `queryClient` is a new object reference on each render (it is not, but worth verifying), this would cause unnecessary re-renders. TanStack Query's `QueryClient` is stable — this is likely safe but should be verified.

---

## 3. UX / Accessibility Debt

### [H] No mobile navigation drawer

**Detail:** The nav collapses to a horizontally-scrollable strip at ≤820px. On most mobile devices the overflow is invisible and the extra nav items cannot be discovered. Users on mobile cannot navigate to Strategies, Allocations, or Executions without knowing to scroll the nav.  
**Fix:** Implement a hamburger menu with a drawer or bottom sheet for mobile.

---

### [M] Field error messages use bare `<small>` tags

**Files:** `src/features/account/AuthPages.tsx:58–60`  
**Detail:** Inline field errors are rendered as `<small>` elements. These are not programmatically associated with the input via `aria-describedby`. Screen readers may not announce them when the field is focused.  
**Fix:** Use `aria-describedby` on inputs pointing to the error element's `id`. Consider using `role="alert"` or `aria-live="polite"` on the error container.

---

### [M] No `<footer>` element

**Detail:** The app has no semantic footer. The landing CTA section acts as a visual footer but has no `<footer>` tag, no copyright, and no legal or contact information.  
**Fix:** Add a `<footer>` to `AppShell` (or as part of the landing page) with copyright, disclaimer link, and any required legal text.

---

### [L] Strategy table at mobile collapses `td:first-child` to block, but loses context

**File:** `src/styles/creator.css` (mobile breakpoint)  
**Detail:** At ≤760px, the strategy table hides `thead` and converts rows to block layout. But the column that becomes the block's "title" (`td:first-child`) contains the strategy name, slug, and description — which is correct. Other cells (`Status`, `Version`, `Published`, `Deployed`, `Actions`) appear without labels. A user on mobile has no column header context for what each value means.  
**Fix:** Add data-label attributes to `<td>` elements in JSX and use CSS `::before { content: attr(data-label) }` to display them in the mobile block layout.

---

## 4. Performance Debt

### [M] Auth pages not lazy-loaded

**File:** `src/app/router.tsx:7-8`  
**Detail:** `LoginPage` and `RegisterPage` are imported eagerly (not lazy). They are included in the main bundle even though they are only needed by unauthenticated users. Authenticated users pay the cost of this bundle unnecessarily.  
**Fix:** Lazy-load auth pages the same way creator/investor pages are lazy-loaded. The impact is small given the pages are simple, but it's consistent.

---

### [L] Marketplace pages not lazy-loaded

**File:** `src/app/router.tsx:8-9`  
**Detail:** `MarketplaceListPage` and `MarketplaceDetailPage` are eagerly imported. Given that not every authenticated user visits the marketplace immediately, these could be lazy.  
**Fix:** Same pattern as creator/investor pages — wrap in `lazy()`.

---

### [L] React Query stale time not configured

**File:** `src/main.tsx:15`  
**Detail:** The QueryClient is configured with `retry: 1` and `refetchOnWindowFocus: false`, but no `staleTime`. The default staleTime is 0, meaning every time a component mounts, React Query considers cached data stale and may refetch. For mostly-static data like instruments, marketplace strategies, and user profile, a staleTime of 5–60 minutes would reduce unnecessary API calls.  
**Fix:** Add `staleTime` to the QueryClient defaults, or configure per-query for stable data.

---

## 5. Summary Table

| Debt Item | Severity | Effort | Impact |
|-----------|---------|--------|--------|
| Token override fragility | H | Low | High |
| Minified CSS source | M | Low | Medium |
| No polling for queued states | H | Low | High |
| No mobile nav drawer | H | Medium | High |
| Instrument search debounce | H | Low | Medium |
| Mixed form patterns | M | High | Medium |
| Duplicate date/error helpers | M | Low | Low |
| RequireAuth loading state | M | Low | Low |
| Registration success feedback | M | Low | Medium |
| No favicon | M | Low | Low |
| Session expiry no redirect | M | Medium | Medium |
| `<i>` element brand mark | L | Low | Low |
| Logout icon confusion | L | Low | Medium |
| EmptyState icon confusion | L | Low | Low |
| No OG/social meta | L | Low | Low |
| No page-level error boundary | L | Medium | Medium |
| No mobile td labels | M | Low | Medium |
| Auth pages not lazy | L | Low | Low |
| Missing staleTime config | L | Low | Low |
| Missing profit/loss tokens | H | Low | High |
