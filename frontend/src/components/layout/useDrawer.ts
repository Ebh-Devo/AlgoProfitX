import { useEffect, useRef, useState } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Mobile drawer behaviour: close on route change, lock scroll, trap focus, Escape, restore focus. */
export function useDrawer(routeKey: string) {
  const [open, setOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => { setOpen(false); }, [routeKey]);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  useEffect(() => {
    if (open) {
      const first = drawerRef.current?.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? drawerRef.current)?.focus({ preventScroll: true });
      const onKey = (e: KeyboardEvent) => {
        if (e.key === "Escape") { setOpen(false); return; }
        if (e.key !== "Tab" || !drawerRef.current) return;
        const all = Array.from(drawerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (!all.length) return;
        const firstEl = all[0];
        const lastEl = all[all.length - 1];
        if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
        else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
      };
      window.addEventListener("keydown", onKey);
      wasOpen.current = true;
      return () => window.removeEventListener("keydown", onKey);
    }
    if (wasOpen.current) { toggleRef.current?.focus(); wasOpen.current = false; }
  }, [open]);

  return { open, setOpen, toggleRef, drawerRef };
}
