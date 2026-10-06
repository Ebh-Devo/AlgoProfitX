import { useEffect, useState } from "react";

interface HeroNode { id: string; label: string; caption: string; x: number; y: number }

/** Conceptual workflow. Positions form a snake: top row left→right, then bottom row right→left. */
const NODES: HeroNode[] = [
  { id: "create", label: "Create", caption: "Define a strategy as a draft.", x: 20, y: 40 },
  { id: "research", label: "Research", caption: "Freeze an Instrument and configuration as an immutable Version.", x: 185, y: 40 },
  { id: "backtest", label: "Backtest", caption: "Run a deterministic historical simulation.", x: 350, y: 40 },
  { id: "publish", label: "Publish", caption: "List a strategy in the marketplace.", x: 350, y: 236 },
  { id: "allocate", label: "Allocate", caption: "Pin an allocation intent to a specific Version.", x: 185, y: 236 },
  { id: "execute", label: "Paper execute", caption: "Observe simulated outcomes. No broker orders.", x: 20, y: 236 },
];

const W = 110;
const H = 44;
/** Connector i links node i to node i+1. */
const LINKS = ["M130 62 H185", "M295 62 H350", "M405 84 V236", "M350 258 H295", "M185 258 H130"];

const TICK_MS = 2200;

/**
 * Animated, purely conceptual illustration of the product workflow.
 * It carries no prices, returns or orders: the "chart" is an abstract dashed path and is labelled as such.
 */
export function HeroVisual() {
  const reduced = typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [active, setActive] = useState(reduced ? -1 : 0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (reduced || paused) return;
    const id = window.setInterval(() => setActive(a => (a + 1) % NODES.length), TICK_MS);
    return () => window.clearInterval(id);
  }, [reduced, paused]);

  const current = NODES[Math.max(active, 0)];

  return (
    <figure
      className="hv gb"
      aria-label="Conceptual illustration of the AlgoProfitX workflow. It contains no market data."
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
    >
      <div className="hv-bar">
        <span className="hv-title"><span className="hv-live" aria-hidden="true" /> Product workflow</span>
        <span className="badge badge-muted">Conceptual · not market data</span>
      </div>

      <svg className="hv-svg" viewBox="0 0 480 300" role="presentation" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="hv-grad" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="480" y2="0">
            <stop offset="0" style={{ stopColor: "var(--l-a)" }} />
            <stop offset="1" style={{ stopColor: "var(--l-b)" }} />
          </linearGradient>
        </defs>

        {/* abstract research field: gridlines and a dashed path, not a price series */}
        {[120, 150, 180, 210].map(y => <line key={y} x1="40" x2="380" y1={y} y2={y} className="hv-grid" />)}
        <path className="hv-path" d="M40 195 C95 185 120 150 170 158 S250 120 300 128 S350 100 380 112" />

        {LINKS.map((d, i) => (
          <g key={i}>
            <path d={d} className={`hv-link${active > i ? " is-lit" : ""}`} pathLength={100} />
            {active === i + 1 && <path key={`p-${active}`} d={d} className="hv-pulse" pathLength={100} />}
          </g>
        ))}

        {NODES.map((n, i) => {
          const state = i === active ? "is-active" : active > i ? "is-done" : "";
          return (
            <g key={n.id} className={`hv-node ${state}`} transform={`translate(${n.x} ${n.y})`} onPointerEnter={() => setActive(i)}>
              <rect width={W} height={H} rx="10" />
              <text x="12" y="17" className="hv-n">{String(i + 1).padStart(2, "0")}</text>
              <text x="12" y="34" className="hv-label">{n.label}</text>
              <circle cx={W - 14} cy="14" r="3.5" className="hv-dot" />
            </g>
          );
        })}
      </svg>

      <figcaption className="hv-caption">
        <strong>{current.label}</strong>
        <span>{current.caption}</span>
      </figcaption>
    </figure>
  );
}
