import { formatCurrency } from "../../lib/format";
import { STRATEGY_TYPE_LABEL, describeEntry, readEmaRule, readInitialCapital } from "./strategyConfig";

/** Read-only, plain-language view of a stored algorithm configuration. Unknown shapes fall back to a neutral note. */
export function AlgorithmSummary({ configuration }: { configuration: unknown }) {
  const rule = readEmaRule(configuration);
  if (!rule) {
    return <p className="hint-line">This Version uses a custom algorithm that has no plain-language summary. See the technical details below.</p>;
  }
  return (
    <dl className="kv">
      <dt>Strategy type</dt>
      <dd>{STRATEGY_TYPE_LABEL}</dd>
      <dt>Entry rule</dt>
      <dd>{describeEntry(rule)}</dd>
      <dt>Short-term EMA</dt>
      <dd>{rule.fast} days</dd>
      <dt>Long-term EMA</dt>
      <dd>{rule.slow} days</dd>
    </dl>
  );
}

export function StartingCapitalSummary({ backtestConfiguration, currency }: { backtestConfiguration: unknown; currency?: string }) {
  const capital = readInitialCapital(backtestConfiguration);
  return (
    <dl className="kv">
      <dt>Starting Capital</dt>
      <dd>{formatCurrency(capital, { currency })}</dd>
    </dl>
  );
}

/** Raw stored data, collapsed by default and never needed for normal use. */
export function TechnicalDetails({ value }: { value: unknown }) {
  return (
    <details className="technical-details">
      <summary>Advanced / Technical details</summary>
      <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
