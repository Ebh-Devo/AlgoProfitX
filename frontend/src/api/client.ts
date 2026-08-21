import { clearSession, getSession } from "../auth/session";
import { appConfig } from "../lib/config";

export interface ApiFieldError {
  path: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly fieldErrors: ApiFieldError[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function normalizeDetail(detail: unknown): { message: string; fieldErrors: ApiFieldError[] } {
  if (typeof detail === "string") return { message: detail, fieldErrors: [] };
  if (Array.isArray(detail)) {
    const fieldErrors = detail.map((entry) => {
      const item = entry as { loc?: unknown[]; msg?: unknown };
      return {
        path: Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "",
        message: typeof item.msg === "string" ? item.msg : "Invalid value",
      };
    });
    return { message: "Please correct the highlighted fields.", fieldErrors };
  }
  return { message: "The request could not be completed.", fieldErrors: [] };
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const session = getSession();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.accessToken) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  }

  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    ...options,
    headers,
  });
  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null) as { detail?: unknown } | T | null;
  if (!response.ok) {
    if (response.status === 401) clearSession();
    const normalized = normalizeDetail(
      body && typeof body === "object" && "detail" in body ? body.detail : undefined,
    );
    throw new ApiError(response.status, normalized.message, normalized.fieldErrors);
  }
  return body as T;
}
