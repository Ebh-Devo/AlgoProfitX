import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { LogOut, Menu, X } from "lucide-react";

import { useAuth } from "../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../auth/roles";
import { Brand } from "./layout/Brand";
import { PUBLIC_NAV, PublicNav } from "./layout/PublicNav";
import { ThemeCycleButton, ThemeSelector } from "./theme/ThemeSelector";
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
  const [scrolled, setScrolled] = useState(false);

  /* Public pages own the tab title; the workspace shell sets its own on entry. */
  useEffect(() => {
    const section = location.pathname.split("/").filter(Boolean)[0];
    document.title = section
      ? `${section.charAt(0).toUpperCase()}${section.slice(1)} · AlgoProfitX`
      : "AlgoProfitX — Testable Strategy Research";
  }, [location.pathname]);

  /* The landing header floats over the hero and picks up a surface once the page scrolls. */
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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
      <header className={`site-header${scrolled ? " is-scrolled" : ""}`}>
        <div className="site-header-inner">
          <Brand />
          {isAuthenticated
            ? <nav className="site-nav-desktop" aria-label="Primary navigation">{links}</nav>
            : <PublicNav />}

          <div className="header-actions">
            <span className="theme-cycle-wrap"><ThemeCycleButton /></span>
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
                <Link className="btn btn-sm btn-cta" to="/register">Get Started</Link>
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
        onClick={e => { if ((e.target as HTMLElement).closest("a")) setOpen(false); }}
        {...(open ? { role: "dialog", "aria-modal": "true" } : {})}
      >
        <div className="site-drawer-links">
          <div className="site-drawer-theme"><span className="menu-group-label">Appearance</span><ThemeSelector /></div>
          {isAuthenticated ? links : (
            <>
              {PUBLIC_NAV.map(entry => entry.children ? (
                <div className="site-drawer-group" key={entry.label} role="group" aria-label={entry.label}>
                  <p>{entry.label}</p>
                  {entry.children.map(c => c.to
                    ? <Link key={c.label} to={c.to}>{c.label}<small>{c.description}</small></Link>
                    : <span key={c.label} className="is-soon" aria-disabled="true">{c.label}<em>Coming soon</em></span>)}
                </div>
              ) : <Link key={entry.label} to={entry.to!}>{entry.label}</Link>)}
            </>
          )}
          <hr />
          {isAuthenticated ? (
            <>
              <NavLink to="/account">Account</NavLink>
              <button type="button" className="site-drawer-logout" onClick={endSession}>Log out</button>
            </>
          ) : (
            <>
              <NavLink to="/login">Log in</NavLink>
              <Link className="btn btn-cta site-drawer-cta" to="/register">Get Started</Link>
            </>
          )}
        </div>
      </nav>

      <main className={isLanding ? "landing-main" : "page-container"} id="main-content" tabIndex={-1}><Outlet /></main>
      <SiteFooter />
    </div>
  );
}
