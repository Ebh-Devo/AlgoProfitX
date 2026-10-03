import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LogOut, Menu, X } from "lucide-react";

import { useAuth } from "../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../auth/roles";
import { Brand } from "./layout/Brand";
import { SiteFooter } from "./layout/SiteFooter";
import { useDrawer } from "./layout/useDrawer";

/** Public-site shell: marketing, marketplace, instruments, login/register. */
export function AppShell() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const creator = hasRole(user, CREATOR_ROLE);
  const investor = hasRole(user, INVESTOR_ROLE);
  const { open, setOpen, toggleRef, drawerRef } = useDrawer(location.pathname);
  const isLanding = location.pathname === "/";

  const endSession = async () => {
    try { await logout(); } finally { navigate("/"); }
  };

  const links = (
    <>
      {isAuthenticated && <NavLink to="/app">Dashboard</NavLink>}
      <NavLink to="/marketplace">Marketplace</NavLink>
      <NavLink to="/instruments">Instruments</NavLink>
      {creator && <NavLink to="/creator/strategies">Strategies</NavLink>}
      {investor && (
        <>
          <NavLink to="/investor/allocations">Allocations</NavLink>
          <NavLink to="/investor/execution-intents">Executions</NavLink>
        </>
      )}
    </>
  );

  return (
    <div className={`app-shell ${isLanding ? "is-landing" : ""}`}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="site-header">
        <div className="site-header-inner">
          <Brand />
          <nav className="site-nav-desktop" aria-label="Primary navigation">{links}</nav>

          <div className="header-actions">
            {isAuthenticated ? (
              <>
                <div className="role-cluster" aria-label="Active roles">
                  {creator && <span className="role-nav">Creator</span>}
                  {investor && <span className="role-nav">Investor</span>}
                </div>
                <NavLink className="account-link" to="/account">
                  <span className="avatar" aria-hidden="true">{user?.email?.[0]?.toUpperCase() ?? "A"}</span>
                  <span>Account</span>
                </NavLink>
                <button type="button" className="icon-btn" onClick={endSession} aria-label="Log out">
                  <LogOut size={16} aria-hidden="true" />
                </button>
              </>
            ) : (
              <>
                <NavLink className="header-link" to="/login">Log in</NavLink>
                <Link className="btn btn-sm" to="/register">Create account</Link>
              </>
            )}
            <button
              ref={toggleRef}
              type="button"
              className="icon-btn mobile-menu-toggle"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              aria-controls="mobile-nav-drawer"
              onClick={() => setOpen(o => !o)}
            >
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </header>

      {open && <div className="scrim" aria-hidden="true" onClick={() => setOpen(false)} />}
      <nav
        ref={drawerRef}
        id="mobile-nav-drawer"
        tabIndex={-1}
        className={`site-drawer ${open ? "is-open" : ""}`}
        aria-label="Mobile navigation"
        aria-hidden={!open}
        {...(open ? { role: "dialog", "aria-modal": "true" } : {})}
      >
        <div className="site-drawer-links">
          {links}
          <hr />
          {isAuthenticated ? (
            <>
              <NavLink to="/account">Account</NavLink>
              <button type="button" className="site-drawer-logout" onClick={endSession}>Log out</button>
            </>
          ) : (
            <>
              <NavLink to="/login">Log in</NavLink>
              <NavLink to="/register">Create account</NavLink>
            </>
          )}
        </div>
      </nav>

      <main className={isLanding ? "landing-main" : "page-container"} id="main-content" tabIndex={-1}><Outlet /></main>
      <SiteFooter />
    </div>
  );
}
