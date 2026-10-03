import { Link } from "react-router-dom";
import { Brand } from "./Brand";

export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="site-footer" aria-label="Site footer">
      <div className="site-footer-inner">
        <div className="site-footer-brand">
          <Brand plain />
          <p className="footer-disclaimer">
            Research infrastructure. Backtests and paper execution results are simulated reference data.
            No broker orders are placed and no funded capital is used.
          </p>
          <p className="footer-copyright">© {year} AlgoProfitX. All rights reserved.</p>
        </div>
        <nav className="site-footer-nav" aria-label="Footer navigation">
          <div className="footer-nav-group">
            <h2>Platform</h2>
            <Link to="/marketplace">Marketplace</Link>
            <Link to="/instruments">Instruments</Link>
          </div>
          <div className="footer-nav-group">
            <h2>Account</h2>
            <Link to="/login">Sign in</Link>
            <Link to="/register">Create account</Link>
          </div>
        </nav>
      </div>
    </footer>
  );
}
