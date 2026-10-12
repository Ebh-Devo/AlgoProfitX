# Catalyst Data Store Migration Audit

Status: inventory and design baseline. No production runtime has been switched.

## Target

The final runtime must use Zoho Catalyst-native services only:

```text
React/Vite -> Catalyst AppSail -> FastAPI -> Catalyst Data Store/ZCQL
```

PostgreSQL, Aiven, SQLAlchemy database sessions, `asyncpg`, Alembic, Redis,
and PostgreSQL TLS configuration are migration-era dependencies only. They
must not be required by the final Production runtime.

## Current Persistence Boundary

The canonical backend is not repository-based today. FastAPI routes inject
`AsyncSession`, and services issue SQLAlchemy ORM statements directly.

- Session and engine: `backend/app/db/session.py`
- ORM base: `backend/app/db/base.py`
- Route dependency: `backend/app/core/dependencies.py`
- Health/readiness: `backend/app/core/health.py`
- Configuration and PostgreSQL URI/TLS policy: `backend/app/core/config.py`
- Alembic environment and revision chain: `backend/alembic/`
- In-process worker startup: `backend/app/main.py`

The first implementation boundary should be:

```text
route -> service/use case -> repository or atomic command port -> Catalyst adapter
```

Routes and business behavior should not contain ZCQL strings.

The verified SDK dependency for the connectivity spike is
`zcatalyst-sdk==1.4.0`, imported as `zcatalyst_sdk`. Its official metadata
requires Python `>=3.10`, `requests~=2.34.2`, and
`typing-extensions~=4.12.1`. The existing dependency lock therefore uses the
compatible Pydantic `2.11.10` / `pydantic-core==2.33.2` pair and
`typing-inspection==0.4.2`; the previous Pydantic pins cannot resolve with the
official Catalyst SDK constraint.

## Entity Inventory

| Domain | Catalyst table candidates | Current source |
| --- | --- | --- |
| Identity | `users`, `roles`, `user_profiles`, `user_roles` | `backend/app/models/user.py` |
| Sessions | `auth_sessions` | `backend/app/models/auth_session.py` |
| Instruments | `exchanges`, `instruments`, `instrument_vendor_mappings` | `backend/app/models/instrument.py` |
| Strategies | `strategies`, `strategy_versions` | `backend/app/models/strategy.py` |
| Historical data | `market_data_datasets`, `market_data_candles` | `backend/app/models/market_data.py` |
| Backtesting | `backtests` | `backend/app/models/backtest.py` |
| Allocations | `allocation_intents` | `backend/app/models/allocation.py` |
| Paper execution | `execution_intents` | `backend/app/models/execution.py` |

`alembic_version` is migration metadata, not an application entity. It must
not be recreated as the production schema authority in Catalyst.

## PostgreSQL Dependencies To Replace

### Provider and schema

- `sqlalchemy.ext.asyncio.AsyncSession` and connection pooling.
- `asyncpg` and `postgresql+asyncpg` URL normalization.
- Alembic revisions, migration advisory locks, and raw SQL backfills.
- PostgreSQL UUID, JSONB, NUMERIC, ENUM, timezone timestamp, and partial-index
  behavior.
- Foreign keys with `CASCADE`, `RESTRICT`, and `SET NULL` actions.
- Unique and composite constraints, including partial unique indexes.
- PostgreSQL regex, JSON, length, and byte-size check constraints.

### Query and command behavior

- ORM joins and eager loading for strategy/instrument/marketplace reads.
- Scalar subqueries for strategy names and version numbers.
- `max(version_number)` plus `coalesce` for version creation.
- Case-insensitive filtering, ordering, pagination, and aggregates.
- `INSERT ... ON CONFLICT DO NOTHING` for role enrollment.
- `SELECT ... FOR UPDATE` for session, strategy, allocation, and execution
  race prevention.
- Conditional updates for execution and backtest claims and stale recovery.

### Runtime and operations

- PostgreSQL catalog/privilege queries in readiness checks.
- `DATABASE_URL`, `PGSSLROOTCERT`, `PGSSLROOTCERT_B64`, and pool settings.
- DigitalOcean PostgreSQL deployment definitions and Alembic pre-deploy jobs.
- Docker Compose PostgreSQL and Redis services.
- Process-local `asyncio.create_task()` backtest worker, which is not durable
  across AppSail restarts or multiple instances.

Redis is listed and provisioned but has no canonical application call sites in
the current backend. Abuse protection and concurrency limits are process-local;
they require an explicit Catalyst design if they must work across instances.

## Integrity and Atomicity Requirements

Catalyst repositories must expose atomic command methods where the current
implementation relies on a transaction or row lock. Do not translate a
protected read followed by an unguarded write into two independent calls.

Required command contracts include:

- Registration: create user, profile, and default-role membership consistently;
  duplicate email must be idempotently rejected.
- Refresh rotation: prevent token reuse and revoke/rotate atomically.
- Strategy versions: allocate the next version number without duplicates.
- Strategy lifecycle: prevent invalid concurrent state transitions.
- Allocations: validate ownership and snapshot the selected strategy version.
- Execution intents: enforce idempotency and one active execution per
  allocation.
- Backtests: claim queued work exactly once, recover stale work, and persist
  terminal state.
- Deletes: preserve history protections currently provided by foreign keys and
  application checks.

Where Catalyst cannot provide a native constraint or transaction, use a
conditional write, idempotency key, compensation path, or durable state
machine. Document every weakened provider guarantee in the adapter contract.

## Data Store Design Rules

- Generate IDs in the application and preserve UUID text values during the
  first migration.
- Store enum values as validated text fields.
- Normalize all timestamps to UTC ISO-8601 values unless the Catalyst SDK
  contract proves a stronger timestamp type is available.
- Preserve decimal monetary and price values without binary float conversion.
- Store small JSON objects only after validating size and object shape.
- Keep candle data separate from dataset metadata. Benchmark row limits,
  batch writes, and range reads before moving historical data into Data Store.
- Evaluate Catalyst File Store for large backtest artifacts; retain searchable
  metadata and checksums in Data Store.
- Use explicit denormalized snapshot fields for marketplace, allocation, and
  execution reads where joins or scalar subqueries are not reliable.
- Provision tables, columns, indexes, and native validators in Development.
  Export/import required data separately because environment deployment does
  not imply copying Development data to Production.

## Migration Work Packages

1. Add provider-neutral domain records, repository protocols, and an explicit
   unit-of-work/atomic-command contract.
2. Implement a Catalyst client wrapper with bounded retries, safe error
   translation, request correlation, and no secret logging.
3. Migrate users, roles, profiles, and auth sessions; replace PostgreSQL health
   checks with a non-mutating Catalyst Data Store check.
4. Migrate instruments and vendor mappings, including active-mapping rules.
5. Migrate strategies and versions, including lifecycle and version allocation.
6. Migrate allocations, marketplace reads, execution intents, and paper
   execution state machines.
7. Migrate market-data metadata and candles after a Catalyst capacity test;
   move large artifacts to a Catalyst-native file service if required.
8. Replace the in-process backtest worker with a durable Catalyst-supported
   job/function/event mechanism.
9. Create a sanitized PostgreSQL export/import utility only if production
   data exists and must be preserved.
10. Remove database URL/TLS/pool/Alembic runtime requirements only after all
    Development gates pass and rollback artifacts exist.

## Required Validation Gates

Development must pass, against Catalyst Data Store:

- API liveness and readiness.
- Registration, login, logout, refresh rotation, and session limits.
- Creator and Investor authorization flows.
- Strategy CRUD, lifecycle, and versioning.
- Instruments and vendor mappings.
- Marketplace reads.
- Allocations and execution idempotency.
- Paper backtests, durable job status, results, and analytics.
- Failure recovery for partial writes, duplicate requests, and worker claims.

Before production declaration, the release artifact must prove that the final
runtime does not require `DATABASE_URL`, `asyncpg`,
`postgresql+asyncpg`, PostgreSQL TLS variables, an Aiven hostname, or an Aiven
credential. Legacy migration tooling may remain outside the production
artifact while the rollback window is open.

## Current Branch Safety

The audit was performed on `codex/production-readiness-worker`. The worktree
already contains an untracked `.release/` directory; it is generated/release
material and was not modified. Catalyst migration implementation should be
developed in a dedicated branch or clearly separated PR series, leaving the
current PostgreSQL release path available as rollback until Development gates
pass.