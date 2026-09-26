import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Link } from "react-router-dom";
import { Check } from "lucide-react";

import { RequireAuth, RequireCreator, RequireInvestor } from "../auth/guards";
import { AppShell } from "../components/AppShell";
import { AccountPage, AppPage, CreatorEnrollPage } from "../features/account/AccountPages";
import { LoginPage, RegisterPage } from "../features/account/AuthPages";
import { MarketplaceDetailPage, MarketplaceListPage } from "../features/marketplace/MarketplacePages";
import { LoadingState } from "../components/PageState";

const creatorPages = () => import("../features/creator/StrategyPages");
const investorAllocationPages = () => import("../features/investor/AllocationPages");
const investorExecutionPages = () => import("../features/investor/ExecutionPages");
const instrumentPages = () => import("../features/instruments/InstrumentPages");
const InstrumentListPage = lazy(async () => ({ default: (await instrumentPages()).InstrumentListPage }));
const InstrumentDetailPage = lazy(async () => ({ default: (await instrumentPages()).InstrumentDetailPage }));
const StrategyDetailPage = lazy(async () => ({ default: (await creatorPages()).StrategyDetailPage }));
const StrategyEditPage = lazy(async () => ({ default: (await creatorPages()).StrategyEditPage }));
const StrategyListPage = lazy(async () => ({ default: (await creatorPages()).StrategyListPage }));
const StrategyNewPage = lazy(async () => ({ default: (await creatorPages()).StrategyNewPage }));
const StrategyVersionPage = lazy(async () => ({ default: (await creatorPages()).StrategyVersionPage }));
const BacktestDetailPage = lazy(async () => ({ default: (await import("../features/creator/BacktestPages")).BacktestDetailPage }));
const AllocationDetailPage = lazy(async () => ({ default: (await investorAllocationPages()).AllocationDetailPage }));
const AllocationListPage = lazy(async () => ({ default: (await investorAllocationPages()).AllocationListPage }));
const ExecutionIntentDetailPage = lazy(async () => ({ default: (await investorExecutionPages()).ExecutionIntentDetailPage }));
const ExecutionIntentListPage = lazy(async () => ({ default: (await investorExecutionPages()).ExecutionIntentListPage }));

function deferred(page: ReactNode) {
  return <Suspense fallback={<LoadingState label="Loading page…" />}>{page}</Suspense>;
}

export function HomePage() {
  const workflow = ["Create", "Version", "Backtest", "Analyze", "Publish", "Allocate", "Paper execute"];
  return <><div className="landing-page">
    <section className="hero premium-hero">
      <div className="hero-copy"><p className="eyebrow"><span className="live-dot" /> Systematic strategy workspace</p><h1>Turn trading ideas into <span>testable strategies.</span></h1><p className="lead">Build versioned strategies, run historical simulations, understand analytics, publish to a discovery marketplace, and explore allocation through paper execution.</p><div className="hero-actions"><Link className="button button-large" to="/register">Start building <span aria-hidden="true">→</span></Link><Link className="button button-secondary button-large" to="/marketplace">Explore marketplace</Link></div><div className="trust-row"><span><Check size={11} aria-hidden="true" />NSE/BSE identity</span><span><Check size={11} aria-hidden="true" />INR-native</span><span><Check size={11} aria-hidden="true" />Session-aware</span><span><Check size={11} aria-hidden="true" />Clearly simulated</span></div></div>
      <div className="hero-terminal" aria-label="Representative AlgoProfitX backtest dashboard">
        <div className="terminal-bar"><span><i /><i /><i /></span><strong>Momentum Alpha · Backtest</strong><span className="badge badge-completed">Completed</span></div>
        <div className="terminal-metrics"><div><small>Total return</small><strong className="positive">+18.42%</strong><em>Simulated</em></div><div><small>Max drawdown</small><strong>−6.18%</strong><em>Historical</em></div><div><small>Win rate</small><strong>61.8%</strong><em>34 trades</em></div><div><small>Profit factor</small><strong>1.74</strong><em>Reference</em></div></div>
        <div className="hero-chart"><div className="chart-grid" /><svg viewBox="0 0 600 190" role="img" aria-label="Representative rising equity curve"><defs><linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#39dfba" stopOpacity=".36"/><stop offset="1" stopColor="#39dfba" stopOpacity="0"/></linearGradient></defs><path className="chart-area" d="M0 160 C45 154 63 135 98 141 S160 112 198 123 S250 85 292 98 S355 70 390 78 S455 42 488 56 S548 25 600 20 L600 190 L0 190 Z"/><path className="chart-line" d="M0 160 C45 154 63 135 98 141 S160 112 198 123 S250 85 292 98 S355 70 390 78 S455 42 488 56 S548 25 600 20"/></svg></div>
        <div className="terminal-footer"><span><b>NSE</b> ALGOPROFITX_TEST_EQ</span><span>1d · INR</span><span>Synthetic reference dataset</span></div>
      </div>
    </section>
    <section className="workflow-section" aria-labelledby="workflow-title"><div className="section-intro"><p className="eyebrow">One auditable workflow</p><h2 id="workflow-title">From hypothesis to paper execution.</h2><p>Every stage keeps identity, configuration, and provenance explicit.</p></div><ol className="workflow-rail">{workflow.map((step, index) => <li key={step}><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong></li>)}</ol></section>
    <section className="feature-split"><article><p className="eyebrow">For creators</p><h2>Build with discipline, not guesswork.</h2><p>Model strategy ideas, bind them to canonical Instruments, create immutable Versions, and move deliberately through draft, published, deployed, and archived states.</p><div className="feature-list"><span><b>Immutable Versions</b><small>Preserve the exact configuration behind every run.</small></span><span><b>Reference Backtesting</b><small>Run deterministic historical simulations with provenance.</small></span><span><b>Analytics that explain</b><small>Return, drawdown, win rate, profit factor, trades, and equity.</small></span></div><Link to="/register">Create your workspace →</Link></article><div className="lifecycle-card card"><div className="card-kicker">Strategy lifecycle</div><div className="lifecycle-track"><span className="done">Draft</span><span className="done">Published</span><span className="active">Deployed</span><span>Archived</span></div><div className="version-preview"><small>Current version</small><strong>Version 04</strong><code>EMA crossover · NSE · 1d</code></div></div></section>
    <section className="feature-split reverse"><article><p className="eyebrow">For investors</p><h2>Discover the strategy, understand the context.</h2><p>Explore public deployed strategies without exposing private Creator configuration. Pin an allocation intent to a Version and inspect every paper outcome.</p><div className="feature-list"><span><b>Curated discovery</b><small>Clear lifecycle, Version, and public strategy context.</small></span><span><b>Version-pinned allocations</b><small>Know exactly what an allocation references.</small></span><span><b>Transparent paper outcomes</b><small>Filled, no-fill, and failed states remain unmistakable.</small></span></div><Link to="/marketplace">Browse the marketplace →</Link></article><div className="discovery-stack"><div className="mini-strategy card"><span className="badge badge-deployed">Deployed</span><small>NSE · Equity</small><h3>Momentum Alpha</h3><p>Systematic trend participation with explicit risk controls.</p><footer><span>Version 4</span><b>View strategy →</b></footer></div><div className="mini-strategy card"><span className="badge badge-published">Published</span><small>NSE · Index</small><h3>Index Regime</h3><p>Reference regime classification for market research.</p><footer><span>Version 2</span><b>View strategy →</b></footer></div></div></section>
    <section className="architecture-band"><div><p className="eyebrow">Built for Indian-market identity</p><h2>Canonical Instruments. Explicit provenance.</h2></div><div className="architecture-grid"><span><b>NSE / BSE</b><small>Exchange identity</small></span><span><b>INR</b><small>Quote currency</small></span><span><b>Sessions</b><small>Calendar-aware design</small></span><span><b>Paper</b><small>No broker execution</small></span></div></section>
    <section className="disclosure-panel"><strong>Research infrastructure, clearly labelled.</strong><p>Backtests are simulated historical results, not live performance. Paper Execution does not place broker orders or use funded capital. Synthetic and reference datasets are identified wherever they appear.</p></section>
    <section className="landing-cta"><p className="eyebrow">Start with a testable idea</p><h2>Build the strategy. Keep the evidence.</h2><p>Start building at <strong>www.algoprofitx.com</strong>.</p><div className="hero-actions"><Link className="button button-large" to="/register">Create account</Link><Link className="button button-secondary button-large" to="/instruments">Explore Instruments</Link></div></section>
  </div><SiteFooter /></>;
}

function SiteFooter() {
  return (
    <footer className="site-footer">
      <span>© {new Date().getFullYear()} AlgoProfitX · Research infrastructure. All simulations are reference data only.</span>
      <span style={{ display: "flex", gap: "1.25rem" }}>
        <Link to="/marketplace">Marketplace</Link>
        <Link to="/instruments">Instruments</Link>
      </span>
    </footer>
  );
}

function NotFoundPage() {
  return (
    <section className="fatal-page">
      <div className="fatal-card card">
        <h1>Page not found</h1>
        <p>The page you requested doesn't exist or has been moved.</p>
        <Link className="button" to="/">Go home</Link>
      </div>
    </section>
  );
}

export const router = createBrowserRouter([
  { path: "/", element: <AppShell />, children: [
    { index: true, element: <HomePage /> },
    { path: "login", element: <LoginPage /> },
    { path: "register", element: <RegisterPage /> },
    { path: "marketplace", element: <MarketplaceListPage /> },
    { path: "marketplace/:slug", element: <MarketplaceDetailPage /> },
    { path: "instruments", element: deferred(<InstrumentListPage />) },
    { path: "instruments/:instrumentId", element: deferred(<InstrumentDetailPage />) },
    { element: <RequireAuth />, children: [
      { path: "app", element: <AppPage /> },
      { path: "account", element: <AccountPage /> },
      { path: "creator/enroll", element: <CreatorEnrollPage /> },
      { element: <RequireCreator />, children: [
        { path: "creator/strategies", element: deferred(<StrategyListPage />) },
        { path: "creator/strategies/new", element: deferred(<StrategyNewPage />) },
        { path: "creator/strategies/:strategyId", element: deferred(<StrategyDetailPage />) },
        { path: "creator/strategies/:strategyId/edit", element: deferred(<StrategyEditPage />) },
        { path: "creator/strategies/:strategyId/versions/:versionId", element: deferred(<StrategyVersionPage />) },
        { path: "creator/strategies/:strategyId/versions/:versionId/backtests/:backtestId", element: deferred(<BacktestDetailPage />) },
      ] },
      { element: <RequireInvestor />, children: [
        { path: "investor/allocations", element: deferred(<AllocationListPage />) },
        { path: "investor/allocations/:allocationId", element: deferred(<AllocationDetailPage />) },
        { path: "investor/execution-intents", element: deferred(<ExecutionIntentListPage />) },
        { path: "investor/execution-intents/:executionIntentId", element: deferred(<ExecutionIntentDetailPage />) },
      ] },
    ] },
    { path: "*", element: <NotFoundPage /> },
  ] },
]);
