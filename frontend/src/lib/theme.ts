/**
 * Theme preference model. The user chooses a PREFERENCE ("system" | "light" | "dark");
 * the app applies the RESOLVED theme ("light" | "dark") as `data-theme` on <html>, where
 * tokens.css swaps the palette. Dark is the default. public/theme-init.js mirrors this
 * logic before first paint — keep the two (and THEME_STORAGE_KEY) in sync.
 */
export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "algoprofitx-theme";
export const DEFAULT_THEME_PREFERENCE: ThemePreference = "dark";
export const THEME_PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];
export const DARK_QUERY = "(prefers-color-scheme: dark)";

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export function readStoredPreference(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(raw) ? raw : DEFAULT_THEME_PREFERENCE;
  } catch {
    return DEFAULT_THEME_PREFERENCE;
  }
}

export function storePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* storage unavailable (private mode / blocked): the preference lasts for this page view only */
  }
}

export function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY).matches : true;
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "system") return systemPrefersDark() ? "dark" : "light";
  return preference;
}

export function applyTheme(resolved: ResolvedTheme): void {
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolved === "light" ? "#eef1f5" : "#0a0c10");
}
