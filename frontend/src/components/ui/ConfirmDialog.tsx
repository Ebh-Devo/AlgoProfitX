import type { ReactNode } from "react";
import { Button } from "./Button";
import { Dialog } from "./Dialog";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  pendingLabel?: string;
  pending?: boolean;
  /** Destructive confirmations use the danger button. */
  tone?: "danger" | "primary";
  error?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Confirmation built on <Dialog>. The safe action (Cancel) comes first in DOM and focus order. */
export function ConfirmDialog({
  open, title, children, confirmLabel, pendingLabel, pending, tone = "danger", error, onConfirm, onCancel,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      title={title}
      onClose={() => { if (!pending) onCancel(); }}
      actions={
        <>
          <Button variant="ghost" type="button" disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} type="button" disabled={pending} onClick={onConfirm}>
            {pending && pendingLabel ? pendingLabel : confirmLabel}
          </Button>
        </>
      }
    >
      {children}
      {error && <div className="dialog-error" role="alert">{error}</div>}
    </Dialog>
  );
}
