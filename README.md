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
| Frontend | Creator and Investor MVP journeys and role-aware navigation |

The frontend uses Vite, React, TypeScript, React Router, TanStack Query, generated OpenAPI types, and Recharts. The backend uses FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL, Pydantic, and pytest.

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

### Migrations

Preferred command from `TradeEBH\`:

```powershell
.\scripts\migrate.ps1
```

The current Alembic head is `e5a1b2c3d4f6` (`rebrand_synthetic_instrument`). Direct manual-venv commands:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current --check-heads
```

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

- Health: <http://127.0.0.1:8000/health>
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

Frontend validation:

```powershell
cd frontend
pnpm typecheck
pnpm test
pnpm build
```

With the API running, regenerate TypeScript OpenAPI contracts after backend schema changes:

```powershell
cd frontend
pnpm generate:api-types
```

The script defaults to `http://127.0.0.1:8000/openapi.json`; set the process-only `OPENAPI_URL` variable for another local endpoint.

The development frontend stores JWTs in `sessionStorage`, clears them after a `401`, and has no refresh-token flow. This is MVP behavior, not production session hardening.

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
