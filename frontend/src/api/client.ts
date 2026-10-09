import { clearSession, getAccessToken, setAccessToken } from "../auth/session";
import { appConfig } from "../lib/config";

export interface ApiFieldError { path: string; message: string; }
/** One entry of a structured Strategy V2 validation result (`DefinitionIssue` in the OpenAPI schema). */
export interface ApiDefinitionIssue {
  path: string; code: string; message: string; severity: "error" | "warning";
  layer: "schema" | "semantic" | "position" | "capability" | "environment";
}
/** Machine-readable part of an object-shaped error `detail`: `{ code, message, issues? }`. */
export interface ApiErrorDetail { code?: string; issues: ApiDefinitionIssue[] }
export class ApiError extends Error {
  constructor(
    public readonly status: number, message: string, public readonly fieldErrors: ApiFieldError[] = [],
    public readonly requestId?: string, public readonly detail: ApiErrorDetail = { issues: [] },
  ) {
    super(message); this.name = "ApiError";
  }
  get code(): string | undefined { return this.detail.code; }
  get issues(): ApiDefinitionIssue[] { return this.detail.issues; }
}

const LAYERS = ["schema", "semantic", "position", "capability", "environment"];
const isIssue = (value: unknown): value is ApiDefinitionIssue => {
  const item = value as Partial<ApiDefinitionIssue> | null;
  return !!item && typeof item === "object" && typeof item.message === "string" && typeof item.code === "string"
    && typeof item.path === "string" && (item.severity === "error" || item.severity === "warning") && LAYERS.includes(item.layer as string);
};

function normalizeDetail(detail: unknown): { message: string; fieldErrors: ApiFieldError[]; detail: ApiErrorDetail } {
  const none: ApiErrorDetail = { issues: [] };
  if (typeof detail === "string") return { message: detail, fieldErrors: [], detail: none };
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    // Structured detail, e.g. `{ code, message, issues }`. Keep every part the backend sent.
    const body = detail as { code?: unknown; message?: unknown; issues?: unknown };
    const issues = Array.isArray(body.issues) ? body.issues.filter(isIssue) : [];
    const code = typeof body.code === "string" ? body.code : undefined;
    const message = typeof body.message === "string" && body.message ? body.message : "The request could not be completed.";
    return { message, fieldErrors: [], detail: { code, issues } };
  }
  if (Array.isArray(detail)) {
    const fieldErrors = detail.map((entry) => {
      const item = entry as { loc?: unknown[]; msg?: unknown };
      return { path: Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "", message: typeof item.msg === "string" ? item.msg : "Invalid value" };
    });
    return { message: "Please correct the highlighted fields.", fieldErrors, detail: none };
  }
  return { message: "The request could not be completed.", fieldErrors: [], detail: none };
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
  const body = await response.json().catch(() => null) as { detail?: unknown; request_id?: unknown } | T | null;
  if (!response.ok) {
    if (response.status === 401) clearSession();
    const requestId = body && typeof body === "object" && "request_id" in body && typeof body.request_id === "string"
      ? body.request_id : response.headers.get("X-Request-ID") ?? undefined;
    if (response.status >= 500) {
      const message = requestId ? `An unexpected server error occurred. Reference: ${requestId}` : "An unexpected server error occurred.";
      throw new ApiError(response.status, message, [], requestId);
    }
    const normalized = normalizeDetail(body && typeof body === "object" && "detail" in body ? body.detail : undefined);
    throw new ApiError(response.status, normalized.message, normalized.fieldErrors, undefined, normalized.detail);
  }
  return body as T;
}
