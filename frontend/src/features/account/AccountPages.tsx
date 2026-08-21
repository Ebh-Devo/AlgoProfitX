import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/auth-context";
import { CREATOR_ROLE, hasRole } from "../../auth/roles";
import { ErrorAlert, LoadingState } from "../../components/PageState";

export function AppPage() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState />;
  return <section><h1>Workspace</h1><p>Choose a product journey from your available roles.</p>
    <div className="card-grid">
      {hasRole(user, CREATOR_ROLE) ? <article className="card"><h2>Creator</h2><p>Create, version, and manage the lifecycle of your strategies.</p><Link className="button" to="/creator/strategies">Manage strategies</Link></article> :
        <article className="card"><h2>Become a Creator</h2><p>Creator enrollment keeps your Investor role.</p><Link className="button" to="/creator/enroll">Enroll as Creator</Link></article>}
      <article className="card"><h2>Investor</h2><p>Browse strategies and manage paper allocation and execution intents.</p><div className="inline-actions"><Link className="button button-secondary" to="/marketplace">Browse Marketplace</Link><Link className="button" to="/investor/allocations">Manage allocations</Link></div></article>
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
  const alreadyCreator = hasRole(user, CREATOR_ROLE);
  const enroll = async () => {
    setError(null);
    try { await enrollCreator(); setComplete(true); } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Creator enrollment failed."); }
  };
  return <section className="auth-card card"><h1>Creator enrollment</h1><p>Creator enrollment adds CREATOR alongside your existing INVESTOR role.</p>
    {alreadyCreator || complete ? <div className="alert alert-success">Your account has the Creator role.</div> : <button className="button" onClick={enroll}>Enroll as Creator</button>}
    {error && <ErrorAlert>{error}</ErrorAlert>}
  </section>;
}
