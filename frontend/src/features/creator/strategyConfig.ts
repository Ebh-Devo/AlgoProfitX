/**
 * Translates between the human-friendly strategy form and the structured configuration the API stores.
 * Stored shape: { entry: { type, fast_period, slow_period }, exit?: { type, direction: "below", fast_period, slow_period } }
 * and { initial_capital }. `exit` is optional so versions saved before exit rules existed stay valid.
 */

export const EMA_CROSSOVER = "ema_crossover";
export const STRATEGY_TYPE_LABEL = "EMA Crossover";

export interface EmaRuleInput { shortTerm: string; longTerm: string }
export interface EmaRuleErrors { shortTerm?: string; longTerm?: string }

export const DEFAULT_EMA_RULE: EmaRuleInput = { shortTerm: "3", longTerm: "9" };
export const DEFAULT_EXIT_RULE: EmaRuleInput = { shortTerm: "3", longTerm: "9" };
export const DEFAULT_CAPITAL = "50000";

const WHOLE = /^\d+$/;

/** Plain-language validation; the backend remains the authority on the same rules. */
export function validateEmaRule({ shortTerm, longTerm }: EmaRuleInput): EmaRuleErrors {
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
  const periods = ({ shortTerm, longTerm }: EmaRuleInput) => ({ fast_period: Number(shortTerm.trim()), slow_period: Number(longTerm.trim()) });
  const configuration: Record<string, unknown> = { entry: { type: EMA_CROSSOVER, ...periods(entry) } };
  if (exit) configuration.exit = { type: EMA_CROSSOVER, direction: "below", ...periods(exit) };
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

export interface EmaRule { fast: number; slow: number }

/** Reads a stored configuration; null when it isn't an EMA crossover entry rule we can describe. */
export function readEmaRule(configuration: unknown): EmaRule | null {
  const entry = (configuration as { entry?: Record<string, unknown> } | null)?.entry;
  if (!entry || typeof entry !== "object" || entry.type !== EMA_CROSSOVER) return null;
  const fast = Number(entry.fast_period);
  const slow = Number(entry.slow_period);
  return Number.isInteger(fast) && Number.isInteger(slow) && fast > 0 && slow > 0 ? { fast, slow } : null;
}

function readEmaPeriods(rule: Record<string, unknown> | undefined): EmaRule | null {
  if (!rule || typeof rule !== "object") return null;
  const fast = Number(rule.fast_period);
  const slow = Number(rule.slow_period);
  return Number.isInteger(fast) && Number.isInteger(slow) && fast > 0 && slow > 0 ? { fast, slow } : null;
}

/** Reads a stored exit rule; null when absent (older versions) or not an EMA crossover below. */
export function readExitRule(configuration: unknown): EmaRule | null {
  const exit = (configuration as { exit?: Record<string, unknown> } | null)?.exit;
  if (!exit || typeof exit !== "object" || exit.type !== EMA_CROSSOVER || exit.direction !== "below") return null;
  return readEmaPeriods(exit);
}

export const describeEntry = ({ fast, slow }: EmaRule) =>
  `Buy when the ${fast}-day EMA crosses above the ${slow}-day EMA.`;

export const describeExit = ({ fast, slow }: EmaRule) =>
  `Sell when the ${fast}-day EMA crosses below the ${slow}-day EMA.`;

export function readInitialCapital(backtestConfiguration: unknown): string | null {
  const v = (backtestConfiguration as { initial_capital?: unknown } | null)?.initial_capital;
  return typeof v === "number" || typeof v === "string" ? String(v) : null;
}
