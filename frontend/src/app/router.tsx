import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter } from "react-router-dom";

import { RequireAuth, RequireCreator, RequireInvestor } from "../auth/guards";
import { AppShell } from "../components/AppShell";
import { AccountPage, AppPage, CreatorEnrollPage } from "../features/account/AccountPages";
import { LoginPage, RegisterPage } from "../features/account/AuthPages";
import { MarketplaceDetailPage, MarketplaceListPage } from "../features/marketplace/MarketplacePages";
import { LoadingState } from "../components/PageState";

const creatorPages = () => import("../features/creator/StrategyPages");
const investorAllocationPages = () => import("../features/investor/AllocationPages");
const investorExecutionPages = () => import("../features/investor/ExecutionPages");
const instrumentPages = () => import("../features/instruments/InstrumentPages");
const InstrumentListPage = lazy(async () => ({ default: (await instrumentPages()).InstrumentListPage }));
const InstrumentDetailPage = lazy(async () => ({ default: (await instrumentPages()).InstrumentDetailPage }));
const StrategyDetailPage = lazy(async () => ({ default: (await creatorPages()).StrategyDetailPage }));
const StrategyEditPage = lazy(async () => ({ default: (await creatorPages()).StrategyEditPage }));
const StrategyListPage = lazy(async () => ({ default: (await creatorPages()).StrategyListPage }));
const StrategyNewPage = lazy(async () => ({ default: (await creatorPages()).StrategyNewPage }));
const StrategyVersionPage = lazy(async () => ({ default: (await creatorPages()).StrategyVersionPage }));
const BacktestDetailPage = lazy(async () => ({ default: (await import("../features/creator/BacktestPages")).BacktestDetailPage }));
const AllocationDetailPage = lazy(async () => ({ default: (await investorAllocationPages()).AllocationDetailPage }));
const AllocationListPage = lazy(async () => ({ default: (await investorAllocationPages()).AllocationListPage }));
const ExecutionIntentDetailPage = lazy(async () => ({ default: (await investorExecutionPages()).ExecutionIntentDetailPage }));
const ExecutionIntentListPage = lazy(async () => ({ default: (await investorExecutionPages()).ExecutionIntentListPage }));

function deferred(page: ReactNode) {
  return <Suspense fallback={<LoadingState label="Loading page…" />}>{page}</Suspense>;
}

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
    { path: "instruments", element: deferred(<InstrumentListPage />) },
    { path: "instruments/:instrumentId", element: deferred(<InstrumentDetailPage />) },
    { element: <RequireAuth />, children: [
      { path: "app", element: <AppPage /> },
      { path: "account", element: <AccountPage /> },
      { path: "creator/enroll", element: <CreatorEnrollPage /> },
      { element: <RequireCreator />, children: [
        { path: "creator/strategies", element: deferred(<StrategyListPage />) },
        { path: "creator/strategies/new", element: deferred(<StrategyNewPage />) },
        { path: "creator/strategies/:strategyId", element: deferred(<StrategyDetailPage />) },
        { path: "creator/strategies/:strategyId/edit", element: deferred(<StrategyEditPage />) },
        { path: "creator/strategies/:strategyId/versions/:versionId", element: deferred(<StrategyVersionPage />) },
        { path: "creator/strategies/:strategyId/versions/:versionId/backtests/:backtestId", element: deferred(<BacktestDetailPage />) },
      ] },
      { element: <RequireInvestor />, children: [
        { path: "investor/allocations", element: deferred(<AllocationListPage />) },
        { path: "investor/allocations/:allocationId", element: deferred(<AllocationDetailPage />) },
        { path: "investor/execution-intents", element: deferred(<ExecutionIntentListPage />) },
        { path: "investor/execution-intents/:executionIntentId", element: deferred(<ExecutionIntentDetailPage />) },
      ] },
    ] },
    { path: "*", element: <NotFoundPage /> },
  ] },
]);
