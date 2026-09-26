import type { HTMLAttributes, ReactNode } from "react";

type CardVariant = "default" | "elevated" | "interactive";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  as?: "div" | "article" | "section";
}

export function Card({ variant = "default", as: Tag = "div", className = "", children, ...rest }: CardProps) {
  const cls = ["card", variant === "elevated" ? "card-elevated" : "", variant === "interactive" ? "card-interactive" : "", className].filter(Boolean).join(" ");
  return <Tag className={cls} {...rest}>{children}</Tag>;
}

export function CardHeader({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card-header ${className}`} {...rest}>{children}</div>;
}

export function CardBody({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card-body ${className}`} {...rest}>{children}</div>;
}

export function CardFooter({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card-footer ${className}`} {...rest}>{children}</div>;
}

export function CardTitle({ children, subtitle }: { children: ReactNode; subtitle?: ReactNode }) {
  return (
    <div className="card-title-block">
      <h2 className="card-title-text">{children}</h2>
      {subtitle && <p className="card-subtitle">{subtitle}</p>}
    </div>
  );
}
