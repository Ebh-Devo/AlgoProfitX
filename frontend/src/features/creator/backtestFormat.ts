import { ApiError } from "../../api/client";
import type { Backtest } from "../../api/types";

/** Display helpers shared by the backtest research workspace. Null always stays "unavailable" — never 0. */

export const NOT_AVAILABLE = "Not available";

export const displayDate = (value?: string | null) =>
  value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : NOT_AVAILABLE;

export const displayDay = (value?: string | null) =>
  value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : NOT_AVAILABLE;

export const errorMessage = (error: unknown, fallback: string) => (error instanceof ApiError ? error.message : fallback);

export const isActive = (status: string) => status === "queued" || status === "running";

export const shortId = (id: string) => id.slice(0, 8);

export const periodLabel = (start?: string | null, end?: string | null) =>
  start && end ? `${displayDay(start)} – ${displayDay(end)}` : null;

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const str = (value: unknown): string | null => (typeof value === "string" && value ? value : null);

export interface Trade {
  side: string;
  entryTimestamp: string | null;
  exitTimestamp: string | null;
  quantity: string | null;
  entryPrice: string | null;
  exitPrice: string | null;
  pnl: string | null;
}

/** Reads trades from `result_summary.trades`, ignoring anything that isn't in the documented shape. */
export function parseTrades(summary: Backtest["result_summary"]): Trade[] {
  const raw = asRecord(summary)?.trades;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    const t = asRecord(item);
    if (!t) return [];
    return [{
      side: str(t.side) ?? "—",
      entryTimestamp: str(t.entry_timestamp),
      exitTimestamp: str(t.exit_timestamp),
      quantity: str(t.quantity),
      entryPrice: str(t.entry_price),
      exitPrice: str(t.exit_price),
      pnl: str(t.pnl),
    }];
  });
}

/** Headline figures the list endpoint already carries for completed runs (null otherwise). */
export function summaryFigures(run: Backtest) {
  const s = asRecord(run.result_summary);
  return {
    totalReturn: str(s?.total_return),
    finalEquity: str(s?.final_equity),
    tradeCount: typeof s?.trade_count === "number" ? s.trade_count : null,
    engine: str(s?.engine_identifier),
    provider: str(s?.provider_identifier),
  };
}

export function instrumentOf(run: Backtest) {
  const i = asRecord(run.instrument_snapshot);
  return i
    ? { symbol: str(i.canonical_symbol), exchangeSymbol: str(i.exchange_symbol), name: str(i.name), exchange: str(i.exchange_code), type: str(i.instrument_type), currency: str(i.quote_currency) }
    : null;
}

export const isSynthetic = (run: Backtest) => asRecord(run.market_data_provenance)?.synthetic === true;

/** Reads a scalar from an immutable Version's backtest_configuration. */
export function configValue(config: unknown, key: string): string | null {
  const v = asRecord(config)?.[key];
  return typeof v === "string" || typeof v === "number" ? String(v) : null;
}

export const MAX_REFERENCE_LENGTH = 500;
