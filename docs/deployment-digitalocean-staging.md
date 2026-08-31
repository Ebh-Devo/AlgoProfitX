# DigitalOcean staging deployment specification

This is a reviewable plan. No DigitalOcean resource, deployment, DNS record, certificate, or paid feature has been created. The proposed app is `algoprofitx-staging` in App Platform region `blr` (Bangalore, backed by `blr1`). Production remains separate and untouched.

## Topology, sizing, and cost

| Component | Configuration | Estimated monthly cost |
| --- | --- | ---: |
| Frontend | Static site; `frontend/`; `pnpm build`; `dist` | $3 conservative mixed-app estimate; confirm in account summary |
| API | One `apps-s-1vcpu-1gb-fixed` instance; 1 shared vCPU/1 GiB; F1 image; one worker | $10.00 |
| Migration | One `apps-s-1vcpu-0.5gb` PRE_DEPLOY job using the F1 image | Prorated only while running; normally cents/deployment |
| PostgreSQL | Standard Basic Regular; one 1 GiB/1 vCPU node; 10 GiB; PostgreSQL 17 | $15.15 |

The steady-state estimate is **$28.15/month**, plus taxes, job runtime, transfer/storage overages, and account-specific static pricing. The static free tier is documented for static-only apps, so this mixed app budget includes $3. The database is managed production-class, not an App Platform development database. Future dedicated egress is up to **$25/month**, producing a planning total of $53.15 before usage and tax. Verify the account summary before provisioning.

PostgreSQL 17 is pinned by major and DigitalOcean supplies its latest supported minor. It is supported through November 2029. This single-node tier is not multi-node HA, but includes managed operation, TLS, daily backups, and seven-day PITR. It is suitable for initial staging and can be resized after measurement.

The 1 GiB database allows 22 backend connections. Staging sets `DB_POOL_SIZE=3` and `DB_MAX_OVERFLOW=1`:

```text
1 replica x 1 worker x (3 + 1) = 4 maximum application connections
```

The migrator uses one direct connection, leaving at least 17 of 22 for administration, platform operations, and recovery. Do not increase replicas, workers, or pool values independently.

## App Spec design

[`deploy/digitalocean/staging.yaml`](../deploy/digitalocean/staging.yaml) contains one static site, one Dockerfile service, one PRE_DEPLOY job, and an attachment to a separately created cluster named `algoprofitx-staging-pg`. Source is `Roshan-Baghwar/TradeEBH` branch `main`; `deploy_on_push: false` requires manual approval after CI.

The API context is `backend`; its root-relative Dockerfile is `backend/Dockerfile`. `http_port` is 8080 and the F1 command consumes App Platform's `PORT`, binds `0.0.0.0`, and runs one worker. Readiness is DB-dependent `/health/ready`; liveness is DB-independent `/health/live`. App Platform drains for 30 seconds and allows 45 seconds after TERM; Uvicorn's grace period remains 30 seconds.

The only migrator executes:

```text
python -m alembic upgrade head && python -m alembic current --check-heads
```

Failure blocks rollout. The advisory lock prevents overlap and web startup never migrates. Order: recovery point, one migration job, head verification in that job, rollout.

`${staging-postgres.DATABASE_URL}` normally supplies `postgresql://` with libpq TLS query parameters. AlgoProfitX converts it to `postgresql+asyncpg://`, removes `sslmode`/`sslrootcert` parameters unsupported by asyncpg, and supplies native `ssl=True` through `DATABASE_REQUIRE_TLS=true`. Credentials remain encoded and unlogged.

The initial network plan uses the public bindable URL over mandatory TLS and adds the App Platform app as a database trusted source. App VPC is not enabled because current dedicated egress and VPC are mutually exclusive; preserving later Angel One allowlisting is deliberate. Reassess before live integrations.

## Environment and secrets matrix

`SECRET_KEY` is intentionally absent from the committed spec. Before deployment, add it as an encrypted app-level `RUN_TIME` variable so API and migration receive it but the frontend build does not.

| Category | Variables | Staging contract |
| --- | --- | --- |
| SECRET | `SECRET_KEY` | At least 32 cryptographically random bytes; encrypted; never reused in production |
| PLATFORM/RESOURCE REFERENCE | `DATABASE_URL` | `${staging-postgres.DATABASE_URL}`, encrypted resource binding |
| PUBLIC CONFIG | `APP_ENV`, `DEBUG`, `DATABASE_REQUIRE_TLS` | `production`, `false`, `true` |
| PUBLIC CONFIG | `FRONTEND_PUBLIC_URL`, `API_PUBLIC_URL`, `CORS_ALLOWED_ORIGINS` | Exact staging HTTPS origins; CORS only `https://staging.algoprofitx.com` |
| PUBLIC CONFIG | `API_DOCS_ENABLED`, `LOG_LEVEL`, `LOG_FORMAT` | `false`, `INFO`, `json` |
| PUBLIC CONFIG | `AUTH_COOKIE_SECURE`, `AUTH_COOKIE_HTTPONLY`, `AUTH_COOKIE_SAMESITE`, `AUTH_COOKIE_PATH` | `true`, `true`, `strict`, `/api/v1/auth` |
| PUBLIC CONFIG | `AUTH_CSRF_COOKIE_DOMAIN`, `AUTH_CSRF_COOKIE_PATH` | `algoprofitx.com`, `/` |
| PUBLIC CONFIG | `ABUSE_PROTECTION_ENABLED`, `MARKET_DATA_PROVIDER` | `true`, `synthetic` |
| OPTIONAL TUNABLE | `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | Staging: `3`, `1` |
| OPTIONAL TUNABLE | `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS`, `DB_POOL_PRE_PING`, `DB_EXTERNAL_TRANSACTION_POOLER` | Defaults: `10`, `1800`, `true`, `false` |
| OPTIONAL TUNABLE | `READINESS_DB_TIMEOUT_SECONDS`, `REQUEST_ID_HEADER` | Defaults: `2`, `X-Request-ID` |
| OPTIONAL TUNABLE | `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `AUTH_MAX_SESSIONS_PER_USER` | Defaults: `30`, `30`, `5` |
| OPTIONAL TUNABLE | `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, `AUTH_JWT_KEY_ID` | Defaults: `algoprofitx-api`, `algoprofitx-web`, `primary` |
| OPTIONAL TUNABLE | `AUTH_REFRESH_COOKIE_NAME`, `AUTH_CSRF_COOKIE_NAME`, `AUTH_COOKIE_DOMAIN` | Defaults; refresh domain remains unset/host-only |
| OPTIONAL TUNABLE | `LOGIN_IP_LIMIT`, `LOGIN_IP_WINDOW_SECONDS`, `LOGIN_ACCOUNT_LIMIT`, `LOGIN_ACCOUNT_WINDOW_SECONDS` | Existing production defaults |
| OPTIONAL TUNABLE | `REGISTRATION_IP_LIMIT`, `REGISTRATION_IP_WINDOW_SECONDS`, `CREATOR_ENROLLMENT_LIMIT`, `CREATOR_ENROLLMENT_WINDOW_SECONDS` | Existing production defaults |
| OPTIONAL TUNABLE | `BACKTEST_BURST_LIMIT`, `BACKTEST_BURST_WINDOW_SECONDS`, `BACKTEST_SUSTAINED_LIMIT`, `BACKTEST_SUSTAINED_WINDOW_SECONDS`, `BACKTEST_MAX_CONCURRENCY_PER_USER` | Existing production defaults |
| OPTIONAL TUNABLE | `EXECUTION_BURST_LIMIT`, `EXECUTION_BURST_WINDOW_SECONDS`, `EXECUTION_SUSTAINED_LIMIT`, `EXECUTION_SUSTAINED_WINDOW_SECONDS` | Existing production defaults |
| OPTIONAL TUNABLE | `MARKET_DATA_TIMEOUT_SECONDS`, `MARKET_DATA_MAX_RETRIES`, `MARKET_DATA_MAX_RANGE_DAYS`, `MARKET_DATA_MAX_CANDLES` | Existing synthetic-provider defaults |
| FRONTEND BUILD CONFIG | `VITE_API_BASE_URL` | `https://api-staging.algoprofitx.com/api/v1`; public; BUILD_TIME only |
| PLATFORM | `PORT` | Supplied from `http_port: 8080`; do not override |

Staging uses production security behavior, synthetic/reference historical data, and paper execution only. There are no Angel One settings or live orders.

## Browser authentication

The HTTPS staging frontend and API are different origins but the same schemeful site because they share registrable domain `algoprofitx.com`. `SameSite=Strict` therefore works between them. Fetch still requires `credentials: include` and exact credentialed CORS.

The refresh cookie stays Secure, HttpOnly, host-only to the API, and `/api/v1/auth`-scoped. Only the random, non-HttpOnly double-submit CSRF token uses `Domain=algoprofitx.com; Path=/`, which lets the frontend read and echo it after reload. This avoids weakening the refresh cookie. Verify cookie attributes and CSRF rejection during acceptance.

## Frontend, routing, headers, and caching

The frontend builds with `pnpm build`, emits `dist`, and uses `catchall_document: index.html` for `/marketplace`, `/instruments`, `/creator/...`, and `/investor/...`. Authority ingress sends all API-host traffic only to the API and all frontend-host traffic only to the site.

The static catch-all is site-wide and cannot exempt missing `/assets/*`; a missing asset may receive SPA HTML instead of a clean 404. This is an acknowledged platform gap.

The current schema has CORS but no arbitrary static response-header map. CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, and `X-Frame-Options` cannot honestly be declared. TLS minimum 1.2 is specified, but the full header contract remains a later edge/CDN gap. A future staging CSP must keep Task E's directives and change only `connect-src` to `https://api-staging.algoprofitx.com`.

Static sites currently default to 24-hour CDN caching and 10-second browser caching, invalidated on deploy. App Spec cannot express separate immutable `/assets/*` and revalidating `index.html`; that exact cache policy remains a later edge/CDN gap.

## Domains, TLS, and egress

Future domains are `staging.algoprofitx.com` and `api-staging.algoprofitx.com`. The spec omits `zone`, so it cannot modify DNS. Later, attach both domains, obtain their CNAME targets (or documented static ingress addresses), and separately authorize only those staging DNS records. Production domains stay untouched.

App Platform provisions and renews HTTPS certificates for attached domains. Confirm CAA compatibility, wait for DNS validation, verify TLS 1.2+ and HTTPS behavior, then test. No certificate is provisioned here.

Dedicated egress is disabled; synthetic data needs no allowlisting. It currently assigns two persistent app-level IPs, costs up to $25/month, affects all app components, and cannot coexist with App VPC. If Angel One later requires it, add `egress.type: DEDICATED_IP` to the complete spec, redeploy, record both IPs, and allowlist them. Omitting it later releases the IPs permanently.

## Future manual deployment runbook

Each action needs separate infrastructure authorization. Stop at every gate.

1. Confirm team/billing access, GitHub read access, least privilege, green `main` CI, and reviewed SHA. **Gate: approve cost.**
2. In `blr1`, create `algoprofitx-staging-pg`: Standard Basic Regular PostgreSQL 17, one 1 GiB/1 vCPU node, 10 GiB.
3. Create `algoprofitx_staging` and non-admin `algoprofitx_staging_app`; reserve `doadmin` for administration.
4. Confirm backups/PITR and TLS; later restrict trusted sources to the App Platform app.
5. Review the spec against current schema/pricing; connect the private GitHub repo; keep deploy-on-push false.
6. Attach the existing managed cluster by exact cluster/database/user names; reject a development database.
7. Add encrypted app-level RUN_TIME `SECRET_KEY`; verify the encrypted database binding.
8. Verify the full environment matrix, staging URLs, exact CORS, production mode, cookies, synthetic provider, and pool `3 + 1`.
9. Verify frontend build/output/API URL and SPA catch-all.
10. Verify one PRE_DEPLOY job with upgrade plus head check; no startup migration.
11. Verify API size, one replica/worker, F1 Dockerfile, `PORT`, termination, and probes.
12. **Gate: approve first manual deployment.** Start with an empty DB; copy no local, production, or user data.
13. Verify Alembic logs migrate base through `c6d1e8f3a9b2`, including advisory lock and head check.
14. Run `python -m app.bootstrap.instruments` once using the supported backend artifact; verify only idempotent reference data.
15. Verify starter-domain behavior and both health endpoints before DNS.
16. Attach the two staging domains without DNS automation; record targets.
17. **Gate: separately authorize DNS.** Add only staging records; wait for DNS/certificates.
18. Verify HTTPS, authority routing, SPA routes, CORS, cookies, CSRF, and no mixed content.
19. Run the checklist below with synthetic/reference data and paper execution only.
20. Record deployment ID, source SHA, encrypted exported spec, migration head, smoke evidence, cost, and gaps.

## Rollback and recovery

Before later migrations, confirm PITR. If PRE_DEPLOY fails, do not promote; inspect logs and keep the last healthy deployment. For an application-only failure, use App Platform rollback while confirming compatibility with the migrated schema.

For destructive/incompatible data change, stop writes, preserve evidence, restore PITR into a new isolated cluster, validate head and critical relationships, and explicitly repoint staging after review. Never overwrite the damaged cluster. Alembic downgrade is not the recovery mechanism. For the first empty deployment, recreate only with approval and rerun migration/bootstrap.

## Smoke checklist

- [ ] Frontend HTTPS loads with no mixed-content/CORS errors or sensitive console output
- [ ] Deep-link/reload works for marketplace, instruments, Creator, and Investor routes
- [ ] API is reachable only on the API staging host
- [ ] `/health/live` returns 200 independently of DB
- [ ] `/health/ready` returns 200 with DB and 503 when DB is deliberately unavailable
- [ ] Registration, login, refresh/reload, CSRF rejection, and logout work with expected cookies
- [ ] Creator enrollment, strategy creation, and version creation work
- [ ] Synthetic Backtest and analytics show correct synthetic/reference disclosure
- [ ] Marketplace, allocation, Execution Intent, and paper execution work
- [ ] No live trading/broker integration is present
- [ ] No secret, token, DB credential, or sensitive payload appears in logs

## Separation and delivery flow

Staging DB != production DB. Staging secrets != production secrets. Staging domains != production domains. Never reuse staging `SECRET_KEY` or credentials. Production is provisioned separately after staging acceptance.

Flow: `feature branch -> PR -> CI -> main -> manually approved staging deployment`. Keep deploy-on-push disabled until deployments and rollback drills are proven. Do not enable automatic production deployment.

## Official references verified 31 August 2026

- [App Spec schema](https://docs.digitalocean.com/products/app-platform/reference/app-spec/)
- [App regions (`blr`)](https://docs.digitalocean.com/reference/pydo/reference/apps/list_regions/)
- [Dockerfile builds](https://docs.digitalocean.com/products/app-platform/reference/dockerfile/)
- [Deployment jobs](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/)
- [Health checks](https://docs.digitalocean.com/products/app-platform/how-to/manage-health-checks/)
- [Static sites and SPA catch-all](https://docs.digitalocean.com/products/app-platform/how-to/manage-static-sites/)
- [Database bindable variables and secrets](https://docs.digitalocean.com/products/app-platform/how-to/use-environment-variables/)
- [Subdomain ingress/domains](https://docs.digitalocean.com/products/app-platform/how-to/manage-domains/)
- [App pricing/egress](https://docs.digitalocean.com/products/app-platform/details/pricing/)
- [Static and dedicated IPs](https://docs.digitalocean.com/products/app-platform/how-to/add-ip-address/)
- [Static cache behavior](https://docs.digitalocean.com/products/app-platform/how-to/cache-content/)
- [Managed PostgreSQL pricing](https://www.digitalocean.com/pricing/managed-databases)
- [PostgreSQL versions/connections/PITR](https://docs.digitalocean.com/products/databases/postgresql/details/limits/)
- [Managed database backup/TLS features](https://docs.digitalocean.com/products/databases/)
- [PostgreSQL TLS connections](https://docs.digitalocean.com/products/databases/postgresql/how-to/connect/)
