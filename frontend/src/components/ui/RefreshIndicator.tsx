import { RefreshCw } from "lucide-react";
import { relativeTime } from "./ActivityFeed";

interface RefreshIndicatorProps {
  /** True while a background refetch is running (not the first load). */
  refreshing: boolean;
  /** Epoch ms of the last successful fetch (react-query `dataUpdatedAt`); 0 when none. */
  updatedAt?: number;
  onRefresh?: () => void;
  /** Set when the last refetch failed but older data is still on screen. */
  stale?: boolean;
}

/**
 * Quiet "this data is live-ish" cue. Reports honestly when data was last fetched,
 * and never implies a push/stream — it only refetches when the user asks or a mutation invalidates.
 */
export function RefreshIndicator({ refreshing, updatedAt, onRefresh, stale }: RefreshIndicatorProps) {
  const when = updatedAt ? `Updated ${relativeTime(new Date(updatedAt).toISOString())}` : null;
  return (
    <div className={`refresh-indicator${refreshing ? " is-refreshing" : ""}${stale ? " is-stale" : ""}`}>
      <span aria-live="polite" className="refresh-text">
        {refreshing ? "Refreshing…" : stale ? "Couldn't refresh — showing earlier data" : when}
      </span>
      {onRefresh && (
        <button type="button" className="refresh-btn" onClick={onRefresh} disabled={refreshing} aria-label="Refresh data">
          <RefreshCw size={14} aria-hidden="true" className={refreshing ? "refresh-spin" : undefined} />
        </button>
      )}
    </div>
  );
}
