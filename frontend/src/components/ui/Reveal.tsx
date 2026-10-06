import type { ReactNode } from "react";
import { useReveal } from "../../lib/useReveal";

/** Fades a block in once as it scrolls into view. Always visible without IntersectionObserver or with reduced motion. */
export function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const r = useReveal<HTMLDivElement>();
  return <div ref={r.ref} className={`${r.className} ${className}`.trim()}>{children}</div>;
}
