import { useRef, useState, type KeyboardEvent } from "react";
import { Check, Lock, Minus } from "lucide-react";

import { useReveal } from "../../lib/useReveal";

const TABS = ["Overview", "Versions", "Backtest", "Execution"] as const;
type Tab = (typeof TABS)[number];

const FLOW = ["Create", "Research", "Backtest", "Paper"];

/**
 * Illustrative workspace preview. "EMA Trend Follower" is a sample name; there are no figures,
 * prices or orders here: metric slots show a dash exactly like an empty report would.
 */
export function ProductPreview() {
  const [tab, setTab] = useState<Tab>("Overview");
  const reveal = useReveal<HTMLDivElement>();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = (i: number) => {
    const n = (i + TABS.length) % TABS.length;
    setTab(TABS[n]);
    refs.current[n]?.focus();
  };
  const onKey = (e: KeyboardEvent) => {
    const i = TABS.indexOf(tab);
    if (e.key === "ArrowRight") { e.preventDefault(); move(i + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); move(i - 1); }
    else if (e.key === "Home") { e.preventDefault(); move(0); }
    else if (e.key === "End") { e.preventDefault(); move(TABS.length - 1); }
  };

  return (
    <div ref={reveal.ref} className={`pv gb ${reveal.className}`} role="group" aria-label="Illustrative preview of the strategy workspace. Sample name, no real data.">
      <div className="pv-chrome" aria-hidden="true"><i /><i /><i /><span>Strategies / EMA Trend Follower</span></div>

      <div className="pv-body">
        <aside className="pv-side" aria-hidden="true">
          <span>Dashboard</span><span className="is-on">Strategies</span><span>Allocations</span><span>Executions</span><span>Marketplace</span>
        </aside>

        <div className="pv-main">
          <header className="pv-head">
            <div>
              <p className="pv-eyebrow">Creator strategy</p>
              <h3>EMA Trend Follower</h3>
            </div>
            <span className="pv-status"><span className="pv-pulse" aria-hidden="true" /> Deployed</span>
          </header>

          <ol className="pv-flow" aria-label="Workflow">
            {FLOW.map((f, i) => (
              <li key={f} style={{ ["--i" as string]: i }}>
                <span className="pv-flow-dot" aria-hidden="true"><Check size={11} /></span>{f}
              </li>
            ))}
          </ol>

          <div className="pv-tabs" role="tablist" aria-label="Strategy sections" onKeyDown={onKey}>
            {TABS.map((t, i) => (
              <button
                key={t}
                ref={el => { refs.current[i] = el; }}
                id={`pv-tab-${t}`}
                type="button"
                role="tab"
                aria-selected={tab === t}
                aria-controls="pv-panel"
                tabIndex={tab === t ? 0 : -1}
                onClick={() => setTab(t)}
              >{t}</button>
            ))}
          </div>

          <div id="pv-panel" role="tabpanel" aria-labelledby={`pv-tab-${tab}`} className="pv-panel" key={tab}>
            {tab === "Overview" && (
              <dl className="pv-kv">
                <div><dt>Strategy</dt><dd>EMA Trend Follower</dd></div>
                <div><dt>Status</dt><dd>Deployed</dd></div>
                <div><dt>Research</dt><dd>Backtest complete</dd></div>
                <div><dt>Execution</dt><dd>Paper</dd></div>
                <div className="is-wide"><dt>Workflow</dt><dd>Create → Research → Backtest → Paper</dd></div>
              </dl>
            )}
            {tab === "Versions" && (
              <ul className="pv-list">
                <li><Lock size={13} aria-hidden="true" /><span><strong>Version 1</strong> · current</span><em>Immutable</em></li>
                <li><span className="pv-ghost" /><span>Instrument pinned to the Version</span></li>
                <li><span className="pv-ghost" /><span>Configuration frozen at creation</span></li>
              </ul>
            )}
            {tab === "Backtest" && (
              <div className="pv-report">
                <p className="pv-state"><Check size={13} aria-hidden="true" /> Backtest complete</p>
                <div className="pv-metrics">
                  {["Total return", "Max drawdown", "Win rate", "Trades"].map(m => (
                    <div key={m}><span>{m}</span><b><Minus size={13} aria-hidden="true" /><span className="visually-hidden">Shown from a real run</span></b></div>
                  ))}
                </div>
                <div className="pv-chart" aria-hidden="true"><i /></div>
                <p className="pv-note">Metrics and the equity curve come from real backtest runs. This preview shows none.</p>
              </div>
            )}
            {tab === "Execution" && (
              <ul className="pv-list">
                <li><span className="badge badge-muted">Paper</span><span>Simulated outcomes only</span></li>
                <li><span className="pv-ghost" /><span>Filled · No fill · Failed are shown distinctly</span></li>
                <li><span className="pv-ghost" /><span>No broker orders are placed</span></li>
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
