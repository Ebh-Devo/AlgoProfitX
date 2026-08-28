const CURRENT_SESSION_STORAGE_KEY = "algoprofitx.auth.session";
const LEGACY_SESSION_STORAGE_KEY = "tradeebh.auth.session";

let accessToken: string | null = null;
type SessionListener = () => void;
const listeners = new Set<SessionListener>();

function cleanLegacyStorage(): void {
  window.sessionStorage.removeItem(CURRENT_SESSION_STORAGE_KEY);
  window.sessionStorage.removeItem(LEGACY_SESSION_STORAGE_KEY);
}

cleanLegacyStorage();

function notify(): void { listeners.forEach((listener) => listener()); }

export function getAccessToken(): string | null { return accessToken; }

export function setAccessToken(token: string): void {
  cleanLegacyStorage(); accessToken = token; notify();
}

export function clearSession(): void {
  cleanLegacyStorage(); accessToken = null; notify();
}

export function subscribeToSession(listener: SessionListener): () => void {
  listeners.add(listener); return () => listeners.delete(listener);
}
