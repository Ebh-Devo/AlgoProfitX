import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

export type InlineStatusState = "idle" | "pending" | "success" | "error";

interface InlineStatusProps {
  state: InlineStatusState;
  pending?: string;
  success?: string;
  error?: string;
}

/** Compact action feedback that always pairs an icon with text, so state never relies on colour alone. */
export function InlineStatus({ state, pending, success, error }: InlineStatusProps) {
  const text = state === "pending" ? pending : state === "success" ? success : state === "error" ? error : undefined;
  return (
    <span className={`inline-status is-${state}`} role={state === "error" ? "alert" : "status"} aria-live="polite">
      {text && (
        <>
          {state === "pending" && <Loader2 size={13} className="btn-spinner" aria-hidden="true" />}
          {state === "success" && <CheckCircle2 size={13} aria-hidden="true" />}
          {state === "error" && <AlertCircle size={13} aria-hidden="true" />}
          {text}
        </>
      )}
    </span>
  );
}
