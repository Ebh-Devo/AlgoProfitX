import type { ReactNode } from "react";

interface SkeletonProps {
  width?: string;
  height?: string;
  className?: string;
}

/** Decorative placeholder block. Wrap groups in <SkeletonGroup> so assistive tech gets one status message. */
export function Skeleton({ width = "100%", height = "0.875rem", className = "" }: SkeletonProps) {
  return <span className={`skeleton ${className}`} style={{ width, height }} aria-hidden="true" />;
}

export function SkeletonGroup({ label, className = "", children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <div className={`skeleton-group ${className}`} role="status" aria-live="polite" aria-busy="true">
      <span className="visually-hidden">{label}</span>
      {children}
    </div>
  );
}

/** Placeholder rows for list/table sections. */
export function SkeletonRows({ rows = 4, label }: { rows?: number; label: string }) {
  return (
    <SkeletonGroup label={label} className="skeleton-rows">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i}>
          <Skeleton width={`${55 - (i % 3) * 8}%`} />
          <Skeleton width="4.5rem" height="1.25rem" />
        </div>
      ))}
    </SkeletonGroup>
  );
}

/** Placeholder for a StatGrid. */
export function SkeletonStats({ count = 4, label }: { count?: number; label: string }) {
  return (
    <SkeletonGroup label={label} className="stat-grid">
      {Array.from({ length: count }, (_, i) => (
        <div className="stat" key={i}>
          <Skeleton width="5rem" height="0.65rem" />
          <Skeleton width="3rem" height="1.5rem" />
        </div>
      ))}
    </SkeletonGroup>
  );
}
