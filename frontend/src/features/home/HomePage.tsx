import { Link } from "react-router-dom";

const sparkline = "M4 52 C 28 50, 36 18, 58 28 S 92 8, 118 16 S 156 48, 188 30 S 228 12, 268 22 S 308 46, 348 20";

const journeys = [
  {
    kicker: "01",
    title: "Create",
    body: "Draft systematic strategies, pin them to canonical instruments, and freeze immutable versions.",
  },
  {
    kicker: "02",
    title: "Prove",
    body: "Run deterministic reference backtests and inspect return, drawdown, and equity-curve analytics.",
  },
  {
    kicker: "03",
    title: "Discover",
    body: "Browse published strategies in a public marketplace that never exposes private configuration.",
  },
  {
    kicker: "04",
    title: "Allocate",
    body: "Pin notional intents to a version, then execute paper fills on synthetic NSE/INR reference data.",
  },
];

const pillars = [
  { title: "Versioned by design", copy: "Every allocation pins a specific strategy version. History stays coherent as creators iterate." },
  { title: "Reference, not live", copy: "Backtests and paper execution use synthetic candles. No broker, no funded capital, no live NSE feed." },
  { title: "Role-aware workspace", copy: "Investors start immediately. Creators enroll without losing investor access." },
];

export function HomePage() {
  return (
    <div className="home">
      <section className="hero home-hero">
        <div className="home-hero-copy">
          <p className="eyebrow">Strategy marketplace</p>
          <h1>Build, discover, and evaluate systematic strategies.</h1>
          <p className="lead">
            TradeEBH separates creator strategy work from investor discovery. Paper Execution is synthetic
            reference infrastructure, not real NSE data or live broker execution.
          </p>
          <div className="hero-actions">
            <Link className="button" to="/register">
              Create account
            </Link>
            <Link className="button button-secondary" to="/marketplace">
              Browse marketplace
            </Link>
          </div>
          <ul className="hero-meta">
            <li>Immutable versions</li>
            <li>Reference backtests</li>
            <li>Paper-only execution</li>
          </ul>
        </div>
        <aside className="hero-panel" aria-hidden="true">
          <div className="hero-panel-glow" />
          <div className="hero-panel-card">
            <div className="hero-panel-top">
              <span className="badge badge-deployed">deployed</span>
              <span className="muted">TRADEEBH_TEST_EQ</span>
            </div>
            <p className="hero-panel-kicker">Reference equity curve</p>
            <strong className="hero-panel-value">+10.42%</strong>
            <svg className="hero-spark" viewBox="0 0 352 64" fill="none">
              <defs>
                <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path d={`${sparkline} L 348 64 L 4 64 Z`} fill="url(#sparkFill)" />
              <path d={sparkline} stroke="var(--accent-hover)" strokeWidth="2.4" />
            </svg>
            <div className="hero-ticks">
              <span>Win rate 61%</span>
              <span>Max DD 5.0%</span>
              <span>Paper · INR</span>
            </div>
          </div>
        </aside>
      </section>

      <section className="home-band">
        {pillars.map((pillar) => (
          <article className="home-pillar" key={pillar.title}>
            <h2>{pillar.title}</h2>
            <p>{pillar.copy}</p>
          </article>
        ))}
      </section>

      <section className="home-journey">
        <div className="section-heading">
          <div>
            <p className="eyebrow">How it works</p>
            <h2>A controlled path from idea to paper fill</h2>
          </div>
        </div>
        <div className="journey-grid">
          {journeys.map((step) => (
            <article className="card journey-card" key={step.kicker}>
              <span className="journey-index">{step.kicker}</span>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="home-cta card">
        <div>
          <p className="eyebrow">Start on paper</p>
          <h2>Open a workspace in minutes</h2>
          <p>New accounts begin as Investors. Enroll as a Creator whenever you are ready to publish.</p>
        </div>
        <div className="inline-actions">
          <Link className="button" to="/register">
            Create account
          </Link>
          <Link className="button button-secondary" to="/login">
            Log in
          </Link>
        </div>
      </section>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <section className="empty-panel">
      <p className="eyebrow">404</p>
      <h1>Page not found</h1>
      <p>That route is not part of the TradeEBH workspace.</p>
      <Link className="button" to="/">
        Back home
      </Link>
    </section>
  );
}
