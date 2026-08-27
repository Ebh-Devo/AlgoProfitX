import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../../auth/roles";
import { ErrorAlert, LoadingState } from "../../components/PageState";

export function AppPage() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState />;
  const creator = hasRole(user, CREATOR_ROLE); const investor = hasRole(user, INVESTOR_ROLE);
  const name = user?.email?.split("@")[0] || "there";
  return <section className="dashboard-page"><div className="dashboard-welcome"><div><p className="eyebrow">Your command center</p><h1>Welcome back, <span>{name}</span></h1><p>Move from strategy research to discovery and paper execution with every decision pinned to a Version.</p></div><div className="inline-actions">{creator && <Link aria-label="Create Strategy" className="button" to="/creator/strategies/new">+ New strategy</Link>}<Link aria-label="Marketplace" className="button button-secondary" to="/marketplace">Discover strategies</Link></div></div>
    <div className="dashboard-stats" aria-label="Workspace capabilities"><article><span>Creator mode</span><strong>{creator ? "Active" : "Available"}</strong><small>{creator ? "Strategies & Backtests" : "Enroll without losing Investor access"}</small></article><article><span>Investor mode</span><strong>{investor ? "Active" : "Unavailable"}</strong><small>Allocation & paper execution</small></article><article><span>Market identity</span><strong>NSE · BSE</strong><small>Canonical reference Instruments</small></article><article><span>Execution</span><strong>Paper only</strong><small>No live broker connectivity</small></article></div>
    <div className="dashboard-grid">
      {creator ? <article className="card dashboard-feature"><div className="feature-icon">↗</div><p className="eyebrow">Creator workspace</p><h2>Build and evaluate</h2><p>Create strategies, bind immutable Versions to canonical Instruments, and inspect every Backtest through explainable analytics.</p><div className="dashboard-links"><Link to="/creator/strategies">Open Strategies <span>→</span></Link><Link to="/creator/strategies/new">Create a Strategy <span>+</span></Link></div></article> :
        <article className="card dashboard-feature"><div className="feature-icon">+</div><p className="eyebrow">Expand your workspace</p><h2>Become a Creator</h2><p>Creator enrollment adds systematic research tools while preserving your Investor role.</p><Link className="button" to="/creator/enroll">Enroll as Creator</Link></article>}
      {investor && <article className="card dashboard-feature"><div className="feature-icon">◎</div><p className="eyebrow">Investor workspace</p><h2>Discover and allocate</h2><p>Explore public strategies, create Version-pinned allocation intents, and understand every synthetic paper outcome.</p><div className="dashboard-links"><Link aria-label="Allocations" to="/investor/allocations">Manage Allocations <span>→</span></Link><Link aria-label="Execution Intents" to="/investor/execution-intents">Execution Intents <span>→</span></Link></div></article>}
      <article className="card dashboard-feature market-reference"><div className="feature-icon">⌁</div><p className="eyebrow">Research foundation</p><h2>Instrument Explorer</h2><p>Search equities and indices, understand tradeability, and inspect exchange, currency, lot, tick, and session metadata.</p><div className="market-strip"><span>NSE</span><span>BSE</span><span>INR</span></div><Link className="button button-secondary" to="/instruments">Browse Instruments</Link></article>
    </div>
    <div className="dashboard-disclosure"><span aria-hidden="true">i</span><p><strong>Designed for transparent research.</strong> Historical Backtests and Paper Execution are simulated workflows, never live performance or funded brokerage activity.</p></div>
  </section>;
}

export function AccountPage() {
  const { user, isLoading } = useAuth();
  if (isLoading || !user) return <LoadingState />;
  return <section><h1>Account</h1><div className="card"><dl className="details-list"><dt>Email</dt><dd>{user.email}</dd><dt>Roles</dt><dd>{user.roles.join(", ")}</dd><dt>Account status</dt><dd>{user.is_active ? "Active" : "Inactive"}</dd></dl></div></section>;
}

export function CreatorEnrollPage() {
  const { user, enrollCreator } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [complete, setComplete] = useState(false);
  const [pending, setPending] = useState(false);
  const alreadyCreator = hasRole(user, CREATOR_ROLE);
  const enroll = async () => {
    setError(null);
    if (pending) return;
    setPending(true);
    try { await enrollCreator(); setComplete(true); } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Creator enrollment failed."); } finally { setPending(false); }
  };
  return <section className="auth-card card"><h1>Creator enrollment</h1><p>Creator enrollment adds CREATOR alongside your existing INVESTOR role.</p>
    {alreadyCreator || complete ? <div className="alert alert-success">Your account has the Creator role.</div> : <button className="button" disabled={pending} onClick={enroll}>{pending ? "Enrolling…" : "Enroll as Creator"}</button>}
    {error && <ErrorAlert>{error}</ErrorAlert>}
  </section>;
}
