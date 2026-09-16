const PRODUCTION_API_BASE_URLS = new Set([
  "https://api.algoprofitx.com/api/v1",
  "https://www.algoprofitx.com/api/v1",
  "https://api-staging.algoprofitx.com/api/v1",
]);

export function validateApiBaseUrl(rawValue: string | undefined, production: boolean): string {
  if (!rawValue) throw new Error("VITE_API_BASE_URL is required. Copy .env.example to .env.");
  let parsed: URL;
  try { parsed = new URL(rawValue); }
  catch { throw new Error("VITE_API_BASE_URL must be an absolute URL."); }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("VITE_API_BASE_URL must not contain credentials, query parameters, or fragments.");
  }
  const normalized = rawValue.replace(/\/$/, "");
  if (production && !PRODUCTION_API_BASE_URLS.has(normalized)) {
    throw new Error("Production VITE_API_BASE_URL must be an approved AlgoProfitX HTTPS API URL.");
  }
  return normalized;
}

export const appConfig = {
  apiBaseUrl: validateApiBaseUrl(import.meta.env.VITE_API_BASE_URL, import.meta.env.PROD),
};
