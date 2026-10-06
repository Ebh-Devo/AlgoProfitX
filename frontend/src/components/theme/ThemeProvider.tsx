import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  DARK_QUERY, DEFAULT_THEME_PREFERENCE, THEME_STORAGE_KEY, applyTheme, isThemePreference, readStoredPreference, resolveTheme, storePreference,
  type ResolvedTheme, type ThemePreference,
} from "../../lib/theme";

interface ThemeContextValue {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (next: ThemePreference) => void;
}

/** Inert default so components stay renderable in isolation (tests, stories); main.tsx always mounts the real provider. */
const ThemeContext = createContext<ThemeContextValue>({ preference: DEFAULT_THEME_PREFERENCE, resolved: "light", setPreference: () => undefined });

/** Holds the preference, applies the resolved theme to <html>, follows the OS in "system" mode and syncs across tabs. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference);
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme(preference));

  useEffect(() => {
    const sync = () => { const next = resolveTheme(preference); setResolved(next); applyTheme(next); };
    sync();
    if (preference !== "system" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(DARK_QUERY);
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, [preference]);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === THEME_STORAGE_KEY && isThemePreference(e.newValue)) setPreferenceState(e.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setPreference = useCallback((next: ThemePreference) => {
    storePreference(next);
    setPreferenceState(next);
  }, []);

  const value = useMemo(() => ({ preference, resolved, setPreference }), [preference, resolved, setPreference]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
