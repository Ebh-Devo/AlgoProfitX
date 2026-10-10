/** Injected at build time (vite.config.ts) with only this environment's approved API base URLs. */
declare const __ALLOWED_API_BASE_URLS__: readonly string[];

export type AppEnvironment = "development" | "production";

export function parseAppEnvironment(rawValue: string | undefined): AppEnvironment {
  if (rawValue === "development" || rawValue === "production") return rawValue;
  throw new Error("VITE_APP_ENV must be exactly 'development' or 'production' in a built bundle.");
}

/**
 * Built bundles talk to their own web origin only (same-origin API proxy), so the allowed API base
 * URL is the environment's web origin plus /api/v1. Local development may use any absolute URL.
 * ``allowed`` is that environment's approved list; a built bundle must supply it.
 */
export function validateApiBaseUrl(
  rawValue: string | undefined,
  production: boolean,
  allowed?: readonly string[],
): string {
  if (!rawValue) throw new Error("VITE_API_BASE_URL is required. Copy .env.example to .env.");
  let parsed: URL;
  try { parsed = new URL(rawValue); }
  catch { throw new Error("VITE_API_BASE_URL must be an absolute URL."); }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("VITE_API_BASE_URL must not contain credentials, query parameters, or fragments.");
  }
  const normalized = rawValue.replace(/\/$/, "");
  if (production) {
    if (!allowed || allowed.length === 0) throw new Error("A built bundle must declare its target environment.");
    if (!allowed.includes(normalized)) {
      throw new Error("Production VITE_API_BASE_URL must be the approved same-origin AlgoProfitX API URL for this environment.");
    }
  }
  return normalized;
}

function resolveApiBaseUrl(): string {
  const production = import.meta.env.PROD;
  if (production) parseAppEnvironment(import.meta.env.VITE_APP_ENV);
  return validateApiBaseUrl(
    import.meta.env.VITE_API_BASE_URL,
    production,
    production ? __ALLOWED_API_BASE_URLS__ : undefined,
  );
}

export const appConfig = {
  apiBaseUrl: resolveApiBaseUrl(),
};
