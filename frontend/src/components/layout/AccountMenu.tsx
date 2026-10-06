import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, LogOut, Settings } from "lucide-react";

import { THEME_PREFERENCES } from "../../lib/theme";
import { useTheme } from "../theme/ThemeProvider";
import { THEME_OPTIONS } from "../theme/ThemeSelector";

interface AccountMenuProps {
  email: string;
  roles: string[];
  onLogout: () => void;
}

/** Disclosure menu: button + role="menu". Arrow keys move, Escape closes, outside click closes. */
export function AccountMenu({ email, roles, onLogout }: AccountMenuProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const { preference, setPreference } = useTheme();
  const initial = (email[0] ?? "A").toUpperCase();

  useEffect(() => {
    if (!open) return;
    const items = () => Array.from(wrapRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"], [role="menuitemradio"]') ?? []);
    items()[0]?.focus();
    const onDown = (e: MouseEvent) => { if (!wrapRef.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); buttonRef.current?.focus(); return; }
      if (e.key === "Tab") { setOpen(false); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const list = items();
      const idx = list.indexOf(document.activeElement as HTMLElement);
      const next = e.key === "ArrowDown" ? (idx + 1) % list.length : (idx - 1 + list.length) % list.length;
      list[next]?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  return (
    <div className="menu" ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className="menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="account-menu"
        onClick={() => setOpen(o => !o)}
      >
        <span className="avatar" aria-hidden="true">{initial}</span>
        <span className="menu-trigger-label">Account menu</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div id="account-menu" className="menu-panel" role="menu" aria-label="Account">
          <div className="menu-header">
            <strong title={email}>{email}</strong>
            <span>{roles.length ? roles.join(" · ") : "Member"}</span>
          </div>
          <Link role="menuitem" className="menu-item" to="/account" onClick={() => setOpen(false)}>
            <Settings size={15} aria-hidden="true" /> Account settings
          </Link>
          <div className="menu-group" role="group" aria-labelledby="appearance-label">
            <span id="appearance-label" className="menu-group-label">Appearance</span>
            {THEME_PREFERENCES.map(value => {
              const { label, Icon } = THEME_OPTIONS[value];
              return (
                <button key={value} role="menuitemradio" aria-checked={preference === value} type="button" className="menu-item menu-item-radio" onClick={() => setPreference(value)}>
                  <Icon size={15} aria-hidden="true" /> {label}
                  <span className="menu-check" aria-hidden="true">{preference === value ? "✓" : ""}</span>
                </button>
              );
            })}
          </div>
          <button role="menuitem" type="button" className="menu-item menu-item-logout" onClick={() => { setOpen(false); onLogout(); }}>
            <LogOut size={15} aria-hidden="true" /> Log out
          </button>
        </div>
      )}
    </div>
  );
}
