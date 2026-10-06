/**
 * Display-only number formatting. Inputs are never rounded for calculation — these helpers run at the
 * presentation layer. Missing or non-numeric values render as "Unavailable", never as 0.
 */

export const UNAVAILABLE = "Unavailable";

type Input = string | number | null | undefined;

function toNumber(value: Input): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Rounds to 2 decimals and removes negative zero so "-0.00" never appears. */
const roundTwo = (n: number) => {
  const r = Math.round((Math.abs(n) + Number.EPSILON) * 100) / 100;
  return n < 0 && r !== 0 ? -r : r;
};

const sign = (n: number, signed?: boolean) => (signed && n > 0 ? "+" : "");

const twoDecimals = (n: number, locale: string) =>
  new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);

/** Indian digit grouping for INR; other currencies use the browser locale. */
const localeFor = (currency: string) => (currency === "INR" ? "en-IN" : undefined) as string;

/** ₹64,761.90 · ₹1,25,000.00 · -₹500.00 */
export function formatCurrency(value: Input, options: { currency?: string; signed?: boolean } = {}): string {
  const n = toNumber(value);
  if (n == null) return UNAVAILABLE;
  const currency = options.currency ?? "INR";
  const rounded = roundTwo(n);
  try {
    const text = new Intl.NumberFormat(localeFor(currency), {
      style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(rounded);
    return `${sign(rounded, options.signed)}${text}`;
  } catch {
    return `${sign(rounded, options.signed)}${twoDecimals(rounded, "en-IN")} ${currency}`;
  }
}

/** Value already expressed as a percentage (29.5238 → "29.52%"). Pass `ratio` for 0–1 values (1 → "100.00%"). */
export function formatPercentage(value: Input, options: { signed?: boolean; ratio?: boolean } = {}): string {
  const n = toNumber(value);
  if (n == null) return UNAVAILABLE;
  const rounded = roundTwo(options.ratio ? n * 100 : n);
  return `${sign(rounded, options.signed)}${twoDecimals(rounded, "en-IN")}%`;
}

/** Plain decimal metric with 2 decimals (profit factor, prices, quantities). */
export function formatNumber(value: Input, options: { signed?: boolean } = {}): string {
  const n = toNumber(value);
  if (n == null) return UNAVAILABLE;
  const rounded = roundTwo(n);
  return `${sign(rounded, options.signed)}${twoDecimals(rounded, "en-IN")}`;
}

/** Whole numbers such as trade counts — no decimal places. */
export function formatInteger(value: Input): string {
  const n = toNumber(value);
  if (n == null) return UNAVAILABLE;
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.round(n));
}
