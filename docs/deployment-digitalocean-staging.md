# AlgoProfitX hybrid staging deployment specification

This runbook is a reviewable plan only. No Cloudflare or DigitalOcean resource, deployment, DNS record, certificate, nameserver, or paid feature has been created. Production remains separate and untouched.

## Provider topology

```text
Browser
  |
  +--> Cloudflare Pages
  |      staging.algoprofitx.com
  |      React/Vite static SPA
  |
  +--> DigitalOcean App Platform (blr)
         api-staging.algoprofitx.com
         FastAPI, 1 instance, 1 Uvicorn worker
                    |
                    v
         DigitalOcean Managed PostgreSQL (Bangalore)
```

DigitalOcean also runs the one-shot `PRE_DEPLOY` Alembic migration job. Cloudflare does not proxy or protect the API. Production's future domains remain `www.algoprofitx.com` and `api.algoprofitx.com`; neither is deployed here.

## Sizing and verified cost estimate

| Provider/component | Configuration | Estimated monthly cost |
| --- | --- | ---: |
| DigitalOcean API | One `apps-s-1vcpu-1gb-fixed` instance; 1 shared vCPU/1 GiB | $10.00 |
| DigitalOcean migration | One `apps-s-1vcpu-0.5gb` PRE_DEPLOY job | Prorated while running; normally cents/deployment |
| DigitalOcean PostgreSQL | Basic Regular; one 1 GiB/1 vCPU node; 10 GiB; PostgreSQL 17 | $15.15 |
| Cloudflare Pages | Static assets, assumed within Free plan limits | $0.00 under stated assumptions |
| Optional future DigitalOcean dedicated egress | Disabled | Up to $25.00 |

The steady-state baseline is **$25.15/month**, plus taxes, migration runtime, and transfer/storage overages. Cloudflare's current Free-plan Pages limits include 500 builds/month, one concurrent build, 20,000 files/site, 25 MiB maximum per asset, and 100 custom domains/project. This is a planning assumption, not a promise of “free forever”; verify plan and account billing before F3. With future dedicated egress, the planning baseline becomes $50.15/month before variable charges.

The database permits 22 backend connections. `DB_POOL_SIZE=3` and `DB_MAX_OVERFLOW=1` cap the single API worker at four; the migrator uses one, leaving at least 17 for platform and administration. Do not change replicas, workers, or pool values independently.

## DigitalOcean contract

[`deploy/digitalocean/staging.yaml`](../deploy/digitalocean/staging.yaml) contains exactly one Dockerfile API service, one `PRE_DEPLOY` migration job, and the managed cluster attachment in `blr`. It has no `static_sites` component and owns only `api-staging.algoprofitx.com`. Source is `Roshan-Baghwar/TradeEBH` branch `main`; `deploy_on_push: false` keeps rollout operator-approved.

The API uses `backend/Dockerfile`, port 8080, one worker, DB-dependent `/health/ready`, DB-independent `/health/live`, and termination draining. The migrator runs:

```text
python -m alembic upgrade head && python -m alembic current --check-heads
```

Failure blocks rollout. Web startup never migrates. `${staging-postgres.DATABASE_URL}` is an encrypted resource binding and `DATABASE_REQUIRE_TLS=true` enforces the database TLS contract. `SECRET_KEY` is intentionally absent and must later be added as an encrypted app-level runtime variable. Synthetic market data and paper execution remain mandatory; no broker, live trading, Droplet, Kubernetes, nginx, Redis, Celery, Terraform, VPC, or dedicated egress is introduced.

The API is not behind Cloudflare Pages. Existing FastAPI CORS response handling is appropriate for browser-facing API traffic, but the application does not add general CSP/HSTS headers to API responses. CSP is not meaningful for JSON API responses; HSTS remains an API-host acceptance item. This gap is reported rather than expanding F2.1 into a backend middleware project.

## Cloudflare Pages contract

[`deploy/cloudflare/pages-staging.md`](../deploy/cloudflare/pages-staging.md) records the operator-entered configuration: GitHub repository `Roshan-Baghwar/TradeEBH`, production branch `main`, root directory `frontend`, `pnpm build`, output `dist`, and production environment variable `VITE_API_BASE_URL=https://api-staging.algoprofitx.com/api/v1`. It contains no live identifiers or credentials.

Vite copies [`frontend/public/_headers`](../frontend/public/_headers) to `dist/_headers`. It applies CSP, HSTS, MIME sniffing protection, referrer and permissions policy, and both modern and legacy frame protection. The final staging CSP is:

```text
default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self' https://api-staging.algoprofitx.com; manifest-src 'self'; upgrade-insecure-requests
```

Only inline styles are allowed because React/Recharts currently generates bounded runtime style attributes. Inline scripts and eval remain forbidden. HSTS is `max-age=31536000`, deliberately without `includeSubDomains` or `preload`.

No top-level `404.html` is emitted, so Pages' documented native SPA handling sends unmatched frontend paths to the root app. No `_redirects`, Function, Worker, or `/api` proxy is needed. Acceptance must cover `/marketplace`, `/instruments`, `/creator/*`, and `/investor/*` reloads.

`_headers` gives hashed `/assets/*` browser responses `public, max-age=31536000, immutable` and `/index.html` `no-cache, max-age=0, must-revalidate`. Cloudflare manages Pages edge caching, Tiered Cache, ETags, and deployment invalidation independently. `_headers` is a response/browser policy, not an edge TTL configuration; verify SPA-fallback response headers live, and add narrowly scoped account Cache Rules in F3 only if exact edge behavior is required.

Preview branch builds start at **None**. Their public `*.pages.dev` origins are not added to API CORS and are not an authenticated staging surface. Automatic production-branch deployments also remain disabled during initial setup; an operator deploys only the reviewed green `main` SHA. Any later automatic `main` rollout is a separate operational decision.

## Browser authentication compatibility

The two HTTPS origins are different origins but the same schemeful site under `algoprofitx.com`. The frontend sends `credentials: include`; FastAPI enables credentialed CORS only for exact `https://staging.algoprofitx.com`. Wildcards and preview origins remain rejected.

The refresh cookie is Secure, HttpOnly, SameSite=Strict, host-only to `api-staging.algoprofitx.com`, and scoped to `/api/v1/auth`. Only the readable double-submit CSRF cookie uses `Domain=algoprofitx.com; Path=/`, enabling the frontend to echo `X-CSRF-Token` after reload. Existing tests cover refresh, CSRF rejection, rotation/reuse, and logout; F3 must verify browser cookie attributes, reload refresh, and logout end to end.

## Domain and DNS decision

First associate `staging.algoprofitx.com` in the Pages dashboard. Current Cloudflare documentation states that a custom **subdomain** need not be a Cloudflare zone: the existing authoritative DNS provider can CNAME it to the assigned `<project>.pages.dev`. Moving authoritative nameservers is required for an apex Pages domain, which is not requested. F3 should therefore prefer the subdomain CNAME path and must not move the whole `algoprofitx.com` zone without a separate decision.

`api-staging.algoprofitx.com` attaches only to DigitalOcean App Platform. No DNS or TLS mutation is part of F2.1. During F3, check CAA compatibility, associate both custom domains with their providers before adding records, then verify issuance and TLS.

## Future gated deployment sequence

Each infrastructure action requires separate authorization.

1. Confirm provider access, green `main`, reviewed SHA, and approve the cost.
2. Create the Bangalore PostgreSQL 17 cluster, application DB/user, trusted source, backups, and TLS settings.
3. Create the DigitalOcean API App from the reviewed spec and attach the managed DB.
4. Add the encrypted backend `SECRET_KEY`; verify all runtime configuration and exact CORS.
5. Approve deployment; require the migration job to succeed and reach Alembic head.
6. Verify the App Platform URL plus `/health/live` and `/health/ready` before custom DNS.
7. Create the Cloudflare Pages GitHub project with production and preview automatic deployments disabled.
8. Configure root/build/output and production `VITE_API_BASE_URL`; deploy only the approved SHA.
9. Verify `dist/_headers`, SPA deep links, asset misses, and the `pages.dev` deployment.
10. Associate `staging.algoprofitx.com` with Pages and `api-staging.algoprofitx.com` with App Platform.
11. Separately approve and add only the two staging DNS records; do not change nameservers.
12. Verify certificates, HTTPS, effective headers/cache behavior, exact CORS, cookies, CSRF, reload refresh, and logout.
13. Run the full product smoke suite with synthetic data and paper execution only.
14. Record deployment IDs, source SHA, encrypted exported spec, migration head, smoke evidence, cost, and gaps.

## Rollback and recovery

For a frontend-only failure, select a previous successful **production** Pages deployment after confirming it remains API/schema compatible; previews are not rollback targets. Frontend rollback neither rolls back nor restores the database.

If the migration job fails, do not promote the API. For an application-only backend failure, use App Platform rollback only after schema compatibility review. For destructive/incompatible data change, stop writes, preserve evidence, restore PITR into a new isolated cluster, validate it, and repoint only after approval. Never overwrite the damaged cluster, and do not treat Alembic downgrade as data recovery.

## Acceptance smoke checklist

- [ ] Frontend HTTPS loads without mixed content, CORS errors, or sensitive console output
- [ ] Effective CSP/HSTS/cache headers match the contract
- [ ] Deep-link/reload works for marketplace, instruments, Creator, and Investor routes
- [ ] API is reachable only on `api-staging.algoprofitx.com`; `/health/live` and `/health/ready` behave correctly
- [ ] Registration, login, refresh after reload, CSRF rejection, and logout work with expected cookies
- [ ] Creator strategy/version, synthetic Backtest, analytics, marketplace, allocation, and paper execution work
- [ ] No preview origin authenticates to the staging API
- [ ] No live trading, broker integration, or secret leakage is present

## Official references verified 1 September 2026

- [Cloudflare Pages contract and references](../deploy/cloudflare/pages-staging.md)
- [DigitalOcean App Spec](https://docs.digitalocean.com/products/app-platform/reference/app-spec/)
- [DigitalOcean App Platform pricing](https://www.digitalocean.com/pricing/app-platform)
- [DigitalOcean Managed Database pricing](https://www.digitalocean.com/pricing/managed-databases)
- [DigitalOcean deployment jobs](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/)
- [DigitalOcean health checks](https://docs.digitalocean.com/products/app-platform/how-to/manage-health-checks/)
- [DigitalOcean environment variables](https://docs.digitalocean.com/products/app-platform/how-to/use-environment-variables/)
- [DigitalOcean domains](https://docs.digitalocean.com/products/app-platform/how-to/manage-domains/)
