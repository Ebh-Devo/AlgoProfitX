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
        <Link className="brand" to="/">TradeEBH</Link>
        <nav aria-label="Primary navigation">
          <NavLink to="/marketplace">Marketplace</NavLink>
          {isAuthenticated && <NavLink to="/app">Workspace</NavLink>}
          {creator && <><NavLink to="/creator/strategies">Strategies</NavLink><span className="role-nav">Creator</span></>}
          {investor && <span className="role-nav">Investor</span>}
        </nav>
        <div className="header-actions">
          {isAuthenticated ? (
            <>
              <NavLink to="/account">Account</NavLink>
              <button className="button button-secondary" onClick={endSession}>Log out</button>
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
