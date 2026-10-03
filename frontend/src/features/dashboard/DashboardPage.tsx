import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Globe,
  Info,
  ListChecks,
  PenLine,
  PlayCircle,
  PlusCircle,
  Store,
  Wallet,
  XCircle,
  Zap,
} from "lucide-react";
import type { ReactNode } from "react";

import { useAuth } from "../../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../../auth/roles";
import { strategiesApi } from "../../api/strategies";
import { investorApi } from "../../api/investor";
import { queryKeys } from "../../api/queryKeys";
import type { Allocation, ExecutionIntent, Strategy } from "../../api/types";
import { EmptyState, ErrorPanel } from "../../components/PageState";
import {
  ActivityFeed,
  PageHeader,
  SectionHeader,
  SkeletonGroup,
  SkeletonRows,
  SkeletonStats,
  Stat,
  StatGrid,
  StatusBadge,
  relativeTime,
  type ActivityEntry,
} from "../../components/ui";

const ACTIVITY_LIMIT = 8;
const STRATEGY_LIMIT = 6;
const EXECUTION_LIMIT = 5;

/* ── Activity derived from timestamps the API actually returns ─ */
export function buildActivity(
  strategies: Strategy[],
  allocations: Allocation[],
  intents: ExecutionIntent[],
): ActivityEntry[] {
  const entries: ActivityEntry[] = [];
  const strategyLink = (id: string, name: string) => <Link to={`/creator/strategies/${id}`}>{name}</Link>;

  for (const s of strategies) {
    entries.push({ id: `s-created-${s.id}`, at: s.created_at, icon: <PenLine size={13} />, title: <>Created draft {strategyLink(s.id, s.name)}</> });
    if (s.published_at) entries.push({ id: `s-pub-${s.id}`, at: s.published_at, icon: <Globe size={13} />, tone: "info", title: <>Published {strategyLink(s.id, s.name)}</> });
    if (s.deployed_at) entries.push({ id: `s-dep-${s.id}`, at: s.deployed_at, icon: <CheckCircle2 size={13} />, tone: "success", title: <>Deployed {strategyLink(s.id, s.name)}</> });
  }

  for (const a of allocations) {
    entries.push({
      id: `a-${a.id}`,
      at: a.created_at,
      icon: <Wallet size={13} />,
      title: <>Allocated {a.notional_amount} {a.currency} to <Link to={`/investor/allocations/${a.id}`}>{a.strategy_name}</Link></>,
      meta: `v${a.strategy_version_number}`,
    });
  }

  for (const e of intents) {
    const link = <Link to={`/investor/execution-intents/${e.id}`}>{e.strategy_name}</Link>;
    const meta = `v${e.strategy_version_number}`;
    entries.push({ id: `e-created-${e.id}`, at: e.created_at, icon: <ListChecks size={13} />, title: <>Execution intent created for {link}</>, meta });
    if (e.started_at) entries.push({ id: `e-start-${e.id}`, at: e.started_at, icon: <PlayCircle size={13} />, tone: "info", title: <>Paper execution started for {link}</>, meta });
    if (e.status === "completed") {
      const at = e.completed_at ?? e.started_at ?? e.created_at;
      entries.push({ id: `e-done-${e.id}`, at, icon: <CheckCircle2 size={13} />, tone: "success", title: <>Paper execution completed for {link}</>, meta });
    } else if (e.status === "failed") {
      const at = e.completed_at ?? e.started_at ?? e.created_at;
      entries.push({ id: `e-fail-${e.id}`, at, icon: <XCircle size={13} />, tone: "danger", title: <>Paper execution failed for {link}</>, meta });
    }
  }

  return entries
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
    .slice(0, ACTIVITY_LIMIT);
}

/* ── Panel shell ─────────────────────────────────────────────── */
function Panel({ id, title, description, actions, footer, children }: {
  id: string; title: string; description?: string; actions?: ReactNode; footer?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="panel" aria-labelledby={id}>
      <div className="panel-head">
        <SectionHeader id={id} title={title} description={description} actions={actions} />
      </div>
      <div className="panel-body is-flush">{children}</div>
      {footer && <div className="panel-foot">{footer}</div>}
    </section>
  );
}

const loadFailed = (what: string) => `We couldn't load ${what}. Check your connection and try again.`;

/* ── Strategy overview ───────────────────────────────────────── */
function StrategyOverview({ query }: { query: ReturnType<typeof useStrategiesQuery> }) {
  const recent = [...(query.data ?? [])]
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, STRATEGY_LIMIT);

  return (
    <Panel
      id="dash-strategies"
      title="Strategies"
      description="Most recently updated"
      actions={<Link className="btn btn-ghost btn-sm" to="/creator/strategies">View all <ArrowRight size={13} aria-hidden="true" /></Link>}
      footer={recent.length > 0 ? (
        <Link className="btn btn-secondary btn-sm" to="/creator/strategies/new"><PlusCircle size={14} aria-hidden="true" /> New strategy</Link>
      ) : undefined}
    >
      {query.isLoading ? (
        <SkeletonRows label="Loading strategies…" rows={4} />
      ) : query.isError ? (
        <div className="panel-body">
          <ErrorPanel title="Strategies unavailable" onRetry={() => void query.refetch()} retrying={query.isFetching}>{loadFailed("your strategies")}</ErrorPanel>
        </div>
      ) : recent.length === 0 ? (
        <EmptyState
          variant="compact"
          icon={<PenLine size={22} />}
          title="No strategies yet"
          action={<Link className="btn btn-primary btn-sm" to="/creator/strategies/new"><PlusCircle size={14} aria-hidden="true" /> Create your first strategy</Link>}
        >
          A strategy starts as a draft. Add an immutable Version with an instrument and configuration, then backtest it.
        </EmptyState>
      ) : (
        <ul className="dash-rows">
          {recent.map(s => (
            <li key={s.id}>
              <div className="dash-row">
                <div className="dash-row-main">
                  <Link to={`/creator/strategies/${s.id}`}>{s.name}</Link>
                  <span>{s.current_version_id ? "Version selected" : "No Version selected"} · {s.is_public ? "Public" : "Private"}</span>
                </div>
                <div className="dash-row-end">
                  <span className="dash-row-time">{relativeTime(s.updated_at)}</span>
                  <StatusBadge status={s.status} />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/* ── Paper execution (investor) ──────────────────────────────── */
function ExecutionOverview({ query }: { query: ReturnType<typeof useIntentsQuery> }) {
  const recent = [...(query.data ?? [])]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, EXECUTION_LIMIT);

  return (
    <Panel
      id="dash-executions"
      title="Paper executions"
      description="Simulated runs of your allocations"
      actions={<Link className="btn btn-ghost btn-sm" to="/investor/execution-intents">View all <ArrowRight size={13} aria-hidden="true" /></Link>}
    >
      {query.isLoading ? (
        <SkeletonRows label="Loading executions…" rows={3} />
      ) : query.isError ? (
        <div className="panel-body">
          <ErrorPanel title="Executions unavailable" onRetry={() => void query.refetch()} retrying={query.isFetching}>{loadFailed("your executions")}</ErrorPanel>
        </div>
      ) : recent.length === 0 ? (
        <EmptyState
          variant="compact"
          icon={<Zap size={22} />}
          title="No execution intents"
          action={<Link className="btn btn-secondary btn-sm" to="/investor/allocations">Go to allocations</Link>}
        >
          Allocate a strategy Version, then create an execution intent to run it in paper mode.
        </EmptyState>
      ) : (
        <ul className="dash-rows">
          {recent.map(e => (
            <li key={e.id}>
              <div className="dash-row">
                <div className="dash-row-main">
                  <Link to={`/investor/execution-intents/${e.id}`}>{e.strategy_name}</Link>
                  <span>v{e.strategy_version_number} · {e.notional_amount_snapshot} {e.currency_snapshot}</span>
                </div>
                <div className="dash-row-end">
                  <span className="dash-row-time">{relativeTime(e.created_at)}</span>
                  <StatusBadge status={e.status} />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/* ── Recent activity ─────────────────────────────────────────── */
function RecentActivity({ loading, errored, entries }: { loading: boolean; errored: boolean; entries: ActivityEntry[] }) {
  return (
    <section className="panel" aria-labelledby="dash-activity">
      <div className="panel-head">
        <SectionHeader id="dash-activity" title="Recent activity" description="From your strategies and executions" />
      </div>
      <div className="panel-body">
        {loading ? (
          <SkeletonGroup label="Loading activity…"><span className="skeleton" style={{ height: "0.875rem" }} /><span className="skeleton" style={{ height: "0.875rem", width: "70%" }} /><span className="skeleton" style={{ height: "0.875rem", width: "85%" }} /></SkeletonGroup>
        ) : entries.length > 0 ? (
          <ActivityFeed entries={entries} label="Recent activity" />
        ) : (
          <EmptyState variant="compact" title="No activity yet">Events appear here as you create strategies and run executions.</EmptyState>
        )}
        {errored && !loading && <p className="hint-line" style={{ marginTop: "var(--space-4)" }}><Info size={13} aria-hidden="true" /> Some activity couldn't be loaded.</p>}
      </div>
    </section>
  );
}

/* ── Quick actions ───────────────────────────────────────────── */
function QuickActions({ creator, investor }: { creator: boolean; investor: boolean }) {
  const items: { to: string; icon: ReactNode; label: string; hint: string }[] = [];
  if (creator) {
    items.push({ to: "/creator/strategies/new", icon: <PlusCircle size={16} />, label: "Create strategy", hint: "Start a new draft" });
    items.push({ to: "/creator/strategies", icon: <PenLine size={16} />, label: "View strategies", hint: "Open a strategy to add Versions and backtests" });
  }
  if (investor) {
    items.push({ to: "/investor/allocations", icon: <Wallet size={16} />, label: "Allocations", hint: "Manage version-pinned allocations" });
    items.push({ to: "/investor/execution-intents", icon: <Zap size={16} />, label: "View executions", hint: "Paper execution intents" });
  }
  items.push({ to: "/marketplace", icon: <Store size={16} />, label: "Browse marketplace", hint: "Published strategies" });
  items.push({ to: "/instruments", icon: <BarChart3 size={16} />, label: "Instruments", hint: "NSE · BSE reference data" });

  return (
    <section className="panel" aria-labelledby="dash-quick">
      <div className="panel-head"><SectionHeader id="dash-quick" title="Quick actions" /></div>
      <ul className="quick-actions">
        {items.map(i => (
          <li key={i.to}>
            <Link className="quick-action" to={i.to}>
              {i.icon}
              <span>{i.label}<small>{i.hint}</small></span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ── Queries (enabled per role) ──────────────────────────────── */
function useStrategiesQuery(enabled: boolean) {
  return useQuery({ queryKey: queryKeys.strategies, queryFn: strategiesApi.list, enabled });
}
function useAllocationsQuery(enabled: boolean) {
  return useQuery({ queryKey: queryKeys.allocations, queryFn: investorApi.listAllocations, enabled });
}
function useIntentsQuery(enabled: boolean) {
  return useQuery({ queryKey: queryKeys.executionIntents, queryFn: investorApi.listExecutionIntents, enabled });
}

const countBy = <T,>(items: T[] | undefined, pred: (item: T) => boolean) => (items ?? []).filter(pred).length;

/* ─── Main DashboardPage ──────────────────────────────────────── */
export function DashboardPage() {
  const { user, isLoading } = useAuth();
  const creator = hasRole(user, CREATOR_ROLE);
  const investor = hasRole(user, INVESTOR_ROLE);

  const strategies = useStrategiesQuery(creator);
  const allocations = useAllocationsQuery(investor);
  const intents = useIntentsQuery(investor);

  if (isLoading) {
    return (
      <div className="skeleton-page">
        <SkeletonGroup label="Loading your dashboard…">
          <span className="skeleton" style={{ width: "40%", height: "2rem" }} />
          <span className="skeleton" style={{ width: "60%", height: "0.875rem" }} />
        </SkeletonGroup>
        <SkeletonStats label="Loading summary…" />
      </div>
    );
  }

  const hasRoleAccess = creator || investor;
  const activityLoading = (creator && strategies.isLoading) || (investor && (allocations.isLoading || intents.isLoading));
  const activityErrored = strategies.isError || allocations.isError || intents.isError;
  const activity = buildActivity(strategies.data ?? [], allocations.data ?? [], intents.data ?? []);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Workspace"
        title="Dashboard"
        description="Where your strategies and simulated executions stand right now."
        actions={
          <>
            {creator ? (
              <Link className="btn btn-primary" to="/creator/strategies/new">
                <PlusCircle size={15} aria-hidden="true" /> New strategy
              </Link>
            ) : investor ? (
              <Link className="btn btn-primary" to="/creator/enroll">Enroll as Creator</Link>
            ) : null}
            <Link className="btn btn-secondary" to="/marketplace"><Store size={15} aria-hidden="true" /> Marketplace</Link>
          </>
        }
      />

      {!hasRoleAccess && (
        <EmptyState
          icon={<PenLine size={22} />}
          title="Set up your workspace"
          action={<Link className="btn btn-primary" to="/creator/enroll">Enroll as Creator</Link>}
        >
          Your account doesn't have a workspace role yet. Enroll as a Creator to build and backtest strategies, or contact support to be added as an Investor.
        </EmptyState>
      )}

      {hasRoleAccess && (
        <div className="dash-stats">
          {creator && (
            <div>
              <h2 className="dash-stats-label">Strategy status</h2>
              {strategies.isLoading ? <SkeletonStats label="Loading strategy summary…" /> : (
                <StatGrid label="Strategy summary">
                  <Stat label="Total" value={strategies.data?.length ?? "—"} hint={strategies.isError ? "Unavailable" : undefined} />
                  <Stat label="Deployed" value={strategies.isError ? "—" : countBy(strategies.data, s => s.status === "deployed")} />
                  <Stat label="Published" value={strategies.isError ? "—" : countBy(strategies.data, s => s.status === "published")} />
                  <Stat label="Drafts" value={strategies.isError ? "—" : countBy(strategies.data, s => s.status === "draft")} hint={countBy(strategies.data, s => s.status === "archived") ? `${countBy(strategies.data, s => s.status === "archived")} archived` : undefined} />
                </StatGrid>
              )}
            </div>
          )}
          {investor && (
            <div>
              <h2 className="dash-stats-label">Execution status</h2>
              {allocations.isLoading || intents.isLoading ? <SkeletonStats label="Loading execution summary…" /> : (
                <StatGrid label="Execution summary">
                  <Stat label="Active allocations" value={allocations.isError ? "—" : countBy(allocations.data, a => a.status === "active")} />
                  <Stat label="Execution intents" value={intents.isError ? "—" : intents.data?.length ?? "—"} />
                  <Stat label="Completed" value={intents.isError ? "—" : countBy(intents.data, e => e.status === "completed")} />
                  <Stat label="Failed" value={intents.isError ? "—" : countBy(intents.data, e => e.status === "failed")} />
                </StatGrid>
              )}
            </div>
          )}
        </div>
      )}

      {hasRoleAccess && (
        <div className="dash-grid">
          <div className="dash-main">
            {creator && <StrategyOverview query={strategies} />}
            {investor && <ExecutionOverview query={intents} />}
          </div>
          <div className="dash-side">
            <RecentActivity loading={activityLoading} errored={activityErrored} entries={activity} />
            <QuickActions creator={creator} investor={investor} />
          </div>
        </div>
      )}

      <div className="dash-note" role="note">
        <Info size={14} aria-hidden="true" />
        <p>
          <strong>Simulation only.</strong> Backtests and paper execution are simulated workflows — not live performance, and no orders are placed with a broker.
          Financial metrics appear only where a real backend result exists.
        </p>
      </div>
    </div>
  );
}
