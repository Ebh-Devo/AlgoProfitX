import type { BacktestAnalytics } from "../../api/types";
import type { Trade } from "../creator/backtestFormat";

/**
 * UI-side contract for the Marketplace Backtest workspace.
 *
 * Nothing here calls the API. Today the backend exposes no endpoint that runs or reads a Backtest for a
 * published Marketplace strategy (Backtests are Creator-owned and the public profile omits them), so
 * `MARKETPLACE_BACKTEST_SUPPORT` is "unavailable". A later integration PR supplies an `ExecutionView`
 * built from real responses; until then the workspace never shows results.
 */

export type DisplayState = "not_configured" | "ready" | "running" | "completed" | "failed" | "unavailable";

export const MARKETPLACE_BACKTEST_SUPPORT = {
  supported: false,
  reason:
    "AlgoProfitX does not yet offer an API to run or read a Backtest for a published Marketplace strategy. " +
    "It needs a Marketplace-scoped Backtest endpoint that returns results and market-data provenance.",
} as const;

/** Every field is optional/null: unknown values are rendered as "Not available", never guessed. */
export interface ProvenanceView {
  dataSource: string | null;
  synthetic: boolean | null;
  timeframe: string | null;
  fillModel: string | null;
  fees: string | null;
  slippage: string | null;
  engine: string | null;
  definitionVersion: string | null;
  limitations: string[];
}

export interface ResultView {
  startingCapital: string;
  netProfitLoss: string;
  returnPercent: string;
  maxDrawdown: string;
  tradeCount: number;
  winRate?: string | null;
  profitFactor?: string | null;
  equityCurve: BacktestAnalytics["equity_curve"];
  trades: Trade[];
  provenance: ProvenanceView;
}

export type ExecutionView =
  | { kind: "unavailable"; reason: string }
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "completed"; result: ResultView }
  | { kind: "failed"; message: string };

export const CAPITAL_MAX = 1_000_000_000;

/** Accepts "50,000" or "1,25,000.50" (₹ optional). Returns an error message, or null when valid. */
export function validateStartingCapital(raw: string): string | null {
  const cleaned = raw.replace(/[,\s₹]/g, "");
  if (!cleaned) return "Enter a starting capital in INR, for example 50,000.";
  if (!/^\d*\.?\d+$|^\d+\.$/.test(cleaned)) return "Starting capital must be a number, for example 50,000.";
  const n = Number(cleaned);
  if (!Number.isFinite(n) || n <= 0) return "Starting capital must be greater than ₹0.";
  if (n > CAPITAL_MAX) return "Starting capital must not exceed ₹100 crore (1,000,000,000).";
  return null;
}

export function resolveDisplayState(execution: ExecutionView, capitalValid: boolean): DisplayState {
  switch (execution.kind) {
    case "unavailable": return "unavailable";
    case "running": return "running";
    case "completed": return "completed";
    case "failed": return "failed";
    default: return capitalValid ? "ready" : "not_configured";
  }
}
