import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";

interface NextStepProps {
  /** Short label for where the user is, e.g. "Draft · no Version yet". */
  context: string;
  title: string;
  children?: ReactNode;
  /** The one meaningful action. Must map to something the API actually supports. */
  action?: ReactNode;
  tone?: "default" | "attention";
}

/** One recommended next action with the state that motivates it. */
export function NextStep({ context, title, children, action, tone = "default" }: NextStepProps) {
  return (
    <section className={`next-step${tone === "attention" ? " is-attention" : ""}`} aria-label="Suggested next step">
      <ArrowRight size={16} aria-hidden="true" className="next-step-mark" />
      <div className="next-step-body">
        <p className="next-step-context">{context}</p>
        <strong>{title}</strong>
        {children && <p className="next-step-text">{children}</p>}
      </div>
      {action && <div className="next-step-action">{action}</div>}
    </section>
  );
}
