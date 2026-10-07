/**
 * Translates between the human-friendly strategy form and the structured configuration the API stores.
 * Stored shape: { entry: { type, action, direction, fast_period, slow_period }, exit?: { same fields } } and
 * { initial_capital }. `action` is the order side (buy/sell), NOT a synonym for long/short: the entry action
 * decides which side the position takes. `exit` is optional, and `action`/`direction` are optional on read so
 * versions saved before they existed stay valid (entry = buy on a cross above, exit = sell on a cross below).
 *
 * V1 is intentionally limited to one EMA-crossover entry and one optional EMA-crossover exit on a single
 * position. A future strategy-definition model (multi-leg strategies such as straddles and strangles, hedging,
 * partial exits, RSI/VWAP/Bollinger, AND/OR conditions) will replace this; do not extend it in that direction.
 */

export const EMA_CROSSOVER = "ema_crossover";
export const STRATEGY_TYPE_LABEL = "EMA Crossover";

export type RuleAction = "buy" | "sell";
export type CrossDirection = "above" | "below";
export const ACTIONS: readonly RuleAction[] = ["buy", "sell"];
export const DIRECTIONS: readonly CrossDirection[] = ["above", "below"];
export const ACTION_LABEL: Record<RuleAction, string> = { buy: "Buy", sell: "Sell" };

export interface EmaRuleInput { action: RuleAction; direction: CrossDirection; shortTerm: string; longTerm: string }
export interface EmaRuleErrors { shortTerm?: string; longTerm?: string }

export const DEFAULT_EMA_RULE: EmaRuleInput = { action: "buy", direction: "above", shortTerm: "3", longTerm: "9" };
export const DEFAULT_EXIT_RULE: EmaRuleInput = { action: "sell", direction: "below", shortTerm: "3", longTerm: "9" };

/** The usual crossover for an action: buy into strength, sell into weakness. */
export const usualDirection = (action: RuleAction): CrossDirection => (action === "buy" ? "above" : "below");

/** V1 holds a single position, so the exit must be on the opposite side of the entry. */
export function validateExitAction(entry: EmaRuleInput, exit: EmaRuleInput): string | null {
  return entry.action === exit.action
    ? `The exit must be the opposite of the entry: after you ${ACTION_LABEL[entry.action].toLowerCase()}, exit by choosing ${ACTION_LABEL[entry.action === "buy" ? "sell" : "buy"]}.`
    : null;
}
export const DEFAULT_CAPITAL = "50000";

const WHOLE = /^\d+$/;

/** Plain-language validation; the backend remains the authority on the same rules. */
export function validateEmaRule({ shortTerm, longTerm }: Pick<EmaRuleInput, "shortTerm" | "longTerm">): EmaRuleErrors {
  const errors: EmaRuleErrors = {};
  const s = shortTerm.trim();
  const l = longTerm.trim();
  if (!WHOLE.test(s) || Number(s) <= 0) errors.shortTerm = "Enter the short-term EMA as a whole number of days, 1 or more.";
  if (!WHOLE.test(l) || Number(l) <= 0) errors.longTerm = "Enter the long-term EMA as a whole number of days, 1 or more.";
  if (!errors.shortTerm && !errors.longTerm && Number(s) >= Number(l))
    errors.shortTerm = "Short-term EMA must be smaller than long-term EMA.";
  return errors;
}

export function buildConfiguration(entry: EmaRuleInput, exit?: EmaRuleInput): Record<string, unknown> {
  const rule = ({ action, direction, shortTerm, longTerm }: EmaRuleInput) => ({
    type: EMA_CROSSOVER, action, direction, fast_period: Number(shortTerm.trim()), slow_period: Number(longTerm.trim()),
  });
  const configuration: Record<string, unknown> = { entry: rule(entry) };
  if (exit) configuration.exit = rule(exit);
  return configuration;
}

/** Accepts "50,000" or "1,25,000.50"; returns null when it isn't a positive number. */
export function parseCapital(raw: string): number | null {
  const cleaned = raw.replace(/[,\s₹]/g, "");
  if (!/^\d*\.?\d+$|^\d+\.$/.test(cleaned)) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export const validateCapital = (raw: string): string | null =>
  parseCapital(raw) == null ? "Enter a starting capital greater than zero, for example 50,000." : null;

export function buildBacktestConfiguration(capital: string): Record<string, unknown> {
  return { initial_capital: parseCapital(capital) };
}

export interface EmaRule { action: RuleAction; direction: CrossDirection; fast: number; slow: number }

function readRule(rule: unknown, defaults: { action: RuleAction; direction: CrossDirection }): EmaRule | null {
  if (!rule || typeof rule !== "object") return null;
  const r = rule as Record<string, unknown>;
  if (r.type !== EMA_CROSSOVER) return null;
  const action = r.action ?? defaults.action;
  const direction = r.direction ?? defaults.direction;
  if (!ACTIONS.includes(action as RuleAction) || !DIRECTIONS.includes(direction as CrossDirection)) return null;
  const fast = Number(r.fast_period);
  const slow = Number(r.slow_period);
  return Number.isInteger(fast) && Number.isInteger(slow) && fast > 0 && slow > 0
    ? { action: action as RuleAction, direction: direction as CrossDirection, fast, slow }
    : null;
}

/** Reads a stored entry rule; null when it isn't an EMA crossover we can describe. Legacy: buy on a cross above. */
export const readEmaRule = (configuration: unknown): EmaRule | null =>
  readRule((configuration as { entry?: unknown } | null)?.entry, { action: "buy", direction: "above" });

/** Reads a stored exit rule; null when absent (older versions). Legacy: sell on a cross below. */
export const readExitRule = (configuration: unknown): EmaRule | null =>
  readRule((configuration as { exit?: unknown } | null)?.exit, { action: "sell", direction: "below" });

const describeRule = ({ action, direction, fast, slow }: EmaRule) =>
  `${ACTION_LABEL[action]} when the ${fast}-day EMA crosses ${direction} the ${slow}-day EMA.`;

export const describeEntry = describeRule;
export const describeExit = describeRule;

export function readInitialCapital(backtestConfiguration: unknown): string | null {
  const v = (backtestConfiguration as { initial_capital?: unknown } | null)?.initial_capital;
  return typeof v === "number" || typeof v === "string" ? String(v) : null;
}
