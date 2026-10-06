import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowRight, BarChart3, Check, FlaskConical, GitBranch, LineChart, Minus, Store, Wallet,
} from "lucide-react";

import { Reveal } from "../../components/ui/Reveal";
import { useReveal } from "../../lib/useReveal";
import { HeroVisual } from "./HeroVisual";
import { ProductPreview } from "./ProductPreview";
import { WorkflowExplorer } from "./WorkflowExplorer";

const CAPABILITIES = [
  { id: "cap-versioned", to: "/#stage-version", icon: <GitBranch size={18} />, title: "Versioned strategies", text: "Every change produces a new immutable Version, so a result always points to the exact configuration that produced it." },
  { id: "cap-backtesting", to: "/#stage-backtest", icon: <FlaskConical size={18} />, title: "Reference backtesting", text: "Deterministic historical simulations with provenance, so a run can be understood and repeated." },
  { id: "cap-analytics", to: "/#stage-analyze", icon: <LineChart size={18} />, title: "Analytics that explain", text: "Total return, max drawdown, win rate, profit factor, trade list and equity curve for every completed run." },
  { id: "cap-marketplace", to: "/marketplace", icon: <Store size={18} />, title: "Marketplace discovery", text: "Browse public deployed strategies without exposing a creator’s private configuration." },
  { id: "cap-allocations", to: "/#stage-allocate", icon: <Wallet size={18} />, title: "Version-pinned allocations", text: "An allocation references one Version, so you always know what it is tied to." },
  { id: "cap-instruments", to: "/instruments", icon: <BarChart3 size={18} />, title: "Instrument master", text: "NSE/BSE instrument identity, INR quote currency and session-aware design underpin every strategy." },
];

const FAQ = [
  { q: "Is this live trading?", a: "No. Backtests are simulated historical runs and paper execution is simulated. No orders are placed with a broker and no funded capital is used." },
  { q: "Where do backtest results come from?", a: "From reference or synthetic datasets that are identified wherever they appear. Results are not live performance." },
  { q: "Who can create strategies?", a: "Create an account and enroll as a Creator. Investors can browse public deployed strategies and pin allocations to a specific Version." },
  { q: "Is anything here investment advice?", a: "No. AlgoProfitX is research and simulation infrastructure. Nothing on the platform is investment advice." },
];

/** Section heading with an accent line that draws in as it enters the viewport. */
function Head({ id, eyebrow, children }: { id: string; eyebrow: string; children: ReactNode }) {
  const r = useReveal<HTMLElement>();
  return (
    <header ref={r.ref} className={`l-head ${r.className}`}>
      <p className="eyebrow">{eyebrow}</p>
      <h2 id={id}>{children}</h2>
      <span className="accent-line" aria-hidden="true" />
    </header>
  );
}

/** Scrolls to in-page anchors after client-side navigation (e.g. from the header menu). */
function useAnchorScroll() {
  const { hash, key } = useLocation();
  useEffect(() => {
    if (!hash) return;
    const raw = hash.slice(1);
    const el = document.getElementById(raw.startsWith("stage-") ? "how-it-works" : raw);
    if (!el) return;
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView?.({ behavior: calm ? "auto" : "smooth", block: "start" });
  }, [hash, key]);
}

export function HomePage() {
  useAnchorScroll();

  return (
    <div className="landing">
      {/* ── Hero ─────────────────────────────────────────────── */}
      <div className="l-hero-stage">
        <div className="l-ambient" aria-hidden="true">
          <span className="l-grid-field" />
          <span className="l-glow l-glow-a" />
          <span className="l-glow l-glow-b" />
          {[0, 1, 2, 3, 4].map(i => <span key={i} className="l-particle" style={{ ["--i" as string]: i }} />)}
        </div>

        <section className="l-hero l-wrap" aria-labelledby="hero-title">
          <div className="l-hero-copy">
            <p className="eyebrow">Systematic strategy research · Indian markets</p>
            <h1 id="hero-title">Turn a trading idea into a strategy you can <span className="l-grad">test</span>.</h1>
            <p className="lead">
              AlgoProfitX is a workspace for building versioned strategies, running historical simulations,
              publishing to a discovery marketplace and exploring allocation through paper execution.
            </p>
            <div className="l-actions">
              <Link className="btn btn-lg btn-cta" to="/register">Start building <ArrowRight size={16} aria-hidden="true" /></Link>
              <Link className="btn btn-lg btn-secondary" to="/marketplace">Explore marketplace</Link>
            </div>
            <ul className="l-proof" aria-label="Platform properties">
              <li><Check size={14} aria-hidden="true" /> NSE/BSE instrument identity</li>
              <li><Check size={14} aria-hidden="true" /> INR-native</li>
              <li><Check size={14} aria-hidden="true" /> Version-pinned</li>
              <li><Check size={14} aria-hidden="true" /> Clearly simulated</li>
            </ul>
          </div>
          <HeroVisual />
        </section>
      </div>

      {/* ── Positioning ──────────────────────────────────────── */}
      <section className="l-band" id="about" aria-labelledby="why-title">
        <Reveal stagger className="l-wrap l-why">
          <h2 id="why-title">Rules you can write down are rules you can test.</h2>
          <p>
            Systematic trading replaces in-the-moment judgement with explicit rules. The value is in being
            able to examine those rules — what they assume, how they behaved historically, and exactly which
            configuration produced a result — before capital is ever involved. AlgoProfitX is built around that
            discipline.
          </p>
        </Reveal>
      </section>

      {/* ── Audience ─────────────────────────────────────────── */}
      <section className="l-section l-wrap" aria-labelledby="audience-title">
        <Head id="audience-title" eyebrow="Who it is for">Two roles, one auditable workflow.</Head>
        <Reveal stagger className="l-audience">
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
        </Reveal>
      </section>

      {/* ── Capabilities ─────────────────────────────────────── */}
      <section className="l-section l-wrap" id="platform" aria-labelledby="cap-title">
        <Head id="cap-title" eyebrow="Platform">What you can do today.</Head>
        <Reveal stagger className="l-grid-wrap">
          <ul className="l-grid" role="list">
            {CAPABILITIES.map(c => (
              <li key={c.title} id={c.id} className="l-cap-item">
                <Link to={c.to} className="l-cap">
                  <span className="l-cap-icon" aria-hidden="true">{c.icon}</span>
                  <h3>{c.title}</h3>
                  <p>{c.text}</p>
                  <span className="l-cap-more" aria-hidden="true"><ArrowRight size={15} /></span>
                </Link>
              </li>
            ))}
          </ul>
        </Reveal>
      </section>

      {/* ── Workflow ─────────────────────────────────────────── */}
      <section className="l-band l-band--glow" id="how-it-works" aria-labelledby="flow-title">
        <div className="l-wrap l-section">
          <Head id="flow-title" eyebrow="Workflow">From hypothesis to paper execution.</Head>
          <WorkflowExplorer />
        </div>
      </section>

      {/* ── Product preview ──────────────────────────────────── */}
      <section className="l-section l-wrap" id="preview" aria-labelledby="preview-title">
        <Head id="preview-title" eyebrow="Inside the workspace">One place to see where a strategy stands.</Head>
        <ProductPreview />
      </section>

      {/* ── Trust & boundaries ───────────────────────────────── */}
      <section className="l-section l-wrap" aria-labelledby="trust-title">
        <Head id="trust-title" eyebrow="Transparency">Research infrastructure, clearly labelled.</Head>
        <Reveal stagger className="l-trust">
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
        </Reveal>
      </section>

      {/* ── FAQ ──────────────────────────────────────────────── */}
      <section className="l-section l-wrap l-faq-section" id="faq" aria-labelledby="faq-title">
        <Head id="faq-title" eyebrow="FAQ">Straight answers.</Head>
        <Reveal stagger className="l-faq">
          {FAQ.map(f => (
            <details key={f.q}>
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </Reveal>
      </section>

      {/* ── CTA ──────────────────────────────────────────────── */}
      <section className="l-wrap" id="get-started" aria-labelledby="cta-title">
        <Reveal>
          <div className="l-cta gb">
            <div>
              <h2 id="cta-title">Build the strategy. Keep the evidence.</h2>
              <p>Create an account to start your first strategy, or explore the instrument master first.</p>
            </div>
            <div className="l-actions">
              <Link className="btn btn-lg btn-cta" to="/register">Create account</Link>
              <Link className="btn btn-lg btn-secondary" to="/instruments">Explore instruments</Link>
            </div>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
