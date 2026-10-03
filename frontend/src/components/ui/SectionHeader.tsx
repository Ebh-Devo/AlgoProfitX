import type { ReactNode } from "react";

interface SectionHeaderProps {
  title: string;
  description?: ReactNode;
  /** Optional count shown beside the title (e.g. number of rows). */
  count?: number;
  actions?: ReactNode;
  id?: string;
}

/** Heading for a section inside a page (h2). Pair with `<section aria-labelledby={id}>`. */
export function SectionHeader({ title, description, count, actions, id }: SectionHeaderProps) {
  return (
    <div className="section-header">
      <div className="section-header-text">
        <h2 id={id}>
          {title}
          {count !== undefined && <span className="section-count" aria-label={`${count} total`}>{count}</span>}
        </h2>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="section-header-actions">{actions}</div>}
    </div>
  );
}
