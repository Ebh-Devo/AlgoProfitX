import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Plus, Trash2 } from "lucide-react";
import { ApiError } from "../../../api/client";
import { instrumentsApi } from "../../../api/instruments";
import { queryKeys } from "../../../api/queryKeys";
import { strategiesApi } from "../../../api/strategies";
import type { DefinitionValidation, DefinitionVocabulary } from "../../../api/types";
import { ErrorPanel } from "../../../components/PageState";
import { Alert, Button, ConfirmDialog, SectionHeader, Skeleton, SkeletonGroup, useToast } from "../../../components/ui";
import { formatCurrency } from "../../../lib/format";
import { parseCapital } from "../strategyConfig";
import {
  MAX_CONDITION_DEPTH, authorableConditions, authorableOperations, buildV2Request, compareOpLabel, conditionKindLabel, crossDirLabel,
  defaultCondition, defaultForm, defaultIndicatorOperand, defaultOperand, edgeDirLabel, evaluationLabel, fillModelLabel, indicatorOf,
  legSideLabel, newRule, operandKindLabel, operationLabel, previewRule, priceFieldLabel, requestFingerprint, timeframeLabel,
  type ConditionForm, type OperandForm, type V2Form,
} from "./definition";
import { BacktestOnlyNotice, IssueList, ValidationReport, schemaVersionLabel } from "./V2Views";

const errorText = (error: unknown, fallback: string) => (error instanceof ApiError ? error.message : fallback);

/* ── Small form helpers ───────────────────────────────────────── */

/** A label wrapping its control, with the editing context appended for screen readers. */
function Field({ label, context, children, hint, className = "" }: { label: string; context?: string; children: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={`v2-field ${className}`}>
      <label className="v2-field-control">
        <span className="v2-field-label">{label}{context && <span className="visually-hidden"> ({context})</span>}</span>
        {children}
      </label>
      {hint}
    </div>
  );
}

function Select({ value, options, onChange, label, context, render }: {
  value: string; options: string[]; onChange: (value: string) => void; label: string; context?: string; render?: (value: string) => string;
}) {
  // A stored value the vocabulary no longer offers stays visible instead of silently switching.
  const all = options.includes(value) ? options : [value, ...options];
  return (
    <Field label={label} context={context}>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {all.map((option) => <option key={option} value={option}>{render ? render(option) : option}</option>)}
      </select>
    </Field>
  );
}

/* ── Operand ──────────────────────────────────────────────────── */

function OperandEditor({ vocab, value, onChange, context }: { vocab: DefinitionVocabulary; value: OperandForm; onChange: (next: OperandForm) => void; context: string }) {
  const kinds = vocab.operand_kinds.filter((kind) => kind !== "indicator" || vocab.indicators.length > 0);
  const indicator = value.kind === "indicator" ? indicatorOf(vocab, value.key) : undefined;
  return (
    <div className="v2-operand" role="group" aria-label={context}>
      <Select label="Value type" context={context} value={value.kind} options={kinds} render={operandKindLabel}
        onChange={(kind) => onChange(defaultOperand(vocab, kind))} />
      {value.kind === "price" && (
        <Select label="Price" context={context} value={value.field} options={vocab.price_fields} render={priceFieldLabel}
          onChange={(field) => onChange({ kind: "price", field })} />
      )}
      {value.kind === "constant" && (
        <Field label="Number" context={context}>
          <input className="input" type="text" inputMode="decimal" value={value.value} onChange={(e) => onChange({ kind: "constant", value: e.target.value })} />
        </Field>
      )}
      {value.kind === "indicator" && (
        <>
          <Select label="Indicator" context={context} value={value.key} options={vocab.indicators.map((item) => item.key)}
            render={(key) => { const item = indicatorOf(vocab, key); return item ? `${item.name.toUpperCase()} (version ${item.version})` : key; }}
            onChange={(key) => { const next = indicatorOf(vocab, key); if (next) onChange(defaultIndicatorOperand(vocab, next)); }} />
          {indicator?.params.map((param) => (
            <Field key={param.name} label={`${param.name.charAt(0).toUpperCase()}${param.name.slice(1)}${param.minimum != null && param.maximum != null ? ` (${param.minimum}–${param.maximum})` : ""}`} context={context}>
              <input className="input" type="text" inputMode="numeric" value={value.params[param.name] ?? ""}
                onChange={(e) => onChange({ ...value, params: { ...value.params, [param.name]: e.target.value } })} />
            </Field>
          ))}
          <Select label="Calculated on" context={context} value={value.source} options={vocab.indicator_source_fields} render={priceFieldLabel}
            onChange={(source) => onChange({ ...value, source })} />
          {indicator && indicator.outputs.length > 1 && (
            <Select label="Output" context={context} value={value.output} options={indicator.outputs} onChange={(output) => onChange({ ...value, output })} />
          )}
        </>
      )}
    </div>
  );
}

/* ── Condition (recursive) ────────────────────────────────────── */

const NESTING_KINDS = ["all", "any", "not", "edge"];

function ConditionEditor({ vocab, node, onChange, context, depth = 0 }: {
  vocab: DefinitionVocabulary; node: ConditionForm; onChange: (next: ConditionForm) => void; context: string; depth?: number;
}) {
  const kinds = authorableConditions(vocab).filter((kind) => depth < MAX_CONDITION_DEPTH || !NESTING_KINDS.includes(kind));
  const leaf = () => defaultCondition(vocab, vocab.condition_kinds.includes("compare") ? "compare" : "cross");
  return (
    <div className={`v2-condition${depth ? " is-nested" : ""}`} role="group" aria-label={context}>
      <Select label="Condition" context={context} value={node.kind} options={kinds} render={conditionKindLabel}
        onChange={(kind) => onChange(kind === node.kind ? node : defaultCondition(vocab, kind))} />

      {(node.kind === "compare" || node.kind === "cross") && (
        <div className="v2-pair">
          <OperandEditor vocab={vocab} value={node.left} context={`${context}, first value`} onChange={(left) => onChange({ ...node, left })} />
          {node.kind === "compare" ? (
            <Select label="Comparison" context={context} value={node.op} options={vocab.compare_operators} render={compareOpLabel} onChange={(op) => onChange({ ...node, op })} />
          ) : (
            <Select label="Direction" context={context} value={node.dir} options={vocab.cross_directions} render={crossDirLabel} onChange={(dir) => onChange({ ...node, dir })} />
          )}
          <OperandEditor vocab={vocab} value={node.right} context={`${context}, second value`} onChange={(right) => onChange({ ...node, right })} />
        </div>
      )}

      {(node.kind === "all" || node.kind === "any") && (
        <div className="v2-children">
          {node.of.map((child, index) => (
            <div key={child.uid} className="v2-child">
              <ConditionEditor vocab={vocab} node={child} depth={depth + 1} context={`${context}, condition ${index + 1}`}
                onChange={(next) => onChange({ ...node, of: node.of.map((item) => (item.uid === child.uid ? next : item)) })} />
              <Button type="button" variant="ghost" size="sm" iconLeft={<Trash2 size={13} aria-hidden="true" />}
                aria-label={`Remove ${context}, condition ${index + 1}`} onClick={() => onChange({ ...node, of: node.of.filter((item) => item.uid !== child.uid) })}>
                Remove
              </Button>
            </div>
          ))}
          <Button type="button" variant="secondary" size="sm" iconLeft={<Plus size={13} aria-hidden="true" />}
            aria-label={`Add a condition to ${context}`} onClick={() => onChange({ ...node, of: [...node.of, leaf()] })}>
            Add condition
          </Button>
        </div>
      )}

      {node.kind === "not" && (
        <div className="v2-children">
          <ConditionEditor vocab={vocab} node={node.of} depth={depth + 1} context={`${context}, negated condition`} onChange={(of) => onChange({ ...node, of })} />
        </div>
      )}

      {node.kind === "edge" && (
        <div className="v2-children">
          <Select label="Trigger when it" context={context} value={node.dir} options={vocab.edge_directions} render={edgeDirLabel} onChange={(dir) => onChange({ ...node, dir })} />
          <ConditionEditor vocab={vocab} node={node.of} depth={depth + 1} context={`${context}, watched condition`} onChange={(of) => onChange({ ...node, of })} />
        </div>
      )}
    </div>
  );
}

/* ── Instrument picker ────────────────────────────────────────── */

function InstrumentPicker({ value, onChange, error }: { value: string; onChange: (id: string) => void; error: string | null }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(timer);
  }, [search]);
  const instruments = useQuery({ queryKey: queryKeys.instruments(debounced), queryFn: () => instrumentsApi.list(debounced) });
  const selected = instruments.data?.find((item) => item.id === value);
  return (
    <div className="form-section-body">
      <div className="form-field">
        <label className="form-label" htmlFor="v2-instrument-search">Search instrument</label>
        <input id="v2-instrument-search" className="input" type="search" placeholder="Search name or symbol" value={search} autoComplete="off" onChange={(e) => setSearch(e.target.value)} />
      </div>
      {instruments.isLoading ? (
        <SkeletonGroup label="Loading instruments…"><Skeleton height="2.5rem" /></SkeletonGroup>
      ) : instruments.isError ? (
        <ErrorPanel title="Couldn't load instruments" onRetry={() => void instruments.refetch()}>{errorText(instruments.error, "Unable to load instruments.")}</ErrorPanel>
      ) : (
        <div className={`form-field ${error ? "has-error" : ""}`}>
          <label className="form-label" htmlFor="v2-instrument-select">Instrument</label>
          <select id="v2-instrument-select" className="input" aria-required="true" aria-invalid={error ? true : undefined} aria-describedby={error ? "v2-instrument-error" : undefined}
            value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="">Select an instrument</option>
            {instruments.data?.map((item) => (
              <option key={item.id} value={item.id}>{item.name} · {item.exchange_symbol} · {item.exchange.code} · {item.instrument_type} · {item.quote_currency}</option>
            ))}
          </select>
          {error && <p className="field-error" role="alert" id="v2-instrument-error">{error}</p>}
        </div>
      )}
      {selected && <p className="field-hint">Selected: {selected.name} · {selected.canonical_symbol}</p>}
    </div>
  );
}

/* ── Save failure copy ────────────────────────────────────────── */

function saveFailureTitle(error: ApiError): string {
  if (error.code === "invalid_strategy_definition") return "The server rejected this definition as invalid. Nothing was saved.";
  if (error.code === "strategy_definition_not_runnable") return "The server says this definition cannot run in the current environment. Nothing was saved.";
  if (error.status === 404) return "The strategy could not be found. Nothing was saved.";
  if (error.status === 409) return "Another Version was created at the same time. Nothing was saved. Review the Versions and try again.";
  if (error.status === 401 || error.status === 403) return "You are not allowed to save a Version here. Nothing was saved.";
  return "The Version could not be saved. Nothing was saved.";
}

/* ── The V2 Version creator ───────────────────────────────────── */

export function V2VersionCreator({ strategyId, onClose }: { strategyId: string; onClose: () => void }) {
  const vocabulary = useQuery({ queryKey: queryKeys.definitionVocabulary, queryFn: () => strategiesApi.getDefinitionVocabulary() });
  return (
    <section className="panel" aria-label="Create Strategy V2 Version">
      <div className="panel-head">
        <SectionHeader title="Create Strategy V2 Version" description="Build rules from the choices below. We check them with the server before anything is saved." />
      </div>
      {vocabulary.isLoading ? (
        <div className="panel-body"><SkeletonGroup label="Loading the Strategy V2 vocabulary…"><Skeleton height="2.5rem" /><Skeleton height="2.5rem" /></SkeletonGroup></div>
      ) : vocabulary.isError || !vocabulary.data ? (
        <div className="panel-body">
          <ErrorPanel title="Couldn't load what Strategy V2 can do" onRetry={() => void vocabulary.refetch()} retrying={vocabulary.isFetching}>
            {errorText(vocabulary.error, "The Strategy V2 vocabulary is unavailable.")} Strategy V2 cannot be built until this loads, so no options are shown. You can still use Strategy V1.
          </ErrorPanel>
          <div className="panel-foot"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button></div>
        </div>
      ) : (
        <V2FormBody strategyId={strategyId} vocab={vocabulary.data} onClose={onClose} />
      )}
    </section>
  );
}

function V2FormBody({ strategyId, vocab, onClose }: { strategyId: string; vocab: DefinitionVocabulary; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const initial = useMemo(() => defaultForm(vocab), [vocab]);
  const [form, setForm] = useState<V2Form>(initial);
  const [instrumentId, setInstrumentId] = useState("");
  const [instrumentError, setInstrumentError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [verdict, setVerdict] = useState<{ fingerprint: string; result: DefinitionValidation } | null>(null);
  const [validateError, setValidateError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<ApiError | Error | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const saving = useRef(false);

  const built = useMemo(() => buildV2Request(vocab, form), [vocab, form]);
  const fingerprint = built.ok ? requestFingerprint(instrumentId, built.configuration, built.backtestConfiguration) : null;
  const dirty = instrumentId !== "" || JSON.stringify(form, (key, value) => (key === "uid" ? undefined : value)) !== JSON.stringify(initial, (key, value) => (key === "uid" ? undefined : value));

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const update = (patch: Partial<V2Form>) => setForm((current) => ({ ...current, ...patch }));

  const validate = useMutation({
    mutationFn: () => {
      if (!built.ok) throw new Error("unbuildable");
      return strategiesApi.validateDefinition({ definition_schema_version: 2, configuration: built.configuration, backtest_configuration: built.backtestConfiguration });
    },
    onSuccess: (result) => { setValidateError(null); setVerdict({ fingerprint: fingerprint ?? "", result }); },
    onError: (reason) => { setVerdict(null); setValidateError(errorText(reason, "Validation could not be completed. Your entries are kept: try again.")); },
  });

  const save = useMutation({
    mutationFn: () => {
      if (!built.ok) throw new Error("unbuildable");
      return strategiesApi.createVersionV2(strategyId, {
        definition_schema_version: 2, instrument_id: instrumentId, configuration: built.configuration, backtest_configuration: built.backtestConfiguration,
      });
    },
    onSuccess: async (version) => {
      toast.success(`Version ${version.version_number} saved (${schemaVersionLabel(version.definition_schema_version)})`, "It is immutable. You can now backtest it.");
      onClose();
      await client.invalidateQueries({ queryKey: queryKeys.versions(strategyId) });
      navigate(`/creator/strategies/${strategyId}/versions/${version.id}`);
    },
    onError: (reason) => { setSaveError(reason instanceof Error ? reason : new Error("Unable to save the Version.")); },
    onSettled: () => { saving.current = false; },
  });

  const checkInputs = (): boolean => {
    setInstrumentError(instrumentId ? null : "Select an instrument before validating.");
    setProblems(built.ok ? [] : built.problems.map((problem) => problem.message));
    return instrumentId !== "" && built.ok;
  };

  const onValidate = () => {
    setSaveError(null);
    if (checkInputs()) validate.mutate();
  };

  const current = verdict && verdict.fingerprint === fingerprint ? verdict.result : null;
  const stale = verdict != null && current == null;
  const canSave = current?.runnable === true && !validate.isPending && !save.isPending;
  const busy = validate.isPending || save.isPending;

  const onSave = () => {
    if (saving.current || !canSave) return;
    saving.current = true;
    setSaveError(null);
    save.mutate();
  };

  const rules = form.rules;
  const operations = authorableOperations(vocab);
  const limitations = [
    vocab.position.max_core_positions === 1 ? "one position at a time" : null,
    vocab.position.max_legs_per_position === 1 ? "one leg per position" : null,
  ].filter(Boolean);

  return (
    <form className="v2-form" aria-label="Create Strategy V2 Version" noValidate onSubmit={(event) => { event.preventDefault(); onValidate(); }}>
      <fieldset className="form-section">
        <legend className="visually-hidden">Instrument</legend>
        <div className="form-section-head"><span className="form-section-num" aria-hidden="true">1</span><div><h3>Instrument</h3><p>The market this Version trades.</p></div></div>
        <InstrumentPicker value={instrumentId} onChange={(id) => { setInstrumentId(id); setInstrumentError(null); }} error={instrumentError} />
      </fieldset>

      <fieldset className="form-section">
        <legend className="visually-hidden">Position</legend>
        <div className="form-section-head">
          <span className="form-section-num" aria-hidden="true">2</span>
          <div><h3>Position</h3><p>How much to trade{limitations.length ? `. The current runtime supports ${limitations.join(" and ")}` : ""}.</p></div>
        </div>
        <div className="form-section-body v2-row">
          <Select label="Direction" value={form.legSide} options={vocab.position.leg_sides} render={legSideLabel} onChange={(legSide) => update({ legSide })} />
          <Field label="Number of shares" hint={<span className="field-hint" id="v2-shares-hint">Explicit share count for every open. There is no hidden default.</span>}>
            <input className="input" type="text" inputMode="decimal" value={form.shares} onChange={(e) => update({ shares: e.target.value })} aria-describedby="v2-shares-hint" />
          </Field>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend className="visually-hidden">Rules</legend>
        <div className="form-section-head"><span className="form-section-num" aria-hidden="true">3</span><div><h3>Rules</h3><p>Each rule says: when this happens, do that. Rules are checked in order on every bar.</p></div></div>
        <div className="form-section-body">
          {rules.map((rule, index) => {
            const context = `Rule ${index + 1}`;
            return (
              <div key={rule.uid} className="v2-rule" role="group" aria-label={context}>
                <div className="v2-rule-head">
                  <h4>{context}</h4>
                  <Button type="button" variant="ghost" size="sm" iconLeft={<Trash2 size={13} aria-hidden="true" />} aria-label={`Remove ${context}`}
                    onClick={() => update({ rules: rules.filter((item) => item.uid !== rule.uid) })}>Remove rule</Button>
                </div>
                <p className="v2-sentence" aria-live="polite"><span className="visually-hidden">Plain-language rule: </span>{previewRule(vocab, form, rule)}</p>
                <h5 className="v2-sub">When</h5>
                <ConditionEditor vocab={vocab} node={rule.when} context={`${context} condition`} onChange={(when) => update({ rules: rules.map((item) => (item.uid === rule.uid ? { ...item, when } : item)) })} />
                <h5 className="v2-sub">Then</h5>
                <Select label="Action" context={context} value={rule.operation} options={operations} render={operationLabel}
                  onChange={(operation) => update({ rules: rules.map((item) => (item.uid === rule.uid ? { ...item, operation } : item)) })} />
              </div>
            );
          })}
          <Button type="button" variant="secondary" size="sm" iconLeft={<Plus size={14} aria-hidden="true" />}
            onClick={() => update({ rules: [...rules, newRule(vocab, operations.includes("close") && rules.some((r) => r.operation === "open") ? "close" : undefined)] })}>
            Add rule
          </Button>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend className="visually-hidden">Backtest settings</legend>
        <div className="form-section-head"><span className="form-section-num" aria-hidden="true">4</span><div><h3>Backtest settings</h3><p>How the simulation runs.</p></div></div>
        <div className="form-section-body v2-row">
          <Field label="Starting capital (₹)" hint={<span className="field-hint" id="v2-capital-hint">A simulation parameter. It is not money deposited with a broker.{parseCapital(form.capital) != null && ` Currently ${formatCurrency(parseCapital(form.capital), { currency: "INR" })}.`}</span>}>
            <input className="input" type="text" inputMode="decimal" value={form.capital} onChange={(e) => update({ capital: e.target.value })} aria-describedby="v2-capital-hint" />
          </Field>
          <Select label="Timeframe" value={form.timeframe} options={vocab.timeframes} render={timeframeLabel} onChange={(timeframe) => update({ timeframe })} />
          <Select label="Rules are checked" value={form.evaluation} options={vocab.evaluation_modes} render={evaluationLabel} onChange={(evaluation) => update({ evaluation })} />
          <Select label="Fill model" value={form.fillModel} options={vocab.fill_models} render={fillModelLabel} onChange={(fillModel) => update({ fillModel })} />
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend className="visually-hidden">Validate and save</legend>
        <div className="form-section-head"><span className="form-section-num" aria-hidden="true">5</span><div><h3>Validate and save</h3><p>Validation checks your rules with the server and saves nothing.</p></div></div>
        <div className="form-section-body">
          <BacktestOnlyNotice />
          {problems.length > 0 && (
            <Alert variant="error" title="Complete these fields first">
              <ul>{problems.map((message) => <li key={message}>{message}</li>)}</ul>
            </Alert>
          )}
          {validateError && <Alert variant="error" title="Validation could not be completed">{validateError}</Alert>}
          {stale && <Alert variant="info">You changed the strategy after validating. Validate again to enable saving.</Alert>}
          {current && <ValidationReport result={current} />}
          {saveError && (
            <Alert variant="error" title={saveError instanceof ApiError ? saveFailureTitle(saveError) : "The Version could not be saved. Nothing was saved."}>
              {saveError instanceof ApiError && saveError.issues.length > 0 ? <IssueList issues={saveError.issues} /> : saveError instanceof ApiError ? saveError.message : "Check your connection and try again. Your entries are kept."}
            </Alert>
          )}
        </div>
      </fieldset>

      <div className="panel-foot">
        <Button type="submit" variant="secondary" loading={validate.isPending} disabled={busy} iconLeft={<CheckCircle2 size={14} aria-hidden="true" />}>
          {validate.isPending ? "Validating…" : "Validate"}
        </Button>
        <Button type="button" loading={save.isPending} disabled={!canSave} onClick={onSave}>{save.isPending ? "Saving…" : "Save Version"}</Button>
        <Button type="button" variant="ghost" disabled={save.isPending} onClick={() => (dirty ? setConfirmDiscard(true) : onClose())}>Cancel</Button>
      </div>

      <ConfirmDialog open={confirmDiscard} title="Discard this draft?" confirmLabel="Discard draft" onCancel={() => setConfirmDiscard(false)} onConfirm={onClose}>
        <p>Your Strategy V2 draft has not been saved. Discarding it cannot be undone.</p>
      </ConfirmDialog>
    </form>
  );
}
