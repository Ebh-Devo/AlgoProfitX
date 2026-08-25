import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { investorApi } from "../../api/investor";
import { queryKeys } from "../../api/queryKeys";
import { EmptyState, ErrorAlert, LoadingState } from "../../components/PageState";
import { allocationLabel, formatMoney, shortId, versionLabel } from "./presentation";

const date = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "Not available";
const message = (error: unknown, fallback: string) => (error instanceof ApiError ? error.message : fallback);
const Status = ({ value }: { value: string }) => <span className={`badge badge-${value}`}>{value}</span>;
const Identity = ({ label, id }: { label: string; id: string }) => (
  <>
    {label}
    <small className="identity-meta">ID {shortId(id)}</small>
  </>
);

export function ExecutionIntentListPage() {
  const query = useQuery({
    queryKey: queryKeys.executionIntents,
    queryFn: investorApi.listExecutionIntents,
  });
  if (query.isLoading) return <LoadingState label="Loading execution intents…" />;
  if (query.isError) return <ErrorAlert>{message(query.error, "Unable to load execution intents.")}</ErrorAlert>;
  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Investor workspace</p>
          <h1>Execution Intents</h1>
          <p>Paper-only instructions using synthetic NSE reference data and no funded capital.</p>
        </div>
        <Link className="button button-secondary" to="/investor/allocations">
          Allocations
        </Link>
      </div>
      {!query.data?.length ? (
        <EmptyState>No execution intents yet. Create one from an Allocation.</EmptyState>
      ) : (
        <div className="card run-list">
          {query.data.map((item) => (
            <Link to={`/investor/execution-intents/${item.id}`} key={item.id}>
              <div>
                <strong>{formatMoney(item.notional_amount_snapshot, item.currency_snapshot)}</strong>
                <small>
                  {item.strategy_name} · {versionLabel(item.strategy_version_number)}
                </small>
              </div>
              <div className="inline-actions">
                <Status value={item.mode} />
                <Status value={item.status} />
              </div>
              <span>{date(item.created_at)}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

const text = (value: unknown) => (value === null || value === undefined ? "Not available" : typeof value === "object" ? JSON.stringify(value, null, 2) : String(value));
function ResultBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      {value && typeof value === "object" ? <pre className="json-view">{text(value)}</pre> : <p>{text(value)}</p>}
    </div>
  );
}
function InstrumentDetails({ snapshot }: { snapshot: Record<string, unknown> | null }) {
  if (!snapshot) {
    return <div className="alert alert-info"><strong>Legacy Instrument unresolved.</strong> This historical intent has no canonical Instrument snapshot.</div>;
  }
  const tradeable = snapshot.is_tradeable === true;
  return (
    <div className="card">
      <div className="card-title-row">
        <h2>{text(snapshot.name)}</h2>
        <Status value={tradeable ? "tradeable" : "non-tradeable"} />
      </div>
      <p>{text(snapshot.canonical_symbol)} · {text(snapshot.exchange_code)}:{text(snapshot.exchange_symbol)}</p>
      <dl className="details-list">
        <dt>Instrument type</dt><dd>{text(snapshot.instrument_type)}</dd>
        <dt>Quote currency</dt><dd>{text(snapshot.quote_currency)}</dd>
        <dt>Lot size</dt><dd>{text(snapshot.lot_size)}</dd>
        <dt>Tick size</dt><dd>{text(snapshot.tick_size)}</dd>
        <dt>Execution eligibility</dt><dd>{tradeable ? "Tradeable equity" : "Non-tradeable index/reference Instrument"}</dd>
      </dl>
    </div>
  );
}
function PaperResult({ result }: { result: Record<string, unknown> }) {
  const outcome = text(result.execution_outcome);
  const noFill = outcome === "no_fill" || outcome === "no_signal";
  const notional = typeof result.notional_amount === "string" && typeof result.quote_currency === "string" ? formatMoney(result.notional_amount, result.quote_currency) : text(result.notional_amount);
  return (
    <section>
      <div className={`alert ${noFill ? "alert-info" : "alert-success"}`}>
        {noFill ? (
          <>
            <strong>Completed without a fill.</strong> This is a normal paper outcome: {text(result.no_fill_reason ?? result.execution_outcome)}.
          </>
        ) : (
          <>
            <strong>Paper execution completed.</strong> Any fill shown is synthetic and not a broker fill.
          </>
        )}
      </div>
      <div className="badge-row">
        <Status value="paper" />
        <Status value="synthetic" />
      </div>
      <div className="card">
        <h2>Paper result</h2>
        <dl className="details-list">
          <dt>Canonical symbol</dt>
          <dd>{text(result.canonical_symbol ?? result.symbol)}</dd>
          <dt>Exchange symbol</dt>
          <dd>{text(result.exchange_symbol ?? result.symbol)}</dd>
          <dt>Exchange</dt>
          <dd>{text(result.exchange ?? result.exchange_code ?? result.market)}</dd>
          <dt>Instrument type</dt>
          <dd>{text(result.instrument_type)}</dd>
          <dt>Quote currency</dt>
          <dd>{text(result.quote_currency)}</dd>
          <dt>Exchange timezone</dt>
          <dd>{text(result.exchange_timezone)}</dd>
          <dt>Lot size</dt>
          <dd>{text(result.lot_size)}</dd>
          <dt>Tick size</dt>
          <dd>{text(result.tick_size)}</dd>
          <dt>Tradeability</dt>
          <dd>{result.is_tradeable === false ? "Non-tradeable" : result.is_tradeable === true ? "Tradeable" : "Legacy result — not recorded"}</dd>
          <dt>Provider</dt>
          <dd>{text(result.provider_identifier)}</dd>
          <dt>Signal</dt>
          <dd>{text(result.signal)}</dd>
          <dt>Outcome</dt>
          <dd>{outcome}</dd>
          <dt>No-fill reason</dt>
          <dd>{text(result.no_fill_reason)}</dd>
          <dt>Notional amount</dt>
          <dd>{notional}</dd>
        </dl>
      </div>
      <div className="result-grid">
        <ResultBlock title="Order" value={result.order} />
        <ResultBlock title="Fill" value={result.fill} />
        <ResultBlock title="Position" value={result.position} />
      </div>
    </section>
  );
}

export function ExecutionIntentDetailPage() {
  const { executionIntentId = "" } = useParams();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const key = queryKeys.executionIntent(executionIntentId);
  const query = useQuery({
    queryKey: key,
    queryFn: () => investorApi.getExecutionIntent(executionIntentId),
  });
  const execute = useMutation({
    mutationFn: () => investorApi.executeIntent(executionIntentId),
    onSuccess: async (result) => {
      setError(null);
      client.setQueryData(key, result);
      await client.invalidateQueries({ queryKey: key });
      await client.invalidateQueries({ queryKey: queryKeys.executionIntents });
    },
    onError: (reason) => setError(message(reason, "Unable to execute paper intent.")),
  });
  if (query.isLoading) return <LoadingState label="Loading execution intent…" />;
  if (query.isError || !query.data) return <ErrorAlert>{query.error instanceof ApiError && query.error.status === 404 ? "Execution intent not found." : "Unable to load execution intent."}</ErrorAlert>;
  const intent = query.data;
  const allocation = allocationLabel(intent.notional_amount_snapshot, intent.currency_snapshot, intent.strategy_name, intent.strategy_version_number);
  return (
    <section>
      <Link to="/investor/execution-intents">← Execution Intents</Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Synthetic paper execution</p>
          <div className="card-title-row">
            <h1>Execution Intent</h1>
            <Status value={intent.status} />
          </div>
          <div className="badge-row">
            <Status value={intent.mode} />
            <Status value="synthetic" />
          </div>
        </div>
        {intent.status === "pending" && (
          <button className="button" disabled={execute.isPending} onClick={() => execute.mutate()}>
            {execute.isPending ? "Executing…" : "Execute Paper Intent"}
          </button>
        )}
      </div>
      <div className="alert alert-info">
        <strong>Synthetic NSE reference data only.</strong> This is not real NSE market data, live broker execution, or funded capital.
      </div>
      {error && <ErrorAlert>{error}</ErrorAlert>}
      <div className="detail-grid">
        <div className="card">
          <h2>Snapshots</h2>
          <dl className="details-list">
            <dt>Amount</dt>
            <dd>{formatMoney(intent.notional_amount_snapshot, intent.currency_snapshot)}</dd>
            <dt>Strategy</dt>
            <dd>
              <Identity label={intent.strategy_name} id={intent.strategy_id} />
            </dd>
            <dt>Strategy Version</dt>
            <dd>
              <Identity label={versionLabel(intent.strategy_version_number)} id={intent.strategy_version_id} />
            </dd>
            <dt>Allocation</dt>
            <dd>
              <Link to={`/investor/allocations/${intent.allocation_intent_id}`}>{allocation}</Link>
              <small className="identity-meta">ID {shortId(intent.allocation_intent_id)}</small>
            </dd>
          </dl>
        </div>
        <div className="card">
          <h2>Timeline</h2>
          <dl className="details-list">
            <dt>Created</dt>
            <dd>{date(intent.created_at)}</dd>
            <dt>Started</dt>
            <dd>{date(intent.started_at)}</dd>
            <dt>Completed</dt>
            <dd>{date(intent.completed_at)}</dd>
          </dl>
        </div>
      </div>
      <InstrumentDetails snapshot={intent.instrument_snapshot} />
      {intent.status === "failed" && (
        <div className="alert alert-error">
          <strong>{intent.error_code || "Paper execution failed"}.</strong> {intent.error_message || "No error detail was provided."}
        </div>
      )}
      {intent.status === "completed" && intent.paper_result_summary && <PaperResult result={intent.paper_result_summary} />}
      {intent.status === "running" && <div className="alert alert-info">Paper execution is currently running.</div>}
      {intent.status === "pending" && <div className="alert alert-info">This intent is pending and has not produced a paper result.</div>}
    </section>
  );
}
