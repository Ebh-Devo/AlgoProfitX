/**
 * Strategy Definition V2 — form state, document builder and plain-language reader.
 *
 * What the runtime can run is decided by the backend (`GET /strategies/definition-vocabulary`) and
 * enforced by `POST /strategies/definitions/validate`. This module holds only (a) the shape of the guided
 * form, (b) the translation of that form into the V2 JSON document, and (c) presentation labels. It never
 * decides capability: every list of choices passed in comes from the vocabulary response.
 */
import type { ApiDefinitionIssue } from "../../../api/client";
import type { DefinitionVocabulary, VocabularyIndicator } from "../../../api/types";
import { parseCapital } from "../strategyConfig";

export const SCHEMA_ID = "algoprofitx.strategy-definition";
export const SCHEMA_VERSION = 2;
/** Condition nesting the guided builder allows (the backend bound is higher; this keeps the form readable). */
export const MAX_CONDITION_DEPTH = 3;
const POSITION_ID = "main";
const LEG_ID = "leg-1";

/* ── Form model ───────────────────────────────────────────────── */

export type OperandForm =
  | { kind: "price"; field: string }
  | { kind: "constant"; value: string }
  | { kind: "indicator"; key: string; params: Record<string, string>; source: string; output: string };

export type ConditionForm = { uid: string } & (
  | { kind: "compare"; op: string; left: OperandForm; right: OperandForm }
  | { kind: "cross"; dir: string; left: OperandForm; right: OperandForm }
  | { kind: "all" | "any"; of: ConditionForm[] }
  | { kind: "not"; of: ConditionForm }
  | { kind: "edge"; dir: string; of: ConditionForm }
);

export interface RuleForm { uid: string; when: ConditionForm; operation: string }

export interface V2Form {
  /** Opening direction of the single leg: a vocabulary leg side ("buy" = long, "sell" = short). */
  legSide: string;
  shares: string;
  rules: RuleForm[];
  capital: string;
  timeframe: string;
  evaluation: string;
  fillModel: string;
}

let counter = 0;
export const uid = () => `n${++counter}`;

/* ── Presentation labels (copy only — availability always comes from the vocabulary) ── */

const titleCase = (value: string) => value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, " ");
const labelled = (labels: Record<string, string>) => (value: string) => labels[value] ?? titleCase(value);

export const conditionKindLabel = labelled({
  compare: "Compare two values", cross: "Crosses", all: "All of these are true", any: "Any of these is true",
  not: "This is not true", edge: "Becomes true",
});
export const compareOpLabel = labelled({ gt: "is greater than", gte: "is at least", lt: "is less than", lte: "is at most" });
export const crossDirLabel = labelled({ above: "crosses above", below: "crosses below" });
export const edgeDirLabel = labelled({ rising: "becomes true (was false on the previous bar)" });
export const operandKindLabel = labelled({ price: "Price", constant: "Number", indicator: "Indicator" });
export const priceFieldLabel = labelled({ open: "Open", high: "High", low: "Low", close: "Close", volume: "Volume" });
export const operationLabel = labelled({ open: "Open a position", close: "Close the position" });
export const legSideLabel = labelled({ buy: "Long (buy to open)", sell: "Short (sell to open)" });
export const timeframeLabel = labelled({ "1d": "Daily (1d)" });
export const evaluationLabel = labelled({ bar_close: "At the bar close" });
export const fillModelLabel = labelled({ same_bar_close: "Filled at the signal bar's close price" });

/** Operations the guided builder knows how to author (the rest need an amount, which V2.0 does not offer). */
const AUTHORABLE_OPERATIONS = ["open", "close"];
const AUTHORABLE_CONDITIONS = ["compare", "cross", "all", "any", "not", "edge"];

export const authorableOperations = (vocab: DefinitionVocabulary) => vocab.operations.filter((op) => AUTHORABLE_OPERATIONS.includes(op));
export const authorableConditions = (vocab: DefinitionVocabulary) => vocab.condition_kinds.filter((kind) => AUTHORABLE_CONDITIONS.includes(kind));

/* ── Defaults (seeded from the vocabulary so nothing unsupported is ever pre-selected) ── */

export function indicatorOf(vocab: DefinitionVocabulary, key: string): VocabularyIndicator | undefined {
  return vocab.indicators.find((item) => item.key === key);
}

export function defaultIndicatorOperand(vocab: DefinitionVocabulary, indicator: VocabularyIndicator, period?: number): OperandForm {
  const params: Record<string, string> = {};
  for (const param of indicator.params) {
    params[param.name] = param.name === "period" && period != null ? String(period) : String(param.minimum ?? 1);
  }
  return {
    kind: "indicator", key: indicator.key, params,
    source: vocab.indicator_source_fields.includes("close") ? "close" : vocab.indicator_source_fields[0] ?? "close",
    output: indicator.outputs[0] ?? "value",
  };
}

export function defaultOperand(vocab: DefinitionVocabulary, kind: string, period?: number): OperandForm {
  if (kind === "indicator" && vocab.indicators[0]) return defaultIndicatorOperand(vocab, vocab.indicators[0], period);
  if (kind === "constant") return { kind: "constant", value: "0" };
  return { kind: "price", field: vocab.price_fields.includes("close") ? "close" : vocab.price_fields[0] ?? "close" };
}

function defaultPair(vocab: DefinitionVocabulary) {
  const kind = vocab.operand_kinds.includes("indicator") && vocab.indicators.length ? "indicator" : "price";
  return {
    left: kind === "indicator" ? defaultOperand(vocab, "indicator", 9) : defaultOperand(vocab, "price"),
    right: kind === "indicator" ? defaultOperand(vocab, "indicator", 21) : defaultOperand(vocab, "constant"),
  };
}

export function defaultCondition(vocab: DefinitionVocabulary, kind: string, direction?: string): ConditionForm {
  const { left, right } = defaultPair(vocab);
  const leaf = () => defaultCondition(vocab, vocab.condition_kinds.includes("compare") ? "compare" : "cross");
  switch (kind) {
    case "compare":
      return { uid: uid(), kind, op: vocab.compare_operators[0] ?? "gt", left: defaultOperand(vocab, "price"), right: defaultOperand(vocab, "constant") };
    case "cross":
      return { uid: uid(), kind, dir: direction && vocab.cross_directions.includes(direction) ? direction : vocab.cross_directions[0] ?? "above", left, right };
    case "all": case "any":
      return { uid: uid(), kind, of: [leaf(), leaf()] };
    case "not":
      return { uid: uid(), kind, of: leaf() };
    default:
      return { uid: uid(), kind: "edge", dir: vocab.edge_directions[0] ?? "rising", of: leaf() };
  }
}

/**
 * The starter entry/exit pair for a direction: a long opens on a bullish cross and closes on a bearish one;
 * a short is the mirror image. They are examples for the user to review, and are swapped automatically only
 * while the user has not edited them.
 */
export function defaultRules(vocab: DefinitionVocabulary, legSide: string): RuleForm[] {
  const kinds = authorableConditions(vocab);
  const operations = authorableOperations(vocab);
  const kind = kinds.includes("cross") ? "cross" : kinds[0] ?? "compare";
  const entry = operations.includes("open") ? "open" : operations[0] ?? "open";
  const exit = operations.includes("close") ? "close" : entry;
  const [openDir, closeDir] = legSide === "sell" ? ["below", "above"] : ["above", "below"];
  return [
    { uid: uid(), when: defaultCondition(vocab, kind, openDir), operation: entry },
    { uid: uid(), when: defaultCondition(vocab, kind, closeDir), operation: exit },
  ];
}

const withoutUids = (value: unknown) => JSON.stringify(value, (key, v) => (key === "uid" ? undefined : v));

/** True while the rules are still exactly the untouched starter pair for `legSide`. */
export const rulesAreStarterDefaults = (vocab: DefinitionVocabulary, legSide: string, rules: RuleForm[]) =>
  withoutUids(rules) === withoutUids(defaultRules(vocab, legSide));

export function defaultForm(vocab: DefinitionVocabulary): V2Form {
  const legSide = vocab.position.leg_sides.includes("buy") ? "buy" : vocab.position.leg_sides[0] ?? "buy";
  return {
    legSide,
    shares: "10",
    rules: defaultRules(vocab, legSide),
    capital: "50000",
    timeframe: vocab.timeframes[0] ?? "1d",
    evaluation: vocab.evaluation_modes[0] ?? "bar_close",
    fillModel: vocab.fill_models[0] ?? "same_bar_close",
  };
}

/** Rules the user can add: one more of the first authorable operation not yet covered, else a copy of the default. */
export const newRule = (vocab: DefinitionVocabulary, operation?: string): RuleForm => ({
  uid: uid(),
  when: defaultCondition(vocab, authorableConditions(vocab).includes("cross") ? "cross" : "compare"),
  operation: operation ?? authorableOperations(vocab)[0] ?? "open",
});

/* ── Form → document ──────────────────────────────────────────── */

const NUMBER = /^-?\d+(\.\d+)?$/;
const POSITIVE_NUMBER = /^\d+(\.\d+)?$/;

/** A JSON number when the text is an integer; otherwise the plain decimal string the backend also accepts. */
const numeric = (text: string): number | string => (/^-?\d+$/.test(text.trim()) ? Number(text.trim()) : text.trim());

export interface BuildProblem { message: string }
export type BuildResult =
  | { ok: true; configuration: Record<string, unknown>; backtestConfiguration: Record<string, unknown> }
  | { ok: false; problems: BuildProblem[] };

function buildOperand(vocab: DefinitionVocabulary, operand: OperandForm, timeframe: string, where: string, problems: BuildProblem[]): Record<string, unknown> {
  if (operand.kind === "price") return { kind: "price", field: operand.field };
  if (operand.kind === "constant") {
    if (!NUMBER.test(operand.value.trim())) problems.push({ message: `${where}: enter a number.` });
    return { kind: "constant", value: numeric(operand.value) };
  }
  const indicator = indicatorOf(vocab, operand.key);
  const params: Record<string, unknown> = {};
  for (const param of indicator?.params ?? []) {
    const text = (operand.params[param.name] ?? "").trim();
    if (!NUMBER.test(text)) {
      if (text || param.required) problems.push({ message: `${where}: enter a number for ${param.name}.` });
      continue;
    }
    params[param.name] = Number(text);
  }
  return {
    kind: "indicator", name: indicator?.name ?? operand.key, version: indicator?.version ?? 1, params,
    source: { kind: "price", field: operand.source }, timeframe, output: operand.output,
  };
}

function buildCondition(vocab: DefinitionVocabulary, node: ConditionForm, timeframe: string, where: string, problems: BuildProblem[]): Record<string, unknown> {
  switch (node.kind) {
    case "compare":
      return { kind: "compare", op: node.op, left: buildOperand(vocab, node.left, timeframe, `${where} (left side)`, problems), right: buildOperand(vocab, node.right, timeframe, `${where} (right side)`, problems) };
    case "cross":
      return { kind: "cross", dir: node.dir, left: buildOperand(vocab, node.left, timeframe, `${where} (left side)`, problems), right: buildOperand(vocab, node.right, timeframe, `${where} (right side)`, problems) };
    case "all": case "any":
      return { kind: node.kind, of: node.of.map((child, i) => buildCondition(vocab, child, timeframe, `${where}, condition ${i + 1}`, problems)) };
    case "not":
      return { kind: "not", of: buildCondition(vocab, node.of, timeframe, where, problems) };
    default:
      return { kind: "edge", dir: node.dir, of: buildCondition(vocab, node.of, timeframe, where, problems) };
  }
}

/**
 * Builds the explicit V2 document and its environment. Only formatting problems that make a JSON value
 * impossible (blank/non-numeric fields) are caught here; every semantic question is the backend's to answer.
 */
export function buildV2Request(vocab: DefinitionVocabulary, form: V2Form): BuildResult {
  const problems: BuildProblem[] = [];
  if (!POSITIVE_NUMBER.test(form.shares.trim()) || Number(form.shares) <= 0) problems.push({ message: "Position size: enter the number of shares, greater than zero." });
  const capital = parseCapital(form.capital);
  if (capital == null) problems.push({ message: "Starting capital: enter an amount greater than zero." });
  if (!form.rules.length) problems.push({ message: "Add at least one rule." });

  const instrumentKind = vocab.position.instrument_kinds[0] ?? "primary";
  const rules = form.rules.map((rule, index) => ({
    id: `rule-${index + 1}`,
    when: buildCondition(vocab, rule.when, form.timeframe, `Rule ${index + 1}`, problems),
    then: [{ op: rule.operation, position: POSITION_ID }],
  }));

  if (problems.length) return { ok: false, problems };
  return {
    ok: true,
    configuration: {
      schema: SCHEMA_ID,
      schema_version: SCHEMA_VERSION,
      timeframe: form.timeframe,
      evaluation: form.evaluation,
      positions: {
        [POSITION_ID]: {
          role: "core",
          hedges: null,
          legs: [{ id: LEG_ID, instrument: { kind: instrumentKind }, side: form.legSide, quantity: 1 }],
          sizing: { unit: vocab.position.sizing_units[0] ?? "shares", value: numeric(form.shares) },
        },
      },
      rules,
    },
    backtestConfiguration: { initial_capital: capital, timeframe: form.timeframe, fill_model: form.fillModel },
  };
}

/* ── Stored document → plain language ─────────────────────────── */

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const OP_PHRASE: Record<string, string> = { gt: "is greater than", gte: "is at least", lt: "is less than", lte: "is at most", eq: "equals" };

function describeOperand(value: unknown): string | null {
  const node = asRecord(value);
  if (!node) return null;
  if (node.kind === "price" && typeof node.field === "string") return `the ${node.field} price`;
  if (node.kind === "constant" && (typeof node.value === "number" || typeof node.value === "string")) return String(node.value);
  if (node.kind === "indicator" && typeof node.name === "string") {
    const params = asRecord(node.params) ?? {};
    const args = Object.values(params).map(String).join(", ");
    const source = asRecord(node.source);
    const of = source && source.kind === "price" && source.field !== "close" ? ` of ${String(source.field)}` : "";
    const output = typeof node.output === "string" && node.output !== "value" ? ` (${node.output})` : "";
    return `${node.name.toUpperCase()}(${args})${of}${output}`;
  }
  return null;
}

/** Plain-language description of a stored condition tree, or null when any part is not recognised. */
export function describeCondition(value: unknown, depth = 0): string | null {
  const node = asRecord(value);
  if (!node || depth > 16) return null;
  switch (node.kind) {
    case "compare": {
      const left = describeOperand(node.left);
      const right = describeOperand(node.right);
      return left && right && typeof node.op === "string" ? `${left} ${OP_PHRASE[node.op] ?? node.op} ${right}` : null;
    }
    case "cross": {
      const left = describeOperand(node.left);
      const right = describeOperand(node.right);
      return left && right && (node.dir === "above" || node.dir === "below") ? `${left} crosses ${node.dir} ${right}` : null;
    }
    case "all": case "any": {
      if (!Array.isArray(node.of)) return null;
      const parts = node.of.map((child) => describeCondition(child, depth + 1));
      return parts.every((part): part is string => part != null)
        ? `${node.kind === "all" ? "all of" : "any of"}: ${parts.map((part) => `(${part})`).join(node.kind === "all" ? " and " : " or ")}`
        : null;
    }
    case "not": {
      const inner = describeCondition(node.of, depth + 1);
      return inner ? `it is not the case that ${inner}` : null;
    }
    case "edge": {
      const inner = describeCondition(node.of, depth + 1);
      return inner && node.dir === "rising" ? `${inner} (newly true on this bar)` : null;
    }
    default:
      return null;
  }
}

export interface DefinitionSummary {
  timeframe: string | null;
  evaluation: string | null;
  position: string | null;
  rules: { id: string; text: string }[];
}

/** Reads a stored V2 document into sentences. Returns null (never a guess) if it does not match the V2 grammar. */
export function summarizeDefinition(configuration: unknown): DefinitionSummary | null {
  const doc = asRecord(configuration);
  const positions = asRecord(doc?.positions);
  if (!doc || !positions || !Array.isArray(doc.rules)) return null;
  const sides: Record<string, string> = {};
  let position: string | null = null;
  for (const [id, raw] of Object.entries(positions)) {
    const pos = asRecord(raw);
    const leg = asRecord(Array.isArray(pos?.legs) ? pos.legs[0] : null);
    const sizing = asRecord(pos?.sizing);
    if (!pos || !leg) return null;
    const direction = leg.side === "sell" ? "short" : leg.side === "buy" ? "long" : null;
    if (!direction) return null;
    sides[id] = direction;
    const size = sizing && sizing.unit === "shares" && sizing.value != null ? `${String(sizing.value)} ${Number(sizing.value) === 1 ? "share" : "shares"}` : null;
    position = `One ${direction} position${size ? ` of ${size}` : ""} in the selected instrument.`;
  }
  const rules: DefinitionSummary["rules"] = [];
  for (const raw of doc.rules) {
    const rule = asRecord(raw);
    const when = describeCondition(rule?.when);
    const then = Array.isArray(rule?.then) ? rule.then.map((item) => asRecord(item)) : [];
    if (!rule || !when || typeof rule.id !== "string" || !then.length) return null;
    const actions: string[] = [];
    for (const operation of then) {
      const direction = typeof operation?.position === "string" ? sides[operation.position] : undefined;
      if (operation?.op === "open" && direction) actions.push(`open a ${direction} position`);
      else if (operation?.op === "close" && direction) actions.push(`close the ${direction} position`);
      else return null;
    }
    rules.push({ id: rule.id, text: `When ${when}, ${actions.join(" and ")}.` });
  }
  return {
    timeframe: typeof doc.timeframe === "string" ? doc.timeframe : null,
    evaluation: typeof doc.evaluation === "string" ? doc.evaluation : null,
    position,
    rules,
  };
}

/** One-sentence live preview of a rule while editing. Mirrors `summarizeDefinition` on the built document. */
export function previewRule(vocab: DefinitionVocabulary, form: V2Form, rule: RuleForm): string {
  const problems: BuildProblem[] = [];
  const when = describeCondition(buildCondition(vocab, rule.when, form.timeframe, "", problems));
  const direction = form.legSide === "sell" ? "short" : "long";
  const action = rule.operation === "close" ? `close the ${direction} position` : `open a ${direction} position`;
  return when ? `When ${when}, ${action}.` : "Complete the highlighted fields to see this rule in words.";
}

/* ── Validation issues → sections ─────────────────────────────── */

export interface IssueGroup { section: string; issues: ApiDefinitionIssue[] }

export function issueSection(issue: ApiDefinitionIssue): string {
  const { path } = issue;
  const rule = /^rules\[(\d+)\]/.exec(path);
  if (rule) return `Rule ${Number(rule[1]) + 1}`;
  if (path.startsWith("positions")) return "Position configuration";
  if (path === "timeframe" || path.startsWith("evaluation") || path.startsWith("backtest_configuration") || issue.layer === "environment") return "Execution environment";
  if (issue.layer === "capability") return "Supported capabilities";
  return "Strategy definition";
}

export function groupIssues(issues: ApiDefinitionIssue[]): IssueGroup[] {
  const groups = new Map<string, ApiDefinitionIssue[]>();
  for (const issue of issues) groups.set(issueSection(issue), [...(groups.get(issueSection(issue)) ?? []), issue]);
  return [...groups].map(([section, items]) => ({ section, issues: items }));
}

/** The request the verdict belongs to; any edit changes it, which invalidates a previous verdict. */
export const requestFingerprint = (instrumentId: string, configuration: unknown, backtestConfiguration: unknown) =>
  JSON.stringify([instrumentId, configuration, backtestConfiguration]);
