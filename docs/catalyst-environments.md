# Catalyst environments and isolation

Single source of truth: [`frontend/environments.json`](../frontend/environments.json) (public origins only; no secrets).

| | Development | Production |
|---|---|---|
| Web | `https://algoprofitx-web-50045554365.development.catalystappsail.in` | `https://www.algoprofitx.com` |
| Upstream API (proxied) | `https://algoprofitx-api-50045554365.development.catalystappsail.in` | `https://api.algoprofitx.com` |

The Development URLs were read from the Catalyst console (project AlgoProfitX, Development environment). Both AppSails are named `algoprofitx-web` and `algoprofitx-api`.

## Guarantees

- The browser only talks to its own web origin; the web server proxies `/api/v1` to one fixed upstream API origin approved for its baked `APP_ENV` (see `allowedUpstreamApiOrigins`). A built frontend must declare `VITE_APP_ENV`, and `scripts/check-environment.mjs` plus `scripts/verify-bundle-isolation.mjs` fail the build on any mismatch. CSP `connect-src` is `'self'` in every environment.
- The deployed Development API (`API_PUBLIC_URL` = the Development API origin) rejects any `CORS_ALLOWED_ORIGINS` other than exactly the Development web origin, and requires `FRONTEND_PUBLIC_URL` to be that origin. The Development pair is not in the Production approved pairs, so Production rejects it.
- `build-catalyst.yml` builds `algoprofitx-web:<sha>-development` and `-production` as separate artifacts. `deploy-catalyst-development.yml` has a fixed Development target and deploys only `algoprofitx-web-development.tar`.

## Development backend settings

Set on the `algoprofitx-api` Development AppSail (values are never committed): `APP_ENV=development`, `API_PUBLIC_URL`, `FRONTEND_PUBLIC_URL` and `CORS_ALLOWED_ORIGINS` set to the Development origins above, plus the secret key. Persistence is Catalyst Data Store only (see [catalyst-runtime.md](catalyst-runtime.md)); there is no database URL.

Because the web server proxies the API same-origin and strips cookie `Domain`, refresh cookies are host-only for the web origin and the cross-subdomain `SameSite=strict` concern does not apply to browser traffic; confirm once deployed.
