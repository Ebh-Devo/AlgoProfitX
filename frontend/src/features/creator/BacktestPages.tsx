import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { strategiesApi } from "../../api/strategies";
import type { Backtest, BacktestAnalytics } from "../../api/types";
import { EmptyState, ErrorAlert, LoadingState } from "../../components/PageState";

const displayDate = (value?: string | null) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not available";
const errorMessage = (error: unknown, fallback: string) => error instanceof ApiError ? error.message : fallback;
const metric = (value: string | null, suffix = "") => value === null ? "Unavailable" : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 })}${suffix}`;
const ratioPercent = (value: string | null) => value === null ? "Unavailable" : `${(Number(value) * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
const Status = ({ value }: { value: string }) => <span className={`badge badge-${value}`} aria-label={`Status: ${value}`}>{value}</span>;

const isActive = (status: string) => status === "queued" || status === "running";

export function VersionBacktests({ strategyId, versionId }: { strategyId: string; versionId: string }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["backtests", strategyId, versionId],
    queryFn: () => strategiesApi.listBacktests(strategyId, versionId),
    refetchInterval: (q) => {
      const data = q.state.data as Backtest[] | undefined;
      return data?.some((b) => isActive(b.status)) ? 5000 : false;
    },
  });

  const create = useMutation({
    mutationFn: () => strategiesApi.createBacktest(strategyId, versionId, { market_data_reference: reference || null }),
    onSuccess: async (result) => {
      setOpen(false);
      setReference("");
      setError(null);
      await client.invalidateQueries({ queryKey: ["backtests", strategyId, versionId] });
      navigate(`/creator/strategies/${strategyId}/versions/${versionId}/backtests/${result.id}`);
    },
    onError: (reason) => setError(errorMessage(reason, "Unable to create Backtest.")),
  });

  const submit = (event: FormEvent) => { event.preventDefault(); create.mutate(); };

  return (
    <section className="backtests-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Synthetic reference runs</p>
          <h2>Backtests</h2>
          <p>Reference backtesting only. These are not live trades or realized Investor performance.</p>
        </div>
        {!open && <button className="button" onClick={() => setOpen(true)}>Create Backtest</button>}
      </div>
      {open && (
        <form className="card form-stack backtest-form" onSubmit={submit}>
          <h3>Create queued Backtest</h3>
          <label>
            Market data reference
            <span className="field-help">Optional identifier for the reference dataset.</span>
            <input maxLength={500} value={reference} onChange={(event) => setReference(event.target.value)} />
          </label>
          {error && <ErrorAlert>{error}</ErrorAlert>}
          <div className="inline-actions">
            <button className="button" disabled={create.isPending}>Create Backtest</button>
            <button type="button" className="button button-secondary" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      )}
      {query.isLoading ? (
        <LoadingState label="Loading Backtests…" />
      ) : query.isError ? (
        <ErrorAlert>{errorMessage(query.error, "Unable to load Backtests.")}</ErrorAlert>
      ) : !query.data?.length ? (
        <EmptyState>No Backtests have been requested for this Version.</EmptyState>
      ) : (
        <div className="card run-list">
          {query.data.map((run) => (
            <Link key={run.id} to={`/creator/strategies/${strategyId}/versions/${versionId}/backtests/${run.id}`}>
              <div><strong>Backtest</strong><small>{run.market_data_reference || run.id}</small></div>
              <Status value={run.status} />
              <span>{displayDate(run.created_at)}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

function Analytics({ data }: { data: BacktestAnalytics }) {
  const points = data.equity_curve.map((point) => ({ ...point, value: Number(point.equity) }));
  const metrics = [["Initial capital", metric(data.initial_capital)], ["Final equity", metric(data.final_equity)], ["Total return", metric(data.total_return, "%")], ["Trade count", String(data.trade_count)], ["Win rate", ratioPercent(data.win_rate)], ["Profit factor", metric(data.profit_factor)], ["Average win", metric(data.average_win)], ["Average loss", metric(data.average_loss)], ["Max drawdown", metric(data.max_drawdown, "%")]];
  return (
    <section aria-labelledby="analytics-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Completed synthetic run</p>
          <h2 id="analytics-heading">Backtest analytics</h2>
          <p>Historical synthetic/reference output only; it is not live or realized Investor performance.</p>
        </div>
      </div>
      <div className="metric-grid">
        {metrics.map(([label, value]) => <div className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>
      <div className="card chart-card">
        <h3>Equity curve</h3>
        {points.length ? (
          <div className="equity-chart" data-testid="equity-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 10, right: 16, bottom: 10, left: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="timestamp" hide />
                <YAxis dataKey="value" stroke="var(--muted)" domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
                <Line type="monotone" dataKey="value" name="Equity" stroke="var(--accent-hover)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyState>No equity points are available.</EmptyState>
        )}
      </div>
      {points.length > 0 && (
        <details className="card equity-details">
          <summary>Equity point detail</summary>
          <div className="strategy-table-wrap">
            <table className="strategy-table">
              <thead><tr><th>Timestamp</th><th>Equity</th></tr></thead>
              <tbody>{data.equity_curve.map((point) => <tr key={`${point.timestamp}-${point.equity}`}><td>{point.timestamp}</td><td>{metric(point.equity)}</td></tr>)}</tbody>
            </table>
          </div>
        </details>
      )}
      <div className="card">
        <dl className="details-list">
          <dt>Engine</dt><dd>{data.engine_identifier}</dd>
          <dt>Provider</dt><dd>{data.provider_identifier}</dd>
        </dl>
      </div>
    </section>
  );
}

export function BacktestDetailPage() {
  const { strategyId = "", versionId = "", backtestId = "" } = useParams();
  const client = useQueryClient();
  const [executeError, setExecuteError] = useState<string | null>(null);

  const key = ["backtest", strategyId, versionId, backtestId];

  const query = useQuery({
    queryKey: key,
    queryFn: () => strategiesApi.getBacktest(strategyId, versionId, backtestId),
    refetchInterval: (q) => {
      const status = (q.state.data as Backtest | undefined)?.status;
      return status && isActive(status) ? 5000 : false;
    },
  });

  const analytics = useQuery({
    queryKey: ["backtest-analytics", strategyId, versionId, backtestId],
    queryFn: () => strategiesApi.getBacktestAnalytics(strategyId, versionId, backtestId),
    enabled: query.data?.status === "completed",
  });

  const execute = useMutation({
    mutationFn: () => strategiesApi.executeBacktest(strategyId, versionId, backtestId),
    onSuccess: async (result) => {
      setExecuteError(null);
      client.setQueryData(key, result);
      await client.invalidateQueries({ queryKey: key });
      await client.invalidateQueries({ queryKey: ["backtests", strategyId, versionId] });
    },
    onError: (reason) => setExecuteError(errorMessage(reason, "Unable to execute Backtest.")),
  });

  if (query.isLoading) return <LoadingState label="Loading Backtest…" />;
  if (query.isError || !query.data) return <ErrorAlert>{query.error instanceof ApiError && query.error.status === 404 ? "Backtest not found." : "Unable to load this Backtest."}</ErrorAlert>;

  const run = query.data;
  const summary = run.result_summary as Record<string, unknown> | null;
  const instrument = run.instrument_snapshot as Record<string, unknown> | null;
  const provenance = run.market_data_provenance as Record<string, unknown> | null;
  const synthetic = provenance?.synthetic === true;

  return (
    <section>
      <Link to={`/creator/strategies/${strategyId}/versions/${versionId}`}>← Strategy Version</Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{synthetic ? "Synthetic reference dataset" : "Historical market dataset"}</p>
          <div className="card-title-row">
            <h1>Backtest detail</h1>
            <Status value={run.status} />
          </div>
          <p>{synthetic ? "This execution uses deterministic reference infrastructure." : "This execution uses a persisted historical dataset."} It is not live trading.</p>
        </div>
        {run.status === "queued" && (
          <button className="button" disabled={execute.isPending} onClick={() => execute.mutate()}>
            {execute.isPending ? "Executing…" : "Execute Backtest"}
          </button>
        )}
      </div>

      {run.status === "queued" && (
        <div className="alert alert-info" role="status">
          <strong>Backtest queued.</strong> This Backtest is waiting to be executed. Click Execute Backtest to begin.
        </div>
      )}
      {run.status === "running" && (
        <div className="alert alert-info" role="status" aria-live="polite">
          <strong>Backtest running.</strong> The engine is processing this run. This page will update automatically.
        </div>
      )}

      {executeError && <ErrorAlert>{executeError}</ErrorAlert>}

      <div className="detail-grid">
        <div className="card">
          <h2>Run timeline</h2>
          <dl className="details-list">
            <dt>Created</dt><dd>{displayDate(run.created_at)}</dd>
            <dt>Started</dt><dd>{displayDate(run.started_at)}</dd>
            <dt>Completed</dt><dd>{displayDate(run.completed_at)}</dd>
            <dt>Requested reference</dt><dd>{run.market_data_reference || "Server-configured provider"}</dd>
          </dl>
        </div>
        <div className="card">
          <h2>Execution identity</h2>
          <dl className="details-list">
            <dt>Engine</dt><dd>{typeof summary?.engine_identifier === "string" ? summary.engine_identifier : "Not available"}</dd>
            <dt>Provider</dt><dd>{run.market_data_provider || (typeof summary?.provider_identifier === "string" ? summary.provider_identifier : "Not available")}</dd>
          </dl>
        </div>
        <div className="card">
          <h2>Instrument snapshot</h2>
          {instrument ? (
            <dl className="details-list">
              <dt>Name</dt><dd>{String(instrument.name)}</dd>
              <dt>Symbol</dt><dd>{String(instrument.canonical_symbol)} · {String(instrument.exchange_symbol)}</dd>
              <dt>Exchange</dt><dd>{String(instrument.exchange_code)}</dd>
              <dt>Type / currency</dt><dd>{String(instrument.instrument_type)} · {String(instrument.quote_currency)}</dd>
            </dl>
          ) : (
            <p className="muted">Legacy/unavailable Instrument metadata.</p>
          )}
        </div>
        <div className="card">
          <h2>Market-data provenance</h2>
          <dl className="details-list">
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
      </div>

      {run.status === "failed" && (
        <div className="alert alert-error" role="alert">
          <strong>Backtest failed{run.error_code ? ` (${run.error_code})` : ""}.</strong>{" "}
          {run.error_message || "No error detail was provided."}
        </div>
      )}

      {run.status === "completed" && (
        analytics.isLoading ? <LoadingState label="Loading analytics…" /> :
        analytics.isError ? <ErrorAlert>{errorMessage(analytics.error, "Unable to load Backtest analytics.")}</ErrorAlert> :
        analytics.data ? <Analytics data={analytics.data} /> : null
      )}

      {run.status !== "completed" && (
        <div className="alert alert-info">Analytics become available only after the Backtest completes successfully.</div>
      )}
    </section>
  );
}
