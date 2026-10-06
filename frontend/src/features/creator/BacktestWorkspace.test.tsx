import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { ApiError } from "../../api/client";
import { BacktestDetailPage, VersionBacktests } from "./BacktestPages";
import { describeEquity } from "./EquityChart";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CartesianGrid: () => null,
  Line: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

const api = vi.hoisted(() => ({
  get: vi.fn(),
  getVersion: vi.fn(),
  listBacktests: vi.fn(),
  createBacktest: vi.fn(),
  getBacktest: vi.fn(),
  executeBacktest: vi.fn(),
  getBacktestAnalytics: vi.fn(),
}));
vi.mock("../../api/strategies", () => ({ strategiesApi: api }));

const base = {
  id: "b1111111-0000-0000-0000-000000000000", strategy_version_id: "v1", instrument_id: "i1",
  instrument_snapshot: { canonical_symbol: "NSE:REF", exchange_symbol: "REF", name: "Reference Equity", exchange_code: "NSE", instrument_type: "equity", quote_currency: "INR" },
  requested_by_user_id: "u1", status: "queued", configuration_snapshot: { fast: 9 }, backtest_configuration_snapshot: { timeframe: "1d" },
  market_data_reference: null, market_data_provider: null, market_data_dataset_id: null, dataset_reference: null,
  timeframe: "1d", range_start: "2026-01-01T00:00:00Z", range_end: "2026-03-01T00:00:00Z", adjustment_policy: "unadjusted",
  data_fetched_at: null, market_data_provenance: null, result_summary: null, error_message: null, error_code: null,
  created_at: "2026-01-01T00:00:00Z", started_at: null, completed_at: null,
};
const completedSummary = (over = {}) => ({ engine_identifier: "ema-ref", provider_identifier: "synthetic", total_return: "12.5", final_equity: "112500", trade_count: 1, ...over });
const completed = { ...base, status: "completed", market_data_provider: "synthetic-local-v1", market_data_provenance: { synthetic: true }, result_summary: completedSummary() };
const trade = { side: "long", entry_timestamp: "2026-01-05T00:00:00Z", exit_timestamp: "2026-02-27T00:00:00Z", quantity: "10", entry_price: "100", exit_price: "112.5", pnl: "125" };
const analytics = {
  backtest_id: base.id, engine_identifier: "ema-ref", provider_identifier: "synthetic", initial_capital: "100000", final_equity: "112500",
  total_return: "12.5", trade_count: 1, win_rate: null, profit_factor: null, average_win: null, average_loss: null, max_drawdown: "2",
  equity_curve: [{ timestamp: "2026-01-01T00:00:00Z", equity: "100000" }, { timestamp: "2026-02-01T00:00:00Z", equity: "112500" }],
};
const version = {
  id: "v1", strategy_id: "s1", version_number: 2, configuration: {}, created_at: "2026-01-01T00:00:00Z",
  backtest_configuration: { timeframe: "1d", start_date: "2026-01-01", end_date: "2026-03-01", initial_capital: 100000 },
  instrument: { canonical_symbol: "NSE:REF", exchange_symbol: "REF", name: "Reference Equity", exchange: { code: "NSE" } },
};

const detailPath = "/creator/strategies/s1/versions/v1/backtests/b1";
function view(ui: ReactNode, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/creator/strategies/:strategyId/versions/:versionId/backtests/:backtestId" element={<BacktestDetailPage />} />
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ id: "s1", name: "EMA Trend Follower" });
  api.getVersion.mockResolvedValue(version);
  api.listBacktests.mockResolvedValue([]);
});

describe("Configure", () => {
  const renderConfig = () => view(<VersionBacktests strategyId="s1" versionId="v1" strategyName="EMA Trend Follower" version={version as never} />);

  it("states what is being tested from the real Version", () => {
    renderConfig();
    const context = screen.getByRole("group", { name: /what is being tested/i });
    expect(within(context).getByText("EMA Trend Follower")).toBeInTheDocument();
    expect(within(context).getByText(/v2/)).toBeInTheDocument();
    expect(within(context).getByText("REF · NSE")).toBeInTheDocument();
    expect(within(context).getByText("1d")).toBeInTheDocument();
    expect(screen.getByText("Reference backtest engine")).toBeInTheDocument();
    expect(screen.getByText("Synthetic reference data")).toBeInTheDocument();
  });

  it("only exposes the one field the API accepts", () => {
    renderConfig();
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.getByLabelText(/Market data reference/)).toBeInTheDocument();
  });

  it("shows a field-level error and does not submit an over-long reference", async () => {
    renderConfig();
    const input = screen.getByLabelText(/Market data reference/);
    await userEvent.click(input);
    await userEvent.paste("x".repeat(501));
    await userEvent.click(screen.getByRole("button", { name: "Run Backtest" }));
    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent(/500 characters/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toContain(error.id);
    expect(api.createBacktest).not.toHaveBeenCalled();
  });

  it("creates a run, then the result page executes it once", async () => {
    api.createBacktest.mockResolvedValue({ ...base, id: "b1" });
    api.getBacktest.mockResolvedValue({ ...base, id: "b1" });
    api.executeBacktest.mockReturnValue(new Promise(() => {}));
    renderConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run Backtest" }));
    await waitFor(() => expect(api.createBacktest).toHaveBeenCalledWith("s1", "v1", { market_data_reference: null }));
    await waitFor(() => expect(api.executeBacktest).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Backtest running.")).toBeInTheDocument();
  });

  it("surfaces a create failure without navigating", async () => {
    api.createBacktest.mockRejectedValue(new ApiError(429, "Too many requests"));
    renderConfig();
    await userEvent.click(screen.getByRole("button", { name: "Run Backtest" }));
    expect(await screen.findByText("Too many requests")).toBeInTheDocument();
    expect(api.getBacktest).not.toHaveBeenCalled();
  });
});

describe("Run lifecycle", () => {
  it("shows honest steps and never a percentage while running", async () => {
    api.getBacktest.mockResolvedValue({ ...base, status: "running", started_at: base.created_at });
    view(null, detailPath);
    const steps = await screen.findByRole("list", { name: "Run progress" });
    expect(within(steps).getByText("Preparing research run")).toBeInTheDocument();
    expect(within(steps).getByText("Running backtest")).toBeInTheDocument();
    expect(within(steps).getByText("Waiting for result")).toBeInTheDocument();
    expect(steps.querySelector("[aria-current='step']")).toHaveTextContent("Running backtest");
    expect(steps).not.toHaveTextContent(/%/);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("announces state changes through a polite live region", async () => {
    api.getBacktest.mockResolvedValue(base);
    view(null, detailPath);
    const live = (await screen.findByText("Backtest queued.")).closest("[role='status']");
    expect(live).toHaveAttribute("aria-live", "polite");
  });

  it("marks the final step failed with the real failure reason and a way forward", async () => {
    api.getBacktest.mockResolvedValue({ ...base, status: "failed", error_code: "market_data_invalid_payload", error_message: "Candles were rejected" });
    view(null, detailPath);
    expect(await screen.findByText("Run failed")).toBeInTheDocument();
    expect(screen.getByText(/Candles were rejected/)).toBeInTheDocument();
    expect(screen.getByText(/market_data_invalid_payload/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to configuration" })).toHaveAttribute("href", "/creator/strategies/s1/versions/v1");
  });

  it("completes: result is revealed after analytics load", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    expect(await screen.findByRole("heading", { name: "Backtest analytics" })).toBeInTheDocument();
    expect(screen.getByText("Result ready.")).toBeInTheDocument();
  });
});

describe("Results", () => {
  it("keeps Strategy and Version context on the run", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    expect(await screen.findByRole("heading", { level: 1, name: /EMA Trend Follower · Version 2/ })).toBeInTheDocument();
    const context = screen.getByRole("group", { name: /what is being tested/i });
    expect(within(context).getByRole("link", { name: "EMA Trend Follower" })).toHaveAttribute("href", "/creator/strategies/s1");
    expect(within(context).getByRole("link", { name: "Version 2" })).toHaveAttribute("href", "/creator/strategies/s1/versions/v1");
  });

  it("still renders the run when Strategy context fails to load", async () => {
    api.get.mockRejectedValue(new ApiError(500, "boom"));
    api.getVersion.mockRejectedValue(new ApiError(500, "boom"));
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    expect(await screen.findByRole("heading", { name: "Backtest analytics" })).toBeInTheDocument();
  });

  it("renders real trades from result_summary with signed P&L", async () => {
    api.getBacktest.mockResolvedValue({ ...completed, result_summary: completedSummary({ trades: [trade] }) });
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    const table = await screen.findByRole("table", { name: "Trades" });
    expect(within(table).getByText("long")).toBeInTheDocument();
    expect(within(table).getByText("+125")).toBeInTheDocument();
  });

  it("explains missing trade detail instead of inventing rows", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    expect(await screen.findByText("Trade detail not available")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Trades" })).not.toBeInTheDocument();
  });

  it("says no trades were opened when trade_count is genuinely zero", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue({ ...analytics, trade_count: 0 });
    view(null, detailPath);
    expect(await screen.findByText("No trades were opened")).toBeInTheDocument();
  });

  it("never turns missing metrics into 0", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    await screen.findByRole("heading", { name: "Backtest analytics" });
    const winRate = screen.getAllByRole("listitem").find((i) => i.getAttribute("aria-label")?.startsWith("Win rate"));
    expect(winRate).toHaveAttribute("aria-label", "Win rate: Unavailable");
  });

  it("gives the equity chart a textual summary built from the real series", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    const chart = await screen.findByRole("img", { name: /equity curve chart/i });
    expect(chart.getAttribute("aria-label")).toMatch(/2 points/);
    expect(chart.getAttribute("aria-label")).toContain(`starts at ${(100000).toLocaleString()}`);
    expect(describeEquity([])).toBeNull();
  });

  it("exposes run ID, timestamps and data provenance", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    await screen.findByRole("heading", { name: "Backtest analytics" });
    const meta = screen.getByRole("complementary", { name: "Run metadata" });
    expect(within(meta).getByText(base.id)).toBeInTheDocument();
    expect(within(meta).getByText("Synthetic reference dataset")).toBeInTheDocument();
  });

  it("switches detail tabs with the keyboard", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    const tab = await screen.findByRole("tab", { name: "Trades" });
    tab.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Run configuration" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Algorithm configuration")).toBeInTheDocument();
  });

  it("offers a retry when the run cannot be loaded", async () => {
    api.getBacktest.mockRejectedValueOnce(new ApiError(503, "Service down")).mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(null, detailPath);
    expect(await screen.findByText("Unable to load backtest data.")).toBeInTheDocument();
    expect(screen.getByText("Service down")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("heading", { name: "Backtest analytics" })).toBeInTheDocument();
  });
});

describe("History", () => {
  const runs = [
    { ...completed, id: "aaaaaaaa-1", created_at: "2026-02-01T00:00:00Z", result_summary: completedSummary({ total_return: "5", trade_count: 1 }) },
    { ...completed, id: "bbbbbbbb-2", created_at: "2026-02-02T00:00:00Z", result_summary: completedSummary({ total_return: "15", trade_count: 3 }) },
    { ...base, id: "cccccccc-3", status: "failed", created_at: "2026-02-03T00:00:00Z", error_message: "x" },
  ];
  const renderHistory = () => view(<VersionBacktests strategyId="s1" versionId="v1" strategyName="EMA Trend Follower" version={version as never} />);
  const bodyRows = () => within(screen.getAllByRole("table")[0]).getAllByRole("row").slice(1);

  it("shows the empty state with a next step", async () => {
    renderHistory();
    expect(await screen.findByText("No backtests yet")).toBeInTheDocument();
    expect(screen.getByText("Run your first backtest to start building your research history.")).toBeInTheDocument();
  });

  it("renders real runs with return and trade count only where they exist", async () => {
    api.listBacktests.mockResolvedValue(runs);
    renderHistory();
    expect(await screen.findByRole("link", { name: "Run aaaaaaaa" })).toBeInTheDocument();
    const failedRow = bodyRows().find((r) => within(r).queryByText("Run cccccccc"));
    expect(failedRow).toHaveTextContent("—");
    expect(bodyRows().find((r) => within(r).queryByText("Run bbbbbbbb"))).toHaveTextContent("15%");
  });

  it("filters by status and updates the count", async () => {
    api.listBacktests.mockResolvedValue(runs);
    renderHistory();
    await screen.findByRole("link", { name: "Run aaaaaaaa" });
    await userEvent.click(screen.getByRole("button", { name: /^Failed/ }));
    expect(screen.getByRole("button", { name: /^Failed/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Showing 1 of 3 runs")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Run aaaaaaaa" })).not.toBeInTheDocument();
  });

  it("sorts by total return with unavailable returns last", async () => {
    api.listBacktests.mockResolvedValue(runs);
    renderHistory();
    await screen.findByRole("link", { name: "Run aaaaaaaa" });
    await userEvent.selectOptions(screen.getByLabelText("Sort"), "return");
    const order = bodyRows().map((r) => within(r).getByRole("link").textContent);
    expect(order).toEqual(["Run bbbbbbbb", "Run aaaaaaaa", "Run cccccccc"]);
  });

  it("uses labelled cells so rows can stack on narrow screens", async () => {
    api.listBacktests.mockResolvedValue(runs);
    renderHistory();
    await screen.findByRole("link", { name: "Run aaaaaaaa" });
    const table = screen.getAllByRole("table")[0];
    expect(table).toHaveClass("is-stacked");
    expect(table.querySelectorAll("td[data-label='Status']")).toHaveLength(3);
  });

  it("surfaces a list error with retry", async () => {
    api.listBacktests.mockRejectedValueOnce(new ApiError(500, "Server error")).mockResolvedValue(runs);
    renderHistory();
    expect(await screen.findByText("Unable to load backtest data.")).toBeInTheDocument();
    expect(screen.getByText("Server error")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("link", { name: "Run aaaaaaaa" })).toBeInTheDocument();
  });

  it("only lets completed runs be selected for comparison", async () => {
    api.listBacktests.mockResolvedValue(runs);
    renderHistory();
    await screen.findByRole("link", { name: "Run aaaaaaaa" });
    expect(screen.getByRole("checkbox", { name: /Compare run cccccccc/ })).toBeDisabled();
  });

  it("compares two completed runs using each run's real analytics", async () => {
    api.listBacktests.mockResolvedValue(runs);
    api.getBacktestAnalytics.mockImplementation(async (_s: string, _v: string, id: string) =>
      id === "aaaaaaaa-1" ? { ...analytics, total_return: "5", max_drawdown: "1" } : { ...analytics, total_return: "15", max_drawdown: "4" });
    renderHistory();
    await screen.findByRole("link", { name: "Run aaaaaaaa" });
    await userEvent.click(screen.getByRole("checkbox", { name: /Compare run aaaaaaaa/ }));
    expect(screen.getByText(/Select one more completed run/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /Compare run bbbbbbbb/ }));
    const table = await screen.findByRole("table", { name: /Side-by-side comparison/ });
    const returnRow = within(table).getByRole("row", { name: /Total return/ });
    await waitFor(() => expect(returnRow).toHaveTextContent("15%"));
    expect(returnRow).toHaveTextContent("5%");
    expect(within(table).getByRole("row", { name: /Max drawdown/ })).toHaveTextContent("4%");
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("table", { name: /Side-by-side comparison/ })).not.toBeInTheDocument();
  });
});
