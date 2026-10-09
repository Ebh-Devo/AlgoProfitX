import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BacktestAnalytics } from "../../api/types";
import { EmptyState } from "../../components/PageState";
import { formatCurrency } from "../../lib/format";
import { displayDay } from "./backtestFormat";

type Point = BacktestAnalytics["equity_curve"][number];

const money = (v: number) => formatCurrency(v);

/** Plain-language description of the real series, used as the chart's accessible name and visible caption. */
export function describeEquity(curve: Point[]): string | null {
  if (!curve.length) return null;
  const values = curve.map((p) => Number(p.equity));
  const first = curve[0];
  const last = curve[curve.length - 1];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = curve.length === 1 ? `1 point on ${displayDay(first.timestamp)}` : `${curve.length} points from ${displayDay(first.timestamp)} to ${displayDay(last.timestamp)}`;
  return `${span}. Equity starts at ${money(values[0])}, ends at ${money(values[values.length - 1])}, low ${money(lo)}, high ${money(hi)}.`;
}

/**
 * Equity curve from the analytics endpoint. Renders only what the API returned; an empty series is an
 * explained empty state, never a placeholder line. Other series (drawdown, trades) can be added as siblings later.
 */
export function EquityChart({ curve }: { curve: Point[] }) {
  const points = curve.map((p) => ({ ...p, value: Number(p.equity) }));
  const summary = describeEquity(curve);
  if (!points.length) {
    return (
      <EmptyState variant="compact" title="No equity series returned">
        No equity points are available.
      </EmptyState>
    );
  }
  return (
    <figure className="equity-figure">
      <div className="equity-chart" data-testid="equity-chart" role="img" aria-label={`Equity curve chart showing portfolio value over time. ${summary}`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 10, right: 12, bottom: 6, left: 4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" hide />
            <YAxis dataKey="value" stroke="var(--muted)" tick={{ fontSize: 12, fontFamily: "var(--font-sans)", fill: "var(--muted)" }} domain={["auto", "auto"]} width={72} tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })} />
            <Tooltip
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}
              labelFormatter={(_, items) => { const ts = items?.[0]?.payload?.timestamp; return typeof ts === "string" ? displayDay(ts) : ""; }}
              formatter={(v) => [typeof v === "number" ? formatCurrency(v) : String(v), "Equity"]}
            />
            <Line type="monotone" dataKey="value" name="Equity" stroke="var(--color-accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="equity-caption">{summary}</figcaption>
    </figure>
  );
}
