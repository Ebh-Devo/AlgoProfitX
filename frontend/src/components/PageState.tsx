import type { ReactNode } from "react";
import { AlertCircle, Inbox, Loader2 } from "lucide-react";

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

export function EmptyState({ title = "Nothing to show yet", children }: { title?: string; children?: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-state-mark" aria-hidden="true"><Inbox size={22} /></span>
      <div>
        <strong>{title}</strong>
        {children && <p>{children}</p>}
      </div>
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
