import environments from "../../environments.json";

export function contentSecurityPolicyFor(appEnv: keyof typeof environments): string {
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
    `connect-src 'self' ${environments[appEnv].apiOrigin}`,
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
