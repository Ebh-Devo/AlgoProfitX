import type { ReactNode } from "react";
import { useReveal } from "../../lib/useReveal";

/**
 * Fades a block in once as it scrolls into view. Always visible without IntersectionObserver or with reduced motion.
 * `stagger` reveals the direct children one after another instead of the block as a whole.
 */
export function Reveal({ children, className = "", stagger = false }: { children: ReactNode; className?: string; stagger?: boolean }) {
  const r = useReveal<HTMLDivElement>();
  return <div ref={r.ref} className={`${r.className}${stagger ? " reveal-stagger" : ""} ${className}`.trim()}>{children}</div>;
}

