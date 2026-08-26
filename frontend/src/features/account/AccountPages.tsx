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
  return <section><div className="page-heading"><div><p className="eyebrow">Your workspace</p><h1>Welcome back</h1><p>Continue a Creator or Investor workflow, or explore the shared Instrument reference.</p></div></div>
    <div className="card-grid">
      {creator ? <article className="card"><p className="eyebrow">Creator</p><h2>Build and evaluate</h2><p>Create strategies, bind Versions to canonical Instruments, and enter Backtests and analytics through each Version.</p><div className="inline-actions"><Link className="button" to="/creator/strategies">Strategies</Link><Link className="button button-secondary" to="/creator/strategies/new">Create Strategy</Link></div></article> :
        <article className="card"><h2>Become a Creator</h2><p>Creator enrollment keeps your Investor role.</p><Link className="button" to="/creator/enroll">Enroll as Creator</Link></article>}
      {investor && <article className="card"><p className="eyebrow">Investor</p><h2>Discover and allocate</h2><p>Explore public strategies and manage paper-only allocation and execution intents.</p><div className="inline-actions"><Link className="button" to="/marketplace">Marketplace</Link><Link className="button button-secondary" to="/investor/allocations">Allocations</Link><Link className="button button-secondary" to="/investor/execution-intents">Execution Intents</Link></div></article>}
      <article className="card"><p className="eyebrow">Reference</p><h2>Canonical Instruments</h2><p>Search equities and indices, understand tradeability, and inspect exchange, currency, lot, and tick metadata.</p><Link className="button button-secondary" to="/instruments">Browse Instruments</Link></article>
    </div>
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
