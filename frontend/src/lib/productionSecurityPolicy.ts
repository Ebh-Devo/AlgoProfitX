import environments from "../../environments.json";

/**
 * The browser talks to its own origin only (same-origin API proxy), so ``connect-src`` is
 * ``'self'`` for every environment; an unknown environment has no policy at all.
 */
export function contentSecurityPolicyFor(appEnv: keyof typeof environments): string {
  if (!Object.hasOwn(environments, appEnv)) throw new Error(`Unknown environment: ${appEnv}`);
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "manifest-src 'self'",
    "upgrade-insecure-requests",
  ].join("; ");
}

export const productionSecurityHeaders = {
  "Content-Security-Policy": contentSecurityPolicyFor("production"),
  "Strict-Transport-Security": "max-age=31536000",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "X-Frame-Options": "DENY",
} as const;

export const productionCachePolicy = {
  hashedAssets: "public, max-age=31536000, immutable",
  html: "no-cache, max-age=0, must-revalidate",
} as const;
