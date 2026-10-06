import { useEffect, useRef, useState } from "react";

/**
 * Progressive reveal: returns a ref and whether the element has entered the viewport.
 * Content is always visible when IntersectionObserver is unavailable or the user prefers reduced motion,
 * so nothing is ever hidden behind an animation that cannot run.
 */
export function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const canObserve = typeof IntersectionObserver !== "undefined"
    && !(typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  const [seen, setSeen] = useState(!canObserve);

  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some(e => e.isIntersecting)) { setSeen(true); io.disconnect(); }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);

  return { ref, className: seen ? "reveal is-in" : "reveal" };
}
