import { useState, useEffect } from "react";
import { Link, NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { Menu, X, LogOut } from "lucide-react";

import { useAuth } from "../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../auth/roles";

export function AppShell() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const creator  = hasRole(user, CREATOR_ROLE);
  const investor = hasRole(user, INVESTOR_ROLE);
  const [mobileOpen, setMobileOpen] = useState(false);

  /* Close drawer on route change */
  useEffect(() => { setMobileOpen(false); }, [location.pathname]);

  /* Prevent body scroll while drawer is open */
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileOpen]);

  const endSession = async () => {
    try { await logout(); }
    finally { navigate("/"); }
  };

  return (
    <div className="app-shell">
      <header className="site-header">
        <Link className="brand" to="/" aria-label="AlgoProfitX home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>AlgoProfit<span>X</span></span>
        </Link>

        {/* Desktop nav */}
        <nav className="site-nav-desktop" aria-label="Primary navigation">
          {isAuthenticated && <NavLink to="/app">Dashboard</NavLink>}
          <NavLink to="/marketplace">Marketplace</NavLink>
          <NavLink to="/instruments">Instruments</NavLink>
          {creator  && <NavLink to="/creator/strategies">Strategies</NavLink>}
          {investor && <>
            <NavLink to="/investor/allocations">Allocations</NavLink>
            <NavLink to="/investor/execution-intents">Executions</NavLink>
          </>}
        </nav>

        {/* Desktop actions */}
        <div className="header-actions">
          {isAuthenticated ? (
            <>
              <div className="role-cluster" aria-label="Active roles">
                {creator  && <span className="role-nav">Creator</span>}
                {investor && <span className="role-nav">Investor</span>}
              </div>
              <NavLink className="account-link" to="/account">
                <span className="avatar" aria-hidden="true">{user?.email?.[0]?.toUpperCase() ?? "A"}</span>
                <span>Account</span>
              </NavLink>
              <button className="logout-button" onClick={endSession} aria-label="Log out">
                <LogOut size={15} aria-hidden="true" />
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login">Log in</NavLink>
              <Link className="button" to="/register">Create account</Link>
            </>
          )}

          {/* Hamburger — mobile only */}
          <button
            className="mobile-menu-toggle"
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav-drawer"
            onClick={() => setMobileOpen(o => !o)}
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </header>

      {/* Mobile drawer overlay */}
      {mobileOpen && (
        <div
          className="mobile-nav-overlay"
          aria-hidden="true"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile drawer */}
      <nav
        id="mobile-nav-drawer"
        className={`mobile-nav-drawer ${mobileOpen ? "mobile-nav-drawer--open" : ""}`}
        aria-label="Mobile navigation"
      >
        <div className="mobile-nav-inner">
          {isAuthenticated && <NavLink to="/app">Dashboard</NavLink>}
          <NavLink to="/marketplace">Marketplace</NavLink>
          <NavLink to="/instruments">Instruments</NavLink>
          {creator  && <NavLink to="/creator/strategies">Strategies</NavLink>}
          {investor && <>
            <NavLink to="/investor/allocations">Allocations</NavLink>
            <NavLink to="/investor/execution-intents">Executions</NavLink>
          </>}
          <div className="mobile-nav-divider" />
          {isAuthenticated ? (
            <>
              <NavLink to="/account">Account</NavLink>
              <button className="mobile-nav-logout" onClick={endSession}>Log out</button>
            </>
          ) : (
            <>
              <NavLink to="/login">Log in</NavLink>
              <NavLink to="/register">Create account</NavLink>
            </>
          )}
        </div>
      </nav>

      <main className="page-container"><Outlet /></main>
    </div>
  );
  /* Note: SiteFooter is rendered inside HomePage for landing context;
     the app shell itself does not include a footer. */
}
