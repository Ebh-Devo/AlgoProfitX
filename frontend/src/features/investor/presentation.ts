export function formatMoney(value: string, currency: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return `${value} ${currency}`;
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : undefined, {
      style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${value} ${currency}`;
  }
}

export const shortId = (value: string) => value.length > 8 ? value.slice(0, 8) : value;
export const versionLabel = (versionNumber: number) => `Version ${versionNumber}`;
export const allocationLabel = (amount: string, currency: string, strategyName: string, strategyVersionNumber: number) =>
  `${formatMoney(amount, currency)} · ${strategyName} · ${versionLabel(strategyVersionNumber)}`;
