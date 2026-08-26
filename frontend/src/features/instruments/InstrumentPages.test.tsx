import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "../../api/client";
import { InstrumentDetailPage, InstrumentListPage } from "./InstrumentPages";

const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn() }));
vi.mock("../../api/instruments", () => ({ instrumentsApi: api }));
const exchange = { id: "x1", code: "NSE", name: "National Stock Exchange", country_code: "IN", timezone: "Asia/Kolkata", default_currency: "INR", calendar_code: "XNSE", is_active: true };
const equity = { id: "i1", exchange, canonical_symbol: "RELIANCE", exchange_symbol: "RELIANCE", name: "Reliance Industries", instrument_type: "equity", quote_currency: "INR", tick_size: "0.05", lot_size: 1, is_tradeable: true, isin: "INE002A01018", is_synthetic: false, is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
const index = { ...equity, id: "i2", canonical_symbol: "NIFTY_50", exchange_symbol: "NIFTY 50", name: "Nifty 50", instrument_type: "index", is_tradeable: false, isin: null, lot_size: null };
function view(ui: React.ReactNode, path = "/instruments") { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[path]}><Routes><Route path="/instruments" element={ui} /><Route path="/instruments/:instrumentId" element={ui} /></Routes></MemoryRouter></QueryClientProvider>); }

describe("Instrument pages", () => {
  beforeEach(() => vi.clearAllMocks());
  it("lists equities and indices with tradeability and filters through the backend contract", async () => { api.list.mockResolvedValue([equity, index]); view(<InstrumentListPage />); expect(await screen.findByText("Reliance Industries")).toBeInTheDocument(); expect(screen.getByText("Nifty 50")).toBeInTheDocument(); expect(screen.getAllByText("Equity")).toHaveLength(2); expect(screen.getAllByText("Index")).toHaveLength(2); expect(screen.getAllByText("Tradeable")).toHaveLength(2); expect(screen.getAllByText("Non-tradeable")).toHaveLength(2); await userEvent.type(screen.getByPlaceholderText("Name or symbol"), "reliance"); await userEvent.selectOptions(screen.getByLabelText("Type"), "equity"); await userEvent.click(screen.getByRole("button", { name: "Search" })); await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ search: "reliance", instrumentType: "equity", offset: 0 }))); });
  it("renders empty and error states", async () => { api.list.mockResolvedValueOnce([]); const rendered = view(<InstrumentListPage />); expect(await screen.findByText(/No Instruments match/)).toBeInTheDocument(); rendered.unmount(); api.list.mockRejectedValueOnce(new ApiError(403, "Access denied")); view(<InstrumentListPage />); expect(await screen.findByRole("alert")).toHaveTextContent("Access denied"); });
  it("shows complete Instrument detail metadata", async () => { api.get.mockResolvedValue(equity); view(<InstrumentDetailPage />, "/instruments/i1"); expect(await screen.findByRole("heading", { name: "Reliance Industries" })).toBeInTheDocument(); expect(screen.getByText("INE002A01018")).toBeInTheDocument(); expect(screen.getByText("National Stock Exchange")).toBeInTheDocument(); expect(screen.getByText("Asia/Kolkata")).toBeInTheDocument(); expect(screen.getByText("0.05")).toBeInTheDocument(); });
  it("explains 404 responses", async () => { api.get.mockRejectedValue(new ApiError(404, "missing")); view(<InstrumentDetailPage />, "/instruments/missing"); expect(await screen.findByRole("alert")).toHaveTextContent("Instrument not found"); });
});
