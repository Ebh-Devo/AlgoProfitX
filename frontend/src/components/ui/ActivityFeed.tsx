import type { ReactNode } from "react";

export interface ActivityEntry {
  id: string;
  icon: ReactNode;
  tone?: "default" | "success" | "danger" | "info";
  /** Main sentence, e.g. "Published India Trend". May contain a link. */
  title: ReactNode;
  /** ISO timestamp — rendered in a <time> element. */
  at: string;
  meta?: ReactNode;
}

const formatter = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function relativeTime(iso: string, now = Date.now()): string {
  const diff = Math.max(0, now - new Date(iso).getTime());
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

/** Chronological feed. Pass entries already sorted newest-first. */
export function ActivityFeed({ entries, label }: { entries: ActivityEntry[]; label: string }) {
  return (
    <ol className="activity-feed" aria-label={label}>
      {entries.map(e => (
        <li key={e.id} className={`activity-item tone-${e.tone ?? "default"}`}>
          <span className="activity-icon" aria-hidden="true">{e.icon}</span>
          <div className="activity-body">
            <p className="activity-title">{e.title}</p>
            <p className="activity-meta">
              <time dateTime={e.at} title={formatter.format(new Date(e.at))}>{relativeTime(e.at)}</time>
              {e.meta && <> · {e.meta}</>}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
