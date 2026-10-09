import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";

import css from "../../styles/marketplace-backtest.css?raw";
import type { MarketplaceStrategy } from "../../api/types";
import { BacktestWorkspaceView, MarketplaceBacktestPage } from "./BacktestWorkspace";
import { MarketplaceDetailPage } from "./MarketplacePages";
import {
  MARKETPLACE_BACKTEST_SUPPORT,
  resolveDisplayState,
  validateStartingCapital,
  type ExecutionView,
  type ResultView,
} from "./backtestContract";

const api = vi.hoisted(() => ({ list: vi.fn(), getBySlug: vi.fn() }));
vi.mock("../../api/marketplace", () => ({ marketplaceApi: api }));
vi.mock("../creator/EquityChart", () => ({ EquityChart: () => <div data-testid="equity-chart" /> }));

const strategy: MarketplaceStrategy = {
  id: "id-1", slug: "trend-momentum", name: "Trend Momentum", description: "Trend following",
  status: "published", published_at: "2025-01-01T00:00:00Z", current_version_id: "abcdef12-0000", current_version_number: 3,
};

function renderRoutes(initial: string) {
  const router = createMemoryRouter(
    [
      { path: "/marketplace/:slug", element: <MarketplaceDetailPage /> },
      { path: "/marketplace/:slug/backtest", element: <MarketplaceBacktestPage /> },
    ],
    { initialEntries: [initial] },
  );
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function renderView(execution: ExecutionView, onRun?: (c: string) => void) {
  const router = createMemoryRouter([{ path: "/", element: <BacktestWorkspaceView strategy={strategy} execution={execution} onRun={onRun} /> }]);
  return render(<RouterProvider router={router} />);
}

// TEST FIXTURE ONLY: never imported by application code.
const FIXTURE_RESULT: ResultView = {
  startingCapital: "50000", netProfitLoss: "1250.50", returnPercent: "2.501", maxDrawdown: "4.2", tradeCount: 2,
  equityCurve: [{ timestamp: "2025-01-01T00:00:00Z", equity: "50000" }, { timestamp: "2025-01-02T00:00:00Z", equity: "51250.5" }],
  trades: [{ side: "buy", entryTimestamp: "2025-01-01T00:00:00Z", exitTimestamp: "2025-01-02T00:00:00Z", quantity: "10", entryPrice: "100", exitPrice: "112", pnl: "120" }],
  provenance: { dataSource: "fixture-provider", synthetic: true, timeframe: "1d", fillModel: "same_bar_close", fees: null, slippage: null, engine: "engine-x", definitionVersion: "2", limitations: ["Fixture limitation"] },
};

describe("Marketplace profile", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the four sections and links to the Backtest workspace", async () => {
    api.getBySlug.mockResolvedValue(strategy);
    renderRoutes("/marketplace/trend-momentum");
    for (const name of ["Strategy Metadata", "Strategy Transparency", "Strategy Allocation", "Backtest & Performance"]) {
      expect(await screen.findByRole("heading", { name })).toBeInTheDocument();
    }
    expect(screen.getAllByText("Version 3").length).toBeGreaterThan(0);
    const cta = screen.getByRole("link", { name: /open backtest workspace/i });
    expect(cta).toHaveAttribute("href", "/marketplace/trend-momentum/backtest");
    expect(screen.queryByText(/verified (strategy|backtest)/i)).not.toBeInTheDocument();
    expect(screen.getByText(/no performance, rating or independent verification is claimed/i)).toBeInTheDocument();
    await userEvent.click(cta);
    expect(await screen.findByText("Backtest workspace")).toBeInTheDocument();
  });
});

describe("Backtest workspace (route)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows strategy and version identity, is unavailable, and fabricates nothing", async () => {
    api.getBySlug.mockResolvedValue(strategy);
    renderRoutes("/marketplace/trend-momentum/backtest");
    expect(await screen.findByRole("heading", { name: "Trend Momentum" })).toBeInTheDocument();
    expect(screen.getByText("Version 3")).toBeInTheDocument();
    expect(screen.getByText("abcdef12")).toBeInTheDocument();
    expect(screen.getByTestId("execution-status")).toHaveAttribute("data-state", "unavailable");
    expect(screen.getByText(MARKETPLACE_BACKTEST_SUPPORT.reason, { exact: false, selector: ".alert, .alert *" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run backtest/i })).toBeDisabled();
    expect(screen.getByTestId("performance-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("performance-results")).not.toBeInTheDocument();
    expect(screen.queryByTestId("equity-chart")).not.toBeInTheDocument();
    expect(screen.queryByText(/net profit/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("Not available").length).toBe(7);
    expect(screen.getByText(/unavailable until a supported backtest result is returned/i)).toBeInTheDocument();
    expect(screen.getByText(/no backtest has been run/i)).toBeInTheDocument();
    expect(screen.getByText(/shown when available\. not available for this strategy yet/i)).toBeInTheDocument();
    expect(screen.getByText(/actual modelling assumptions are known/i)).toBeInTheDocument();
    expect(screen.queryByText(/set by the strategy version/i)).not.toBeInTheDocument();
    expect(screen.getByText(/backtesting \(this page\)/i)).toBeInTheDocument();
    expect(screen.getByText("Paper trading")).toBeInTheDocument();
    expect(screen.getByText("Live trading")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to strategy profile/i })).toHaveAttribute("href", "/marketplace/trend-momentum");
  });

  it("shows an error state when the strategy cannot be loaded", async () => {
    api.getBySlug.mockRejectedValue(new Error("boom"));
    renderRoutes("/marketplace/trend-momentum/backtest");
    expect(await screen.findByText("Unable to load this strategy.")).toBeInTheDocument();
  });

  it("shows a loading state first", () => {
    api.getBySlug.mockReturnValue(new Promise(() => undefined));
    renderRoutes("/marketplace/trend-momentum/backtest");
    expect(screen.getByText("Loading strategy…")).toBeInTheDocument();
  });
});

describe("Starting capital validation", () => {
  it.each([["", /enter a starting capital/i], ["abc", /must be a number/i], ["0", /greater than/i], ["-5", /must be a number/i], ["2000000000", /not exceed/i]])(
    "rejects %j", (value, message) => expect(validateStartingCapital(value)).toMatch(message));
  it.each(["50000", "50,000", "₹1,25,000.50"])("accepts %j", (value) => expect(validateStartingCapital(value)).toBeNull());

  it("shows an accessible error and moves between Not configured and Ready", async () => {
    const onRun = vi.fn();
    renderView({ kind: "idle" }, onRun);
    const input = screen.getByLabelText(/starting capital/i);
    expect(screen.getByTestId("execution-status")).toHaveAttribute("data-state", "not_configured");
    expect(screen.getByRole("button", { name: /run backtest/i })).toBeDisabled();
    await userEvent.type(input, "abc");
    await userEvent.tab();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(await screen.findByText(/must be a number/i)).toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, "50,000");
    expect(screen.getByTestId("execution-status")).toHaveAttribute("data-state", "ready");
    expect(screen.getByText(/no backtest has been run yet/i)).toBeInTheDocument();
    expect(screen.queryByTestId("performance-results")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /run backtest/i }));
    expect(onRun).toHaveBeenCalledWith("50,000");
  });

  it("never enables Run without a supplied handler", async () => {
    renderView({ kind: "idle" });
    await userEvent.type(screen.getByLabelText(/starting capital/i), "50000");
    expect(screen.getByRole("button", { name: /run backtest/i })).toBeDisabled();
  });
});

describe("Execution states", () => {
  it("maps each execution kind to one display state", () => {
    expect(resolveDisplayState({ kind: "unavailable", reason: "x" }, true)).toBe("unavailable");
    expect(resolveDisplayState({ kind: "running" }, true)).toBe("running");
    expect(resolveDisplayState({ kind: "failed", message: "m" }, true)).toBe("failed");
    expect(resolveDisplayState({ kind: "idle" }, false)).toBe("not_configured");
    expect(resolveDisplayState({ kind: "idle" }, true)).toBe("ready");
  });

  it("running shows loading and no results", () => {
    renderView({ kind: "running" });
    expect(screen.getByText("Running Backtest…")).toBeInTheDocument();
    expect(screen.queryByTestId("performance-results")).not.toBeInTheDocument();
  });

  it("failed shows the message and no results", () => {
    renderView({ kind: "failed", message: "The engine rejected the run." });
    expect(screen.getAllByText("The engine rejected the run.").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("performance-results")).not.toBeInTheDocument();
  });

  it("completed renders only the supplied result, with unknown provenance marked unavailable", () => {
    renderView({ kind: "completed", result: FIXTURE_RESULT });
    const perf = screen.getByTestId("performance-results");
    expect(within(perf).getByText("+₹1,250.50")).toBeInTheDocument();
    expect(within(perf).getByText("+2.50%")).toBeInTheDocument();
    expect(within(perf).getByText("4.20%")).toBeInTheDocument();
    expect(within(perf).getByTestId("equity-chart")).toBeInTheDocument();
    expect(within(perf).getByRole("table")).toBeInTheDocument();
    expect(screen.getByText(/fixture-provider · Synthetic reference dataset/)).toBeInTheDocument();
    expect(screen.getByText("same_bar_close")).toBeInTheDocument();
    expect(screen.getByText("Fixture limitation")).toBeInTheDocument();
    expect(screen.getAllByText("Not available").length).toBe(2);
  });
});

describe("Unsaved changes and theming", () => {
  it("asks before leaving with an unused capital entry", async () => {
    const router = createMemoryRouter(
      [
        { path: "/", element: <BacktestWorkspaceView strategy={strategy} execution={{ kind: "idle" }} /> },
        { path: "/marketplace/:slug", element: <p>profile</p> },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    await userEvent.type(screen.getByLabelText(/starting capital/i), "50000");
    await userEvent.click(screen.getByRole("link", { name: /back to strategy profile/i }));
    expect(await screen.findByText("Leave without running?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByText("profile")).not.toBeInTheDocument();
  });

  it("does not block when nothing was entered", async () => {
    const router = createMemoryRouter(
      [
        { path: "/", element: <BacktestWorkspaceView strategy={strategy} execution={{ kind: "idle" }} /> },
        { path: "/marketplace/:slug", element: <p>profile</p> },
      ],
    );
    render(<RouterProvider router={router} />);
    await userEvent.click(screen.getByRole("link", { name: /back to strategy profile/i }));
    expect(await screen.findByText("profile")).toBeInTheDocument();
  });

  it("styles with theme tokens only, so Light, Dark and System share one stylesheet", () => {
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(css).not.toMatch(/(rgb|hsl)a?\(/);
    expect(css).toMatch(/max-width: 640px/);
  });
});
