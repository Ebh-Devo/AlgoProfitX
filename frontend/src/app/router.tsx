import { createBrowserRouter } from "react-router-dom";

import { RequireAuth } from "../auth/guards";
import { AppShell } from "../components/AppShell";
import { AccountPage, AppPage, CreatorEnrollPage } from "../features/account/AccountPages";
import { LoginPage, RegisterPage } from "../features/account/AuthPages";
import { MarketplaceDetailPage, MarketplaceListPage } from "../features/marketplace/MarketplacePages";

function HomePage() {
  return <section className="hero"><p className="eyebrow">Strategy marketplace</p><h1>Build, discover, and evaluate systematic strategies.</h1><p className="lead">TradeEBH separates creator strategy work from investor discovery. Paper Execution is synthetic reference infrastructure, not real NSE data or live broker execution.</p></section>;
}

function NotFoundPage() { return <section><h1>Page not found</h1></section>; }

export const router = createBrowserRouter([
  { path: "/", element: <AppShell />, children: [
    { index: true, element: <HomePage /> },
    { path: "login", element: <LoginPage /> },
    { path: "register", element: <RegisterPage /> },
    { path: "marketplace", element: <MarketplaceListPage /> },
    { path: "marketplace/:slug", element: <MarketplaceDetailPage /> },
    { element: <RequireAuth />, children: [
      { path: "app", element: <AppPage /> },
      { path: "account", element: <AccountPage /> },
      { path: "creator/enroll", element: <CreatorEnrollPage /> },
    ] },
    { path: "*", element: <NotFoundPage /> },
  ] },
]);
