import { AlertCircle, CheckCircle2, MinusCircle, TriangleAlert } from "lucide-react";
import type { ApiDefinitionIssue } from "../../../api/client";
import type { DefinitionValidation } from "../../../api/types";
import { Alert } from "../../../components/ui";
import { formatCurrency } from "../../../lib/format";
import { configValue } from "../backtestFormat";
import { evaluationLabel, fillModelLabel, groupIssues, summarizeDefinition, timeframeLabel } from "./definition";

/* ── Version identity ─────────────────────────────────────────── */

/** "Strategy V1" / "Strategy V2", always from the persisted `definition_schema_version`, never from the JSON. */
export const schemaVersionLabel = (schemaVersion: number | null | undefined) => `Strategy V${schemaVersion ?? 1}`;

export function DefinitionVersionBadge({ schemaVersion }: { schemaVersion: number | null | undefined }) {
  return <span className={`badge ${schemaVersion === 2 ? "badge-accent" : "badge-muted"}`}>{schemaVersionLabel(schemaVersion)}</span>;
}

/** True for any persisted version the current execution adapter cannot paper/live trade (everything but V1). */
export const isBacktestOnly = (schemaVersion: number | null | undefined) => schemaVersion != null && schemaVersion !== 1;

export const V2_EXECUTION_NOTICE =
  "Strategy V2 versions can be backtested only. Publishing, deploying and paper allocation are not available for V2 because the current execution adapter does not support it.";

export function BacktestOnlyNotice() {
  return <Alert variant="info" title="Backtest only">{V2_EXECUTION_NOTICE}</Alert>;
}

/* ── Stored V2 definition, in words ───────────────────────────── */

export function V2DefinitionSummary({ configuration }: { configuration: unknown }) {
  const summary = summarizeDefinition(configuration);
  if (!summary) {
    return <p className="hint-line">This Strategy V2 definition could not be summarised in plain language. See the technical details below.</p>;
  }
  return (
    <div className="v2-summary">
      <dl className="kv">
        <dt>Definition</dt>
        <dd>{schemaVersionLabel(2)} · rule-based</dd>
        <dt>Timeframe</dt>
        <dd>{summary.timeframe ? timeframeLabel(summary.timeframe) : "Not recorded"}</dd>
        <dt>Rules are checked</dt>
        <dd>{summary.evaluation ? evaluationLabel(summary.evaluation) : "Not recorded"}</dd>
        <dt>Position</dt>
        <dd>{summary.position ?? "Not recorded"}</dd>
      </dl>
      <ol className="v2-rule-list" aria-label="Strategy rules">
        {summary.rules.map((rule, index) => (
          <li key={rule.id}><span className="v2-rule-num">Rule {index + 1}</span> {rule.text}</li>
        ))}
      </ol>
    </div>
  );
}

export function V2EnvironmentSummary({ backtestConfiguration, currency }: { backtestConfiguration: unknown; currency?: string }) {
  const capital = configValue(backtestConfiguration, "initial_capital");
  const timeframe = configValue(backtestConfiguration, "timeframe");
  const fill = configValue(backtestConfiguration, "fill_model");
  return (
    <dl className="kv">
      <dt>Starting capital</dt>
      <dd>{formatCurrency(capital, { currency })} <span className="muted">(simulation parameter, not a deposit)</span></dd>
      <dt>Timeframe</dt>
      <dd>{timeframe ? timeframeLabel(timeframe) : "Not recorded"}</dd>
      <dt>Fill model</dt>
      <dd>{fill ? fillModelLabel(fill) : "Not recorded"}</dd>
    </dl>
  );
}

/* ── Validation results ───────────────────────────────────────── */

export function IssueList({ issues }: { issues: ApiDefinitionIssue[] }) {
  const groups = groupIssues(issues);
  return (
    <div className="v2-issues">
      {groups.map((group) => (
        <section key={group.section} aria-label={group.section} className="v2-issue-group">
          <h4>{group.section}</h4>
          <ul>
            {[...group.issues].sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "error" ? -1 : 1)).map((issue, index) => (
              <li key={`${issue.path}-${issue.code}-${index}`} className={`v2-issue is-${issue.severity}`}>
                <span className={`badge ${issue.severity === "error" ? "badge-danger" : "badge-warning"}`}>
                  {issue.severity === "error" ? <AlertCircle size={12} aria-hidden="true" /> : <TriangleAlert size={12} aria-hidden="true" />}
                  {issue.severity === "error" ? "Error" : "Warning"}
                </span>
                <span className="v2-issue-text">
                  {issue.message}
                  <span className="v2-issue-meta"> <code>{issue.code}</code>{issue.path ? <> at <code>{issue.path}</code></> : null}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Verdict({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className={`v2-verdict ${ok ? "is-yes" : "is-no"}`}>
      {ok ? <CheckCircle2 size={15} aria-hidden="true" /> : <MinusCircle size={15} aria-hidden="true" />}
      <span>{label}</span>
      <strong>{ok ? "Yes" : "No"}</strong>
    </li>
  );
}

/** The backend's verdict, verbatim: valid / savable / runnable, every issue, and capability gaps. */
export function ValidationReport({ result }: { result: DefinitionValidation }) {
  const errors = result.issues.filter((issue) => issue.severity === "error").length;
  const warnings = result.issues.length - errors;
  return (
    <div className="v2-report" aria-label="Validation result">
      {result.runnable ? (
        <Alert variant="success" title="Runnable in the current environment">
          This definition can be saved as a Version and backtested{warnings ? `. ${warnings} warning${warnings === 1 ? "" : "s"} below.` : "."}
        </Alert>
      ) : result.savable ? (
        <Alert variant="warning" title="Well-formed, but not runnable yet">
          The structure is valid, but the current runtime cannot execute it, so it cannot be saved as a Version.
        </Alert>
      ) : (
        <Alert variant="error" title="This definition has problems to fix">
          {errors} error{errors === 1 ? "" : "s"} must be fixed before it can be saved. Your entries are kept.
        </Alert>
      )}
      <ul className="v2-verdicts" aria-label="Verdict">
        <Verdict ok={result.valid} label="Valid definition" />
        <Verdict ok={result.savable} label="Can be saved" />
        <Verdict ok={result.runnable} label="Runnable in the current environment" />
      </ul>
      {result.unsupported_capabilities.length > 0 && (
        <div className="v2-capabilities" role="group" aria-label="Unsupported capabilities">
          <h4>Not available in the current runtime</h4>
          <p>This strategy needs capabilities that backtesting does not provide yet:</p>
          <ul>{result.unsupported_capabilities.map((name) => <li key={name}><code>{name}</code></li>)}</ul>
        </div>
      )}
      {result.issues.length > 0 && <IssueList issues={result.issues} />}
      {result.required_capabilities.length > 0 && (
        <details className="technical-details">
          <summary>Capabilities this strategy uses</summary>
          <ul className="v2-capability-list">{result.required_capabilities.map((name) => <li key={name}><code>{name}</code></li>)}</ul>
        </details>
      )}
    </div>
  );
}
