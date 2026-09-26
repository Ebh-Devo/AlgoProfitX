# AlgoProfitX — Frontend User Flows
> Phase 1 audit · September 2026

---

## Flow 1 — Public Visitor

### 1.1 Landing → Discovery
```
/ (HomePage)
├── Read hero section, workflow rail, feature splits
├── Click "Explore marketplace" → /marketplace
│   └── Browse public strategy cards (list)
│       └── Click strategy → /marketplace/:slug (detail)
└── Click "Explore Instruments" → /instruments
    └── Search/filter → paginate
        └── Click row → /instruments/:id (detail)
```

**API calls triggered:**  
- `/marketplace` page: `GET /marketplace/strategies?limit=20&offset=0`  
- `/marketplace/:slug`: `GET /marketplace/strategies/:slug`  
- `/instruments` page: `GET /instruments?limit=20&offset=0&is_active=true`  
- `/instruments/:id`: `GET /instruments/:id`  

**Current state:** All pages render without authentication. Error states handled. Empty states handled. No login gate for public pages.

---

### 1.2 Landing → Register

```
/ → Click "Start building" or "Create account"
→ /register (RegisterPage)
  ├── Fill: Name (optional), Email, Password
  ├── Submit → POST /auth/register
  │   ├── Success → redirect to /login
  │   │   └── User must log in again (no auto-login after registration)
  │   └── Error → ErrorAlert + field-level errors from API
  └── Click "Log in" → /login
```

**Known UX friction:** User must complete a second step (login) after successful registration. No verification email step exists in the current flow — registration is immediate.

---

### 1.3 Landing → Login

```
/ → Click "Log in"
→ /login (LoginPage)
  ├── Fill: Email, Password
  ├── Submit → POST /auth/login → GET /auth/me
  │   ├── Success → redirect to /app (or saved "from" location)
  │   └── Error → ErrorAlert + field-level errors
  └── Click "Create an account" → /register
```

**Redirect logic:** If user accessed a protected route while unauthenticated, location is saved in router state and restored after login.

---

## Flow 2 — New User (Post-Registration)

### 2.1 First Login → Dashboard

```
POST /auth/login → /app (AppPage)
  ├── Auth state restored via GET /auth/me
  ├── Dashboard shows:
  │   ├── Role status row: Creator (Available) + Investor (Active) + Market Identity + Execution (Paper)
  │   ├── "Expand your workspace" card → link to /creator/enroll
  │   ├── "Investor workspace" card → links to /investor/allocations + /investor/execution-intents
  │   └── "Instrument Explorer" card → link to /instruments
  └── No real backend data shown — static capability descriptions only
```

**Note:** New users automatically have the `INVESTOR` role. They do NOT have the `CREATOR` role by default.

---

### 2.2 Creator Enrollment

```
/app → "Enroll as Creator" button → /creator/enroll (CreatorEnrollPage)
  ├── Page shows: explanation + "Enroll as Creator" button
  ├── Click → POST /auth/creator/enroll
  │   ├── Success → shows "Your account has the Creator role." alert
  │   │   └── AuthContext updates with new user object (now has CREATOR + INVESTOR roles)
  │   │   └── Nav immediately shows "Strategies" link
  │   └── Error → ErrorAlert
  └── If already Creator → shows success state immediately (no API call needed)
```

---

## Flow 3 — Creator Workspace

### 3.1 Creator → Strategy Management

```
/creator/strategies (StrategyListPage)
  ├── GET /strategies → table of strategies with status badges
  ├── Click "Create strategy" → /creator/strategies/new
  └── Click "View" → /creator/strategies/:id (detail)
      └── Click "Edit metadata" → /creator/strategies/:id/edit
```

---

### 3.2 Create Strategy

```
/creator/strategies/new (StrategyNewPage)
  ├── Fill: Name, Slug, Description
  ├── Submit → POST /strategies
  │   ├── Success → redirect to /creator/strategies/:id (new strategy detail)
  │   └── Error → ErrorAlert + field-level errors (e.g. slug collision)
  └── Click "← Strategies" → /creator/strategies
```

**New strategy starts in `draft` status.**

---

### 3.3 Strategy Detail → Lifecycle Management

```
/creator/strategies/:id (StrategyDetailPage)
  ├── GET /strategies/:id + GET /strategies/:id/versions (parallel)
  ├── Metadata card: slug, current version, timestamps
  ├── Lifecycle panel (Lifecycle component):
  │   ├── draft → available actions: [publish, archive]
  │   │   ├── "Publish" → POST /strategies/:id/publish → status: published
  │   │   └── "Archive" → confirm prompt → POST /strategies/:id/archive → status: archived (terminal)
  │   ├── published → available actions: [deploy, archive]
  │   │   ├── "Deploy" → POST /strategies/:id/deploy → status: deployed
  │   │   └── "Archive" → confirm prompt → terminal
  │   ├── deployed → available actions: [archive]
  │   └── archived → no actions (terminal)
  ├── Versions section (VersionCreator + version list):
  │   ├── Click "Create Version" → inline form appears
  │   │   ├── Search instruments → GET /instruments?search=...
  │   │   ├── Select instrument from dropdown
  │   │   ├── Enter JSON: algorithm config + backtest config
  │   │   └── Submit → POST /strategies/:id/versions
  │   └── Click version → /creator/strategies/:id/versions/:versionId
  └── Danger zone:
      ├── "Delete strategy" → confirm prompt
      └── Confirm → DELETE /strategies/:id → redirect to /creator/strategies
```

---

### 3.4 Strategy Version Detail → Backtest Workflow

```
/creator/strategies/:id/versions/:versionId (StrategyVersionPage)
  ├── GET /strategies/:id/versions/:versionId
  ├── Instrument summary card (or legacy/unresolved message)
  ├── Algorithm config JSON (read-only pre block)
  ├── Backtest config JSON (read-only pre block)
  └── VersionBacktests section (lazy-loaded):
      ├── GET /strategies/:id/versions/:versionId/backtests
      ├── "Create Backtest" → inline form
      │   ├── Optional: Market data reference field
      │   └── Submit → POST /strategies/:id/versions/:versionId/backtests
      └── Click backtest row → /creator/strategies/:id/versions/:versionId/backtests/:backtestId
```

---

### 3.5 Backtest Execution → Analytics

```
/creator/strategies/:id/versions/:versionId/backtests/:backtestId (BacktestDetailPage)
  ├── GET /strategies/.../backtests/:id
  ├── Status: queued → "Execute Backtest" button visible
  │   └── Click → POST .../execute → updates status to running/completed/failed
  ├── Status: completed → loads analytics automatically
  │   ├── GET .../analytics → BacktestAnalytics data
  │   ├── Metrics grid: capital, return, trade count, win rate, profit factor, etc.
  │   ├── Equity curve chart (Recharts LineChart)
  │   ├── Equity point detail table (collapsible)
  │   └── Engine/provider identity cards
  ├── Status: failed → error alert with error_code + error_message
  └── Status: running/queued → info alert (no auto-refresh — user must reload)
```

**Critical gap:** Queued/running backtests have no polling or WebSocket — user must manually refresh the page to check status.

---

## Flow 4 — Investor Workspace

### 4.1 Investor → Allocation Management

```
/investor/allocations (AllocationListPage)
  ├── GET /allocations → list of allocation intents
  ├── "Create allocation" → inline form appears
  │   ├── GET /marketplace/strategies?limit=100&offset=0 (loads eligible deployed strategies)
  │   ├── Select deployed strategy from dropdown
  │   ├── Enter notional amount (INR)
  │   ├── Enter currency (default: INR)
  │   └── Submit → POST /allocations
  └── Click allocation row → /investor/allocations/:id
```

---

### 4.2 Allocation Detail → Create Execution Intent

```
/investor/allocations/:id (AllocationDetailPage)
  ├── GET /allocations/:id
  ├── Details: amount, strategy name, pinned version, timestamps
  ├── "Create Execution Intent" → POST /allocations/:id/execution-intents
  │   └── On success → redirect to /investor/execution-intents/:newId
  ├── "Edit allocation" → inline edit form (amount + currency)
  │   └── Submit → PATCH /allocations/:id
  └── Danger zone: "Delete allocation" → confirm → DELETE /allocations/:id
```

---

### 4.3 Execution Intent → Paper Execution

```
/investor/execution-intents (ExecutionIntentListPage)
  └── GET /execution-intents → list rows

/investor/execution-intents/:id (ExecutionIntentDetailPage)
  ├── GET /execution-intents/:id
  ├── Status: pending → "Execute Paper Intent" button
  │   └── Click → POST /execution-intents/:id/execute
  │       ├── Success → intent status updates (running → completed or failed)
  │       └── Error → ErrorAlert
  ├── Status: completed → PaperResult component
  │   ├── Alert: filled or no-fill outcome
  │   ├── Paper result detail table (symbol, signal, outcome, notional, etc.)
  │   └── Order / Fill / Position result blocks (JSON)
  ├── Status: failed → error alert with error_code + error_message
  └── Status: running → info alert (no auto-refresh)
```

---

## Flow 5 — Account Management

### 5.1 Account Settings

```
/account (AccountPage)
  ├── GET /auth/me (already in cache from AuthProvider)
  ├── Shows: email, roles, account status
  └── No edit capability — read only
```

**Current state:** Very sparse page. No ability to change email, password, or name. No settings whatsoever.

---

## Flow 6 — Session Lifecycle

### 6.1 Session Restore on App Load

```
App loads → AuthProvider mounts
  → POST /auth/refresh (uses HttpOnly cookie)
    ├── Success → setAccessToken(token) → GET /auth/me → user loaded into context
    │   └── UI shows authenticated state, nav adapts to roles
    └── Failure (no cookie or expired) → clearSession() → user is unauthenticated
        └── UI shows unauthenticated state
```

### 6.2 Token Expiry During Session

```
User makes request → 401 response
  → apiRequest triggers refreshAccessToken()
    ├── POST /auth/refresh → Success → retry original request
    └── Failure → clearSession() → throws ApiError(401)
        └── Unhandled in pages → ErrorAlert shown
        └── No automatic redirect to /login (relies on user clicking links)
```

**Note:** On token expiry, the user is not automatically redirected to `/login`. They see an API error. They must manually navigate to log in again.

### 6.3 Logout

```
Click logout (↗ button) in header
  → POST /auth/logout (with CSRF header)
  → clearSession() (regardless of API result — finally block)
  → navigate to /
  → React Query cache cleared for ["auth", "me"]
```

---

## Flow 7 — Error Recovery Paths

| Scenario | Current Behavior |
|---------|-----------------|
| Page-level API error | `ErrorAlert` component rendered inline in page |
| 404 from API | Custom message in ErrorAlert (e.g., "Strategy not found.") |
| 5xx from API | `ApiError` with reference ID shown in ErrorAlert |
| App-level JS crash | `AppErrorBoundary` shows full-screen reload prompt |
| Network offline | fetch() throws, caught as non-ApiError, generic "try again" message |
| Invalid route | `NotFoundPage` (`<h1>Page not found</h1>`) — no styling |

---

## Flow 8 — Complete Navigation State Machine

```
Unauthenticated
  ├── / (landing)
  ├── /login
  ├── /register
  ├── /marketplace (+ /:slug)
  └── /instruments (+ /:id)

Authenticated (INVESTOR role, no CREATOR)
  ├── Everything above
  ├── /app (dashboard — shows "Enroll as Creator" prompt)
  ├── /account
  ├── /creator/enroll
  ├── /investor/allocations (+ /:id)
  └── /investor/execution-intents (+ /:id)

Authenticated (INVESTOR + CREATOR roles)
  ├── Everything above
  ├── /app (dashboard — shows Creator workspace card)
  ├── /creator/strategies (+ /new)
  ├── /creator/strategies/:id (+ /edit)
  ├── /creator/strategies/:id/versions/:versionId
  └── /creator/strategies/:id/versions/:versionId/backtests/:backtestId
```
