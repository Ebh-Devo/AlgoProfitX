# AlgoProfitX

AlgoProfitX is a strategy-first trading marketplace MVP connecting strategy Creators and Investors. It supports strategy versioning, reference backtesting and analytics, marketplace discovery, allocation intents, and deterministic paper execution.

The intended product domain is [https://www.algoprofitx.com](https://www.algoprofitx.com) (`algoprofitx.com`). This document does not imply that a production deployment is currently live there.

> Product name: **AlgoProfitX**. Repository name and existing local folder: **TradeEBH** until the GitHub repository is renamed separately.

> Paper Execution uses synthetic NSE/INR reference data. It is not real NSE market data, live broker execution, or funded capital.

## Contents

- [Current status](#current-status)
- [Windows prerequisites](#windows-prerequisites)
- [Fresh Windows setup](#fresh-windows-setup)
- [PostgreSQL](#postgresql)
- [Backend](#backend)
- [Production runtime packaging](docs/production-runtime.md)
- [Frontend](#frontend)
- [Two-terminal workflow](#two-terminal-workflow)
- [Demo walkthrough](#demo-walkthrough)
- [Troubleshooting](#troubleshooting)
- [Future work](#future-work)

## Current status

| Area | Implemented |
| --- | --- |
| Identity | Registration, login, JWT authentication, `/auth/me`, roles |
| Creator | Enrollment/authorization, Strategy CRUD, immutable Versions |
| Lifecycle | Draft, publish, deploy, and archive transitions |
| Marketplace | Anonymous public Strategy list and detail |
| Backtesting | Requests, deterministic reference execution, status/errors |
| Analytics v1 | Return, trades, win/loss, drawdown, equity curve |
| Investor | Allocation Intents pinned to a Strategy Version |
| Execution | Execution Intents and deterministic Paper Execution |
| Market foundation | Exchange/Instrument identity, vendor-neutral mappings, anonymous discovery APIs |
| Historical datasets | Provider-independent async boundary, immutable daily candles, checksums, provenance, synthetic default |
| Frontend | Creator and Investor MVP journeys and role-aware navigation |

The frontend uses Vite, React, TypeScript, React Router, TanStack Query, generated OpenAPI types, and Recharts. The backend uses FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL, Pydantic, and pytest.

Provider-neutral production runtime packaging and its environment, migration, health-probe, and local image-test contracts are documented in [Production runtime packaging](docs/production-runtime.md). No production deployment exists yet.

## Windows prerequisites

| Tool | Supported/recommended version |
| --- | --- |
| Windows | Windows 10/11 x64 |
| Git | Current Git for Windows |
| Python | CPython 3.13 x64 |
| PostgreSQL | PostgreSQL 17 recommended locally; scripts support 16+ |
| Node.js | Current Node.js LTS |
| pnpm | `pnpm@11.19.0` (declared in `frontend/package.json`) |
| VS Code | Optional |
| Docker | Optional; not required for native Windows development |

Redis is not required by any currently implemented functionality.

### Historical market-data architecture

Backtests resolve the server-configured provider, acquire or reuse an immutable `MarketDataDataset`, validate normalized OHLCV candles, and execute only from persisted candles. The default `synthetic` adapter is deterministic and credential-free. No real vendor adapter is configured: production use still requires a contracted, appropriately licensed market-data source and provider-specific credentials. Provider mappings remain private, are resolved by provider and validity range, and are snapshotted into bounded provenance without secrets. Phase 2F.1 supports daily (`1d`), unadjusted data; it does not claim to provide real NSE history.

Install Node.js LTS:

```powershell
winget install --id OpenJS.NodeJS.LTS -e --source winget
```

Restart PowerShell or refresh `PATH` afterward. Use Corepack when available:

```powershell
corepack enable
corepack prepare pnpm@11.19.0 --activate
```

Otherwise install pnpm globally:

```powershell
npm install -g pnpm
```

Do not use `npm install` for project dependencies; the frontend uses `pnpm-lock.yaml`.

## Fresh Windows setup

```powershell
git clone <repository-url>
cd TradeEBH
```

This repository's current URL is `https://github.com/Roshan-Baghwar/TradeEBH.git`. Renaming it requires a separate GitHub account operation; no code change can perform that safely.

### Preferred bootstrap

Run from `TradeEBH\`:

```powershell
.\scripts\bootstrap-windows.ps1
```

This verifies Python 3.13, creates `TradeEBH\.venv`, and installs deterministic dependencies from committed `backend\requirements.lock`.

```powershell
.\scripts\bootstrap-windows.ps1 -PythonCommand 'C:\Path\To\python.exe'
```

### Manual backend environment

For direct backend commands:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.lock
```

This creates `backend\.venv`. The canonical root scripts use `TradeEBH\.venv`; prefer `bootstrap-windows.ps1` when using the root scripts.

If activation is blocked:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## PostgreSQL

| Setting | Native Windows value |
| --- | --- |
| Host | `localhost` |
| Port | `5432` |
| Application role | `tradebh` |
| Development database | `tradeebh` |
| Test database | `tradeebh_test` |

Credentials belong only in local configuration. Never commit passwords, tokens, private keys, or database URLs containing real passwords.

These database and role identifiers intentionally remain compatibility names for existing installations. Fresh setup uses the same defaults so scripts, CI, and local environments remain interoperable. Renaming them requires a separately planned PostgreSQL administrative migration; the application never drops or recreates them during this rebrand.

Start PostgreSQL, then run from `TradeEBH\`:

```powershell
.\scripts\initialize-postgres.ps1
```

The safe initializer securely prompts for PostgreSQL superuser authentication, creates missing role/databases, leaves existing resources unchanged, and never drops databases. It is idempotent where practical and supports partially initialized installations. Use `-PsqlPath` if `psql` cannot be found. Never put a real password in documentation or committed scripts.

Docker is optional. An older Docker mapping may expose PostgreSQL on `5433`; native PostgreSQL normally uses `5432`. Match local URLs to the service actually running.

## Backend

### Configuration

Use [backend/.env.example](backend/.env.example). From `TradeEBH\backend`:

```powershell
cd backend
Copy-Item .env.example .env
```

Configure local-only values:

```dotenv
DATABASE_URL=postgresql+asyncpg://tradebh:<local-password>@localhost:5432/tradeebh
TEST_DATABASE_URL=postgresql+asyncpg://tradebh:<local-password>@localhost:5432/tradeebh_test
SECRET_KEY=<local-development-secret>
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

`.env` is ignored by Git. Native PostgreSQL URLs use port `5432`. Generate a unique local secret; never reuse placeholder/example secrets in production.

#### Production configuration safety

Production mode is enabled only by setting `APP_ENV=production`; it is never inferred from a hostname or hosting platform. In that mode startup fails closed unless debug is off, the JWT secret is non-placeholder and at least 32 bytes, the canonical HTTPS frontend origin is allowed, public URLs use the expected HTTPS domains, the PostgreSQL host is non-local, and encrypted database transport is required. The expected public topology is `https://www.algoprofitx.com` for the frontend and `https://api.algoprofitx.com` for the API. These are configuration targets only and do not mean either service is currently deployed.

Set `DATABASE_REQUIRE_TLS=true` for managed PostgreSQL; this enables asyncpg's generic SSL transport without assuming a particular cloud provider. Production SQL echo is always disabled. `API_DOCS_ENABLED` defaults to false in production, removing `/docs`, `/redoc`, and `/openapi.json`; programmatic schema generation through `app.openapi()` remains available to CI. Generate each production `SECRET_KEY` with a cryptographically secure secret generator and store it outside source control—never copy a value from this README or `.env.example`.

The canonical browser origin is `https://www.algoprofitx.com`. The apex `https://algoprofitx.com` should permanently redirect to the canonical `www` origin rather than act as an application origin. Credentialed CORS permits only exact configured origins so the browser can send the host-only refresh cookie to the API; wildcard origins remain forbidden. The synthetic market-data provider remains permitted so a production-mode staging/paper/backtesting environment can start before a licensed real-data adapter exists; it must not be presented as real NSE data.

#### Application abuse controls

Registration and login are rate-limited by the ASGI client address; login also has a normalized email-key limit that behaves identically whether or not an account exists. Creator enrollment, Backtest creation/execution, and Paper Execution Intent creation/execution use authenticated user IDs. Backtest execution additionally has a per-user concurrency limit. Policies are configured through the `*_LIMIT` and `*_WINDOW_SECONDS` settings shown in `backend/.env.example`, and production refuses to start with `ABUSE_PROTECTION_ENABLED=false`.

These controls are async-safe but process-local. They do not coordinate across workers or replicas, and client identity deliberately ignores untrusted forwarded headers until trusted-proxy runtime configuration exists. A multi-replica deployment must replace the storage implementation with a distributed limiter such as Redis without changing route semantics. Edge/CDN/WAF controls are still required; this application layer is not DDoS protection.

#### Runtime health and observability

`GET /health/live` is the lightweight liveness probe: it performs no database,
market-data, or other external call. The legacy `GET /health` remains a
compatibility alias. `GET /health/ready` performs only a bounded PostgreSQL
`SELECT 1`, using `READINESS_DB_TIMEOUT_SECONDS=2` by default, and returns a
sanitized `503 {"status":"unavailable"}` when the database cannot be reached.
Readiness deliberately never contacts a market-data provider or broker. Alembic
head verification remains the responsibility of Task C's one-runner deployment
migration job; it is not repeated on frequent readiness probes and the
application never migrates on startup.

Every request receives an `X-Request-ID`. A caller value is preserved only when
it is 1–64 characters and matches the restricted identifier alphabet; otherwise
a UUID is generated. The ID is placed in context for downstream events and
returned in the response. It is diagnostic metadata, not a credential.

Production defaults to newline-delimited JSON logs; development defaults to a
readable console format. Request completion events include only request ID,
method, route template/path without query text, status, and duration. Headers,
cookies, and bodies are not logged. The centralized event helper recursively
redacts token, cookie, password, secret, API-key, and database-credential fields,
and also scrubs bearer values and PostgreSQL URL passwords. Unexpected failures
are logged internally with the request ID and stack trace while clients receive
only a generic error and reference ID. Expected HTTP/domain failures retain
their existing API behavior.

The application emits bounded security, Backtest, market-data, and paper-only
execution lifecycle events and feeds a provider-neutral metrics interface. The
default metrics implementation exports nothing and there is no public
`/metrics` endpoint; a production monitoring backend remains a deployment
choice. Because the application already emits one structured completion event,
run Uvicorn with `--no-access-log` in production to avoid duplicate access
records (keep Uvicorn error logs enabled).

Normal ASGI graceful shutdown stops new acceptance according to the server,
allows its configured grace period for in-flight requests, and then disposes the
SQLAlchemy engine. Process-local limiter state is not forcibly cleared during
shutdown. Long-running Backtests may eventually require a durable worker/job
system; this task does not add one.

#### Authentication sessions

Browser authentication uses short-lived HS256 access JWTs in memory and opaque rotating refresh tokens in an HttpOnly cookie. Access JWTs contain `sub`, `type`, `exp`, `iat`, `iss`, `aud`, and `jti`, plus a `kid` header for future signing-key rotation. Refresh-token plaintext is never persisted: the database stores only a SHA-256 hash in a restrictive `AuthSession` record. Refresh rotates the token atomically; reuse of a rotated token revokes that session family. Logout revokes the current session and clears its cookies, and the configurable per-user session cap prunes older records.

Refresh and logout use double-submit CSRF protection: JavaScript reads the separate non-HttpOnly `algoprofitx_csrf` cookie and sends it as `X-CSRF-Token`, while the refresh token remains inaccessible to JavaScript. Cookies are host-only by default, scoped to `/api/v1/auth`, and `SameSite=Strict`; production requires both `Secure=true` and an HttpOnly refresh cookie. Credentialed CORS remains restricted to exact configured origins.

The frontend removes both `algoprofitx.auth.session` and the legacy `tradeebh.auth.session` key, never writes new tokens to browser storage, restores page reloads through refresh, retries a failed bearer request at most once, and deduplicates concurrent refresh attempts. Email verification delivery, password reset, MFA, asymmetric signing keys, and user-facing session management remain future work.

### Migrations

Production uses a single migration runner; application replicas never run Alembic
on startup. The provider-neutral release sequence is: verify backup/PITR health,
take a manual snapshot for a significant migration when supported, stop or hold
the new application release, run `alembic upgrade head` exactly once, verify
`alembic current --check-heads`, and only then start or promote application
replicas. Online Alembic runs acquire an AlgoProfitX-specific PostgreSQL advisory
lock and fail clearly if another migrator owns it. Alembic downgrade is useful
for development validation, but production data recovery relies on a tested
snapshot/PITR restore plan rather than downgrade.

Preferred command from `TradeEBH\`:

```powershell
.\scripts\migrate.ps1
```

The current Alembic head is `c6d1e8f3a9b2` (`harden_historical_retention`). Direct manual-venv commands:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current --check-heads
```

#### Production database durability

Production application processes use SQLAlchemy's async adapted queue pool with
conservative defaults: `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=2`,
`DB_POOL_TIMEOUT_SECONDS=10`, `DB_POOL_RECYCLE_SECONDS=1800`, and
`DB_POOL_PRE_PING=true`. Development and tests retain `NullPool` for isolation.
Set `DB_EXTERNAL_TRANSACTION_POOLER=true` only when `DATABASE_URL` explicitly
targets a separately operated transaction-mode pooler; this project does not
deploy one. TLS connect arguments remain active in either mode. FastAPI disposes
the engine during graceful shutdown.

Size PostgreSQL deliberately: approximate maximum application connections as
`workers × (pool_size + max_overflow)`, plus migration, administration, and
provider-reserved capacity. At the defaults, two workers can open at most
`2 × (5 + 2) = 14` application connections. Production expects managed
PostgreSQL with encryption at rest, encrypted transport, automated backups,
PITR, and private-network access; the database must not be publicly exposed.

Historical retention treats Strategy Versions, Backtests, market-data datasets
and provenance, Allocations, and Execution Intents/results as reproducibility
records. Their parent foreign keys restrict deletion. A user account should be
deactivated and, when required, anonymized instead of deleted once it owns or
requested history. A published/deployed/archived Strategy is archived, not
deleted; only an unused draft can be deleted. Dataset-owned candles, user-role
links, profiles, and Auth Sessions remain lifecycle children and may be removed
with their aggregate. Instrument and vendor-mapping references remain
restrictive; deactivate superseded reference data instead of deleting it.

Initial product objectives are **RPO <= 15 minutes** and **RTO <= 2 hours**.
These are targets, not guarantees, until the selected managed service is
configured and restore drills demonstrate them. Before significant migrations,
confirm automated backup/PITR health, confirm restore capability, take a manual
snapshot when supported, retain the recovery point and instructions, migrate
once, and verify the Alembic head.

A provider-neutral restore drill must never overwrite production:

1. Create an isolated restore database and restore the chosen snapshot/PITR point.
2. Verify private TLS connectivity and run `alembic current --check-heads` plus `alembic check`.
3. Compare critical counts and relationships for users, strategies, Strategy Versions, Backtests, datasets/candles, Allocations, executions, and relevant Auth Sessions.
4. Check that every historical child resolves its required parent, dataset candle counts/checksums are internally consistent, and execution/allocation strategy-version pairs match.
5. Run registration/authentication, strategy/history reads, backtest reads, and paper-execution read smoke checks against the isolated environment.
6. Record timings and findings, then destroy the isolated drill environment according to the provider's safe process.

Restoring the application database does not guarantee that an external market
data vendor can reproduce data that was never persisted; vendor licensing,
availability, and separate source retention remain external concerns.

### Market and Instrument bootstrap

After migrating, run the versioned, idempotent reference-data bootstrap from `backend`:

```powershell
python -m app.bootstrap.instruments
```

The Phase 2A bootstrap uses stable UUIDs and creates NSE, BSE, the explicitly synthetic `ALGOPROFITX_TEST_EQ` reference equity, and non-tradeable NIFTY 50 and NIFTY Bank index identities. It is a small platform reference manifest—not a live NSE/BSE Instrument Master and not market data.

The synthetic equity keeps UUID `20000000-0000-4000-8000-000000000001`. The rebrand migration changes only its current canonical symbol and display name. Persisted Strategy JSON, Backtests, provenance, Allocation Intents, Execution Intents, and paper-result snapshots containing legacy `TRADEEBH_TEST_EQ` remain unchanged and supported by the execution providers.

Anonymous read-only discovery is available at:

- `GET /api/v1/instruments`
- `GET /api/v1/instruments/{instrument_id}`

The list supports bounded `limit`/`offset` pagination and `exchange`, `instrument_type`, `symbol`, `search`, `is_tradeable`, and `is_active` filters. Vendor identifiers are deliberately excluded. Instrument writes remain bootstrap/import-only; inactive records are hidden by default but remain directly readable by UUID.

### Run the API

Preferred command from `TradeEBH\`:

```powershell
.\scripts\run-api.ps1
```

Direct equivalent:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Liveness: <http://127.0.0.1:8000/health/live> (`/health` remains an alias)
- Readiness: <http://127.0.0.1:8000/health/ready>
- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>

### Tests and database safety

Tests refuse to run without `TEST_DATABASE_URL` and verify that the database name is exactly `tradeebh_test`. Never test against `tradeebh`.

Preferred command from `TradeEBH\`:

```powershell
.\scripts\test.ps1
```

Temporary current-shell configuration, if needed:

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://tradebh:<local-password>@localhost:5432/tradeebh_test'
.\scripts\test.ps1
Remove-Item Env:TEST_DATABASE_URL
```

Direct manual-venv equivalent:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
$env:TEST_DATABASE_URL='postgresql+asyncpg://tradebh:<local-password>@localhost:5432/tradeebh_test'
$env:DATABASE_URL=$env:TEST_DATABASE_URL
python -m alembic -c alembic.ini upgrade head
python -m pytest
```

## Frontend

Use [frontend/.env.example](frontend/.env.example). From `TradeEBH\frontend`:

```powershell
cd frontend
Copy-Item .env.example .env
```

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Install and run:

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Open <http://localhost:5173>. The backend needs `CORS_ALLOWED_ORIGINS=http://localhost:5173`. If CORS errors appear, update `backend\.env` and restart the backend.

The intended production topology is `https://www.algoprofitx.com` for the SPA
and `https://api.algoprofitx.com` for the API. Production builds accept only
`VITE_API_BASE_URL=https://api.algoprofitx.com/api/v1`; localhost remains valid
for development. All `VITE_*` variables are public browser configuration and
must never contain passwords, tokens, API keys, signing secrets, or private
vendor settings. Domain ownership and these configuration targets do not mean
the frontend is deployed: it remains a localhost/development application until
separate hosting, DNS, certificate, and release work is completed.

The provider-neutral [frontend production hosting contract](docs/frontend-production-hosting.md)
defines the required HTTPS and apex-to-`www` redirects, browser-history SPA
fallback, CSP and other security headers, cache behavior, source-map policy,
and API boundary. The eventual frontend hosting/edge layer must apply these
headers and rewrite rules; no provider has been selected or configured here.

Frontend validation:

```powershell
cd frontend
pnpm typecheck
pnpm test
$env:VITE_API_BASE_URL='https://api.algoprofitx.com/api/v1'
pnpm build
Remove-Item Env:VITE_API_BASE_URL
```

With the API running, regenerate TypeScript OpenAPI contracts after backend schema changes:

```powershell
cd frontend
pnpm generate:api-types
```

The script defaults to `http://127.0.0.1:8000/openapi.json`; set the process-only `OPENAPI_URL` variable for another local endpoint.

Access JWTs remain in memory only and legacy browser-storage keys are actively
removed. Refresh uses the Secure, HttpOnly, host-only API cookie through
`credentials: include`; frontend JavaScript reads only the separate CSRF cookie
and sends `X-CSRF-Token`. The exact production frontend origin must remain in
the backend credentialed CORS allowlist. Localhost uses environment-specific
cookie/CORS settings without weakening production cookie policy.

## Two-terminal workflow

Open two PowerShell terminals at `TradeEBH\`.

Terminal 1 — backend:

```powershell
.\scripts\migrate.ps1
.\scripts\run-api.ps1
```

Terminal 2 — frontend:

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Open <http://localhost:5173>.

## Demo walkthrough

1. Register an account.
2. Log in.
3. Enroll as a Creator if needed; the Investor role is preserved.
4. Create a draft Strategy.
5. Create an immutable Strategy Version by selecting the canonical Instrument (for this reference walkthrough, `ALGOPROFITX_TEST_EQ`).

Configuration example:

```json
{
  "entry": {
    "type": "ema_crossover",
    "fast_period": 5,
    "slow_period": 12
  }
}
```

Backtest configuration example:

```json
{
  "initial_capital": "100000.00",
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "commission": "0.00",
  "slippage": "0.00"
}
```

6. Save both Version JSON objects. Instrument identity is stored separately from the algorithm JSON; a matching legacy `configuration.instrument` value is accepted only for transitional compatibility.
7. Publish the Strategy.
8. Deploy the Strategy.
9. Create/execute a Backtest and inspect Analytics.
10. Browse the Marketplace as an Investor.
11. Create an Allocation Intent; the server pins the current Version.
12. Create and execute a pending Paper Execution Intent.

`ALGOPROFITX_TEST_EQ` and its NSE/INR candles are deterministic synthetic fixtures—not a real security or real market data. Paper Execution does not contact a broker or use funded capital.

## Troubleshooting

| Symptom | Safe resolution |
| --- | --- |
| `python -m pytest`: `No module named pytest` | The wrong/global Python is active. Activate `.venv` or use `.\scripts\test.ps1`. |
| `TEST_DATABASE_URL must be set` | Use `test.ps1` with `backend\.env`, or set a temporary URL targeting only `tradeebh_test`. |
| `pnpm` not recognized | Install Node.js LTS, then use Corepack or `npm install -g pnpm`. |
| `node` not recognized after installation | Restart the terminal or refresh `PATH`. |
| Blank browser page | Verify `frontend\.env` and `VITE_API_BASE_URL`, then restart Vite. |
| Browser CORS failures | Set `CORS_ALLOWED_ORIGINS=http://localhost:5173` and restart the backend. |
| PostgreSQL port mismatch | Native uses `5432`; an old Docker mapping may use `5433`. |
| PowerShell activation blocked | Use `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`. |
| `psql` not found | Install PostgreSQL command-line tools or pass `-PsqlPath`. |

## Future work

Not yet implemented:

- real market data and an exchange-backed Instrument Master;
- real brokers, live execution, and reconciliation;
- funded balances, payments, or custody;
- production authentication/session hardening;
- advanced portfolio and risk analytics;
- real execution workers, retries, and Redis-backed queues.

## Repository structure

```text
TradeEBH/
├── backend/                 FastAPI application, migrations, tests
├── frontend/                Vite + React + TypeScript application
├── scripts/                 Canonical Windows development scripts
├── .github/workflows/       CI configuration
├── docker-compose.yml       Optional local infrastructure
└── README.md
```
