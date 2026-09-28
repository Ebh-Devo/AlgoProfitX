import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Zap,
  Store,
  BarChart3,
  PlusCircle,
  ArrowRight,
  TrendingUp,
  Clock,
  AlertCircle,
  ShieldCheck,
  FlaskConical,
  Lock,
} from "lucide-react";

import { useAuth } from "../../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../../auth/roles";
import { strategiesApi } from "../../api/strategies";
import { investorApi } from "../../api/investor";
import { queryKeys } from "../../api/queryKeys";
import { EmptyState, ErrorAlert, LoadingState } from "../../components/PageState";
import type { Strategy, Allocation, ExecutionIntent } from "../../api/types";

/* ── Utility: format short relative date ─────────────────────── */
function relativeDate(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

/* ── Strategy status badge ───────────────────────────────────── */
function StrategyStatusBadge({ status }: { status: Strategy["status"] }) {
  const map: Record<Strategy["status"], string> = {
    draft: "badge badge-muted",
    published: "badge badge-info",
    deployed: "badge badge-success",
    archived: "badge",
  };
  return <span className={map[status]}>{status}</span>;
}

/* ── Creator section ─────────────────────────────────────────── */
function CreatorSection() {
  const {
    data: strategies,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: queryKeys.strategies,
    queryFn: strategiesApi.list,
  });

  if (isLoading) {
    return (
      <div className="dash-section-loading" role="status" aria-live="polite">
        <div className="dash-spinner" aria-hidden="true" />
        <span>Loading strategies…</span>
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorAlert>
        {error instanceof Error ? error.message : "Could not load strategies."}
      </ErrorAlert>
    );
  }

  const recent = (strategies ?? []).slice(0, 4);

  return (
    <section className="dash-card" aria-labelledby="creator-section-heading">
      <div className="dash-card-header">
        <div className="dash-card-title-group">
          <span className="dash-card-icon" aria-hidden="true"><BookOpen size={18} /></span>
          <div>
            <h2 id="creator-section-heading" className="dash-card-title">My Strategies</h2>
            <p className="dash-card-subtitle">Your strategy portfolio</p>
          </div>
        </div>
        <Link className="dash-card-action" to="/creator/strategies" aria-label="View all strategies">
          View all <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </div>

      {recent.length === 0 ? (
        <EmptyState title="No strategies yet">
          <span>Create your first strategy to begin systematic research.</span>
          <Link className="btn btn-primary btn-sm" to="/creator/strategies/new" style={{ marginTop: "0.75rem", display: "inline-flex" }}>
            <PlusCircle size={14} aria-hidden="true" />
            New strategy
          </Link>
        </EmptyState>
      ) : (
        <ul className="dash-strategy-list" role="list">
          {recent.map(s => (
            <li key={s.id} className="dash-strategy-item">
              <div className="dash-strategy-item-left">
                <Link
                  className="dash-strategy-name"
                  to={`/creator/strategies/${s.id}`}
                  aria-label={`Strategy: ${s.name}`}
                >
                  {s.name}
                </Link>
                <span className="dash-strategy-meta">
                  <Clock size={11} aria-hidden="true" />
                  {relativeDate(s.updated_at)}
                </span>
              </div>
              <StrategyStatusBadge status={s.status} />
            </li>
          ))}
        </ul>
      )}

      <div className="dash-card-footer">
        <Link className="btn btn-secondary btn-sm" to="/creator/strategies/new">
          <PlusCircle size={14} aria-hidden="true" />
          New strategy
        </Link>
      </div>
    </section>
  );
}

/* ── Investor section ────────────────────────────────────────── */
function InvestorSection() {
  const allocQuery = useQuery<Allocation[]>({
    queryKey: queryKeys.allocations,
    queryFn: investorApi.listAllocations,
  });

  const execQuery = useQuery<ExecutionIntent[]>({
    queryKey: queryKeys.executionIntents,
    queryFn: investorApi.listExecutionIntents,
  });

  const isLoading = allocQuery.isLoading || execQuery.isLoading;
  const isError = allocQuery.isError || execQuery.isError;
  const errorMsg =
    (allocQuery.error instanceof Error ? allocQuery.error.message : null) ??
    (execQuery.error instanceof Error ? execQuery.error.message : null) ??
    "Could not load investor data.";

  if (isLoading) {
    return (
      <div className="dash-section-loading" role="status" aria-live="polite">
        <div className="dash-spinner" aria-hidden="true" />
        <span>Loading portfolio…</span>
      </div>
    );
  }

  if (isError) {
    return <ErrorAlert>{errorMsg}</ErrorAlert>;
  }

  const allocations = allocQuery.data ?? [];
  const executions = execQuery.data ?? [];
  const activeAllocations = allocations.filter(a => a.status === "active");
  const recentExecutions = executions.slice(0, 3);

  return (
    <section className="dash-card" aria-labelledby="investor-section-heading">
      <div className="dash-card-header">
        <div className="dash-card-title-group">
          <span className="dash-card-icon" aria-hidden="true"><Zap size={18} /></span>
          <div>
            <h2 id="investor-section-heading" className="dash-card-title">Investor Portfolio</h2>
            <p className="dash-card-subtitle">Allocations and paper execution</p>
          </div>
        </div>
        <Link className="dash-card-action" to="/investor/allocations" aria-label="View all allocations">
          View all <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </div>

      {/* Stat row */}
      <div className="dash-investor-stats" role="group" aria-label="Portfolio summary">
        <div className="dash-investor-stat">
          <span className="dash-investor-stat-label">Active allocations</span>
          <strong className="dash-investor-stat-value">{activeAllocations.length}</strong>
        </div>
        <div className="dash-investor-stat">
          <span className="dash-investor-stat-label">Execution intents</span>
          <strong className="dash-investor-stat-value">{executions.length}</strong>
        </div>
        <div className="dash-investor-stat">
          <span className="dash-investor-stat-label">Execution mode</span>
          <strong className="dash-investor-stat-value dash-investor-stat--paper">Paper only</strong>
        </div>
      </div>

      {/* Recent executions */}
      {recentExecutions.length === 0 ? (
        <EmptyState title="No execution intents">
          <span>Allocate a strategy version to begin paper execution.</span>
        </EmptyState>
      ) : (
        <ul className="dash-exec-list" role="list">
          {recentExecutions.map(e => (
            <li key={e.id} className="dash-exec-item">
              <div className="dash-exec-item-left">
                <Link
                  className="dash-exec-name"
                  to={`/investor/execution-intents/${e.id}`}
                  aria-label={`Execution for strategy: ${e.strategy_name}`}
                >
                  {e.strategy_name}
                </Link>
                <span className="dash-exec-meta">v{e.strategy_version_number}</span>
              </div>
              <span className="badge badge-info">{e.notional_amount_snapshot} {e.currency_snapshot}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="dash-card-footer">
        <Link className="btn btn-secondary btn-sm" to="/investor/allocations">
          Manage allocations
        </Link>
        <Link className="btn btn-ghost btn-sm" to="/investor/execution-intents">
          Execution intents
        </Link>
      </div>
    </section>
  );
}

/* ── Explore section (always visible) ───────────────────────── */
function ExploreSection({ creator }: { creator: boolean }) {
  return (
    <section className="dash-card" aria-labelledby="explore-section-heading">
      <div className="dash-card-header">
        <div className="dash-card-title-group">
          <span className="dash-card-icon" aria-hidden="true"><Store size={18} /></span>
          <div>
            <h2 id="explore-section-heading" className="dash-card-title">Explore</h2>
            <p className="dash-card-subtitle">Research and discovery</p>
          </div>
        </div>
      </div>

      <div className="dash-explore-grid">
        <Link className="dash-explore-tile" to="/marketplace" aria-label="Browse the strategy marketplace">
          <span className="dash-explore-tile-icon" aria-hidden="true"><Store size={20} /></span>
          <strong>Marketplace</strong>
          <span>Discover public strategies</span>
        </Link>
        <Link className="dash-explore-tile" to="/instruments" aria-label="Browse instruments">
          <span className="dash-explore-tile-icon" aria-hidden="true"><BarChart3 size={20} /></span>
          <strong>Instruments</strong>
          <span>NSE · BSE reference data</span>
        </Link>
        {creator && (
          <Link className="dash-explore-tile" to="/creator/strategies/new" aria-label="Create a new strategy">
            <span className="dash-explore-tile-icon" aria-hidden="true"><PlusCircle size={20} /></span>
            <strong>New strategy</strong>
            <span>Start building your thesis</span>
          </Link>
        )}
        {!creator && (
          <Link className="dash-explore-tile dash-explore-tile--cta" to="/creator/enroll" aria-label="Enroll as a creator">
            <span className="dash-explore-tile-icon" aria-hidden="true"><TrendingUp size={20} /></span>
            <strong>Become a Creator</strong>
            <span>Unlock systematic research tools</span>
          </Link>
        )}
      </div>
    </section>
  );
}

/* ── Platform status / coming soon strip ─────────────────────── */
function PlatformStatusStrip() {
  return (
    <aside className="dash-status-strip" aria-label="Platform feature status">
      <div className="dash-status-item dash-status-item--active">
        <FlaskConical size={14} aria-hidden="true" />
        <span>Backtesting</span>
        <span className="badge badge-success">Active</span>
      </div>
      <div className="dash-status-item dash-status-item--active">
        <Zap size={14} aria-hidden="true" />
        <span>Paper execution</span>
        <span className="badge badge-success">Active</span>
      </div>
      <div className="dash-status-item dash-status-item--soon">
        <BarChart3 size={14} aria-hidden="true" />
        <span>Analytics dashboard</span>
        <span className="badge badge-muted"><Lock size={10} aria-hidden="true" /> Soon</span>
      </div>
      <div className="dash-status-item dash-status-item--paper-only">
        <ShieldCheck size={14} aria-hidden="true" />
        <span>Execution mode</span>
        <span className="badge badge-warning">Paper only</span>
      </div>
    </aside>
  );
}

/* ─── Main DashboardPage ──────────────────────────────────────── */
export function DashboardPage() {
  const { user, isLoading } = useAuth();
  const creator = hasRole(user, CREATOR_ROLE);
  const investor = hasRole(user, INVESTOR_ROLE);

  if (isLoading) return <LoadingState label="Loading your dashboard…" />;

  const displayName = user?.email?.split("@")[0] ?? "there";

  return (
    <div className="dash-page">
      {/* ── Welcome header ───────────────────────────────────── */}
      <header className="dash-page-header">
        <div className="dash-page-header-left">
          <p className="eyebrow">Your command center</p>
          <h1 className="dash-page-title">
            Welcome back, <span className="dash-page-title-name">{displayName}</span>
          </h1>
          <p className="dash-page-subtitle">
            Move from strategy research to discovery and paper execution — every decision pinned to a Version.
          </p>
        </div>
        <div className="dash-page-header-actions">
          {creator && (
            <Link className="btn btn-primary" to="/creator/strategies/new" aria-label="Create a new strategy">
              <PlusCircle size={15} aria-hidden="true" />
              New strategy
            </Link>
          )}
          <Link className="btn btn-secondary" to="/marketplace" aria-label="Browse the marketplace">
            <Store size={15} aria-hidden="true" />
            Explore marketplace
          </Link>
        </div>
      </header>

      {/* ── Account capability strip ──────────────────────── */}
      <div className="dash-capability-strip" role="group" aria-label="Workspace capabilities">
        <div className="dash-capability-item">
          <span className="dash-capability-label">Creator mode</span>
          <span className={`dash-capability-value ${creator ? "dash-capability-value--active" : "dash-capability-value--neutral"}`}>
            {creator ? "Active" : "Available"}
          </span>
        </div>
        <div className="dash-capability-item">
          <span className="dash-capability-label">Investor mode</span>
          <span className={`dash-capability-value ${investor ? "dash-capability-value--active" : "dash-capability-value--inactive"}`}>
            {investor ? "Active" : "Unavailable"}
          </span>
        </div>
        <div className="dash-capability-item">
          <span className="dash-capability-label">Markets</span>
          <span className="dash-capability-value dash-capability-value--neutral">NSE · BSE</span>
        </div>
        <div className="dash-capability-item">
          <span className="dash-capability-label">Execution</span>
          <span className="dash-capability-value dash-capability-value--paper">Paper only</span>
        </div>
      </div>

      {/* ── Card grid ────────────────────────────────────── */}
      <div className="dash-content-grid">
        {creator && (
          <div className="dash-content-col dash-content-col--creator">
            <CreatorSection />
          </div>
        )}
        {investor && (
          <div className="dash-content-col dash-content-col--investor">
            <InvestorSection />
          </div>
        )}
        {!creator && !investor && (
          <div className="dash-content-col dash-content-col--full">
            <section className="dash-card dash-card--setup" aria-labelledby="setup-heading">
              <div className="dash-card-header">
                <div className="dash-card-title-group">
                  <span className="dash-card-icon" aria-hidden="true"><AlertCircle size={18} /></span>
                  <div>
                    <h2 id="setup-heading" className="dash-card-title">Set up your workspace</h2>
                    <p className="dash-card-subtitle">Enroll in a role to unlock features</p>
                  </div>
                </div>
              </div>
              <p className="dash-setup-body">
                Your account doesn't have a workspace role yet. Enroll as a Creator to build and backtest strategies,
                or contact support to be added as an Investor.
              </p>
              <div className="dash-card-footer">
                <Link className="btn btn-primary" to="/creator/enroll">Enroll as Creator</Link>
              </div>
            </section>
          </div>
        )}
        <div className={`dash-content-col ${creator || investor ? "dash-content-col--explore" : "dash-content-col--full"}`}>
          <ExploreSection creator={creator} />
        </div>
      </div>

      {/* ── Platform status ──────────────────────────────── */}
      <PlatformStatusStrip />

      {/* ── Research disclosure ──────────────────────────── */}
      <div className="dash-disclosure" role="note">
        <AlertCircle size={14} aria-hidden="true" className="dash-disclosure-icon" />
        <p>
          <strong>Designed for transparent research.</strong>{" "}
          Historical Backtests and Paper Execution are simulated workflows — never live performance or funded brokerage activity.
          No financial metrics (P&amp;L, returns, Sharpe, drawdown, win rate) are shown without a real backend result.
        </p>
      </div>
    </div>
  );
}

