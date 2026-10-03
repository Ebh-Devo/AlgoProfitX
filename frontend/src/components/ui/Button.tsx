import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size    = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?:  Variant;
  size?:     Size;
  loading?:  boolean;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary:   "btn btn-primary",
  secondary: "btn btn-secondary",
  ghost:     "btn btn-ghost",
  danger:    "btn btn-danger",
};

const SIZE_CLASS: Record<Size, string> = {
  sm: "btn-sm",
  md: "",
  lg: "btn-lg",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, iconLeft, iconRight, disabled, children, className = "", ...rest }, ref) => (
    <button
      ref={ref}
      className={[VARIANT_CLASS[variant], SIZE_CLASS[size], className].filter(Boolean).join(" ")}
      disabled={disabled || loading}
      aria-busy={loading}
      aria-disabled={disabled || loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 size={14} className="btn-spinner" aria-hidden="true" /> : iconLeft}
      {children}
      {!loading && iconRight}
    </button>
  ),
);
Button.displayName = "Button";
