import { Monitor, Moon, Sun } from "lucide-react";
import type { KeyboardEvent } from "react";

import { THEME_PREFERENCES, type ThemePreference } from "../../lib/theme";
import { useTheme } from "./ThemeProvider";

export const THEME_OPTIONS: Record<ThemePreference, { label: string; Icon: typeof Sun }> = {
  system: { label: "System", Icon: Monitor },
  light: { label: "Light", Icon: Sun },
  dark: { label: "Dark", Icon: Moon },
};

/** Segmented System / Light / Dark control (radiogroup, roving tabindex, arrow keys). Used in the mobile drawer. */
export function ThemeSelector() {
  const { preference, setPreference } = useTheme();
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = THEME_PREFERENCES[(THEME_PREFERENCES.indexOf(preference) + step + THEME_PREFERENCES.length) % THEME_PREFERENCES.length];
    setPreference(next);
    e.currentTarget.querySelector<HTMLElement>(`[data-theme-option="${next}"]`)?.focus();
  };
  return (
    <div className="theme-selector" role="radiogroup" aria-label="Theme" onKeyDown={onKeyDown}>
      {THEME_PREFERENCES.map(value => {
        const { label, Icon } = THEME_OPTIONS[value];
        const checked = preference === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            data-theme-option={value}
            className="theme-option"
            onClick={() => setPreference(value)}
          >
            <Icon size={14} aria-hidden="true" /> {label}
          </button>
        );
      })}
    </div>
  );
}

/** Compact header control: one icon button that cycles System → Light → Dark. */
export function ThemeCycleButton() {
  const { preference, setPreference } = useTheme();
  const next = THEME_PREFERENCES[(THEME_PREFERENCES.indexOf(preference) + 1) % THEME_PREFERENCES.length];
  const { Icon, label } = THEME_OPTIONS[preference];
  return (
    <button
      type="button"
      className="icon-btn theme-cycle"
      aria-label={`Theme: ${label}. Switch to ${THEME_OPTIONS[next].label}`}
      title={`Theme: ${label}`}
      onClick={() => setPreference(next)}
    >
      <Icon size={16} aria-hidden="true" />
    </button>
  );
}
