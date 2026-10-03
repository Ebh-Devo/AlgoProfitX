import type { ReactNode } from "react";

interface StatProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  /** Market tone — only for P&L-style values; always pair with a sign in the value text. */
  tone?: "profit" | "loss";
}

export function Stat({ label, value, hint, tone }: StatProps) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className={`stat-value${tone ? ` is-${tone}` : ""}`}>{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

export function StatGrid({ children, label }: { children: ReactNode; label?: string }) {
  return <div className="stat-grid" role="group" aria-label={label}>{children}</div>;
}
