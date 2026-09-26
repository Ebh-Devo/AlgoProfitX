import type { ReactNode } from "react";
import { AlertCircle, CheckCircle2, Info, TriangleAlert, X } from "lucide-react";

type AlertVariant = "info" | "success" | "warning" | "error" | "disclosure";

interface AlertProps {
  variant?: AlertVariant;
  title?:   string;
  children: ReactNode;
  onClose?: () => void;
  className?: string;
}

const ICONS: Record<AlertVariant, ReactNode> = {
  info:        <Info        size={16} aria-hidden="true" />,
  success:     <CheckCircle2 size={16} aria-hidden="true" />,
  warning:     <TriangleAlert size={16} aria-hidden="true" />,
  error:       <AlertCircle size={16} aria-hidden="true" />,
  disclosure:  <Info        size={16} aria-hidden="true" />,
};

export function Alert({ variant = "info", title, children, onClose, className = "" }: AlertProps) {
  return (
    <div className={`alert alert-${variant} ${className}`} role={variant === "error" ? "alert" : "status"} aria-live={variant === "error" ? "assertive" : "polite"}>
      <span className="alert-icon">{ICONS[variant]}</span>
      <div className="alert-body">
        {title && <strong className="alert-title">{title}</strong>}
        <div className="alert-content">{children}</div>
      </div>
      {onClose && (
        <button className="alert-close" onClick={onClose} aria-label="Dismiss">
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

/** Convenience wrapper for backend error messages */
export function ErrorAlert({ children }: { children: ReactNode }) {
  return <Alert variant="error">{children}</Alert>;
}

/** Paper-trading disclosure banner */
export function DisclosureAlert({ children }: { children: ReactNode }) {
  return <Alert variant="disclosure">{children}</Alert>;
}
