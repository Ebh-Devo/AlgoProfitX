import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../auth/roles";

export function AppShell() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const creator = hasRole(user, CREATOR_ROLE);
  const investor = hasRole(user, INVESTOR_ROLE);

  const endSession = () => {
    logout();
    navigate("/");
  };

  return (
    <div className="app-shell">
      <header className="site-header">
        <Link className="brand" to="/" aria-label="AlgoProfitX home"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>AlgoProfit<span>X</span></span></Link>
        <nav aria-label="Primary navigation">
          {isAuthenticated && <NavLink to="/app">Dashboard</NavLink>}
          <NavLink to="/marketplace">Marketplace</NavLink>
          <NavLink to="/instruments">Instruments</NavLink>
          {creator && <NavLink to="/creator/strategies">Strategies</NavLink>}
          {investor && <><NavLink to="/investor/allocations">Allocations</NavLink><NavLink to="/investor/execution-intents">Executions</NavLink></>}
        </nav>
        <div className="header-actions">
          {isAuthenticated ? (
            <>
              <div className="role-cluster" aria-label="Active roles">{creator && <span className="role-nav">Creator</span>}{investor && <span className="role-nav">Investor</span>}</div>
              <NavLink className="account-link" to="/account"><span className="avatar" aria-hidden="true">{user?.email?.[0]?.toUpperCase() ?? "A"}</span><span>Account</span></NavLink>
              <button className="logout-button" onClick={endSession} aria-label="Log out">↗</button>
            </>
          ) : (
            <>
              <NavLink to="/login">Log in</NavLink>
              <Link className="button" to="/register">Create account</Link>
            </>
          )}
        </div>
      </header>
      <main className="page-container"><Outlet /></main>
    </div>
  );
}
