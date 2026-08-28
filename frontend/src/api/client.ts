import { clearSession, getAccessToken, setAccessToken } from "../auth/session";
import { appConfig } from "../lib/config";

export interface ApiFieldError { path: string; message: string; }
export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly fieldErrors: ApiFieldError[] = []) {
    super(message); this.name = "ApiError";
  }
}

function normalizeDetail(detail: unknown): { message: string; fieldErrors: ApiFieldError[] } {
  if (typeof detail === "string") return { message: detail, fieldErrors: [] };
  if (Array.isArray(detail)) {
    const fieldErrors = detail.map((entry) => {
      const item = entry as { loc?: unknown[]; msg?: unknown };
      return { path: Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "", message: typeof item.msg === "string" ? item.msg : "Invalid value" };
    });
    return { message: "Please correct the highlighted fields.", fieldErrors };
  }
  return { message: "The request could not be completed.", fieldErrors: [] };
}

function cookieValue(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split("; ").find((cookie) => cookie.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

let refreshPromise: Promise<string> | null = null;

export function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const csrf = cookieValue("algoprofitx_csrf");
    const response = await fetch(`${appConfig.apiBaseUrl}/auth/refresh`, {
      method: "POST", credentials: "include", headers: csrf ? { "X-CSRF-Token": csrf } : {},
    });
    const body = await response.json().catch(() => null) as { access_token?: string } | null;
    if (!response.ok || !body?.access_token) {
      clearSession(); throw new ApiError(response.status, "Authentication session expired");
    }
    setAccessToken(body.access_token); return body.access_token;
  })().finally(() => { refreshPromise = null; });
  return refreshPromise;
}

export async function apiRequest<T>(path: string, options: RequestInit = {}, allowRefresh = true): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (path === "/auth/logout") {
    const csrf = cookieValue("algoprofitx_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, { ...options, credentials: "include", headers });
  if (response.status === 401 && allowRefresh && !path.startsWith("/auth/")) {
    await refreshAccessToken(); return apiRequest<T>(path, options, false);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null) as { detail?: unknown } | T | null;
  if (!response.ok) {
    if (response.status === 401) clearSession();
    const normalized = normalizeDetail(body && typeof body === "object" && "detail" in body ? body.detail : undefined);
    throw new ApiError(response.status, normalized.message, normalized.fieldErrors);
  }
  return body as T;
}
