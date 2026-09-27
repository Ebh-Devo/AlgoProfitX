import { forwardRef, type InputHTMLAttributes, type ReactNode, useId } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  error?: string;
  hint?: ReactNode;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, iconLeft, iconRight, id: customId, className = "", disabled, ...rest }, ref) => {
    const generatedId = useId();
    const inputId = customId || generatedId;
    const errorId = `${inputId}-error`;
    const hintId = `${inputId}-hint`;

    const describedBy = [
      error ? errorId : null,
      hint ? hintId : null,
    ].filter(Boolean).join(" ") || undefined;

    return (
      <div className={`form-field ${error ? "has-error" : ""} ${disabled ? "is-disabled" : ""}`}>
        {label && (
          <label htmlFor={inputId} className="form-label">
            {label}
          </label>
        )}
        <div className="input-wrapper">
          {iconLeft && <span className="input-icon-left" aria-hidden="true">{iconLeft}</span>}
          <input
            ref={ref}
            id={inputId}
            disabled={disabled}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={[`input`, error ? "input-error" : "", iconLeft ? "has-icon-left" : "", iconRight ? "has-icon-right" : "", className].filter(Boolean).join(" ")}
            {...rest}
          />
          {iconRight && <span className="input-icon-right">{iconRight}</span>}
        </div>
        {hint && !error && (
          <p id={hintId} className="field-hint">
            {hint}
          </p>
        )}
        {error && <FormError id={errorId}>{error}</FormError>}
      </div>
    );
  }
);
Input.displayName = "Input";

export interface FormErrorProps {
  id?: string;
  children?: ReactNode;
  className?: string;
}

export function FormError({ id, children, className = "" }: FormErrorProps) {
  if (!children) return null;
  return (
    <p id={id} className={`field-error ${className}`} role="alert">
      {children}
    </p>
  );
}
