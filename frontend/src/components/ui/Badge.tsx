import type { HTMLAttributes, ReactNode } from "react";
import { Archive, CheckCircle2, CircleDashed, Clock, Globe, Loader2, PenLine, XCircle } from "lucide-react";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "info" | "accent" | "muted";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const VARIANT_CLASS: Record<BadgeVariant, string> = {
  default: "badge",
  success: "badge badge-success",
  warning: "badge badge-warning",
  danger:  "badge badge-danger",
  info:    "badge badge-info",
  accent:  "badge badge-accent",
  muted:   "badge badge-muted",
};

export function Badge({ variant = "default", className = "", children, ...rest }: BadgeProps) {
  return (
    <span className={[VARIANT_CLASS[variant], className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </span>
  );
}

/* Maps strategy/version lifecycle states to badge variants */
const STATUS_MAP: Record<string, BadgeVariant> = {
  draft:      "muted",
  published:  "info",
  deployed:   "success",
  archived:   "muted",
  active:     "success",
  completed:  "success",
  failed:     "danger",
  pending:    "warning",
  cancelled:  "muted",
  queued:     "warning",
  running:    "info",
};

/** Icons make status legible without colour. Decorative: the text label is always rendered. */
const STATUS_ICON: Record<string, ReactNode> = {
  draft:     <PenLine size={12} aria-hidden="true" />,
  published: <Globe size={12} aria-hidden="true" />,
  deployed:  <CheckCircle2 size={12} aria-hidden="true" />,
  archived:  <Archive size={12} aria-hidden="true" />,
  active:    <CheckCircle2 size={12} aria-hidden="true" />,
  completed: <CheckCircle2 size={12} aria-hidden="true" />,
  failed:    <XCircle size={12} aria-hidden="true" />,
  pending:   <Clock size={12} aria-hidden="true" />,
  queued:    <Clock size={12} aria-hidden="true" />,
  running:   <Loader2 size={12} aria-hidden="true" className="status-spin" />,
  cancelled: <CircleDashed size={12} aria-hidden="true" />,
};

export function StatusBadge({ status, className = "" }: { status: string; className?: string }) {
  const variant = STATUS_MAP[status.toLowerCase()] ?? "default";
  return (
    <Badge variant={variant} className={`badge-status ${className}`}>
      {STATUS_ICON[status.toLowerCase()]}
      {status}
    </Badge>
  );
}

/** Shows P&L direction — always pairs color with a sign symbol. */
export function FinancialBadge({ value, formatted }: { value: number; formatted: string }) {
  const cls = value > 0 ? "badge-profit" : value < 0 ? "badge-loss" : "badge-neutral-val";
  const sign = value > 0 ? "+" : "";
  return (
    <span className={`badge-financial ${cls}`} aria-label={`${sign}${formatted}`}>
      <span aria-hidden="true">{sign}</span>{formatted}
    </span>
  );
}
