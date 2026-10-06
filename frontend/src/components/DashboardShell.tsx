import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3, BookOpen, ChevronRight, FlaskConical, LayoutDashboard, Lock, LogOut, Menu, Store, X, Zap,
} from "lucide-react";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../auth/roles";
import { AccountMenu } from "./layout/AccountMenu";
import { Brand } from "./layout/Brand";
import { buildCrumbs } from "./layout/breadcrumbs";
import { useDrawer } from "./layout/useDrawer";

interface NavItem { to: string; label: string; icon: ReactNode; end?: boolean }
interface NavGroup { label: string; items: NavItem[] }

function NavList({ group }: { group: NavGroup }) {
  return (
    <div className="ws-nav-group">
      <p className="ws-nav-label" id={`nav-${group.label}`}>{group.label}</p>
      <ul role="list" aria-labelledby={`nav-${group.label}`}>
        {group.items.map(item => (
          <li key={item.to}>
            <NavLink to={item.to} end={item.end} className="ws-nav-item">
              <span className="ws-nav-icon" aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DashboardShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const creator = hasRole(user, CREATOR_ROLE);
  const investor = hasRole(user, INVESTOR_ROLE);
  const { open, setOpen, toggleRef, drawerRef } = useDrawer(location.pathname);

  const endSession = async () => {
    try { await logout(); } finally { navigate("/"); }
  };

  const email = user?.email ?? "Account";
  const roles = [creator && "Creator", investor && "Investor"].filter(Boolean) as string[];
  const crumbs = buildCrumbs(location.pathname);
  const here = crumbs[crumbs.length - 1]?.label ?? "Dashboard";

  /* Keep the tab title and screen-reader context in step with client-side navigation. */
  const generic = ["Details", "Version", "Backtest", "Edit"].includes(here);
  const title = [here, ...(generic && crumbs.length > 2 ? [crumbs[crumbs.length - 2].label] : []), "AlgoProfitX"].join(" · ");
  useEffect(() => { document.title = title; }, [title]);

  const groups: NavGroup[] = [
    { label: "Overview", items: [{ to: "/app", label: "Dashboard", icon: <LayoutDashboard size={17} />, end: true }] },
    ...(creator
      ? [{ label: "Build", items: [{ to: "/creator/strategies", label: "Strategies", icon: <FlaskConical size={17} /> }] }]
      : []),
    ...(investor
      ? [{
          label: "Invest",
          items: [
            { to: "/investor/allocations", label: "Allocations", icon: <BookOpen size={17} /> },
            { to: "/investor/execution-intents", label: "Executions", icon: <Zap size={17} /> },
          ],
        }]
      : []),
    {
      label: "Discover",
      items: [
        { to: "/marketplace", label: "Marketplace", icon: <Store size={17} /> },
        { to: "/instruments", label: "Instruments", icon: <BarChart3 size={17} /> },
      ],
    },
  ];

  const sidebar = (
    <>
      {groups.map(g => <NavList key={g.label} group={g} />)}
      <div className="ws-nav-group">
        <p className="ws-nav-label">Coming soon</p>
        <span className="ws-nav-item is-disabled" aria-disabled="true">
          <span className="ws-nav-icon" aria-hidden="true"><BarChart3 size={17} /></span>
          <span>Analytics</span>
          <Lock size={12} className="ws-nav-lock" aria-label="Not yet available" />
        </span>
        {!creator && <Link className="ws-cta" to="/creator/enroll">Become a creator <ChevronRight size={14} aria-hidden="true" /></Link>}
      </div>
    </>
  );

  return (
    <div className="workspace">
      <a className="skip-link" href="#main-content">Skip to content</a>

      <aside className="ws-sidebar">
        <div className="ws-sidebar-head"><Brand to="/app" /></div>
        <nav className="ws-nav" aria-label="Application navigation">{sidebar}</nav>
        <div className="ws-sidebar-foot">
          <div className="ws-identity" title={email}>
            <span className="avatar" aria-hidden="true">{(email[0] ?? "A").toUpperCase()}</span>
            <span className="ws-identity-text">
              <strong>{email}</strong>
              <small>{roles.length ? roles.join(" · ") : "Member"}</small>
            </span>
          </div>
          <span className="env-chip" title="Backtests and paper execution are simulated. No broker orders are placed.">
            <span className="env-dot" aria-hidden="true" /> Simulated · Paper
          </span>
        </div>
      </aside>

      <div className="ws-body">
        <header className="ws-topbar" role="banner">
          <button
            ref={toggleRef}
            type="button"
            className="icon-btn ws-menu-toggle"
            aria-label={open ? "Close navigation" : "Open navigation"}
            aria-expanded={open}
            aria-controls="ws-drawer"
            onClick={() => setOpen(o => !o)}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>

          <nav className="crumbs" aria-label="Breadcrumb">
            <ol>
              {crumbs.map((c, i) => (
                <li key={`${c.label}-${i}`}>
                  {c.to ? <Link to={c.to}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
                </li>
              ))}
            </ol>
          </nav>

          <div className="ws-topbar-right">
            <span className="env-chip env-chip--compact" title="Backtests and paper execution are simulated. No broker orders are placed.">
              <span className="env-dot" aria-hidden="true" /> Paper
            </span>
            <AccountMenu email={email} roles={roles} onLogout={endSession} />
          </div>
        </header>

        <main className="ws-main" id="main-content" tabIndex={-1}>
          <div className="ws-content">
            <span className="visually-hidden" role="status" aria-live="polite">{`${here} page`}</span>
            <div className="route-view" key={location.pathname}><Outlet /></div>
          </div>
        </main>
      </div>

      {open && <div className="scrim" aria-hidden="true" onClick={() => setOpen(false)} />}
      <nav
        ref={drawerRef}
        id="ws-drawer"
        tabIndex={-1}
        className={`ws-drawer ${open ? "is-open" : ""}`}
        aria-label="Mobile application navigation"
        aria-hidden={!open}
        {...(open ? { role: "dialog", "aria-modal": "true" } : {})}
      >
        <div className="ws-sidebar-head"><Brand to="/app" /></div>
        <div className="ws-nav">{sidebar}</div>
        <div className="ws-sidebar-foot">
          <div className="ws-identity">
            <span className="avatar" aria-hidden="true">{(email[0] ?? "A").toUpperCase()}</span>
            <span className="ws-identity-text">
              <strong>{email}</strong>
              <small>{roles.length ? roles.join(" · ") : "Member"}</small>
            </span>
          </div>
          <button type="button" className="btn btn-secondary ws-logout" onClick={endSession}>
            <LogOut size={15} aria-hidden="true" /> Log out
          </button>
        </div>
      </nav>
    </div>
  );
}
