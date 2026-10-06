import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { ApiError } from "../../api/client";
import { StrategyDetailPage, StrategyEditPage, StrategyListPage, StrategyNewPage, StrategyVersionPage } from "./StrategyPages";

const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn(), lifecycle: vi.fn(), listVersions: vi.fn(), getVersion: vi.fn(), createVersion: vi.fn() }));
const instrumentApi = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("../../api/strategies", () => ({ strategiesApi: api }));
vi.mock("../../api/instruments", () => ({ instrumentsApi: instrumentApi }));
const strategy = { id: "s1", creator_id: "u1", name: "India Trend", slug: "india-trend", description: "Trend strategy", status: "draft", is_public: false, current_version_id: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", published_at: null, deployed_at: null };
const instrument = { id: "i1", canonical_symbol: "NSE:NIFTY_50", exchange_symbol: "NIFTY 50", name: "NIFTY 50 Index", instrument_type: "index", quote_currency: "INR", tick_size: null, lot_size: null, is_tradeable: false, isin: null, is_synthetic: false, is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", exchange: { id: "e1", code: "NSE", name: "National Stock Exchange of India", country_code: "IN", timezone: "Asia/Kolkata", default_currency: "INR", calendar_code: "XNSE", is_active: true } };
const version = { id: "v1", strategy_id: "s1", instrument_id: "i1", instrument, version_number: 1, configuration: { symbol: "NIFTY" }, backtest_configuration: { capital: 100000 }, created_at: "2026-01-02T00:00:00Z" };
function view(ui: ReactNode, path = "/") { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><MemoryRouter initialEntries={[path]}><Routes><Route path="/creator/strategies" element={ui} /><Route path="/creator/strategies/new" element={ui} /><Route path="/creator/strategies/:strategyId" element={ui} /><Route path="/creator/strategies/:strategyId/edit" element={ui} /><Route path="/creator/strategies/:strategyId/versions/:versionId" element={ui} /></Routes></MemoryRouter></QueryClientProvider>); }
beforeEach(() => { vi.clearAllMocks(); api.listVersions.mockResolvedValue([]); instrumentApi.list.mockResolvedValue([instrument]); });

describe("Creator strategy pages", () => {
  it("shows empty, populated, and error list states", async () => {
    api.list.mockResolvedValueOnce([]); const first = view(<StrategyListPage />, "/creator/strategies"); expect(await screen.findByText(/No strategies yet/)).toBeInTheDocument(); first.unmount();
    api.list.mockResolvedValueOnce([strategy]); const second = view(<StrategyListPage />, "/creator/strategies"); expect(await screen.findByText("India Trend")).toBeInTheDocument(); second.unmount();
    api.list.mockRejectedValueOnce(new ApiError(500, "Service unavailable")); view(<StrategyListPage />, "/creator/strategies"); expect(await screen.findByText(/couldn.t load your strategies/i)).toBeInTheDocument(); expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
  it("creates a strategy from the name alone without sending a slug", async () => {
    api.create.mockResolvedValueOnce(strategy); view(<StrategyNewPage />, "/creator/strategies/new");
    await userEvent.type(screen.getByLabelText("Name"), "India Trend V2"); await userEvent.click(screen.getByRole("button", { name: "Create strategy" }));
    await waitFor(() => expect(api.create).toHaveBeenCalled());
    const payload = api.create.mock.calls[0][0]; expect(payload).toEqual({ name: "India Trend V2", description: null }); expect(payload).not.toHaveProperty("slug");
  });
  it("surfaces API errors on create", async () => {
    api.create.mockRejectedValueOnce(new ApiError(500, "Service unavailable")); view(<StrategyNewPage />, "/creator/strategies/new");
    await userEvent.type(screen.getByLabelText("Name"), "India Trend"); await userEvent.click(screen.getByRole("button", { name: "Create strategy" }));
    expect(await screen.findByText("Service unavailable")).toBeInTheDocument();
  });
  it("edits strategy metadata", async () => { api.get.mockResolvedValue(strategy); api.update.mockResolvedValue({ ...strategy, name: "Updated Trend" }); view(<StrategyEditPage />, "/creator/strategies/s1/edit"); const name = await screen.findByLabelText("Name"); await userEvent.clear(name); await userEvent.type(name, "Updated Trend"); await userEvent.click(screen.getByRole("button", { name: "Save changes" })); await waitFor(() => expect(api.update).toHaveBeenCalledWith("s1", expect.objectContaining({ name: "Updated Trend" }))); expect(api.update.mock.calls[0][1]).not.toHaveProperty("slug"); });
  it("requires confirmation before deletion", async () => { api.get.mockResolvedValue(strategy); api.delete.mockResolvedValue(undefined); view(<StrategyDetailPage />, "/creator/strategies/s1"); await userEvent.click(await screen.findByRole("button", { name: "More" })); await userEvent.click(screen.getByRole("menuitem", { name: "Delete strategy" })); expect(api.delete).not.toHaveBeenCalled(); await userEvent.click(screen.getByRole("button", { name: "Delete permanently" })); await waitFor(() => expect(api.delete).toHaveBeenCalledWith("s1")); });
  it("loads searchable Instruments and creates a Version with canonical identity", async () => { api.get.mockResolvedValue(strategy); api.createVersion.mockResolvedValue(version); view(<StrategyDetailPage />, "/creator/strategies/s1"); await userEvent.click(await screen.findByRole("button", { name: "Create Version" })); expect(await screen.findByRole("option", { name: /NIFTY 50 Index.*NSE.*non-tradeable/ })).toBeInTheDocument(); expect(screen.queryByLabelText(/Instrument UUID/i)).not.toBeInTheDocument(); await userEvent.type(screen.getByPlaceholderText("Search name or symbol"), "nifty"); await waitFor(() => expect(instrumentApi.list).toHaveBeenCalledWith("nifty")); await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1"); fireEvent.change(screen.getByLabelText("Short-term EMA (days)"), { target: { value: "12" } }); fireEvent.change(screen.getByLabelText("Long-term EMA (days)"), { target: { value: "5" } }); await userEvent.click(screen.getByRole("button", { name: "Create Version" })); expect(await screen.findByText(/must be smaller than long-term EMA/)).toBeInTheDocument(); expect(api.createVersion).not.toHaveBeenCalled(); fireEvent.change(screen.getByLabelText("Long-term EMA (days)"), { target: { value: "26" } }); await userEvent.click(screen.getByRole("button", { name: "Create Version" })); await waitFor(() => expect(api.createVersion).toHaveBeenCalledWith("s1", expect.objectContaining({ instrument_id: "i1", configuration: { entry: { type: "ema_crossover", fast_period: 12, slow_period: 26 } }, backtest_configuration: { initial_capital: 50000 } }))); });
  it("renders Version Instrument metadata and legacy unresolved detail safely", async () => { api.get.mockResolvedValue(strategy); api.listVersions.mockResolvedValue([version]); const first = view(<StrategyDetailPage />, "/creator/strategies/s1"); expect(await screen.findByText("Version 1")).toBeInTheDocument(); first.unmount(); api.getVersion.mockResolvedValue(version); const second = view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1"); expect(await screen.findByText("NIFTY 50 Index")).toBeInTheDocument(); expect(screen.getByText(/index.*non-tradeable/)).toBeInTheDocument(); expect(screen.getByText("NSE:NIFTY_50")).toBeInTheDocument(); second.unmount(); api.getVersion.mockResolvedValue({ ...version, instrument_id: null, instrument: null }); view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1"); expect(await screen.findByText("legacy / unresolved")).toBeInTheDocument(); });
  it.each([["draft", "Publish"], ["published", "Deploy"], ["deployed", "Archive"]])("runs allowed %s lifecycle action", async (status, action) => { api.get.mockResolvedValue({ ...strategy, status }); api.lifecycle.mockResolvedValue({ ...strategy, status }); view(<StrategyDetailPage />, "/creator/strategies/s1"); if (action === "Archive") fireEvent.click(await screen.findByRole("button", { name: "More" })); else fireEvent.click(await screen.findByRole("button", { name: action })); if (action === "Archive") { expect(api.lifecycle).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("menuitem", { name: "Archive" })); fireEvent.click(screen.getByRole("button", { name: "Confirm archive" })); } await waitFor(() => expect(api.lifecycle).toHaveBeenCalledWith("s1", action.toLowerCase())); });
  it("surfaces publish-without-Version conflict and hides invalid archived actions", async () => { api.get.mockResolvedValue(strategy); api.lifecycle.mockRejectedValue(new ApiError(409, "Strategy must have at least one version before publishing")); const first = view(<StrategyDetailPage />, "/creator/strategies/s1"); await userEvent.click(await screen.findByRole("button", { name: "Publish" })); expect(await screen.findByText(/at least one version/)).toBeInTheDocument(); first.unmount(); api.get.mockResolvedValue({ ...strategy, status: "archived" }); view(<StrategyDetailPage />, "/creator/strategies/s1"); expect(await screen.findByText(/Archived is terminal/)).toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Deploy" })).not.toBeInTheDocument(); });
  it("filters, searches and sorts the strategy list, with a recoverable no-match state", async () => {
    api.list.mockResolvedValue([
      { ...strategy, id: "a", name: "Zeta Trend", slug: "zeta-trend", status: "draft", updated_at: "2026-03-01T00:00:00Z" },
      { ...strategy, id: "b", name: "Alpha Revert", slug: "alpha-revert", status: "published", is_public: true, updated_at: "2026-02-01T00:00:00Z" },
    ]);
    view(<StrategyListPage />, "/creator/strategies");
    expect(await screen.findByText("Zeta Trend")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Draft/ })).toHaveTextContent("1");
    const names = () => screen.getAllByRole("row").slice(1).map(r => r.querySelector("a")?.textContent);
    expect(names()).toEqual(["Zeta Trend", "Alpha Revert"]);
    await userEvent.selectOptions(screen.getByLabelText("Sort"), "name");
    expect(names()).toEqual(["Alpha Revert", "Zeta Trend"]);
    await userEvent.click(screen.getByRole("button", { name: /^Published/ }));
    expect(names()).toEqual(["Alpha Revert"]);
    expect(screen.getByRole("status")).toHaveTextContent("Showing 1 of 2 strategies");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search strategies" }), "nothing-here");
    expect(await screen.findByText("No strategies match")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(names()).toHaveLength(2);
  });
  it("does not render a slug input when creating or editing", async () => {
    const created = view(<StrategyNewPage />, "/creator/strategies/new");
    expect(screen.getByLabelText("Name")).toBeInTheDocument(); expect(screen.queryByLabelText(/slug/i)).not.toBeInTheDocument(); expect(screen.getAllByRole("textbox")).toHaveLength(2); created.unmount();
    api.get.mockResolvedValue(strategy); view(<StrategyEditPage />, "/creator/strategies/s1/edit");
    await screen.findByLabelText("Name"); expect(screen.queryByLabelText(/slug/i)).not.toBeInTheDocument();
  });
  it("shows a state-appropriate primary action and keeps destructive actions in the menu", async () => {
    api.get.mockResolvedValue({ ...strategy, status: "published" }); view(<StrategyDetailPage />, "/creator/strategies/s1");
    expect(await screen.findByRole("button", { name: "Deploy" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByRole("menuitem", { name: "Archive" })).toBeInTheDocument(); expect(screen.getByRole("menuitem", { name: "Delete strategy" })).toBeInTheDocument();
  });
  it("cancelling the delete dialog does not delete", async () => { api.get.mockResolvedValue(strategy); view(<StrategyDetailPage />, "/creator/strategies/s1"); await userEvent.click(await screen.findByRole("button", { name: "More" })); await userEvent.click(screen.getByRole("menuitem", { name: "Delete strategy" })); await userEvent.click(screen.getByRole("button", { name: "Cancel" })); expect(api.delete).not.toHaveBeenCalled(); });
  it("returns focus to the More trigger after a menu action opens and closes a dialog", async () => {
    api.get.mockResolvedValue(strategy); view(<StrategyDetailPage />, "/creator/strategies/s1");
    const more = await screen.findByRole("button", { name: "More" }); await userEvent.click(more);
    await userEvent.click(screen.getByRole("menuitem", { name: "Delete strategy" }));
    expect(more).toHaveFocus();
  });
  it("does not nest alert roles for lifecycle errors", async () => {
    api.get.mockResolvedValue(strategy); api.lifecycle.mockRejectedValue(new ApiError(409, "Needs a Version"));
    view(<StrategyDetailPage />, "/creator/strategies/s1"); await userEvent.click(await screen.findByRole("button", { name: "Publish" }));
    const alert = await screen.findByRole("alert"); expect(alert).toHaveTextContent("Needs a Version"); expect(alert.parentElement?.closest("[role=alert]")).toBeNull();
  });
});

describe("Strategy list interaction (PR #26)", () => {
  it("restores filters from the URL and offers an honest next action per row", async () => {
    api.list.mockResolvedValue([
      { ...strategy, id: "a", name: "Zeta Trend", slug: "zeta-trend", status: "draft" },
      { ...strategy, id: "b", name: "Alpha Revert", slug: "alpha-revert", status: "published", is_public: true, current_version_id: "v1" },
    ]);
    view(<StrategyListPage />, "/creator/strategies?status=published");
    expect(await screen.findByText("Alpha Revert")).toBeInTheDocument();
    expect(screen.queryByText("Zeta Trend")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Published/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("link", { name: "View in marketplace: Alpha Revert" })).toHaveAttribute("href", "/marketplace/alpha-revert");
  });

  it("offers a clear-search control that resets results", async () => {
    api.list.mockResolvedValue([strategy]);
    view(<StrategyListPage />, "/creator/strategies?q=zzz");
    expect(await screen.findByText("No strategies match")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(await screen.findByText("India Trend")).toBeInTheDocument();
  });

  it("suggests the next step on a draft detail page without duplicating the Version call to action", async () => {
    api.get.mockResolvedValue(strategy);
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    expect(await screen.findByRole("region", { name: "Suggested next step" })).toHaveTextContent("Next: create a Version");
    expect(screen.getAllByRole("button", { name: "Create Version" })).toHaveLength(1);
  });

  it("points a draft that has Versions at the latest one", async () => {
    api.get.mockResolvedValue({ ...strategy, current_version_id: "v1" });
    api.listVersions.mockResolvedValue([version]);
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    expect(await screen.findByRole("link", { name: "Open latest Version" })).toHaveAttribute("href", "/creator/strategies/s1/versions/v1");
  });
});
