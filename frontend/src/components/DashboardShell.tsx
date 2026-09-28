import { useState, useEffect, useRef } from "react";
import { Link, NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Store,
  BookOpen,
  FlaskConical,
  BarChart3,
  User,
  LogOut,
  Menu,
  X,
  ChevronRight,
  Lock,
  Zap,
} from "lucide-react";

import { useAuth } from "../auth/auth-context";
import { CREATOR_ROLE, hasRole, INVESTOR_ROLE } from "../auth/roles";

/* ─── Nav item shapes ──────────────────────────────────────────── */
interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  /** true → show always; false → creator; null → investor */
  always?: boolean;
  requiresCreator?: boolean;
  requiresInvestor?: boolean;
  comingSoon?: boolean;
}

/* ─── Coming-soon decorative item ─────────────────────────────── */
function ComingSoonItem({ label, icon }: { label: string; icon: React.ReactNode }) {
  return (
    <span className="sidebar-nav-item sidebar-nav-item--disabled" aria-disabled="true" title={`${label} — coming soon`}>
      <span className="sidebar-nav-icon" aria-hidden="true">{icon}</span>
      <span className="sidebar-nav-label">{label}</span>
      <span className="sidebar-nav-badge" aria-label="coming soon"><Lock size={10} /></span>
    </span>
  );
}

/* ─── Main DashboardShell ──────────────────────────────────────── */
export function DashboardShell() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const creator = hasRole(user, CREATOR_ROLE);
  const investor = hasRole(user, INVESTOR_ROLE);
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleBtnRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const prevOpenRef = useRef(mobileOpen);

  /* Close drawer on route change */
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  /* Prevent body scroll while drawer is open */
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileOpen]);

  /* Mobile drawer accessibility: focus trap, Escape, restore focus */
  useEffect(() => {
    if (mobileOpen) {
      const focusables = drawerRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (focusables && focusables.length > 0) focusables[0].focus();
      else drawerRef.current?.focus();

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") { setMobileOpen(false); return; }
        if (e.key === "Tab" && drawerRef.current) {
          const all = Array.from(
            drawerRef.current.querySelectorAll<HTMLElement>(
              'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )
          );
          if (!all.length) return;
          const first = all[0], last = all[all.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    } else if (prevOpenRef.current) {
      toggleBtnRef.current?.focus();
    }
  }, [mobileOpen]);

  useEffect(() => { prevOpenRef.current = mobileOpen; }, [mobileOpen]);

  const endSession = async () => {
    try { await logout(); } finally { navigate("/"); }
  };

  const displayName = user?.email?.split("@")[0] ?? "Account";
  const initials = (user?.email?.[0] ?? "A").toUpperCase();

  /* ── Nav groups ─────────────────────────────────────────────── */
  const primaryNav: NavItem[] = [
    { to: "/app", label: "Dashboard", icon: <LayoutDashboard size={18} />, always: true },
    { to: "/marketplace", label: "Marketplace", icon: <Store size={18} />, always: true },
  ];

  const workspaceNav: NavItem[] = [
    ...(creator ? [{ to: "/creator/strategies", label: "Strategies", icon: <BookOpen size={18} /> }] : []),
    ...(creator ? [{ to: "/creator/strategies", label: "Backtesting", icon: <FlaskConical size={18} />, comingSoon: false }] : []),
    ...(investor ? [{ to: "/investor/allocations", label: "Allocations", icon: <Zap size={18} /> }] : []),
  ];

  const comingSoonNav = [
    ...(!creator ? [{ label: "Strategies", icon: <BookOpen size={18} /> }] : []),
    { label: "Analytics", icon: <BarChart3 size={18} /> },
  ];

  return (
    <div className="dashboard-shell">
      {/* ── App header (mobile only compact header + desktop brand) */}
      <header className="dash-header" role="banner">
        <Link className="dash-brand" to="/" aria-label="AlgoProfitX home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>AlgoProfit<span>X</span></span>
        </Link>

        {/* Desktop: right-side account info */}
        <div className="dash-header-right">
          <div className="dash-role-cluster" aria-label="Active roles">
            {creator && <span className="role-pill role-pill--creator">Creator</span>}
            {investor && <span className="role-pill role-pill--investor">Investor</span>}
          </div>
          <NavLink className="dash-account-link" to="/account" aria-label="Account settings">
            <span className="dash-avatar" aria-hidden="true">{initials}</span>
            <span className="dash-account-name">{displayName}</span>
          </NavLink>
          <button className="dash-logout-btn" onClick={endSession} aria-label="Log out">
            <LogOut size={15} aria-hidden="true" />
          </button>
        </div>

        {/* Mobile hamburger */}
        <button
          ref={toggleBtnRef}
          className="dash-mobile-toggle"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileOpen}
          aria-controls="dash-mobile-nav"
          onClick={() => setMobileOpen(o => !o)}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </header>

      <div className="dash-body">
        {/* ── Persistent sidebar (desktop) ─────────────────────── */}
        <nav className="dash-sidebar" aria-label="Application navigation">
          <SidebarContent
            primaryNav={primaryNav}
            workspaceNav={workspaceNav}
            comingSoonNav={comingSoonNav}
            creator={creator}
            investor={investor}
            displayName={displayName}
            initials={initials}
            isAuthenticated={isAuthenticated}
            onLogout={endSession}
            mobile={false}
          />
        </nav>

        {/* ── Main content ─────────────────────────────────────── */}
        <main className="dash-main" id="main-content">
          <Outlet />
        </main>
      </div>

      {/* ── Mobile overlay ───────────────────────────────────────── */}
      {mobileOpen && (
        <div
          className="dash-mobile-overlay"
          aria-hidden="true"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ── Mobile nav drawer ────────────────────────────────────── */}
      <nav
        ref={drawerRef}
        id="dash-mobile-nav"
        tabIndex={-1}
        className={`dash-mobile-drawer ${mobileOpen ? "dash-mobile-drawer--open" : ""}`}
        aria-label="Mobile application navigation"
        aria-modal={mobileOpen ? "true" : undefined}
        aria-hidden={!mobileOpen}
        role="dialog"
      >
        <SidebarContent
          primaryNav={primaryNav}
          workspaceNav={workspaceNav}
          comingSoonNav={comingSoonNav}
          creator={creator}
          investor={investor}
          displayName={displayName}
          initials={initials}
          isAuthenticated={isAuthenticated}
          onLogout={endSession}
          mobile={true}
        />
      </nav>
    </div>
  );
}

/* ─── Shared sidebar content ───────────────────────────────────── */
interface SidebarContentProps {
  primaryNav: NavItem[];
  workspaceNav: NavItem[];
  comingSoonNav: { label: string; icon: React.ReactNode }[];
  creator: boolean;
  investor: boolean;
  displayName: string;
  initials: string;
  isAuthenticated: boolean;
  onLogout: () => void;
  mobile: boolean;
}

function SidebarContent({
  primaryNav,
  workspaceNav,
  comingSoonNav,
  creator,
  investor,
  displayName,
  initials,
  onLogout,
  mobile,
}: SidebarContentProps) {
  return (
    <div className="sidebar-inner">
      {/* Brand (mobile drawer) */}
      {mobile && (
        <div className="sidebar-brand-row">
          <Link className="dash-brand" to="/" aria-label="AlgoProfitX home">
            <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
            <span>AlgoProfit<span>X</span></span>
          </Link>
        </div>
      )}

      {/* Primary nav */}
      <div className="sidebar-section">
        <p className="sidebar-section-label">Navigation</p>
        <ul role="list" className="sidebar-nav-list">
          {primaryNav.map(item => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/app"}
                className={({ isActive }) =>
                  `sidebar-nav-item ${isActive ? "sidebar-nav-item--active" : ""}`
                }
                aria-current={undefined}
              >
                {({ isActive }) => (
                  <>
                    <span className="sidebar-nav-icon" aria-hidden="true">{item.icon}</span>
                    <span className="sidebar-nav-label">{item.label}</span>
                    {isActive && <ChevronRight size={14} className="sidebar-nav-chevron" aria-hidden="true" />}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>

      {/* Workspace nav */}
      {(creator || investor) && (
        <div className="sidebar-section">
          <p className="sidebar-section-label">Workspace</p>
          <ul role="list" className="sidebar-nav-list">
            {workspaceNav.map(item => (
              <li key={`${item.to}-${item.label}`}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    `sidebar-nav-item ${isActive ? "sidebar-nav-item--active" : ""}`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span className="sidebar-nav-icon" aria-hidden="true">{item.icon}</span>
                      <span className="sidebar-nav-label">{item.label}</span>
                      {isActive && <ChevronRight size={14} className="sidebar-nav-chevron" aria-hidden="true" />}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
            {investor && (
              <li>
                <NavLink
                  to="/investor/execution-intents"
                  className={({ isActive }) =>
                    `sidebar-nav-item ${isActive ? "sidebar-nav-item--active" : ""}`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span className="sidebar-nav-icon" aria-hidden="true"><Zap size={18} /></span>
                      <span className="sidebar-nav-label">Executions</span>
                      {isActive && <ChevronRight size={14} className="sidebar-nav-chevron" aria-hidden="true" />}
                    </>
                  )}
                </NavLink>
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Coming-soon / enrollment CTA */}
      {(!creator || comingSoonNav.length > 0) && (
        <div className="sidebar-section">
          <p className="sidebar-section-label">Coming soon</p>
          <ul role="list" className="sidebar-nav-list">
            {comingSoonNav.map(item => (
              <li key={item.label}>
                <ComingSoonItem label={item.label} icon={item.icon} />
              </li>
            ))}
          </ul>
          {!creator && (
            <Link className="sidebar-enroll-cta" to="/creator/enroll">
              Become a Creator →
            </Link>
          )}
        </div>
      )}

      {/* Instruments */}
      <div className="sidebar-section">
        <p className="sidebar-section-label">Research</p>
        <ul role="list" className="sidebar-nav-list">
          <li>
            <NavLink
              to="/instruments"
              className={({ isActive }) =>
                `sidebar-nav-item ${isActive ? "sidebar-nav-item--active" : ""}`
              }
            >
              {({ isActive }) => (
                <>
                  <span className="sidebar-nav-icon" aria-hidden="true"><BarChart3 size={18} /></span>
                  <span className="sidebar-nav-label">Instruments</span>
                  {isActive && <ChevronRight size={14} className="sidebar-nav-chevron" aria-hidden="true" />}
                </>
              )}
            </NavLink>
          </li>
        </ul>
      </div>

      {/* Spacer */}
      <div className="sidebar-spacer" aria-hidden="true" />

      {/* Account + logout */}
      <div className="sidebar-footer">
        <NavLink
          className={({ isActive }) =>
            `sidebar-account-row ${isActive ? "sidebar-account-row--active" : ""}`
          }
          to="/account"
          aria-label="Account settings"
        >
          <span className="sidebar-footer-avatar" aria-hidden="true">{initials}</span>
          <div className="sidebar-footer-info">
            <span className="sidebar-footer-name">{displayName}</span>
            <span className="sidebar-footer-role">
              {creator && investor ? "Creator · Investor" : creator ? "Creator" : "Investor"}
            </span>
          </div>
          <User size={14} className="sidebar-footer-icon" aria-hidden="true" />
        </NavLink>
        <button className="sidebar-logout-btn" onClick={onLogout} aria-label="Log out of AlgoProfitX">
          <LogOut size={15} aria-hidden="true" />
          <span>Log out</span>
        </button>
      </div>
    </div>
  );
}

