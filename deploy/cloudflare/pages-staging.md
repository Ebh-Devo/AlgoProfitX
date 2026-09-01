# Cloudflare Pages staging contract

This is an operator-reviewed configuration contract, not live infrastructure. F2.1 creates no Cloudflare project, token, account identifier, domain, or DNS record.

## Pages project settings

| Dashboard field | Required value |
| --- | --- |
| Git provider | GitHub integration |
| Repository | `Roshan-Baghwar/TradeEBH` |
| Production branch | `main` |
| Root directory | `frontend` |
| Build command | `pnpm build` |
| Build output directory | `dist` |
| Production environment variable | `VITE_API_BASE_URL=https://api-staging.algoprofitx.com/api/v1` |
| Custom domain | `staging.algoprofitx.com` |

The root directory changes the build working directory to `frontend`; therefore `dist` is relative to `frontend`, not the repository root. The repository declares `pnpm@11.19.0` in `frontend/package.json`. No Wrangler configuration is needed for the Git integration.

Keep automatic production-branch deployments disabled while the project is first configured. After CI is green and an operator approves the reviewed `main` SHA, enable production-branch deployment (or manually retry that approved commit) for the first rollout. Any later decision to auto-deploy `main` is an F3 operational change, not part of this source contract.

## Static serving contract

Vite copies `frontend/public/_headers` to `dist/_headers`. Pages parses it for static responses; it is not downloadable as an asset. There are no Pages Functions or Workers. Because the output deliberately has no top-level `404.html`, Pages' native SPA behavior serves the root application for unmatched paths, including `/marketplace`, `/instruments`, `/creator/*`, and `/investor/*`. The API has a separate hostname and is never proxied through a frontend `/api` path.

The CSP allows only same-origin resources plus `connect-src https://api-staging.algoprofitx.com`. `style-src 'unsafe-inline'` remains necessary because the current React/Recharts UI emits runtime style attributes; scripts do not allow inline code or eval. HSTS is `max-age=31536000` without `includeSubDomains` or `preload`; either broader flag requires a future domain-wide HTTPS audit and explicit production decision.

`_headers` sets the browser policy for hashed `/assets/*` to one year and immutable, and sets `/index.html` to revalidate. Pages' SPA fallback response is generated from the root asset; verify its effective `Cache-Control` during F3 acceptance. Cloudflare documents that Pages assets use its managed CDN/Tiered Cache and deployment invalidation behavior. `_headers` controls response/browser caching; it does not configure edge cache TTL. If exact custom edge behavior is still required, add narrowly scoped Cache Rules in F3 after live-header verification. Do not cache API responses here.

## Domains and previews

Associate `staging.algoprofitx.com` in the Pages project's Custom domains screen before adding DNS. Because it is a subdomain, Cloudflare documents that the parent zone does not need to use Cloudflare authoritative nameservers: the existing DNS provider can add a CNAME from `staging.algoprofitx.com` to the assigned `<project>.pages.dev` hostname. An apex Pages domain would require the zone and Cloudflare nameservers. No nameserver or DNS change occurs in F2.1; the subdomain path is the F3 decision.

Disable preview branch builds initially. Preview URLs are public, and the DigitalOcean API permits only the exact credentialed origin `https://staging.algoprofitx.com`; arbitrary `*.pages.dev` origins must not be added to CORS. Preview deployments are therefore not an authenticated staging-test surface. Revisit only with an explicit access and exact-origin design.

## Official references verified 1 September 2026

- [Build configuration and root directory](https://developers.cloudflare.com/pages/configuration/build-configuration/)
- [Monorepos](https://developers.cloudflare.com/pages/configuration/monorepos/)
- [GitHub integration](https://developers.cloudflare.com/pages/configuration/git-integration/github-integration/)
- [Branch deployment controls](https://developers.cloudflare.com/pages/configuration/branch-build-controls/)
- [Production environment variables](https://developers.cloudflare.com/pages/configuration/build-configuration/#environment-variables)
- [Custom domains](https://developers.cloudflare.com/pages/configuration/custom-domains/)
- [SPA serving and caching](https://developers.cloudflare.com/pages/configuration/serving-pages/)
- [`_headers`](https://developers.cloudflare.com/pages/configuration/headers/)
- [Preview deployments](https://developers.cloudflare.com/pages/configuration/preview-deployments/)
- [Limits](https://developers.cloudflare.com/pages/platform/limits/)
- [Rollbacks](https://developers.cloudflare.com/pages/configuration/rollbacks/)
