import type { ReactNode } from "react";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return <div className="loading-state" role="status" aria-live="polite"><span className="loading-orbit" aria-hidden="true" /><div><strong>{label}</strong><span className="skeleton-line" /><span className="skeleton-line short" /></div></div>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state"><span className="empty-state-mark" aria-hidden="true">↗</span><div><strong>Nothing to show yet</strong><p>{children}</p></div></div>;
}

export function ErrorAlert({ children }: { children: ReactNode }) {
  return <div className="alert alert-error" role="alert">{children}</div>;
}
