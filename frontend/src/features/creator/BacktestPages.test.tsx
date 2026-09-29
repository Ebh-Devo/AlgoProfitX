import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { ApiError } from "../../api/client";
import { BacktestDetailPage, VersionBacktests } from "./BacktestPages";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CartesianGrid: () => null,
  Line: () => <span>Equity series</span>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

const api = vi.hoisted(() => ({
  listBacktests: vi.fn(),
  createBacktest: vi.fn(),
  getBacktest: vi.fn(),
  executeBacktest: vi.fn(),
  getBacktestAnalytics: vi.fn(),
}));
vi.mock("../../api/strategies", () => ({ strategiesApi: api }));

const queued = {
  id: "b1", strategy_version_id: "v1", instrument_id: "i1",
  instrument_snapshot: { canonical_symbol: "TRADEEBH_TEST_EQ", exchange_symbol: "TRADEEBH_TEST_EQ", name: "AlgoProfitX Synthetic Reference Equity", exchange_code: "NSE", instrument_type: "equity", quote_currency: "INR", tick_size: "0.01", lot_size: 1, is_tradeable: true },
  requested_by_user_id: "u1", status: "queued", configuration_snapshot: {}, backtest_configuration_snapshot: {},
  market_data_reference: null, market_data_provider: null, market_data_dataset_id: null, dataset_reference: null,
  timeframe: "1d", range_start: null, range_end: null, adjustment_policy: "unadjusted",
  data_fetched_at: null, market_data_provenance: null, result_summary: null,
  error_message: null, error_code: null,
  created_at: "2026-01-01T00:00:00Z", started_at: null, completed_at: null,
};
const running = { ...queued, status: "running", started_at: "2026-01-01T00:01:00Z" };
const completed = {
  ...queued, status: "completed",
  market_data_provider: "synthetic-local-v1", dataset_reference: "synthetic-reference-candles-v1",
  range_start: "2026-01-01T00:00:00Z", range_end: "2026-01-03T15:00:00Z",
  data_fetched_at: "2026-01-03T15:01:00Z", market_data_provenance: { synthetic: true },
  started_at: "2026-01-01T00:01:00Z", completed_at: "2026-01-01T00:02:00Z",
  result_summary: { engine_identifier: "reference-v1", provider_identifier: "synthetic-v1" },
};
const failed = { ...queued, status: "failed", error_message: "Reference engine rejected configuration", started_at: queued.created_at, completed_at: queued.created_at };
const analytics = {
  backtest_id: "b1", engine_identifier: "reference-v1", provider_identifier: "synthetic-v1",
  initial_capital: "100000.00000000", final_equity: "110000.00000000", total_return: "10.00000000",
  trade_count: 2, win_rate: null, profit_factor: null, average_win: "12000.00000000",
  average_loss: null, max_drawdown: "5.00000000",
  equity_curve: [
    { timestamp: "2026-01-01T00:00:00Z", equity: "100000.00000000" },
    { timestamp: "2026-01-02T00:00:00Z", equity: "110000.00000000" },
  ],
};

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function view(ui: ReactNode, path = "/") {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/creator/strategies/:strategyId/versions/:versionId/backtests/:backtestId" element={ui} />
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

// ─── Version Backtests ────────────────────────────────────────────────────────

describe("Version Backtests", () => {
  it("renders empty and populated lists", async () => {
    api.listBacktests.mockResolvedValueOnce([]);
    const first = view(<VersionBacktests strategyId="s1" versionId="v1" />);
    expect(await screen.findByText(/No Backtests/)).toBeInTheDocument();
    first.unmount();
    api.listBacktests.mockResolvedValueOnce([queued]);
    view(<VersionBacktests strategyId="s1" versionId="v1" />);
    expect(await screen.findByText("queued")).toBeInTheDocument();
  });

  it("creates a queued Backtest without client-controlled fields", async () => {
    api.listBacktests.mockResolvedValue([]);
    api.createBacktest.mockResolvedValue(queued);
    view(<VersionBacktests strategyId="s1" versionId="v1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Create Backtest" }));
    await userEvent.type(screen.getByLabelText(/Market data reference/), "synthetic-snapshot");
    await userEvent.click(screen.getByRole("button", { name: "Create Backtest" }));
    await waitFor(() => expect(api.createBacktest).toHaveBeenCalledWith("s1", "v1", { market_data_reference: "synthetic-snapshot" }));
  });

  it("polls the list while any run is queued or running", async () => {
    vi.useFakeTimers();
    api.listBacktests.mockResolvedValue([queued]);
    view(<VersionBacktests strategyId="s1" versionId="v1" />);
    await act(() => vi.advanceTimersByTimeAsync(100));
    const firstCount = api.listBacktests.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(api.listBacktests.mock.calls.length).toBeGreaterThan(firstCount);
    vi.useRealTimers();
  });

  it("stops polling the list when all runs are completed or failed", async () => {
    vi.useFakeTimers();
    api.listBacktests.mockResolvedValue([completed]);
    view(<VersionBacktests strategyId="s1" versionId="v1" />);
    await act(() => vi.advanceTimersByTimeAsync(100));
    const callCount = api.listBacktests.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(api.listBacktests.mock.calls.length).toBe(callCount);
    vi.useRealTimers();
  });

  it("shows an error when list loading fails", async () => {
    api.listBacktests.mockRejectedValue(new ApiError(500, "Server error"));
    view(<VersionBacktests strategyId="s1" versionId="v1" />);
    expect(await screen.findByText("Server error")).toBeInTheDocument();
  });
});

// ─── Backtest detail ──────────────────────────────────────────────────────────

describe("Backtest detail", () => {
  it("renders queued status and executes a queued Backtest", async () => {
    api.getBacktest.mockResolvedValue(queued);
    api.executeBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByText("queued")).toBeInTheDocument();
    expect(api.getBacktestAnalytics).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Execute Backtest" }));
    await waitFor(() => expect(api.executeBacktest).toHaveBeenCalledWith("s1", "v1", "b1"));
  });

  it("shows queued status message", async () => {
    api.getBacktest.mockResolvedValue(queued);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByText(/Backtest queued/)).toBeInTheDocument();
  });

  it("disables Execute button while mutation is pending", async () => {
    api.getBacktest.mockResolvedValue(queued);
    api.executeBacktest.mockReturnValue(new Promise(() => {})); // never resolves
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await userEvent.click(await screen.findByRole("button", { name: "Execute Backtest" }));
    expect(screen.getByRole("button", { name: "Executing…" })).toBeDisabled();
  });

  it("shows running status message and no Execute button", async () => {
    api.getBacktest.mockResolvedValue(running);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByText("running")).toBeInTheDocument();
    expect(screen.getByText(/Backtest running/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Execute/ })).not.toBeInTheDocument();
    expect(api.getBacktestAnalytics).not.toHaveBeenCalled();
  });

  it("surfaces execution conflicts (409)", async () => {
    api.getBacktest.mockResolvedValue(queued);
    api.executeBacktest.mockRejectedValue(new ApiError(409, "Backtest cannot execute while running"));
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await userEvent.click(await screen.findByRole("button", { name: "Execute Backtest" }));
    expect(await screen.findByText("Backtest cannot execute while running")).toBeInTheDocument();
  });

  it("surfaces execution unavailable (503)", async () => {
    api.getBacktest.mockResolvedValue(queued);
    api.executeBacktest.mockRejectedValue(new ApiError(503, "Execution service unavailable"));
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await userEvent.click(await screen.findByRole("button", { name: "Execute Backtest" }));
    expect(await screen.findByText("Execution service unavailable")).toBeInTheDocument();
  });

  it("shows generic error for unexpected execution failure", async () => {
    api.getBacktest.mockResolvedValue(queued);
    api.executeBacktest.mockRejectedValue(new Error("network failure"));
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await userEvent.click(await screen.findByRole("button", { name: "Execute Backtest" }));
    expect(await screen.findByText("Unable to execute Backtest.")).toBeInTheDocument();
  });

  it("renders failed status and safe error without analytics", async () => {
    api.getBacktest.mockResolvedValue(failed);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(screen.getByText(/Reference engine rejected configuration/)).toBeInTheDocument();
    expect(api.getBacktestAnalytics).not.toHaveBeenCalled();
  });

  it("shows analytics only for completed runs with null semantics and equity data", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByRole("heading", { name: "Backtest analytics" })).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable")).toHaveLength(3);
    expect(screen.getByTestId("equity-chart")).toBeInTheDocument();
    expect(screen.getByText("Equity series")).toBeInTheDocument();
    expect(screen.getByText("2026-01-02T00:00:00Z")).toBeInTheDocument();
    expect(api.getBacktestAnalytics).toHaveBeenCalledOnce();
  });

  it("does not request analytics for queued", async () => {
    api.getBacktest.mockResolvedValue(queued);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await screen.findByText("queued");
    expect(api.getBacktestAnalytics).not.toHaveBeenCalled();
  });

  it("does not request analytics for running", async () => {
    api.getBacktest.mockResolvedValue(running);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await screen.findByText("running");
    expect(api.getBacktestAnalytics).not.toHaveBeenCalled();
  });

  it("displays analytics error safely", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockRejectedValue(new ApiError(500, "Analytics unavailable"));
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByText("Analytics unavailable")).toBeInTheDocument();
  });

  it("null metrics remain Unavailable", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue({ ...analytics, win_rate: null, profit_factor: null, average_loss: null });
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await screen.findByRole("heading", { name: "Backtest analytics" });
    expect(screen.getAllByText("Unavailable")).toHaveLength(3);
  });

  it("renders canonical Instrument and trusted provenance without vendor mappings", async () => {
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByText("AlgoProfitX Synthetic Reference Equity")).toBeInTheDocument();
    expect(screen.getByText(/TRADEEBH_TEST_EQ.*TRADEEBH_TEST_EQ/)).toBeInTheDocument();
    expect(screen.getAllByText("synthetic-local-v1").length).toBeGreaterThan(0);
    expect(screen.getByText("synthetic-reference-candles-v1")).toBeInTheDocument();
    expect(screen.getByText("unadjusted")).toBeInTheDocument();
    expect(screen.queryByText(/vendor/i)).not.toBeInTheDocument();
  });

  it("renders legacy null provenance safely", async () => {
    api.getBacktest.mockResolvedValue({ ...queued, instrument_id: null, instrument_snapshot: null, timeframe: null, adjustment_policy: null });
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByText("Legacy/unavailable Instrument metadata.")).toBeInTheDocument();
    expect(screen.getAllByText("Legacy/unavailable").length).toBeGreaterThan(2);
  });

  it("shows 404 message when Backtest not found", async () => {
    api.getBacktest.mockRejectedValue(new ApiError(404, "Not found"));
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    expect(await screen.findByText("Backtest not found.")).toBeInTheDocument();
  });

  it("updates backtest query after successful execution", async () => {
    api.getBacktest.mockResolvedValue(queued);
    api.executeBacktest.mockResolvedValue(running);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await userEvent.click(await screen.findByRole("button", { name: "Execute Backtest" }));
    await waitFor(() => expect(api.executeBacktest).toHaveBeenCalledWith("s1", "v1", "b1"));
  });

  // ── Polling tests ─────────────────────────────────────────────────────────

  it("polls while status is queued", async () => {
    vi.useFakeTimers();
    api.getBacktest.mockResolvedValue(queued);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await act(() => vi.advanceTimersByTimeAsync(100));
    const before = api.getBacktest.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(api.getBacktest.mock.calls.length).toBeGreaterThan(before);
    vi.useRealTimers();
  });

  it("polls while status is running", async () => {
    vi.useFakeTimers();
    api.getBacktest.mockResolvedValue(running);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await act(() => vi.advanceTimersByTimeAsync(100));
    const before = api.getBacktest.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(api.getBacktest.mock.calls.length).toBeGreaterThan(before);
    vi.useRealTimers();
  });

  it("stops polling when status is completed", async () => {
    vi.useFakeTimers();
    api.getBacktest.mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await act(() => vi.advanceTimersByTimeAsync(100));
    const callCount = api.getBacktest.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(api.getBacktest.mock.calls.length).toBe(callCount);
    vi.useRealTimers();
  });

  it("stops polling when status is failed", async () => {
    vi.useFakeTimers();
    api.getBacktest.mockResolvedValue(failed);
    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await act(() => vi.advanceTimersByTimeAsync(100));
    const callCount = api.getBacktest.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(api.getBacktest.mock.calls.length).toBe(callCount);
    vi.useRealTimers();
  });

  // ── Lifecycle transition tests ─────────────────────────────────────────────

  it("transitions queued → running → completed as polling updates data", async () => {
    vi.useFakeTimers();
    api.getBacktest
      .mockResolvedValueOnce(queued)
      .mockResolvedValueOnce(running)
      .mockResolvedValue(completed);
    api.getBacktestAnalytics.mockResolvedValue(analytics);

    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(screen.getByText("queued")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(screen.getByText("running")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(screen.getByText("completed")).toBeInTheDocument();

    vi.useRealTimers();
  }, 15000);

  it("transitions queued → failed with error display", async () => {
    vi.useFakeTimers();
    api.getBacktest
      .mockResolvedValueOnce(queued)
      .mockResolvedValue(failed);

    view(<BacktestDetailPage />, "/creator/strategies/s1/versions/v1/backtests/b1");
    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(screen.getByText("queued")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText(/Reference engine rejected configuration/)).toBeInTheDocument();

    vi.useRealTimers();
  }, 15000);
});
