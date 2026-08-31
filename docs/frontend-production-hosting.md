# AlgoProfitX frontend production hosting contract

This is a provider-neutral contract for a future hosting/edge implementation. It
is not deployable infrastructure and does not indicate that production is live.

## Origins and redirects

- Serve the SPA only at `https://www.algoprofitx.com`.
- Redirect HTTP to HTTPS before serving content.
- Permanently redirect `https://algoprofitx.com` to the same path and query on
  `https://www.algoprofitx.com` with 301 or 308 status.
- The browser API origin is `https://api.algoprofitx.com`; production builds
  must set `VITE_API_BASE_URL=https://api.algoprofitx.com/api/v1`.
- Every `VITE_*` value is public browser configuration. It must never contain a
  password, token, API key, signing secret, or private vendor setting.

## SPA fallback

History routes such as `/marketplace`, `/instruments`, `/creator/...`, and
`/investor/...` must fall back to `/index.html` when no frontend route file
exists. Requests under `/assets/` and other static filenames must return 404 on
a miss. Requests for `api.algoprofitx.com` must never enter the SPA rewrite.

## Security headers

Apply the exact baseline exported by
`frontend/src/lib/productionSecurityPolicy.ts` to HTML and static responses.
The CSP deliberately forbids inline/eval scripts and permits connections only
to self and the AlgoProfitX API. `style-src 'unsafe-inline'` is the sole inline
exception because Recharts/React currently emit bounded runtime style
attributes for chart layout and tooltips; scripts remain strict. All fonts are
local/system fonts and no third-party scripts or font services are required.

HSTS uses `max-age=31536000` without `includeSubDomains` or `preload`. Those
flags are deferred until every current and future subdomain is verified as
HTTPS-only; preload must be a separate deliberate operational decision. CSP
`frame-ancestors 'none'` is authoritative, with `X-Frame-Options: DENY` retained
only for older clients.

## Caching and artifacts

- Hashed `/assets/*` files: `Cache-Control: public, max-age=31536000, immutable`.
- `index.html` and SPA fallback responses:
  `Cache-Control: no-cache, max-age=0, must-revalidate`.
- Static asset misses remain 404 and are not rewritten.
- Do not cache authenticated API responses in frontend hosting/CDN rules. API
  caching requires a separate backend/edge policy.
- Vite public source maps are explicitly disabled. A future private monitoring
  upload workflow may revisit this without publishing `.map` files.

## Browser authentication contract

The frontend sends API requests with `credentials: include`. The API refresh
cookie is Secure, HttpOnly, SameSite=Strict, host-only to
`api.algoprofitx.com`, and scoped to `/api/v1/auth`; frontend JavaScript neither
needs nor can read it. JavaScript reads only the non-HttpOnly CSRF cookie and
echoes it in `X-CSRF-Token` for refresh/logout. Access tokens remain in memory.
The API must allow the exact credentialed origin `https://www.algoprofitx.com`;
localhost remains a separate development configuration.
