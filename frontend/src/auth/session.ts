const SESSION_STORAGE_KEY = "algoprofitx.auth.session";
const LEGACY_SESSION_STORAGE_KEY = "tradeebh.auth.session";

export interface StoredSession {
  accessToken: string;
}

type SessionListener = () => void;
const listeners = new Set<SessionListener>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function getSession(): StoredSession | null {
  const stored = window.sessionStorage.getItem(SESSION_STORAGE_KEY)
    ?? window.sessionStorage.getItem(LEGACY_SESSION_STORAGE_KEY);
  if (!stored) return null;

  try {
    const parsed = JSON.parse(stored) as StoredSession;
    return typeof parsed.accessToken === "string" && parsed.accessToken
      ? parsed
      : null;
  } catch {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    window.sessionStorage.removeItem(LEGACY_SESSION_STORAGE_KEY);
    return null;
  }
}

export function saveSession(session: StoredSession): void {
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  window.sessionStorage.removeItem(LEGACY_SESSION_STORAGE_KEY);
  notify();
}

export function clearSession(): void {
  window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  window.sessionStorage.removeItem(LEGACY_SESSION_STORAGE_KEY);
  notify();
}

export function subscribeToSession(listener: SessionListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
