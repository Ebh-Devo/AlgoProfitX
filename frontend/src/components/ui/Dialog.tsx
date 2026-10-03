import { useEffect, useId, useRef, type ReactNode } from "react";

interface DialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Footer actions (buttons). Destructive confirmations should put the safe action first. */
  actions?: ReactNode;
}

/** Modal built on the native <dialog>: focus trap, Escape and backdrop semantics come from the platform. */
export function Dialog({ open, title, onClose, children, actions }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      if (typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", "");
    }
    if (!open && el.open) el.close?.();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={e => { if (e.target === ref.current) onClose(); }}
    >
      <div className="dialog-head"><h2 id={titleId}>{title}</h2></div>
      <div className="dialog-body">{children}</div>
      {actions && <div className="dialog-foot">{actions}</div>}
    </dialog>
  );
}
