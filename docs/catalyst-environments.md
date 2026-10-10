# Catalyst environments and isolation

Single source of truth: [`frontend/environments.json`](../frontend/environments.json) (public origins only; no secrets).

| | Development | Production |
|---|---|---|
| Web | `https://algoprofitx-web-50045554365.development.catalystappsail.in` | `https://www.algoprofitx.com` |
| API | `https://algoprofitx-api-50045554365.development.catalystappsail.in` | `https://api.algoprofitx.com` |

The Development URLs were read from the Catalyst console (project AlgoProfitX, Development environment). Both AppSails are named `algoprofitx-web` and `algoprofitx-api`.

## Guarantees

- A built frontend must declare `VITE_APP_ENV` (`development` or `production`). The bundle only accepts API URLs on that environment's allow-list, and the Docker build runs `scripts/check-environment.mjs` so a mismatch fails the build.
- The web server derives its CSP `connect-src` from `APP_ENV` (baked into the image) and refuses to start without a known value. There is no override and no wildcard.
- The deployed Development API (`API_PUBLIC_URL` = the Development API origin) rejects any `CORS_ALLOWED_ORIGINS` other than exactly the Development web origin. The Development pair is not in the Production approved pairs, so Production rejects it.
- `build-catalyst.yml` builds `algoprofitx-web:<sha>-development` and `-production` as separate artifacts. `deploy-catalyst-development.yml` has a fixed Development target and deploys only `algoprofitx-web-development.tar`.

## Development backend settings

Set on the `algoprofitx-api` Development AppSail (values are never committed): `APP_ENV=development`, `API_PUBLIC_URL`, `FRONTEND_PUBLIC_URL` and `CORS_ALLOWED_ORIGINS` set to the Development origins above, plus the database and secret key.

The two AppSails are on different `catalystappsail.in` subdomains. Cookie `SameSite`/domain behaviour across them should be checked once deployed.
