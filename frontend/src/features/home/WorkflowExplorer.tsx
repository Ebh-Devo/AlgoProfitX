import { useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { useReveal } from "../../lib/useReveal";

interface Stage {
  id: string;
  name: string;
  summary: string;
  you: string;
  get: string;
  boundary: string;
  cta?: { to: string; label: string };
}

/** Every stage below maps to a workflow that exists in the product today. */
export const STAGES: Stage[] = [
  { id: "create", name: "Create", summary: "Define a strategy against canonical NSE/BSE Instruments.", you: "Name a strategy and keep it as a draft while you work.", get: "A draft strategy in your creator workspace.", boundary: "Strategies are research objects. Creating one does not trade anything.", cta: { to: "/register", label: "Register to begin" } },
  { id: "version", name: "Version", summary: "Freeze the exact configuration as an immutable Version.", you: "Pick an Instrument and supply a JSON configuration.", get: "An immutable Version. Changing the idea means a new Version.", boundary: "Versions are never edited in place, so results always point at what produced them." },
  { id: "backtest", name: "Backtest", summary: "Run a deterministic historical simulation.", you: "Start a backtest on a Version.", get: "A run with provenance you can inspect and repeat.", boundary: "Backtests use reference or synthetic datasets and are labelled as simulated." },
  { id: "analyze", name: "Analyze", summary: "Read return, drawdown, win rate, profit factor and trades.", you: "Open a completed run.", get: "Metrics, a trade list and an equity curve for that run.", boundary: "Figures appear only when a real backtest result exists. They are not live performance." },
  { id: "publish", name: "Publish", summary: "Move a strategy through published and deployed states.", you: "Publish a draft that has at least one Version.", get: "A public listing in the marketplace.", boundary: "Listings do not expose a creator’s private configuration.", cta: { to: "/marketplace", label: "Browse listed strategies" } },
  { id: "allocate", name: "Allocate", summary: "Investors pin an allocation intent to a specific Version.", you: "Choose a published strategy and a notional amount.", get: "A version-pinned allocation you can revisit.", boundary: "An allocation is an intent. No funds move and no broker is involved." },
  { id: "execute", name: "Paper execute", summary: "Observe filled, no-fill and failed outcomes — simulated.", you: "Create an execution intent for an allocation.", get: "A paper outcome, with its state clearly shown.", boundary: "Paper execution places no broker orders and uses no funded capital." },
];

export function WorkflowExplorer() {
  const [index, setIndex] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const reveal = useReveal<HTMLDivElement>();
  const stage = STAGES[index];

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
    <div ref={reveal.ref} className={`wf ${reveal.className}`}>
      <div className="wf-tabs" role="tablist" aria-label="Workflow stages" aria-orientation="horizontal" onKeyDown={onKey}>
        {STAGES.map((s, i) => (
          <button
            key={s.id}
            ref={el => { tabs.current[i] = el; }}
            id={`wf-tab-${s.id}`}
            type="button"
            role="tab"
            className="wf-tab"
            aria-selected={i === index}
            aria-controls="wf-panel"
            tabIndex={i === index ? 0 : -1}
            onClick={() => setIndex(i)}
          >
            <span className="wf-n">{String(i + 1).padStart(2, "0")}</span>
            <span>{s.name}</span>
          </button>
        ))}
      </div>
      <div className="wf-progress" aria-hidden="true"><span style={{ width: `${((index + 1) / STAGES.length) * 100}%` }} /></div>

      <div id="wf-panel" role="tabpanel" aria-labelledby={`wf-tab-${stage.id}`} className="wf-panel" key={stage.id}>
        <div>
          <p className="wf-step">Step {index + 1} of {STAGES.length}</p>
          <h3>{stage.name}</h3>
          <p className="wf-summary">{stage.summary}</p>
        </div>
        <dl className="wf-facts">
          <div><dt>You</dt><dd>{stage.you}</dd></div>
          <div><dt>You get</dt><dd>{stage.get}</dd></div>
          <div><dt>Worth knowing</dt><dd>{stage.boundary}</dd></div>
        </dl>
        {stage.cta && <Link className="l-link wf-cta" to={stage.cta.to}>{stage.cta.label} <ArrowRight size={14} aria-hidden="true" /></Link>}
      </div>
    </div>
  );
}
