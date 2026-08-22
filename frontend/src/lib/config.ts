const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL;

if (!rawApiBaseUrl) {
  throw new Error("VITE_API_BASE_URL is required. Copy .env.example to .env.");
}

try {
  new URL(rawApiBaseUrl);
} catch {
  throw new Error("VITE_API_BASE_URL must be an absolute URL.");
}

export const appConfig = {
  apiBaseUrl: rawApiBaseUrl.replace(/\/$/, ""),
};
