import { Link } from "react-router-dom";

import { Reveal } from "../../components/ui/Reveal";
import { WorkflowExplorer } from "./WorkflowExplorer";
import {
  ArrowRight, BarChart3, Check, FlaskConical, GitBranch, LineChart, Minus, ScrollText, Store, Wallet,
} from "lucide-react";

const CAPABILITIES = [
  { icon: <GitBranch size={18} />, title: "Versioned strategies", text: "Every change produces a new immutable Version, so a result always points to the exact configuration that produced it." },
  { icon: <FlaskConical size={18} />, title: "Reference backtesting", text: "Deterministic historical simulations with provenance, so a run can be understood and repeated." },
  { icon: <LineChart size={18} />, title: "Analytics that explain", text: "Total return, max drawdown, win rate, profit factor, trade list and equity curve for every completed run." },
  { icon: <Store size={18} />, title: "Marketplace discovery", text: "Browse public deployed strategies without exposing a creator’s private configuration." },
  { icon: <Wallet size={18} />, title: "Version-pinned allocations", text: "An allocation references one Version, so you always know what it is tied to." },
  { icon: <BarChart3 size={18} />, title: "Instrument master", text: "NSE/BSE instrument identity, INR quote currency and session-aware design underpin every strategy." },
];

const METRICS = ["Total return", "Max drawdown", "Win rate", "Profit factor", "Trades"];

export function HomePage() {
  return (
    <div className="landing">
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="l-hero l-wrap" aria-labelledby="hero-title">
        <div className="l-hero-copy">
          <p className="eyebrow">Systematic strategy research · Indian markets</p>
          <h1 id="hero-title">Turn a trading idea into a strategy you can test.</h1>
          <p className="lead">
            AlgoProfitX is a workspace for building versioned strategies, running historical simulations,
            publishing to a discovery marketplace and exploring allocation through paper execution.
          </p>
          <div className="l-actions">
            <Link className="btn btn-lg" to="/register">Start building <ArrowRight size={16} aria-hidden="true" /></Link>
            <Link className="btn btn-lg btn-secondary" to="/marketplace">Explore marketplace</Link>
          </div>
          <ul className="l-proof" aria-label="Platform properties">
            <li><Check size={14} aria-hidden="true" /> NSE/BSE instrument identity</li>
            <li><Check size={14} aria-hidden="true" /> INR-native</li>
            <li><Check size={14} aria-hidden="true" /> Version-pinned</li>
            <li><Check size={14} aria-hidden="true" /> Clearly simulated</li>
          </ul>
        </div>

        <figure className="l-preview" aria-label="Layout preview of a backtest report. Contains no real data.">
          <div className="l-preview-bar">
            <span className="l-preview-title"><ScrollText size={14} aria-hidden="true" /> Backtest report</span>
            <span className="badge badge-muted">Layout preview · no data</span>
          </div>
          <dl className="l-preview-metrics">
            {METRICS.map(m => (
              <div key={m}>
                <dt>{m}</dt>
                <dd><Minus size={14} aria-hidden="true" /><span className="visually-hidden">No data</span></dd>
              </div>
            ))}
          </dl>
          <div className="l-preview-chart" aria-hidden="true">
            <svg viewBox="0 0 600 180" preserveAspectRatio="none">
              {[36, 72, 108, 144].map(y => <line key={y} x1="0" x2="600" y1={y} y2={y} className="grid" />)}
              <path className="curve" d="M0 140 C60 132 90 120 140 126 S220 96 280 104 S380 70 440 78 S540 44 600 38" />
            </svg>
            <span>Equity curve</span>
          </div>
          <div className="l-preview-rows" aria-hidden="true">
            {[0, 1, 2].map(i => (
              <div key={i}><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /></div>
            ))}
          </div>
        </figure>
      </section>

      {/* ── Positioning ──────────────────────────────────────── */}
      <section className="l-band" aria-labelledby="why-title">
        <div className="l-wrap l-why">
          <h2 id="why-title">Rules you can write down are rules you can test.</h2>
          <p>
            Systematic trading replaces in-the-moment judgement with explicit rules. The value is in being
            able to examine those rules — what they assume, how they behaved historically, and exactly which
            configuration produced a result — before capital is ever involved. AlgoProfitX is built around that
            discipline.
          </p>
        </div>
      </section>

      {/* ── Audience ─────────────────────────────────────────── */}
      <section className="l-section l-wrap" aria-labelledby="audience-title">
        <header className="l-head">
          <p className="eyebrow">Who it is for</p>
          <h2 id="audience-title">Two roles, one auditable workflow.</h2>
        </header>
        <Reveal>
        <div className="l-audience">
          <article className="card">
            <h3>Creators</h3>
            <p>Model strategy ideas, bind them to Instruments, create immutable Versions and move them deliberately through draft, published, deployed and archived states.</p>
            <ul className="l-ticks">
              <li><Check size={14} aria-hidden="true" /> Immutable Versions preserve every configuration</li>
              <li><Check size={14} aria-hidden="true" /> Reference backtests with provenance</li>
              <li><Check size={14} aria-hidden="true" /> Analytics that explain a run</li>
            </ul>
            <Link className="l-link" to="/register">Create your workspace <ArrowRight size={14} aria-hidden="true" /></Link>
          </article>
          <article className="card">
            <h3>Investors</h3>
            <p>Explore public deployed strategies, pin an allocation intent to a Version and inspect every paper outcome — without access to a creator’s private configuration.</p>
            <ul className="l-ticks">
              <li><Check size={14} aria-hidden="true" /> Clear lifecycle and Version context</li>
              <li><Check size={14} aria-hidden="true" /> Allocations tied to a specific Version</li>
              <li><Check size={14} aria-hidden="true" /> Filled, no-fill and failed states stay unmistakable</li>
            </ul>
            <Link className="l-link" to="/marketplace">Browse the marketplace <ArrowRight size={14} aria-hidden="true" /></Link>
          </article>
        </div>
        </Reveal>
      </section>

      {/* ── Capabilities ─────────────────────────────────────── */}
      <section className="l-section l-wrap" aria-labelledby="cap-title">
        <header className="l-head">
          <p className="eyebrow">Platform</p>
          <h2 id="cap-title">What you can do today.</h2>
        </header>
        <Reveal>
        <ul className="l-grid" role="list">
          {CAPABILITIES.map(c => (
            <li key={c.title} className="l-cap">
              <span className="l-cap-icon" aria-hidden="true">{c.icon}</span>
              <h3>{c.title}</h3>
              <p>{c.text}</p>
            </li>
          ))}
        </ul>
        </Reveal>
      </section>

      {/* ── Workflow ─────────────────────────────────────────── */}
      <section className="l-band" aria-labelledby="flow-title">
        <div className="l-wrap l-section">
          <header className="l-head">
            <p className="eyebrow">Workflow</p>
            <h2 id="flow-title">From hypothesis to paper execution.</h2>
          </header>
          <WorkflowExplorer />
        </div>
      </section>

      {/* ── Trust & boundaries ───────────────────────────────── */}
      <section className="l-section l-wrap" aria-labelledby="trust-title">
        <header className="l-head">
          <p className="eyebrow">Transparency</p>
          <h2 id="trust-title">Research infrastructure, clearly labelled.</h2>
        </header>
        <Reveal>
        <div className="l-trust">
          <div className="card">
            <h3>How results are presented</h3>
            <ul className="l-ticks">
              <li><Check size={14} aria-hidden="true" /> Backtests are simulated historical results, not live performance.</li>
              <li><Check size={14} aria-hidden="true" /> Synthetic and reference datasets are identified wherever they appear.</li>
              <li><Check size={14} aria-hidden="true" /> Every outcome links back to the Version that produced it.</li>
            </ul>
          </div>
          <div className="card">
            <h3>Boundaries today</h3>
            <ul className="l-ticks l-ticks--muted">
              <li><Minus size={14} aria-hidden="true" /> Paper execution places no broker orders and uses no funded capital.</li>
              <li><Minus size={14} aria-hidden="true" /> Live broker connectivity is not available.</li>
              <li><Minus size={14} aria-hidden="true" /> Nothing on the platform is investment advice.</li>
            </ul>
          </div>
        </div>
        </Reveal>
      </section>

      {/* ── CTA ──────────────────────────────────────────────── */}
      <section className="l-wrap" aria-labelledby="cta-title">
        <div className="l-cta">
          <div>
            <h2 id="cta-title">Build the strategy. Keep the evidence.</h2>
            <p>Create an account to start your first strategy, or explore the instrument master first.</p>
          </div>
          <div className="l-actions">
            <Link className="btn btn-lg" to="/register">Create account</Link>
            <Link className="btn btn-lg btn-secondary" to="/instruments">Explore instruments</Link>
          </div>
        </div>
      </section>
    </div>
  );
}
