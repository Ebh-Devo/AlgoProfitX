import type { ReactNode } from "react";
import { AlertCircle, Inbox, Loader2, RotateCw } from "lucide-react";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <Loader2 className="loading-orbit" size={32} aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <span className="skeleton-line" />
        <span className="skeleton-line short" />
      </div>
    </div>
  );
}

interface EmptyStateProps {
  title?: string;
  children?: ReactNode;
  icon?: ReactNode;
  /** Primary next step (typically a link/button). */
  action?: ReactNode;
  /** "compact" drops the dashed frame — use inside a panel that already has one. */
  variant?: "default" | "compact";
}

export function EmptyState({ title = "Nothing to show yet", children, icon, action, variant = "default" }: EmptyStateProps) {
  return (
    <div className={`empty-state${variant === "compact" ? " is-compact" : ""}`}>
      <span className="empty-state-mark" aria-hidden="true">{icon ?? <Inbox size={22} />}</span>
      <div className="empty-state-body">
        <strong>{title}</strong>
        {children && <p>{children}</p>}
        {action && <div className="empty-state-action">{action}</div>}
      </div>
    </div>
  );
}

/** Recoverable failure panel. Shows a friendly message, never the raw backend error. */
export function ErrorPanel({ title, children, onRetry, retrying }: { title: string; children?: ReactNode; onRetry?: () => void; retrying?: boolean }) {
  return (
    <div className="error-panel" role="alert">
      <AlertCircle size={18} aria-hidden="true" className="error-panel-icon" />
      <div className="error-panel-body">
        <strong>{title}</strong>
        {children && <p>{children}</p>}
      </div>
      {onRetry && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry} disabled={retrying}>
          <RotateCw size={13} aria-hidden="true" /> {retrying ? "Retrying…" : "Try again"}
        </button>
      )}
    </div>
  );
}

export function ErrorAlert({ children }: { children: ReactNode }) {
  return (
    <div className="alert alert-error" role="alert" aria-live="assertive">
      <AlertCircle size={16} aria-hidden="true" className="alert-icon" />
      <div className="alert-body">{children}</div>
    </div>
  );
}
