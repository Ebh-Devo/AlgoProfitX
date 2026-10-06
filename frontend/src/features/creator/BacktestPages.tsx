import { FormEvent, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, CircleDashed, GitCompareArrows, Loader2, Play, X } from "lucide-react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { strategiesApi } from "../../api/strategies";
import type { Backtest, BacktestAnalytics, StrategyVersion } from "../../api/types";
import { EmptyState, ErrorPanel, LoadingState } from "../../components/PageState";
import { Alert, Button, FilterChips, InlineStatus, StatusBadge, Tabs } from "../../components/ui";
import { EquityChart } from "./EquityChart";
import {
  MAX_REFERENCE_LENGTH, configValue, displayDate, displayDay, errorMessage, instrumentOf, isActive, isSynthetic,
  metric, parseTrades, periodLabel, ratioPercent, shortId, summaryFigures, NOT_AVAILABLE,
} from "./backtestFormat";

const runPath = (strategyId: string, versionId: string, runId: string) =>
  `/creator/strategies/${strategyId}/versions/${versionId}/backtests/${runId}`;

/* ── Shared: "what am I testing?" ─────────────────────────────── */

interface ContextProps {
  strategyId: string;
  versionId: string;
  strategyName?: string;
  versionNumber?: number;
  /** Overrides the Version link text where the page header already names the Version. */
  versionLabel?: string;
  fields: { label: string; value: ReactNode }[];
}

/** One strong context block so a result can never be mistaken for another Strategy/Version. */
function ResearchContext({ strategyId, versionId, strategyName, versionNumber, versionLabel, fields }: ContextProps) {
  return (
    <div role="group" aria-label="What is being tested"><dl className="research-context">
      <div className="research-context-lead">
        <dt>Strategy</dt>
        <dd><Link to={`/creator/strategies/${strategyId}`}>{strategyName ?? "Strategy"}</Link></dd>
      </div>
      <div className="research-context-lead">
        <dt>Version</dt>
        <dd><Link to={`/creator/strategies/${strategyId}/versions/${versionId}`}>{versionLabel ?? (versionNumber != null ? `Version ${versionNumber}` : "Version")}</Link></dd>
      </div>
      {fields.map((f) => (
        <div key={f.label}><dt>{f.label}</dt><dd>{f.value}</dd></div>
      ))}
    </dl></div>
  );
}

/* ── Version page: configure + history + compare ──────────────── */

interface VersionBacktestsProps {
  strategyId: string;
  versionId: string;
  strategyName?: string;
  version?: StrategyVersion;
}

export function VersionBacktests({ strategyId, versionId, strategyName, version }: VersionBacktestsProps) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [reference, setReference] = useState("");
  const [touched, setTouched] = useState(false);

  const referenceError = reference.length > MAX_REFERENCE_LENGTH
    ? `Keep the reference to ${MAX_REFERENCE_LENGTH} characters or fewer (currently ${reference.length}).`
    : null;

  const create = useMutation({
    mutationFn: () => strategiesApi.createBacktest(strategyId, versionId, { market_data_reference: reference.trim() || null }),
    onSuccess: async (result) => {
      setReference("");
      setTouched(false);
      await client.invalidateQueries({ queryKey: queryKeys.backtests(strategyId, versionId) });
      // The result page runs the queued Backtest immediately and shows the real lifecycle.
      navigate(runPath(strategyId, versionId, result.id), { state: { autoRun: true } });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (referenceError) return;
    create.mutate();
  };

  const bt = version?.backtest_configuration;
  const instrument = version?.instrument;
  const timeframe = configValue(bt, "timeframe");
  const start = configValue(bt, "start_date");
  const end = configValue(bt, "end_date");
  const capital = configValue(bt, "initial_capital");
  const period = start && end ? `${displayDay(start)} – ${displayDay(end)}` : null;

  const refId = "backtest-reference";
  const errId = `${refId}-error`;

  return (
    <section className="research" aria-labelledby="research-heading">
      <div className="section-header">
        <div className="section-header-text">
          <p className="eyebrow">Backtest research</p>
          <h2 id="research-heading">Backtests</h2>
          <p>Reference backtesting only. These are not live trades or realized Investor performance.</p>
        </div>
      </div>

      <form className="panel research-config" onSubmit={submit} noValidate aria-label="Configure backtest">
        <div className="panel-head">
          <div>
            <h3 className="research-h3">Configure</h3>
            <p className="research-sub">Everything below is fixed by this immutable Version except the optional data reference.</p>
          </div>
        </div>
        <div className="panel-body research-config-body">
          <ResearchContext
            strategyId={strategyId}
            versionId={versionId}
            strategyName={strategyName}
            versionNumber={version?.version_number}
            versionLabel={version ? `v${version.version_number} · immutable` : undefined}
            fields={[
              { label: "Instrument", value: instrument ? <><strong>{instrument.exchange_symbol}</strong> <span className="muted">{instrument.exchange.code}</span></> : "Legacy / unresolved" },
              { label: "Timeframe", value: timeframe ?? (version ? "1d (engine default)" : NOT_AVAILABLE) },
              { label: "Period", value: period ?? (version ? "Set by the data provider" : NOT_AVAILABLE) },
              { label: "Initial capital", value: capital ? metric(capital) : NOT_AVAILABLE },
            ]}
          />
          <div className="research-engine">
            <div>
              <span className="research-label">Engine</span>
              <strong>Reference backtest engine</strong>
              <p>A single long-only EMA crossover reference run. Not a general strategy engine.</p>
            </div>
            <div>
              <span className="research-label">Market data</span>
              <strong>Synthetic reference data</strong>
              <p>The server-configured provider supplies deterministic reference candles. Real NSE history is not connected yet.</p>
            </div>
          </div>

          <div className="form-field">
            <label htmlFor={refId}>Market data reference <span className="field-optional">(optional)</span></label>
            <input
              id={refId}
              className="input"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              onBlur={() => setTouched(true)}
              aria-invalid={touched && referenceError ? true : undefined}
              aria-describedby={`${refId}-help${touched && referenceError ? ` ${errId}` : ""}`}
              autoComplete="off"
              spellCheck={false}
            />
            <div className="field-footer">
              <span id={`${refId}-help`} className="field-help">Optional identifier recorded with the run for the reference dataset.</span>
              <span className="field-counter" aria-hidden="true">{reference.length}/{MAX_REFERENCE_LENGTH}</span>
            </div>
            {touched && referenceError && <p id={errId} className="field-error" role="alert">{referenceError}</p>}
          </div>

          {create.isError && (
            <Alert variant="error" title="Run could not be started">{errorMessage(create.error, "Unable to create Backtest.")}</Alert>
          )}
        </div>
        <div className="panel-foot research-config-foot">
          <Button type="submit" loading={create.isPending} iconLeft={<Play size={14} aria-hidden="true" />}>
            {create.isPending ? "Preparing run…" : "Run Backtest"}
          </Button>
          <InlineStatus state={create.isPending ? "pending" : "idle"} pending="Preparing research run" />
        </div>
      </form>

      <RunHistory strategyId={strategyId} versionId={versionId} version={version} />
    </section>
  );
}

/* ── History + compare ────────────────────────────────────────── */

type StatusFilter = "all" | "completed" | "failed" | "active";
type SortKey = "newest" | "oldest" | "return";

const matches = (run: Backtest, f: StatusFilter) =>
  f === "all" || (f === "active" ? isActive(run.status) : run.status === f);

function RunHistory({ strategyId, versionId, version }: { strategyId: string; versionId: string; version?: StrategyVersion }) {
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortKey>("newest");
  const [selected, setSelected] = useState<string[]>([]);

  const query = useQuery({
    queryKey: queryKeys.backtests(strategyId, versionId),
    queryFn: () => strategiesApi.listBacktests(strategyId, versionId),
    refetchInterval: (q) => {
      const data = q.state.data as Backtest[] | undefined;
      return data?.some((b) => isActive(b.status)) ? 5000 : false;
    },
  });

  const runs = query.data ?? [];
  const counts = useMemo(() => ({
    all: runs.length,
    completed: runs.filter((r) => r.status === "completed").length,
    failed: runs.filter((r) => r.status === "failed").length,
    active: runs.filter((r) => isActive(r.status)).length,
  }), [runs]);

  const visible = useMemo(() => {
    const rows = runs.filter((r) => matches(r, filter));
    const ret = (r: Backtest) => { const v = summaryFigures(r).totalReturn; return v == null ? null : Number(v); };
    return [...rows].sort((a, b) => {
      if (sort === "oldest") return a.created_at.localeCompare(b.created_at);
      if (sort === "return") {
        const x = ret(a), y = ret(b);
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        return y - x;
      }
      return b.created_at.localeCompare(a.created_at);
    });
  }, [runs, filter, sort]);

  const toggle = (id: string) =>
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : cur.length >= 2 ? [cur[1], id] : [...cur, id]));

  return (
    <div className="research-history" aria-labelledby="history-heading" role="region">
      <div className="section-header">
        <div className="section-header-text">
          <h3 id="history-heading" className="research-h3">Run history <span className="section-count">{runs.length}</span></h3>
        </div>
      </div>

      {query.isLoading ? (
        <LoadingState label="Loading Backtests…" />
      ) : query.isError ? (
        <ErrorPanel title="Unable to load backtest data." onRetry={() => void query.refetch()} retrying={query.isFetching}>
          <span>{errorMessage(query.error, "Try again.")}</span>
        </ErrorPanel>
      ) : !runs.length ? (
        <EmptyState title="No backtests yet">Run your first backtest to start building your research history.</EmptyState>
      ) : (
        <>
          <div className="toolbar">
            <FilterChips<StatusFilter>
              label="Filter runs by status"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All", count: counts.all },
                { value: "completed", label: "Completed", count: counts.completed },
                { value: "failed", label: "Failed", count: counts.failed },
                { value: "active", label: "In progress", count: counts.active },
              ]}
            />
            <span className="toolbar-spacer" />
            <label className="toolbar-sort">
              Sort
              <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="return">Total return (high to low)</option>
              </select>
            </label>
          </div>
          <p className="result-count" role="status">Showing {visible.length} of {runs.length} runs</p>

          {visible.length === 0 ? (
            <EmptyState variant="compact" title="No runs match this filter">Choose another status to see more runs.</EmptyState>
          ) : (
            <div className="table-wrap is-stacked data-region">
              <table className="data-table is-stacked research-table">
                <caption className="visually-hidden">Backtest runs for this Version</caption>
                <thead>
                  <tr>
                    <th scope="col"><span className="visually-hidden">Compare</span></th>
                    <th scope="col">Run</th>
                    <th scope="col">Version</th>
                    <th scope="col">Instrument</th>
                    <th scope="col">Period</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="num">Return</th>
                    <th scope="col" className="num">Trades</th>
                    <th scope="col">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((run) => {
                    const fig = summaryFigures(run);
                    const inst = instrumentOf(run);
                    const done = run.status === "completed";
                    const period = periodLabel(run.range_start, run.range_end);
                    return (
                      <tr key={run.id}>
                        <td className="cell-select" data-label="Compare">
                          <input
                            type="checkbox"
                            checked={selected.includes(run.id)}
                            disabled={!done}
                            onChange={() => toggle(run.id)}
                            aria-label={`Compare run ${shortId(run.id)}${done ? "" : " (only completed runs can be compared)"}`}
                          />
                        </td>
                        <td className="cell-title" data-label="Run">
                          <span className="cell-primary">
                            <Link to={runPath(strategyId, versionId, run.id)}>Run {shortId(run.id)}</Link>
                            {run.market_data_reference && <small>{run.market_data_reference}</small>}
                          </span>
                        </td>
                        <td data-label="Version">{version ? `Version ${version.version_number}` : "This Version"}</td>
                        <td data-label="Instrument">{inst?.symbol ?? "Legacy"}</td>
                        <td data-label="Period" className="cell-muted">{period ?? NOT_AVAILABLE}</td>
                        <td data-label="Status"><StatusBadge status={run.status} /></td>
                        <td data-label="Return" className="num">{fig.totalReturn == null ? "—" : metric(fig.totalReturn, "%")}</td>
                        <td data-label="Trades" className="num">{fig.tradeCount == null ? "—" : fig.tradeCount.toLocaleString()}</td>
                        <td data-label="Created" className="cell-muted">{displayDate(run.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <ComparePanel
            strategyId={strategyId}
            versionId={versionId}
            runs={selected.map((id) => runs.find((r) => r.id === id)).filter((r): r is Backtest => !!r)}
            onClear={() => setSelected([])}
          />
        </>
      )}
    </div>
  );
}

function ComparePanel({ strategyId, versionId, runs, onClear }: { strategyId: string; versionId: string; runs: Backtest[]; onClear: () => void }) {
  const results = useQueries({
    queries: runs.map((r) => ({
      queryKey: queryKeys.backtestAnalytics(strategyId, versionId, r.id),
      queryFn: () => strategiesApi.getBacktestAnalytics(strategyId, versionId, r.id),
    })),
  });

  if (runs.length === 0) return null;
  if (runs.length === 1) {
    return (
      <p className="compare-hint" role="status"><GitCompareArrows size={14} aria-hidden="true" /> Select one more completed run to compare it with Run {shortId(runs[0].id)}.</p>
    );
  }

  const data = results.map((r) => r.data as BacktestAnalytics | undefined);
  const failed = results.find((r) => r.isError);
  const rows: { label: string; cell: (run: Backtest, a?: BacktestAnalytics) => ReactNode }[] = [
    { label: "Created", cell: (r) => displayDate(r.created_at) },
    { label: "Instrument", cell: (r) => instrumentOf(r)?.symbol ?? "Legacy" },
    { label: "Timeframe", cell: (r) => r.timeframe ?? NOT_AVAILABLE },
    { label: "Period", cell: (r) => periodLabel(r.range_start, r.range_end) ?? NOT_AVAILABLE },
    { label: "Data provider", cell: (r) => r.market_data_provider ?? NOT_AVAILABLE },
    { label: "Engine", cell: (r, a) => a?.engine_identifier ?? summaryFigures(r).engine ?? NOT_AVAILABLE },
    { label: "Initial capital", cell: (_, a) => (a ? metric(a.initial_capital) : "…") },
    { label: "Final equity", cell: (_, a) => (a ? metric(a.final_equity) : "…") },
    { label: "Total return", cell: (_, a) => (a ? metric(a.total_return, "%") : "…") },
    { label: "Max drawdown", cell: (_, a) => (a ? metric(a.max_drawdown, "%") : "…") },
    { label: "Trade count", cell: (_, a) => (a ? a.trade_count.toLocaleString() : "…") },
    { label: "Win rate", cell: (_, a) => (a ? ratioPercent(a.win_rate) : "…") },
  ];

  return (
    <section className="panel compare-panel" aria-labelledby="compare-heading">
      <div className="panel-head">
        <h3 id="compare-heading" className="research-h3">Compare runs</h3>
        <Button variant="ghost" size="sm" onClick={onClear} iconLeft={<X size={13} aria-hidden="true" />}>Clear</Button>
      </div>
      <div className="panel-body is-flush">
        {failed && <Alert variant="error" title="Unable to load comparison data.">{errorMessage(failed.error, "Try again.")}</Alert>}
        <div className="table-wrap">
          <table className="data-table compare-table">
            <caption className="visually-hidden">Side-by-side comparison of two backtest runs</caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                {runs.map((r, i) => (
                  <th scope="col" key={r.id}>{i === 0 ? "Run A" : "Run B"} · <Link to={runPath(strategyId, versionId, r.id)}>{shortId(r.id)}</Link></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th scope="row">{row.label}</th>
                  {runs.map((r, i) => <td key={r.id}>{row.cell(r, data[i])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/* ── Run lifecycle (honest states, no invented progress) ──────── */

type StepState = "todo" | "active" | "done" | "failed";

function RunLifecycle({ run, executing, resultLoading }: { run: Backtest; executing: boolean; resultLoading: boolean }) {
  const running = executing || run.status === "running";
  const queued = run.status === "queued" && !executing;
  const completed = run.status === "completed";
  const failed = run.status === "failed";

  const steps: { label: string; state: StepState }[] = [
    { label: "Preparing research run", state: "done" },
    { label: "Running backtest", state: running ? "active" : queued ? "todo" : failed ? "failed" : "done" },
    { label: "Waiting for result", state: completed ? (resultLoading ? "active" : "done") : "todo" },
    { label: failed ? "Run failed" : "Backtest completed", state: completed && !resultLoading ? "done" : failed ? "failed" : "todo" },
  ];

  const headline = queued ? "Backtest queued." : running ? "Backtest running." : failed ? "Run failed." : resultLoading ? "Collecting result." : "Result ready.";
  const detail = queued
    ? "This Backtest is waiting to be executed. Click Execute Backtest to begin."
    : running
      ? "The engine is processing this run. This page will update automatically."
      : failed
        ? "The run stopped before producing a result."
        : resultLoading
          ? "Fetching the analytics recorded for this run."
          : null;

  return (
    <div className={`panel lifecycle is-${failed ? "failed" : completed && !resultLoading ? "done" : running ? "running" : "queued"}`}>
      <div className="lifecycle-text" role="status" aria-live="polite">
        <strong>{headline}</strong>
        {detail && <span>{detail}</span>}
      </div>
      <ol className="lifecycle-steps" aria-label="Run progress">
        {steps.map((s) => (
          <li key={s.label} className={`lifecycle-step is-${s.state}`} aria-current={s.state === "active" ? "step" : undefined}>
            <span className="lifecycle-mark" aria-hidden="true">
              {s.state === "done" ? <Check size={12} /> : s.state === "failed" ? <X size={12} /> : s.state === "active" ? <Loader2 size={12} className="status-spin" /> : <CircleDashed size={12} />}
            </span>
            <span>{s.label}</span>
            <span className="visually-hidden">{s.state === "done" ? " (done)" : s.state === "active" ? " (in progress)" : s.state === "failed" ? " (failed)" : " (not started)"}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/* ── Result: metrics, chart, trades ───────────────────────────── */

function Analytics({ data, run }: { data: BacktestAnalytics; run: Backtest }) {
  const positive = Number(data.total_return) > 0;
  const metrics: [string, string][] = [
    ["Initial capital", metric(data.initial_capital)],
    ["Final equity", metric(data.final_equity)],
    // total_return is stored as a percentage value (e.g. 10.5 = 10.5%) by the backend engine
    ["Total return", `${positive ? "+" : ""}${metric(data.total_return, "%")}`],
    ["Trade count", data.trade_count.toLocaleString()],
    // win_rate is a decimal ratio (0–1) stored by the analytics service; multiply × 100 to display
    ["Win rate", ratioPercent(data.win_rate)],
    ["Profit factor", metric(data.profit_factor)],
    ["Average win", metric(data.average_win)],
    ["Average loss", metric(data.average_loss)],
    // max_drawdown is stored as a percentage value by the analytics service
    ["Max drawdown", metric(data.max_drawdown, "%")],
  ];
  const curve = data.equity_curve;
  const trades = parseTrades(run.result_summary);

  return (
    <section className="analytics result-reveal" aria-labelledby="analytics-heading">
      <div className="section-header">
        <div className="section-header-text">
          <p className="eyebrow">Completed synthetic run</p>
          <h2 id="analytics-heading">Backtest analytics</h2>
          <p>Historical synthetic/reference output only; it is not live or realized Investor performance.</p>
        </div>
      </div>

      <div className="rs-metrics" role="list" aria-label="Backtest metrics">
        {metrics.map(([label, value]) => (
          <div className={`rs-metric${value === "Unavailable" ? " is-unavailable" : ""}${label === "Total return" ? " is-primary" : ""}`} key={label} role="listitem" aria-label={`${label}: ${value}`}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <div className="panel chart-panel">
        <div className="panel-head"><h3 id="equity-curve-heading" className="research-h3">Equity curve</h3></div>
        <div className="panel-body">
          <EquityChart curve={curve} />
        </div>
        {curve.length > 0 && (
          <details className="equity-details">
            <summary>Equity point detail</summary>
            <div className="table-wrap">
              <table className="data-table" aria-label="Equity curve data points">
                <thead><tr><th scope="col">Timestamp</th><th scope="col" className="num">Equity</th></tr></thead>
                <tbody>{curve.map((point) => <tr key={`${point.timestamp}-${point.equity}`}><td>{point.timestamp}</td><td className="num">{metric(point.equity)}</td></tr>)}</tbody>
              </table>
            </div>
          </details>
        )}
      </div>

      <Tabs
        label="Run detail"
        items={[
          { id: "trades", label: `Trades`, content: <TradesPanel trades={trades} tradeCount={data.trade_count} /> },
          {
            id: "config",
            label: "Run configuration",
            content: (
              <div className="config-grid">
                <div><h4 className="research-h4">Algorithm configuration</h4><pre className="json-view">{JSON.stringify(run.configuration_snapshot, null, 2)}</pre></div>
                <div><h4 className="research-h4">Backtest configuration</h4><pre className="json-view">{JSON.stringify(run.backtest_configuration_snapshot, null, 2)}</pre></div>
              </div>
            ),
          },
        ]}
      />
    </section>
  );
}

function TradesPanel({ trades, tradeCount }: { trades: ReturnType<typeof parseTrades>; tradeCount: number }) {
  if (!trades.length) {
    return tradeCount === 0
      ? <EmptyState variant="compact" title="No trades were opened">This run completed without a trade signal.</EmptyState>
      : <EmptyState variant="compact" title="Trade detail not available">This run reports trades but did not record their detail.</EmptyState>;
  }
  return (
    <div className="table-wrap is-stacked">
      <table className="data-table is-stacked" aria-label="Trades">
        <thead>
          <tr>
            <th scope="col">Side</th><th scope="col">Entry</th><th scope="col">Exit</th>
            <th scope="col" className="num">Quantity</th><th scope="col" className="num">Entry price</th><th scope="col" className="num">Exit price</th><th scope="col" className="num">P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => {
            const pnl = t.pnl == null ? null : Number(t.pnl);
            return (
              <tr key={`${t.entryTimestamp}-${i}`}>
                <td data-label="Side">{t.side}</td>
                <td data-label="Entry" className="cell-muted">{displayDate(t.entryTimestamp)}</td>
                <td data-label="Exit" className="cell-muted">{displayDate(t.exitTimestamp)}</td>
                <td data-label="Quantity" className="num">{metric(t.quantity)}</td>
                <td data-label="Entry price" className="num">{metric(t.entryPrice)}</td>
                <td data-label="Exit price" className="num">{metric(t.exitPrice)}</td>
                <td data-label="P&L" className={`num${pnl == null ? "" : pnl > 0 ? " is-profit" : pnl < 0 ? " is-loss" : ""}`}>
                  {pnl == null ? "Unavailable" : `${pnl > 0 ? "+" : ""}${metric(t.pnl)}`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ── Run metadata (provenance) ────────────────────────────────── */

function RunMetadata({ run }: { run: Backtest }) {
  const summary = run.result_summary as Record<string, unknown> | null;
  const provenance = run.market_data_provenance as Record<string, unknown> | null;
  const instrument = run.instrument_snapshot as Record<string, unknown> | null;
  const synthetic = isSynthetic(run);
  return (
    <aside className="research-side" aria-label="Run metadata">
      <section className="panel">
        <div className="panel-head"><h2 className="research-h3">Run timeline</h2></div>
        <div className="panel-body">
          <dl className="kv">
            <dt>Run ID</dt><dd className="mono">{run.id}</dd>
            <dt>Created</dt><dd>{displayDate(run.created_at)}</dd>
            <dt>Started</dt><dd>{displayDate(run.started_at)}</dd>
            <dt>Completed</dt><dd>{displayDate(run.completed_at)}</dd>
            <dt>Requested reference</dt><dd>{run.market_data_reference || "Server-configured provider"}</dd>
          </dl>
        </div>
      </section>
      <section className="panel">
        <div className="panel-head"><h2 className="research-h3">Execution identity</h2></div>
        <div className="panel-body">
          <dl className="kv">
            <dt>Engine</dt><dd>{typeof summary?.engine_identifier === "string" ? summary.engine_identifier : "Not available"}</dd>
            <dt>Provider</dt><dd>{run.market_data_provider || (typeof summary?.provider_identifier === "string" ? summary.provider_identifier : "Not available")}</dd>
          </dl>
        </div>
      </section>
      <details className="panel research-details" open>
        <summary><h2 className="research-h3">Instrument snapshot</h2></summary>
        <div className="panel-body">
          {instrument ? (
            <dl className="kv">
              <dt>Name</dt><dd>{String(instrument.name)}</dd>
              <dt>Symbol</dt><dd>{String(instrument.canonical_symbol)} · {String(instrument.exchange_symbol)}</dd>
              <dt>Exchange</dt><dd>{String(instrument.exchange_code)}</dd>
              <dt>Type / currency</dt><dd>{String(instrument.instrument_type)} · {String(instrument.quote_currency)}</dd>
            </dl>
          ) : (
            <p className="muted">Legacy/unavailable Instrument metadata.</p>
          )}
        </div>
      </details>
      <details className="panel research-details" open>
        <summary><h2 className="research-h3">Market-data provenance</h2></summary>
        <div className="panel-body">
          <dl className="kv">
            <dt>Dataset type</dt><dd>{synthetic ? "Synthetic reference dataset" : "Real historical market dataset"}</dd>
            <dt>Provider</dt><dd>{run.market_data_provider || "Legacy/unavailable"}</dd>
            <dt>Dataset</dt><dd>{run.market_data_dataset_id || run.dataset_reference || "Legacy/unavailable"}</dd>
            <dt>Timeframe</dt><dd>{run.timeframe || "Legacy/unavailable"}</dd>
            <dt>Date range</dt><dd>{run.range_start && run.range_end ? `${displayDate(run.range_start)} — ${displayDate(run.range_end)}` : "Legacy/unavailable"}</dd>
            <dt>Candles</dt><dd>{typeof provenance?.candle_count === "number" ? provenance.candle_count : "Legacy/unavailable"}</dd>
            <dt>Adjustment</dt><dd>{run.adjustment_policy || "Legacy/unavailable"}</dd>
            <dt>Checksum</dt><dd>{typeof provenance?.normalized_checksum === "string" ? `${provenance.normalized_checksum.slice(0, 12)}…` : "Legacy/unavailable"}</dd>
            <dt>Fetched</dt><dd>{displayDate(run.data_fetched_at)}</dd>
          </dl>
        </div>
      </details>
    </aside>
  );
}

/* ── Backtest detail page ─────────────────────────────────────── */

export function BacktestDetailPage() {
  const { strategyId = "", versionId = "", backtestId = "" } = useParams();
  const client = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [executeError, setExecuteError] = useState<string | null>(null);
  const autoRan = useRef(false);

  const key = queryKeys.backtest(strategyId, versionId, backtestId);

  // Strategy/Version context is best-effort: the run must render even if these fail.
  const strategyQuery = useQuery({ queryKey: queryKeys.strategy(strategyId), queryFn: () => strategiesApi.get(strategyId), retry: false });
  const versionQuery = useQuery({ queryKey: queryKeys.version(strategyId, versionId), queryFn: () => strategiesApi.getVersion(strategyId, versionId), retry: false });

  const query = useQuery({
    queryKey: key,
    queryFn: () => strategiesApi.getBacktest(strategyId, versionId, backtestId),
    refetchInterval: (q) => {
      const status = (q.state.data as Backtest | undefined)?.status;
      return status && isActive(status) ? 5000 : false;
    },
  });

  const analytics = useQuery({
    queryKey: queryKeys.backtestAnalytics(strategyId, versionId, backtestId),
    queryFn: () => strategiesApi.getBacktestAnalytics(strategyId, versionId, backtestId),
    enabled: query.data?.status === "completed",
  });

  const execute = useMutation({
    mutationFn: () => strategiesApi.executeBacktest(strategyId, versionId, backtestId),
    onSuccess: async (result) => {
      setExecuteError(null);
      client.setQueryData(key, result);
      await client.invalidateQueries({ queryKey: key });
      await client.invalidateQueries({ queryKey: queryKeys.backtests(strategyId, versionId) });
    },
    onError: (reason) => setExecuteError(errorMessage(reason, "Unable to execute Backtest.")),
  });

  // "Run Backtest" on the Version page hands off here: execute the queued run once, then drop the flag.
  const wantsAutoRun = (location.state as { autoRun?: boolean } | null)?.autoRun === true;
  useEffect(() => {
    if (!wantsAutoRun || autoRan.current || query.data?.status !== "queued") return;
    autoRan.current = true;
    navigate(location.pathname, { replace: true, state: null });
    execute.mutate();
  }, [wantsAutoRun, query.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (query.isLoading) return <LoadingState label="Loading Backtest…" />;
  if (query.isError || !query.data) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return notFound
      ? <ErrorPanel title="Backtest not found.">This run does not exist for the selected Version.</ErrorPanel>
      : <ErrorPanel title="Unable to load backtest data." onRetry={() => void query.refetch()} retrying={query.isFetching}>
          {query.error instanceof ApiError ? query.error.message : "Try again."}
        </ErrorPanel>;
  }

  const run = query.data;
  const strategyName = strategyQuery.data?.name;
  const versionNumber = versionQuery.data?.version_number;
  const synthetic = isSynthetic(run);
  const inst = instrumentOf(run);
  const summary = run.result_summary as Record<string, unknown> | null;
  const engine = typeof summary?.engine_identifier === "string" ? summary.engine_identifier : null;
  const provider = run.market_data_provider || (typeof summary?.provider_identifier === "string" ? summary.provider_identifier : null);
  const resultLoading = run.status === "completed" && analytics.isLoading;

  return (
    <div className="research-page">
      <Link className="back-crumb" to={`/creator/strategies/${strategyId}/versions/${versionId}`}>
        <ArrowLeft size={14} aria-hidden="true" /> {strategyName ?? "Strategy"} · {versionNumber != null ? `Version ${versionNumber}` : "Version"}
      </Link>

      <header className="page-header">
        <div className="page-header-text">
          <p className="eyebrow">{synthetic ? "Synthetic reference dataset" : "Historical market dataset"}</p>
          <div className="title-with-status">
            <h1>{strategyName ?? "Strategy"}{versionNumber != null ? ` · Version ${versionNumber}` : ""}</h1>
            <StatusBadge status={run.status} />
          </div>
          <p className="meta-line"><span>Backtest run <span className="mono">{shortId(run.id)}</span></span><span>{synthetic ? "Deterministic reference infrastructure" : "Persisted historical dataset"} · not live trading</span></p>
        </div>
        {run.status === "queued" && !execute.isPending && (
          <div className="page-header-actions">
            <Button iconLeft={<Play size={14} aria-hidden="true" />} onClick={() => execute.mutate()}>Execute Backtest</Button>
          </div>
        )}
        {execute.isPending && (
          <div className="page-header-actions">
            <Button loading disabled>Executing…</Button>
          </div>
        )}
      </header>

      <ResearchContext
        strategyId={strategyId}
        versionId={versionId}
        strategyName={strategyName}
        versionNumber={versionNumber}
        fields={[
          { label: "Instrument", value: inst?.symbol ?? "Legacy / unresolved" },
          { label: "Timeframe", value: run.timeframe ?? NOT_AVAILABLE },
          { label: "Period", value: periodLabel(run.range_start, run.range_end) ?? NOT_AVAILABLE },
          { label: "Data source", value: provider ?? NOT_AVAILABLE },
          { label: "Engine", value: engine ?? NOT_AVAILABLE },
        ]}
      />

      <RunLifecycle run={run} executing={execute.isPending} resultLoading={resultLoading} />

      {executeError && <Alert variant="error" title="Execution failed">{executeError}</Alert>}

      {run.status === "failed" && (
        <div className="alert alert-error failure-panel" role="alert">
          <div className="alert-body">
            <strong>Backtest failed{run.error_code ? ` (${run.error_code})` : ""}.</strong>{" "}
            {run.error_message || "No error detail was provided."}
            <p className="failure-next"><Link to={`/creator/strategies/${strategyId}/versions/${versionId}`}>Back to configuration</Link> to start a new run.</p>
          </div>
        </div>
      )}

      <div className="research-layout">
        <div className="research-main">
          {run.status === "completed" && (
            analytics.isLoading ? <LoadingState label="Loading analytics…" /> :
            analytics.isError ? (
              <ErrorPanel title="Unable to load backtest data." onRetry={() => void analytics.refetch()} retrying={analytics.isFetching}>
                <span>{errorMessage(analytics.error, "Try again.")}</span>
              </ErrorPanel>
            ) :
            analytics.data ? <Analytics data={analytics.data} run={run} /> : null
          )}
          {run.status !== "completed" && (
            <div className="alert alert-info">
              <div className="alert-body">Analytics become available only after the Backtest completes successfully.</div>
            </div>
          )}
        </div>
        <RunMetadata run={run} />
      </div>
    </div>
  );
}
