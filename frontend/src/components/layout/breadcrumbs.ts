export interface Crumb { label: string; to?: string }

const LABELS: Record<string, string> = {
  app: "Dashboard",
  account: "Account",
  enroll: "Become a creator",
  strategies: "Strategies",
  new: "New strategy",
  edit: "Edit",
  allocations: "Allocations",
  "execution-intents": "Executions",
  marketplace: "Marketplace",
  instruments: "Instruments",
};

/** Routing prefixes / folded segments that have no page of their own. */
const SKIP = new Set(["app", "creator", "investor", "versions", "backtests"]);

/** Builds a breadcrumb trail from a pathname. Opaque IDs become "Details" / "Version" / "Backtest". */
export function buildCrumbs(pathname: string): Crumb[] {
  const parts = pathname.split("/").filter(Boolean);
  const crumbs: Crumb[] = [{ label: "Dashboard", to: "/app" }];
  let acc = "";
  parts.forEach((part, i) => {
    acc += `/${part}`;
    if (SKIP.has(part)) return;
    const prev = parts[i - 1];
    const label = LABELS[part] ?? (prev === "versions" ? "Version" : prev === "backtests" ? "Backtest" : "Details");
    crumbs.push({ label, to: i === parts.length - 1 ? undefined : acc });
  });
  if (crumbs.length === 1) return [{ label: "Dashboard" }];
  return crumbs;
}
