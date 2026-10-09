import { useEffect, useId, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, CheckCircle2, CircleCheck, CircleDashed, Loader2, Lock, Play } from "lucide-react";
import { Link, useBlocker, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { marketplaceApi } from "../../api/marketplace";
import { queryKeys } from "../../api/queryKeys";
import type { MarketplaceStrategy } from "../../api/types";
import { EmptyState, ErrorAlert, LoadingState } from "../../components/PageState";
import { Alert, Button, ConfirmDialog, Input, SectionHeader, Stat, StatGrid, StatusBadge } from "../../components/ui";
import { formatCurrency, formatInteger, formatNumber, formatPercentage } from "../../lib/format";
import { EquityChart } from "../creator/EquityChart";
import { NOT_AVAILABLE, displayDay } from "../creator/backtestFormat";
import {
  MARKETPLACE_BACKTEST_SUPPORT,
  resolveDisplayState,
  validateStartingCapital,
  type DisplayState,
  type ExecutionView,
  type ProvenanceView,
  type ResultView,
} from "./backtestContract";

const STATE_COPY: Record<DisplayState, { label: string; tone: "muted" | "info" | "success" | "danger" | "warning"; text: string }> = {
  not_configured: { label: "Not configured", tone: "muted", text: "Enter a valid starting capital to configure this Backtest. No Backtest has been run." },
  ready: { label: "Ready to run", tone: "info", text: "The configuration is valid. No Backtest has been run yet." },
  running: { label: "Running", tone: "info", text: "The Backtest is running. Results appear only when the run finishes." },
  completed: { label: "Completed", tone: "success", text: "The run finished. Figures below come from the returned result." },
  failed: { label: "Failed", tone: "danger", text: "The run did not complete. No results are shown." },
  unavailable: { label: "Unavailable", tone: "warning", text: "Running a Backtest for this strategy is not available." },
};

function StateIcon({ state }: { state: DisplayState }) {
  if (state === "running") return <Loader2 size={18} aria-hidden="true" className="loading-orbit" />;
  if (state === "completed") return <CircleCheck size={18} aria-hidden="true" />;
  if (state === "failed") return <AlertCircle size={18} aria-hidden="true" />;
  if (state === "unavailable") return <Lock size={18} aria-hidden="true" />;
  if (state === "ready") return <CheckCircle2 size={18} aria-hidden="true" />;
  return <CircleDashed size={18} aria-hidden="true" />;
}

/** Reusable execution-status panel. Always says plainly whether anything has run. */
export function ExecutionStatus({ state, detail }: { state: DisplayState; detail?: string }) {
  const copy = STATE_COPY[state];
  return (
    <div className={`bt-status bt-status-${state}`} role="status" data-testid="execution-status" data-state={state}>
      <span className={`bt-status-mark tone-${copy.tone}`}><StateIcon state={state} /></span>
      <div>
        <strong>{copy.label}</strong>
        <p>{detail ?? copy.text}</p>
      </div>
    </div>
  );
}

const orUnavailable = (value: string | null | undefined) => (value ? value : NOT_AVAILABLE);

export function ProvenancePanel({ provenance }: { provenance: ProvenanceView | null }) {
  const p = provenance;
  const dataset = p ? (p.synthetic === true ? "Synthetic reference dataset" : p.synthetic === false ? "Historical market dataset" : null) : null;
  return (
    <section className="bt-card" aria-labelledby="bt-prov-title">
      <SectionHeader id="bt-prov-title" title="Provenance & assumptions" description="Only facts supplied by a returned result or the strategy version are shown. Anything else is marked unavailable." />
      <dl className="details-list">
        <dt>Data source</dt><dd>{orUnavailable(p?.dataSource)}{dataset ? ` · ${dataset}` : ""}</dd>
        <dt>Timeframe</dt><dd>{orUnavailable(p?.timeframe)}</dd>
        <dt>Fill model</dt><dd>{orUnavailable(p?.fillModel)}</dd>
        <dt>Fees</dt><dd>{orUnavailable(p?.fees)}</dd>
        <dt>Slippage</dt><dd>{orUnavailable(p?.slippage)}</dd>
        <dt>Engine</dt><dd>{orUnavailable(p?.engine)}</dd>
        <dt>Definition version</dt><dd>{orUnavailable(p?.definitionVersion)}</dd>
      </dl>
      <h3 className="bt-subhead">Limitations</h3>
      {p?.limitations.length ? (
        <ul className="bt-list">{p.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      ) : (
        <p className="field-hint">No limitations were supplied. A backtest is a simulation on historical or reference data; it is not a forecast and not live or paper trading.</p>
      )}
    </section>
  );
}

export function TradeHistory({ trades }: { trades: ResultView["trades"] }) {
  if (!trades.length) {
    return <EmptyState variant="compact" title="No trades returned">The result contains no trades.</EmptyState>;
  }
  return (
    <div className="bt-table-wrap" role="region" aria-label="Trade history" tabIndex={0}>
      <table className="bt-table">
        <caption className="sr-only">Trade history with entry and exit details</caption>
        <thead>
          <tr><th scope="col">Side</th><th scope="col">Entry</th><th scope="col">Exit</th><th scope="col" className="num">Qty</th><th scope="col" className="num">Entry price</th><th scope="col" className="num">Exit price</th><th scope="col" className="num">P&amp;L</th></tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={`${t.entryTimestamp}-${i}`}>
              <td>{t.side}</td>
              <td>{displayDay(t.entryTimestamp)}</td>
              <td>{displayDay(t.exitTimestamp)}</td>
              <td className="num">{formatNumber(t.quantity)}</td>
              <td className="num">{formatNumber(t.entryPrice)}</td>
              <td className="num">{formatNumber(t.exitPrice)}</td>
              <td className="num">{formatCurrency(t.pnl, { signed: true })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const tone = (v: string) => (Number(v) > 0 ? "profit" : Number(v) < 0 ? "loss" : undefined);

/** Renders only a supplied `result`; with none, explains why there is nothing to show. */
export function PerformancePanel({ state, result, detail }: { state: DisplayState; result: ResultView | null; detail?: string }) {
  if (state !== "completed" || !result) {
    const empty: Record<Exclude<DisplayState, "completed">, string> = {
      not_configured: "Results appear here after a Backtest has been configured and run.",
      ready: "No results yet: the Backtest has not been run.",
      running: "Waiting for the run to finish.",
      failed: detail ?? "The run failed, so there are no results.",
      unavailable: "There are no results because Backtests cannot be run for this strategy yet.",
    };
    return (
      <section className="bt-card" aria-labelledby="bt-perf-title" data-testid="performance-empty">
        <SectionHeader id="bt-perf-title" title="Performance" />
        {state === "running" ? <LoadingState label="Running Backtest…" /> : (
          <EmptyState variant="compact" title="No performance data">{empty[state === "completed" ? "unavailable" : state]}</EmptyState>
        )}
      </section>
    );
  }
  return (
    <section className="bt-card" aria-labelledby="bt-perf-title" data-testid="performance-results">
      <SectionHeader id="bt-perf-title" title="Performance" description="Simulated results from the returned Backtest. Not a forecast and not live trading." />
      <StatGrid label="Backtest performance metrics">
        <Stat label="Starting capital" value={formatCurrency(result.startingCapital)} />
        <Stat label="Net profit / loss" value={formatCurrency(result.netProfitLoss, { signed: true })} tone={tone(result.netProfitLoss)} />
        <Stat label="Return" value={formatPercentage(result.returnPercent, { signed: true })} tone={tone(result.returnPercent)} />
        <Stat label="Max drawdown" value={formatPercentage(result.maxDrawdown)} />
        <Stat label="Trades" value={formatInteger(result.tradeCount)} />
        {result.winRate != null && <Stat label="Win rate" value={formatPercentage(result.winRate, { ratio: true })} />}
        {result.profitFactor != null && <Stat label="Profit factor" value={formatNumber(result.profitFactor)} />}
      </StatGrid>
      <h3 className="bt-subhead">Equity curve</h3>
      <EquityChart curve={result.equityCurve} />
      <h3 className="bt-subhead">Trade history</h3>
      <TradeHistory trades={result.trades} />
    </section>
  );
}

const PHASES = [
  { key: "backtest", label: "Backtesting", text: "Simulation on historical or reference data. No orders; no capital." },
  { key: "paper", label: "Paper trading", text: "Simulated execution going forward. Not part of this page." },
  { key: "live", label: "Live trading", text: "Real orders with real money. Not offered by AlgoProfitX." },
];

export interface WorkspaceViewProps {
  strategy: MarketplaceStrategy;
  execution: ExecutionView;
  /** Provided only when a real, supported API call exists. Omitted → the Run control stays disabled. */
  onRun?: (startingCapital: string) => void;
}

export function BacktestWorkspaceView({ strategy, execution, onRun }: WorkspaceViewProps) {
  const [capital, setCapital] = useState("");
  const [touched, setTouched] = useState(false);
  const noteId = useId();
  const error = validateStartingCapital(capital);
  const state = resolveDisplayState(execution, error === null);
  const runnable = Boolean(onRun) && state === "ready";
  const dirty = capital.trim() !== "";

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (runnable && !error) onRun?.(capital);
  };

  const version = strategy.current_version_number ? `Version ${strategy.current_version_number}` : "Version not available";
  const versionId = strategy.current_version_id ? strategy.current_version_id.slice(0, 8) : null;
  const detail = execution.kind === "failed" ? execution.message : undefined;
  const result = execution.kind === "completed" ? execution.result : null;

  return (
    <section className="strategy-detail bt-workspace">
      <Link className="back-link" to={`/marketplace/${encodeURIComponent(strategy.slug)}`}>
        <ArrowLeft size={16} aria-hidden="true" /> Back to strategy profile
      </Link>
      <p className="eyebrow">Backtest workspace</p>
      <div className="card-title-row"><h1>{strategy.name}</h1><StatusBadge status={strategy.status} /></div>
      <p className="bt-identity">
        <strong>{version}</strong>
        {versionId && <> · immutable id <span className="mono">{versionId}</span></>}
      </p>

      <ol className="bt-phases" aria-label="Backtesting compared with paper and live trading">
        {PHASES.map((p) => (
          <li key={p.key} aria-current={p.key === "backtest" ? "step" : undefined} className={p.key === "backtest" ? "is-current" : undefined}>
            <strong>{p.label}{p.key === "backtest" ? " (this page)" : ""}</strong>
            <span>{p.text}</span>
          </li>
        ))}
      </ol>

      <div className="bt-grid">
        <section className="bt-card" aria-labelledby="bt-config-title">
          <SectionHeader id="bt-config-title" title="Configuration" />
          <form onSubmit={submit} noValidate>
            <fieldset className="bt-fieldset">
              <legend>Your settings</legend>
              <Input
                label="Starting capital (INR)"
                inputMode="decimal"
                autoComplete="off"
                placeholder="50,000"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                onBlur={() => setTouched(true)}
                error={touched ? error ?? undefined : undefined}
                hint="Simulated capital in ₹. No real money is used."
                iconLeft={<span>₹</span>}
              />
            </fieldset>
            <fieldset className="bt-fieldset" disabled>
              <legend>Fixed by strategy version</legend>
              <dl className="details-list">
                <dt>Instrument &amp; rules</dt><dd>Defined by {version}; protected and not editable here.</dd>
                <dt>Timeframe, fill model, fees, slippage</dt><dd>Set by the strategy version; shown under Provenance once a result exists.</dd>
              </dl>
            </fieldset>
            <p id={noteId} className="field-hint">{runnable ? "Running uses the capital above." : "The Run control is off until Backtests are supported for this strategy."}</p>
            <Button type="submit" iconLeft={<Play size={14} />} disabled={!runnable} aria-describedby={noteId}>Run Backtest</Button>
          </form>
        </section>

        <section className="bt-card" aria-labelledby="bt-status-title">
          <SectionHeader id="bt-status-title" title="Execution status" />
          <ExecutionStatus state={state} detail={detail} />
          {state === "unavailable" && (
            <Alert variant="info" title="What is needed">
              {MARKETPLACE_BACKTEST_SUPPORT.reason}
            </Alert>
          )}
        </section>
      </div>

      <PerformancePanel state={state} result={result} detail={detail} />
      <ProvenancePanel provenance={result?.provenance ?? null} />

      <ConfirmDialog open={blocker.state === "blocked"} title="Leave without running?" confirmLabel="Leave and discard"
        onCancel={() => blocker.reset?.()} onConfirm={() => blocker.proceed?.()}>
        <p>Your starting-capital entry has not been used. If you leave this page it will be lost.</p>
      </ConfirmDialog>
    </section>
  );
}

/** Route component. Support is fixed to "unavailable" until the API-integration PR supplies real execution. */
export function MarketplaceBacktestPage() {
  const { slug = "" } = useParams();
  const query = useQuery({ queryKey: queryKeys.marketplaceDetail(slug), queryFn: () => marketplaceApi.getBySlug(slug), enabled: Boolean(slug) });

  if (query.isLoading) return <LoadingState label="Loading strategy…" />;
  if (query.isError || !query.data) {
    const message = query.error instanceof ApiError && query.error.status === 404 ? "This marketplace strategy is not available." : "Unable to load this strategy.";
    return (
      <section className="strategy-detail">
        <Link className="back-link" to="/marketplace"><ArrowLeft size={16} aria-hidden="true" /> Back to Marketplace</Link>
        <ErrorAlert>{message}</ErrorAlert>
      </section>
    );
  }
  const execution: ExecutionView = MARKETPLACE_BACKTEST_SUPPORT.supported
    ? { kind: "idle" }
    : { kind: "unavailable", reason: MARKETPLACE_BACKTEST_SUPPORT.reason };
  return <BacktestWorkspaceView strategy={query.data} execution={execution} />;
}
