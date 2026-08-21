import type { ReactNode } from "react";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return <p className="page-state" role="status">{label}</p>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}

export function ErrorAlert({ children }: { children: ReactNode }) {
  return <div className="alert alert-error" role="alert">{children}</div>;
}
