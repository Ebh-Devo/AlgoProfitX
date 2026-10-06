import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Lock, Minus } from "lucide-react";

import { useReveal } from "../../lib/useReveal";

interface Stage {
  id: string;
  name: string;
  summary: string;
  you: string;
  get: string;
  boundary: string;
  cta: { to: string; label: string };
  /** Accent for this stage; moves blue → cyan → indigo across the journey. */
  accent: string;
}

/** Every stage below maps to a workflow that exists in the product today. */
export const STAGES: Stage[] = [
  { id: "create", name: "Create", accent: "#4f6ef7", summary: "Define a strategy against canonical NSE/BSE Instruments.", you: "Name a strategy and keep it as a draft while you work.", get: "A draft strategy in your creator workspace.", boundary: "Strategies are research objects. Creating one does not trade anything.", cta: { to: "/register", label: "Start with a draft" } },
  { id: "version", name: "Version", accent: "#5a82f3", summary: "Freeze the exact configuration as an immutable Version.", you: "Pick an Instrument, set your entry rule and choose a starting capital.", get: "An immutable Version. Changing the idea means a new Version.", boundary: "Versions are never edited in place, so results always point at what produced them.", cta: { to: "/register", label: "Create a Version" } },
  { id: "backtest", name: "Backtest", accent: "#3f9bef", summary: "Run a deterministic historical simulation.", you: "Start a backtest on a Version.", get: "A run with provenance you can inspect and repeat.", boundary: "Backtests use reference or synthetic datasets and are labelled as simulated.", cta: { to: "/register", label: "Run a backtest" } },
  { id: "analyze", name: "Analyze", accent: "#2bb3dd", summary: "Read return, drawdown, win rate, profit factor and trades.", you: "Open a completed run.", get: "Metrics, a trade list and an equity curve for that run.", boundary: "Figures appear only when a real backtest result exists. They are not live performance.", cta: { to: "/register", label: "Read a run report" } },
  { id: "publish", name: "Publish", accent: "#22bfd0", summary: "Move a strategy through published and deployed states.", you: "Publish a draft that has at least one Version.", get: "A public listing in the marketplace.", boundary: "Listings do not expose a creator’s private configuration.", cta: { to: "/marketplace", label: "Browse listed strategies" } },
  { id: "allocate", name: "Allocate", accent: "#6d7cff", summary: "Investors pin an allocation intent to a specific Version.", you: "Choose a published strategy and a notional amount.", get: "A version-pinned allocation you can revisit.", boundary: "An allocation is an intent. No funds move and no broker is involved.", cta: { to: "/marketplace", label: "Find a strategy" } },
  { id: "execute", name: "Paper execute", accent: "#8a74fa", summary: "Observe filled, no-fill and failed outcomes — simulated.", you: "Create an execution intent for an allocation.", get: "A paper outcome, with its state clearly shown.", boundary: "Paper execution places no broker orders and uses no funded capital.", cta: { to: "/register", label: "Try paper execution" } },
];

const chip = (text: string, tone = "") => <span className={`wf-chip ${tone}`}>{text}</span>;

/** Small supporting illustration per stage. Labels and states only: no figures. */
function StageVisual({ id }: { id: string }): ReactNode {
  switch (id) {
    case "create":
      return <div className="wf-vis-row"><span className="wf-vis-title">Draft strategy</span>{chip("Draft")}</div>;
    case "version":
      return <><div className="wf-vis-row"><span className="wf-vis-title"><Lock size={12} aria-hidden="true" /> Version 1</span>{chip("Immutable", "is-on")}</div><div className="wf-vis-row">{chip("Instrument")}{chip("Configuration")}</div></>;
    case "backtest":
      return <><div className="wf-vis-row"><span className="wf-vis-title">Backtest run</span>{chip("Complete", "is-on")}</div><div className="wf-vis-chart" aria-hidden="true"><i /></div></>;
    case "analyze":
      return <div className="wf-vis-metrics">{["Return", "Drawdown", "Win rate", "Trades"].map(m => <div key={m}><span>{m}</span><b><Minus size={12} aria-hidden="true" /></b></div>)}</div>;
    case "publish":
      return <div className="wf-vis-row">{chip("Draft")}<ArrowRight size={12} aria-hidden="true" />{chip("Published", "is-on")}<ArrowRight size={12} aria-hidden="true" />{chip("Deployed")}</div>;
    case "allocate":
      return <><div className="wf-vis-row"><span className="wf-vis-title">Allocation</span>{chip("Pinned to Version", "is-on")}</div><div className="wf-vis-row">{chip("Intent only")}</div></>;
    default:
      return <div className="wf-vis-row">{chip("Filled", "is-on")}{chip("No fill")}{chip("Failed")}</div>;
  }
}

export function WorkflowExplorer() {
  const [index, setIndex] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const reveal = useReveal<HTMLDivElement>();
  const location = useLocation();
  const stage = STAGES[index];

  /* Deep links such as /#stage-backtest (from the header menu) select that stage. */
  useEffect(() => {
    const m = /^#stage-(.+)$/.exec(location.hash);
    const at = m ? STAGES.findIndex(s => s.id === m[1]) : -1;
    if (at >= 0) setIndex(at);
  }, [location.hash, location.key]);

  const move = (to: number) => {
    const next = (to + STAGES.length) % STAGES.length;
    setIndex(next);
    tabs.current[next]?.focus();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(index + 1); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(index - 1); }
    else if (e.key === "Home") { e.preventDefault(); move(0); }
    else if (e.key === "End") { e.preventDefault(); move(STAGES.length - 1); }
  };

  return (
    <div ref={reveal.ref} className={`wf ${reveal.className}`} style={{ "--stage": stage.accent } as CSSProperties}>
      <div className="wf-tabs" role="tablist" aria-label="Workflow stages" aria-orientation="horizontal" onKeyDown={onKey}>
        {STAGES.map((s, i) => (
          <button
            key={s.id}
            ref={el => { tabs.current[i] = el; }}
            id={`wf-tab-${s.id}`}
            type="button"
            role="tab"
            className={`wf-tab${i < index ? " is-done" : ""}${i === index - 1 ? " is-leading" : ""}`}
            style={{ "--tab-accent": s.accent } as CSSProperties}
            aria-selected={i === index}
            aria-controls="wf-panel"
            tabIndex={i === index ? 0 : -1}
            onClick={() => setIndex(i)}
          >
            <span className="wf-dot" aria-hidden="true" />
            <span className="wf-n">{String(i + 1).padStart(2, "0")}</span>
            <span>{s.name}</span>
          </button>
        ))}
      </div>

      <div id="wf-panel" role="tabpanel" aria-labelledby={`wf-tab-${stage.id}`} className="wf-panel" key={stage.id}>
        <div>
          <p className="wf-step">Step {index + 1} of {STAGES.length}</p>
          <h3>{stage.name}</h3>
          <p className="wf-summary">{stage.summary}</p>
          <div className="wf-vis" aria-hidden="true"><StageVisual id={stage.id} /></div>
        </div>
        <dl className="wf-facts">
          <div><dt>You</dt><dd>{stage.you}</dd></div>
          <div><dt>You get</dt><dd>{stage.get}</dd></div>
          <div><dt>Worth knowing</dt><dd>{stage.boundary}</dd></div>
        </dl>
        <Link className="l-link wf-cta" to={stage.cta.to}>{stage.cta.label} <ArrowRight size={14} aria-hidden="true" /></Link>
      </div>
    </div>
  );
}
