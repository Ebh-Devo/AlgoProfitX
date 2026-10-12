# Catalyst-only runtime

AlgoProfitX runs entirely on Zoho Catalyst. Persistence is Catalyst Data Store, queried with ZCQL. No
PostgreSQL, Aiven, Redis or any other external database or infrastructure is part of a deployed runtime.

```text
Browser -> web AppSail (static SPA + restricted /api/v1 proxy) -> API AppSail (FastAPI) -> Catalyst Data Store / ZCQL
```

## Persistence providers

| Provider | Allowed where | Purpose |
|---|---|---|
| `catalyst` | everywhere; the default for every non-test environment | the only provider a deployed runtime can use |
| `postgresql` | `APP_ENV` `test` or `development`, never in production, never inside a Catalyst AppSail | local test tooling for the legacy PostgreSQL test suite |

Guards (`backend/app/core/config.py`, tested in `test_production_config.py` and `test_catalyst_only_runtime.py`):

- `PERSISTENCE_PROVIDER=postgresql` is a configuration error in production and whenever
  `X_ZOHO_CATALYST_LISTEN_PORT` is set (the AppSail marker). The runtime then serves only `/health/live`
  and returns 503 for everything else; it never opens a database connection.
- With the Catalyst provider, `DATABASE_URL`, `PGSSLROOTCERT*` and `DATABASE_REQUIRE_TLS` are discarded at
  startup, so a leftover variable on an AppSail can never be used.
- There is no silent fallback: an unset provider resolves to `catalyst` (outside `APP_ENV=test`).

## Dependencies

`backend/requirements-production.txt` (the deployed image) contains no `asyncpg`, `alembic`, `redis` or
other database driver, and the image ships no `alembic/` directory. Redis was never used by application
code and is removed everywhere (manifests, lock, settings, Compose).

**Documented exception:** `sqlalchemy` stays in the production manifest. The shared domain models still
subclass SQLAlchemy declarative types and many modules import their enums and column types. It is used as
a type library only: no engine, session or driver is created in the Catalyst provider (asserted by
`test_catalyst_only_runtime.py`). Extracting the enums and records from the ORM models, which would let
SQLAlchemy leave the image, is a follow-up refactor.

## Data Store tables (Development)

`AlgoProfitXUsers`, `Roles`, `AuthSessions`, `AuthSessionSlots`, `RefreshClaims`, `Exchanges`, `Instruments`,
`Strategies`, `StrategyVersions`, `StrategyLocks`, `Backtests`, `BacktestClaims`, `BacktestTerminals`,
`Allocations`, `Executions`, `ExecutionClaims`, and `MigrationProbe`. Column-level documentation:
`catalyst-*-development-schema.md`. Tables are provisioned by an operator in the Catalyst console; the
application never creates, alters or drops them.

The Data Store has no transactions. Uniqueness-based claim and lock tables (`StrategyLocks`,
`AuthSessionSlots`, `RefreshClaims`, `BacktestClaims`, `BacktestTerminals`, `ExecutionClaims`) provide
mutual exclusion and exactly-once behavior; they are preserved unchanged.

## Strategy V2 and `definition_schema_version`

`definition_schema_version` (1 = V1 adapter, 2 = V2 runtime) is the only selector for how a stored
definition is interpreted. It is needed on `StrategyVersions` and on `Backtests` (snapshot).

Until the column is provisioned on a table, the code treats the table as legacy:

- every row reads as V1 (identical to the PostgreSQL default and migration), V1 behavior is unchanged;
- writing a V2 version or V2 backtest is **refused** (503 `strategy_definition_v2_storage_unavailable`)
  rather than stored where it would read back as V1;
- availability is probed read-only and cached (30 s when absent, 5 min when present); a failed probe with an
  unreadable table is an outage and is surfaced, never treated as "column missing".

V2 versions can be backtested only; publishing, deploying and allocating them is refused with the structured
409 `strategy_definition_version_unsupported_for_execution` (same contract as the PostgreSQL path).

The exact, documented console plan (with sources, what Catalyst does and does not state, runbook and rollback) is in
[catalyst-v2-schema-plan.md](catalyst-v2-schema-plan.md); it is **not approved and not applied**. Summary of the proposal: add an integer column `definition_schema_version`
(not mandatory, default 1, not unique, not indexed) to `AlgoProfitXStrategyVersions` and
`AlgoProfitXBacktests`. No data rewrite. Rollback: stop writing V2 (revert the application; the nullable
column is harmless to leave) and never drop the column while any row has a value other than 1.

## ZCQL result limits (documented) and how reads are bounded

Sources: Catalyst Docs, [General Syntax of SELECT](https://docs.catalyst.zoho.com/en/cloud-scale/help/zcql/select/),
[LIMIT clause](https://docs.catalyst.zoho.com/en/cloud-scale/help/zcql/limit/) and the
[Cloud Scale FAQ](https://docs.catalyst.zoho.com/en/faq/cloud-scale/) (read 2026-10-10).

| Documented | Detail |
|---|---|
| Rows per SELECT | **at most 300** ("a maximum of 300 rows in one SELECT query"; FAQ: "Why do I get only 300 rows ... ?"). |
| Explicit columns | **at most 20** ("a maximum of 20 columns"); `SELECT *` has no stated column limit. |
| More rows | iterate with `LIMIT [offset,]count`; the docs are not consistent about whether `offset` is 0- or 1-based. |
| **Not stated** | what happens when a limit is exceeded (error or silent cut), a maximum `LIMIT` value, query-length or rate limits. |

Design (`persistence/catalyst/paging.py`), assuming the worst where the docs are silent:

- Every multi-row read goes through `query_all`: **keyset paging on `ROWID`** (`... AND ROWID > <last> ORDER BY ROWID LIMIT 250`),
  which needs no offset semantics. Pages are below the 300 cap and a short page ends the loop.
- It **fails closed**: more than `DEFAULT_MAX_ROWS` (5,000) rows, or pages that cannot be continued safely (missing/non-numeric/
  non-advancing `ROWID`), raise `CatalystResultTooLarge`/`CatalystPersistenceError`. A truncated list is never returned.
- Reads that need more than 20 columns (`Backtests`, 29-30; `Executions`, 22) use `SELECT *`; no explicit list exceeds 20.
- Single-row lookups keep `LIMIT 1`. A static test fails if a new direct `async_query_rows` call has no `LIMIT`.
- Affected before this change: marketplace (read *all* strategies, drafts included, then filtered in Python), instrument catalog,
  strategies per creator, versions per strategy (**a version number computed as `max()+1` over a 300-row cut would collide after the
  300th version**), backtests per version, allocations/executions per investor, claims and slots.
- Tests emulate the provider (silent 300-row cut, 20-column rejection) in `tests/catalyst_memory.py`; with the old unpaged code 8 of the
  paging tests fail.

### Live verification (Development ZCQL Console, read-only, 2026-10-10; authorized as "Phase A" in #46)

SELECT statements only against non-sensitive tables (Instruments, Exchanges, Strategies, Backtests, StrategyVersions); no writes,
no schema change, no Production. Results:

| Question | Observed |
|---|---|
| `ORDER BY ROWID` | accepted; ascending numeric ROWIDs (`DESC` also works) |
| `WHERE ROWID > <n>` | accepted; numeric compare; works together with `status = '...'`, `is_active = true`, `ORDER BY ROWID` and `LIMIT 250` (the exact shapes `query_all` generates) |
| `SELECT *` | accepted; returns every column plus `CREATORID`/`CREATEDTIME`/`MODIFIEDTIME` (Instruments 21 columns, Backtests 32; more than 20 is fine); NULL shows as `null` in the console grid |
| Explicit columns above 20 | **accepted**: 21 and the 29 columns the previous code used both returned in full. The documented 20-column limit is **not enforced** (at least in the console, today); the code still avoids relying on that |
| `LIMIT` above 300 | **error**: `ZCQL CANNOT HAVE MORE THAN 300 ROWS in LIMIT` (300 accepted, 301 rejected) |
| `LIMIT offset,count` | offsets are **1-based** (`0` behaves like `1`; `3,1` is the third row; `4,1` returns nothing). The docs' example is ambiguous; keyset paging is unaffected |
| Unknown column in a `SELECT` | **error**: `Unkown Table <T> or Unkown Column <c> in SELECT` (sic), as the schema-capability probe assumes |

Console trap found: after an *error*, the Output panel keeps showing the **previous** result, so a failed query can look like it
returned data. (I initially misread `LIMIT 1000` that way; the error is recorded above.)

**Still not verified live** (needs more than 300 rows, i.e. writes or a scratch table, which are not authorized): whether a SELECT
*without* a `LIMIT` over a result larger than 300 rows is cut silently or is an error (the code assumes a silent cut and pages below it),
and how the SDK (not the console) shapes results for `SELECT *`. The code paths that were *not* exercised live are the repository
CRUD operations of this branch (they need a Development deployment, a later gate).

## Backtesting

Supported modes: `inline` and `disabled`. Production must be `disabled`. There is no `worker` mode, no
Catalyst Job Scheduling submission and no background poller. A claimed backtest carries a lease
(`BACKTEST_CLAIM_LEASE_SECONDS`); a request that dies leaves a claim that expires and can be reclaimed
through the claim table. Market data is synthetic.

## Same-origin proxy

The browser talks only to the web origin; `frontend/server.py` forwards a restricted set of requests to the
API:

- only `/api/v1` and below; `..`, `.`, empty segments, `//`, backslashes, encoded `.`/`/`/`\`/NUL, control
  characters, non-ASCII and over-long targets are rejected (400); other `/api/*` is 400;
- only `GET`, `HEAD`, `POST`, `PATCH`, `DELETE` (405 otherwise; no `PUT`, no `OPTIONS`, no `CONNECT`);
- the upstream is one HTTPS origin taken from `frontend/environments.json` for the baked `APP_ENV`;
  `API_PUBLIC_ORIGIN` may only select another origin already approved for that environment;
- only `Accept`, `Authorization`, `Content-Type`, `Cookie`, `User-Agent`, `X-CSRF-Token`, `X-Request-ID`
  are forwarded; `Host` is the upstream's, hop-by-hop headers are dropped both ways;
- bodies up to 8 MiB (chunked supported with limits), upstream timeout 30 s (504), upstream failure 502
  without detail, status codes and bodies preserved;
- upstream `Set-Cookie` has any `Domain=` attribute removed so cookies stay host-only to the web origin;
  set `AUTH_CSRF_COOKIE_DOMAIN` unset in Development.

CSP is `connect-src 'self'` for every environment (no API origin, no wildcard); the server refuses to start
without a known `APP_ENV`.

## Bundle isolation

A built web bundle carries only its own environment's approved API URL and web origin (injected at build time by
`vite.config.ts`; the environment table is not imported into browser code). `scripts/verify-bundle-isolation.mjs` inspects
the build output and fails on any other environment's origin, any API upstream origin, retired hosting origins, or the legacy
Cloudflare `_headers` file (which is removed from every build). It runs in the Docker build and in CI for both environments, and CI
also asserts each bundle fails the other environment's check and that a build without a declared environment fails.

## Environments

`frontend/environments.json` is the single table of approved origins (public values only). A built bundle
must declare `VITE_APP_ENV`, and the Docker build fails if the API URL is not the same-origin URL approved
for it (`frontend/scripts/check-environment.mjs`). Production URLs are unchanged:
`https://www.algoprofitx.com` (web) proxying to `https://api.algoprofitx.com`.

## Testing

Automated tests use in-memory Data Store doubles (`tests/catalyst_memory.py`) and never touch a live Catalyst
environment. The legacy PostgreSQL suite needs a local `TEST_DATABASE_URL` (a `tradeebh_test` database on
localhost) and runs only as test tooling.

### Running the tests locally (reproduces CI)

`tests/conftest.py` detaches settings from your git-ignored `backend/.env` (only `TEST_DATABASE_URL` is still read from it,
on purpose) and defaults `SECRET_KEY` the way CI does, so a local run sees the same configuration as CI. From `backend/`:

```bash
# Catalyst-only checks: no database needed (any TEST_DATABASE_URL value is never connected to)
TEST_DATABASE_URL=postgresql+asyncpg://x:x@localhost:5432/tradeebh_test   python -m pytest tests/test_catalyst_*.py tests/test_web_proxy.py tests/test_workflow_environment_isolation.py

# Everything, including the legacy PostgreSQL suite (needs a local database named tradeebh_test)
python -m pytest
```

```powershell
$env:TEST_DATABASE_URL='postgresql+asyncpg://tradebh:<local-password>@localhost:5432/tradeebh_test'
python -m pytest
```

The end-to-end Catalyst tests (`test_catalyst_end_to_end.py`) run the real app on the Catalyst provider against an in-memory
Data Store that mirrors the real tables' uniqueness; they use dev's own HTTP helpers, so the Catalyst provider is exercised
through the same API calls as the PostgreSQL contract tests. They are still doubles, not a live Catalyst test.

### Live Catalyst integration procedure (prepared, not run)

Run only with explicit approval, against Development, using a throwaway user and strategy:

1. `GET /health/catalyst` -> SDK, Data Store and ZCQL checks pass (read-only).
2. Register, log in, refresh, log out; confirm cookies (`HttpOnly` refresh cookie scoped to `/api/v1/auth`,
   readable CSRF cookie, no `Domain`) and that a missing `X-CSRF-Token` yields 403.
3. Create a V1 strategy/version, publish, deploy, allocate (investor), confirm rows in the Data Store.
4. With the schema column unprovisioned: a V2 create returns the 503 above and stores nothing.
5. After the approved schema change: V2 create succeeds, V2 backtest completes, publish/allocate of V2 is 409.
6. Delete the throwaway rows through the repository cleanup paths.
