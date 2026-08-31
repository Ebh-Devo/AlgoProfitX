# Production runtime packaging

No production deployment exists yet. This provider-neutral packaging does not create cloud resources, publish an image, configure DNS, or run migrations automatically.

## Artifacts and process

Build the backend OCI image from `backend/Dockerfile` with `backend/` as its context. It uses CPython 3.13.7 on Debian Bookworm slim and contains the FastAPI application, Alembic migrations, and production dependencies constrained by the canonical lock. It contains no database or frontend server. The unprivileged user/group `10001:10001` owns the application files; the runtime does not write to `/app`.

The image starts one Uvicorn process with one worker:

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1 --timeout-graceful-shutdown 30 --no-access-log
```

`PORT` defaults to `8000`. `UVICORN_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS` can change the 30-second grace period. Uvicorn handles SIGTERM/SIGINT, drains in-flight requests, and runs the FastAPI lifespan shutdown, which disposes the SQLAlchemy engine. Long-running Backtests may later move to a durable worker/job architecture.

Initially scale by container replicas, not in-process workers. Approximate maximum application connections as `replicas x workers x (DB_POOL_SIZE + DB_MAX_OVERFLOW)`. With one worker and defaults `5 + 2`, each replica can open seven application connections. Reserve capacity for migration, administration, and provider overhead.

The frontend remains a separate Vite static artifact. From `frontend/`, `pnpm build` writes `frontend/dist`. Production builds require `VITE_API_BASE_URL=https://api.algoprofitx.com/api/v1`; this is public browser configuration, not a secret. FastAPI does not serve the frontend.

## Health and migration

- Liveness: `GET /health/live` checks process health without PostgreSQL or market-data access.
- Readiness: `GET /health/ready` checks traffic eligibility and PostgreSQL readiness, returning 503 when unavailable.

The OCI `HEALTHCHECK` uses Python's standard library and liveness semantics, so curl and database access are unnecessary. Configure managed-runtime probes with the same distinct mappings.

Use the same image as a separate one-shot migration job. The existing PostgreSQL advisory lock rejects overlapping runners. The web process never migrates on startup.

```text
python -m alembic upgrade head
python -m alembic current --check-heads
```

Release order: confirm backup/PITR or a recovery checkpoint, migrate once, verify the head, then roll out replicas. `python -m alembic check` is an optional schema-model drift check in CI or a controlled verification environment; it does not replace `current --check-heads`.

## Production environment contract

Inject secrets at runtime; never pass them as build arguments or copy them into the image.

Required secrets:

- `DATABASE_URL`: external `postgresql+asyncpg` URL containing database credentials.
- `SECRET_KEY`: unique high-entropy value of at least 32 bytes.

Required public/runtime configuration:

- `APP_ENV=production`, `DEBUG=false`, `DATABASE_REQUIRE_TLS=true`.
- `FRONTEND_PUBLIC_URL`, `API_PUBLIC_URL`, and comma-separated `CORS_ALLOWED_ORIGINS` using the validated AlgoProfitX HTTPS origins.
- `AUTH_COOKIE_SECURE=true`, `AUTH_COOKIE_HTTPONLY=true`, `AUTH_COOKIE_SAMESITE`, and `AUTH_COOKIE_PATH`.
- `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, and `AUTH_JWT_KEY_ID`.
- `ABUSE_PROTECTION_ENABLED=true`.
- `MARKET_DATA_PROVIDER=synthetic` is a valid initial baseline. It means synthetic/reference historical data, not real NSE market data.

Optional tunables with application defaults:

- `PORT`, `UVICORN_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS`, `LOG_LEVEL`, `LOG_FORMAT`, `API_DOCS_ENABLED`, `READINESS_DB_TIMEOUT_SECONDS`, and `REQUEST_ID_HEADER`.
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS`, `DB_POOL_PRE_PING`, and `DB_EXTERNAL_TRANSACTION_POOLER`.
- Access/refresh/session lifetime, cookie name/domain, and all login, registration, creator, Backtest, and execution abuse-control settings.
- Synthetic market-data timeout, retry, range, and candle limits.

`backend/.env.example` is the field-by-field development reference. Production values belong in the runtime secret/config store. Logs go to stdout/stderr (JSON by default in production). Historical datasets remain in PostgreSQL; there is no local SQLite or persistent-filesystem fallback.

## Local image test

Docker packaging is additive and is not required for normal Windows development or tests.

```powershell
docker build --build-arg VCS_REF=$(git rev-parse HEAD) --build-arg SOURCE_URL=https://github.com/Roshan-Baghwar/TradeEBH -t algoprofitx-backend:f1 .\backend
docker run --rm -p 8000:8000 --env-file .\backend\.env algoprofitx-backend:f1
```

The environment file is runtime-only and is never copied into the image. A syntactically valid but unreachable development PostgreSQL URL is enough for a liveness-only smoke because `/health/live` does not connect. Readiness requires the confirmed local development/test PostgreSQL environment.

Inspect the result:

```powershell
docker image inspect algoprofitx-backend:f1 --format '{{.Config.User}}'
docker run --rm --entrypoint sh algoprofitx-backend:f1 -c 'test ! -e /app/.env && test ! -d /app/tests && test ! -d /app/.git'
```

The expected user is `10001:10001`. The backend-scoped `.dockerignore` excludes secrets, Git/editor metadata, caches, tests/coverage, database dumps, frontend output, and Node dependencies while preserving application and Alembic files.
