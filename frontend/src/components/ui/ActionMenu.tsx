import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { MoreHorizontal } from "lucide-react";

export interface ActionMenuItem {
  label: string;
  icon?: ReactNode;
  /** Navigates when set; otherwise `onSelect` runs. */
  to?: string;
  onSelect?: () => void;
  tone?: "danger";
  disabled?: boolean;
}

interface ActionMenuProps {
  /** Accessible name of the menu, e.g. "Actions for India Trend". */
  label: string;
  items: ActionMenuItem[];
  /** Visible trigger text; the trigger is icon-only when omitted. */
  triggerText?: string;
}

/** Disclosure menu: button + role="menu". Arrow keys move, Escape closes and restores focus, outside click closes. */
export function ActionMenu({ label, items, triggerText }: ActionMenuProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const els = () => Array.from(wrapRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])') ?? []);
    els()[0]?.focus();
    const onDown = (e: MouseEvent) => { if (!wrapRef.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); buttonRef.current?.focus(); return; }
      if (e.key === "Tab") { setOpen(false); return; }
      const list = els();
      const idx = list.indexOf(document.activeElement as HTMLElement);
      let next = -1;
      if (e.key === "ArrowDown") next = (idx + 1) % list.length;
      else if (e.key === "ArrowUp") next = (idx - 1 + list.length) % list.length;
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = list.length - 1;
      if (next < 0) return;
      e.preventDefault();
      list[next]?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <div className="menu action-menu" ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className={`btn btn-secondary btn-sm action-menu-trigger${triggerText ? "" : " is-icon"}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={triggerText ? undefined : label}
        onClick={() => setOpen(o => !o)}
      >
        <MoreHorizontal size={16} aria-hidden="true" />
        {triggerText}
      </button>
      {open && (
        <div id={menuId} className="menu-panel action-menu-panel" role="menu" aria-label={label}>
          {items.map(item => {
            const cls = `menu-item${item.tone === "danger" ? " is-danger" : ""}`;
            if (item.to && !item.disabled) {
              return (
                <Link key={item.label} role="menuitem" className={cls} to={item.to} onClick={close}>
                  {item.icon}{item.label}
                </Link>
              );
            }
            return (
              <button
                key={item.label}
                role="menuitem"
                type="button"
                className={cls}
                aria-disabled={item.disabled || undefined}
                onClick={() => { if (item.disabled) return; close(); buttonRef.current?.focus(); item.onSelect?.(); }}
              >
                {item.icon}{item.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
