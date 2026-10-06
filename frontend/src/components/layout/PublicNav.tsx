import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { ChevronDown } from "lucide-react";

export interface NavLeaf {
  label: string;
  description: string;
  /** Route or landing-page anchor. Omitted for content that does not exist yet. */
  to?: string;
}

export interface NavEntry {
  label: string;
  to?: string;
  children?: NavLeaf[];
}

/**
 * Public navigation. Every destination is a real route or a section on the landing page;
 * anything without a destination is flagged as coming soon instead of linking nowhere.
 */
export const PUBLIC_NAV: NavEntry[] = [
  {
    label: "Platform",
    children: [
      { label: "Strategies", description: "Immutable, versioned strategy definitions", to: "/#cap-versioned" },
      { label: "Backtesting", description: "Deterministic historical simulations", to: "/#stage-backtest" },
      { label: "Paper Trading", description: "Simulated execution. No broker orders", to: "/#stage-execute" },
      { label: "Analytics", description: "Return, drawdown, win rate and trades per run", to: "/#cap-analytics" },
    ],
  },
  { label: "Marketplace", to: "/marketplace" },
  { label: "How It Works", to: "/#how-it-works" },
  {
    label: "Resources",
    children: [
      { label: "Documentation", description: "Product documentation", },
      { label: "FAQ", description: "Common questions, answered plainly", to: "/#faq" },
      { label: "Getting Started", description: "Create an account and your first strategy", to: "/#get-started" },
    ],
  },
  { label: "Instruments", to: "/instruments" },
  { label: "About", to: "/#about" },
];

const CLOSE_DELAY = 140;

function Dropdown({ entry, open, onOpen, onClose }: { entry: NavEntry; open: boolean; onOpen: () => void; onClose: () => void }) {
  const wrap = useRef<HTMLLIElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const timer = useRef<number>(0);
  const byHover = useRef(false);
  const panelId = useId();

  const focusItem = useCallback((delta: 1 | -1 | "first" | "last") => {
    const items = Array.from(wrap.current?.querySelectorAll<HTMLElement>("[data-nav-item]") ?? []);
    if (!items.length) return;
    const at = items.indexOf(document.activeElement as HTMLElement);
    const next = delta === "first" ? 0 : delta === "last" ? items.length - 1 : (at + delta + items.length) % items.length;
    items[next].focus();
  }, []);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const cancel = () => window.clearTimeout(timer.current);
  const later = () => { cancel(); timer.current = window.setTimeout(onClose, CLOSE_DELAY); };

  return (
    <li
      ref={wrap}
      className={`pnav-item${open ? " is-open" : ""}`}
      onMouseEnter={() => { cancel(); if (!open) byHover.current = true; onOpen(); }}
      onMouseLeave={later}
      onBlur={e => { if (!wrap.current?.contains(e.relatedTarget as Node | null)) onClose(); }}
      onKeyDown={e => {
        if (e.key === "Escape" && open) { e.stopPropagation(); onClose(); button.current?.focus(); }
        else if (e.key === "ArrowDown") { e.preventDefault(); onOpen(); window.setTimeout(() => focusItem(document.activeElement === button.current ? "first" : 1), 0); }
        else if (e.key === "ArrowUp" && open) { e.preventDefault(); focusItem(-1); }
        else if (e.key === "Home" && open && document.activeElement !== button.current) { e.preventDefault(); focusItem("first"); }
        else if (e.key === "End" && open && document.activeElement !== button.current) { e.preventDefault(); focusItem("last"); }
      }}
    >
      <button
        ref={button}
        type="button"
        className="pnav-trigger"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => { if (open && !byHover.current) onClose(); else onOpen(); byHover.current = false; }}
      >
        {entry.label}
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      <div id={panelId} className="pnav-panel" hidden={!open}>
        <ul>
          {entry.children?.map(c => (
            <li key={c.label}>
              {c.to ? (
                <Link data-nav-item className="pnav-link" to={c.to} onClick={onClose}>
                  <strong>{c.label}</strong>
                  <span>{c.description}</span>
                </Link>
              ) : (
                <span data-nav-item tabIndex={0} className="pnav-link is-soon" aria-disabled="true">
                  <strong>{c.label} <em>Coming soon</em></strong>
                  <span>{c.description}</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </li>
  );
}

/** Desktop marketing navigation with disclosure dropdowns (hover or click, full keyboard support). */
export function PublicNav() {
  const [openKey, setOpenKey] = useState<string | null>(null);

  useEffect(() => {
    if (!openKey) return;
    const onDown = (e: MouseEvent) => {
      if (!(e.target as Element).closest(".pnav")) setOpenKey(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [openKey]);

  return (
    <nav className="site-nav-desktop pnav" aria-label="Primary navigation">
      <ul>
        {PUBLIC_NAV.map(entry =>
          entry.children ? (
            <Dropdown
              key={entry.label}
              entry={entry}
              open={openKey === entry.label}
              onOpen={() => setOpenKey(entry.label)}
              onClose={() => setOpenKey(k => (k === entry.label ? null : k))}
            />
          ) : (
            <li key={entry.label} className="pnav-item">
              {entry.to?.startsWith("/#")
                ? <Link className="pnav-trigger" to={entry.to}>{entry.label}</Link>
                : <NavLink className="pnav-trigger" to={entry.to!}>{entry.label}</NavLink>}
            </li>
          ),
        )}
      </ul>
    </nav>
  );
}
