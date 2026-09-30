/**
 * C2 Strategy Versions — focused tests
 *
 * Covers: version list states, instrument search/selection, version creation
 * (validation, success, errors), version detail, accessibility, and navigation.
 */
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { ApiError } from "../../api/client";
import { StrategyDetailPage, StrategyVersionPage } from "./StrategyPages";

/* ── API mocks ────────────────────────────────────────────────── */
const api = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
  lifecycle: vi.fn(),
  listVersions: vi.fn(),
  getVersion: vi.fn(),
  createVersion: vi.fn(),
}));
const instrumentApi = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("../../api/strategies", () => ({ strategiesApi: api }));
vi.mock("../../api/instruments", () => ({ instrumentsApi: instrumentApi }));

/* ── Fixture data ─────────────────────────────────────────────── */
const exchange = {
  id: "e1",
  code: "NSE",
  name: "National Stock Exchange of India",
  country_code: "IN",
  timezone: "Asia/Kolkata",
  default_currency: "INR",
  calendar_code: "XNSE",
  is_active: true,
};

const instrument = {
  id: "i1",
  canonical_symbol: "NSE:NIFTY_50",
  exchange_symbol: "NIFTY 50",
  name: "NIFTY 50 Index",
  instrument_type: "index",
  quote_currency: "INR",
  tick_size: 0.05,
  lot_size: 50,
  is_tradeable: false,
  isin: null,
  is_synthetic: false,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  exchange,
};

const instrument2 = {
  ...instrument,
  id: "i2",
  name: "BANKNIFTY Index",
  exchange_symbol: "BANKNIFTY",
  canonical_symbol: "NSE:BANKNIFTY",
  is_tradeable: true,
};

const strategy = {
  id: "s1",
  creator_id: "u1",
  name: "India Trend",
  slug: "india-trend",
  description: "Trend strategy",
  status: "draft" as const,
  is_public: false,
  current_version_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  published_at: null,
  deployed_at: null,
};

const version1 = {
  id: "v1",
  strategy_id: "s1",
  instrument_id: "i1",
  instrument,
  version_number: 1,
  configuration: { period: 14 },
  backtest_configuration: { capital: 100000 },
  created_at: "2026-01-02T00:00:00Z",
};

const version2 = {
  id: "v2",
  strategy_id: "s1",
  instrument_id: "i2",
  instrument: instrument2,
  version_number: 2,
  configuration: { period: 20 },
  backtest_configuration: { capital: 200000 },
  created_at: "2026-01-03T00:00:00Z",
};

/* ── Test render helper ───────────────────────────────────────── */
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function view(ui: ReactNode, path: string) {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/creator/strategies/:strategyId" element={ui} />
          <Route path="/creator/strategies/:strategyId/versions/:versionId" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue(strategy);
  api.listVersions.mockResolvedValue([]);
  instrumentApi.list.mockResolvedValue([instrument]);
});

/* ── Helper: open the version creator form ─────────────────────── */
async function openCreator() {
  view(<StrategyDetailPage />, "/creator/strategies/s1");
  const btn = await screen.findByRole("button", { name: "Create Version" });
  await userEvent.click(btn);
  // Wait for instrument selector to render
  await screen.findByLabelText("Instrument");
}

/* ═══════════════════════════════════════════════════════════════
   Version list — states
   ═══════════════════════════════════════════════════════════════ */
describe("Version list", () => {
  it("shows loading state while versions are fetching", async () => {
    api.listVersions.mockReturnValue(new Promise(() => {}));
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    expect(await screen.findByText("Loading Versions…")).toBeInTheDocument();
  });

  it("shows empty state when no versions exist", async () => {
    api.listVersions.mockResolvedValue([]);
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    expect(await screen.findByText(/No Versions yet/)).toBeInTheDocument();
  });

  it("shows populated list with version numbers", async () => {
    api.listVersions.mockResolvedValue([version1, version2]);
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    expect(await screen.findByText("Version 1")).toBeInTheDocument();
    expect(screen.getByText("Version 2")).toBeInTheDocument();
  });

  it("shows instrument info in each version list item", async () => {
    api.listVersions.mockResolvedValue([version1]);
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    await screen.findByText("Version 1");
    expect(screen.getByText(/NIFTY 50 Index.*NSE/)).toBeInTheDocument();
  });

  it("shows Current badge on the current version", async () => {
    api.get.mockResolvedValue({ ...strategy, current_version_id: "v2" });
    api.listVersions.mockResolvedValue([version1, version2]);
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    // Wait for version list to render
    const versionItems = await screen.findAllByText(/^Version \d+$/);
    expect(versionItems.length).toBeGreaterThan(0);
    expect(screen.getByText("Current")).toBeInTheDocument();
  });

  it("shows an error when version list API fails", async () => {
    api.listVersions.mockRejectedValue(new ApiError(500, "Versions unavailable"));
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    expect(await screen.findByText("Versions unavailable")).toBeInTheDocument();
  });

  it("version list items link to the version detail page", async () => {
    api.listVersions.mockResolvedValue([version1]);
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    const link = await screen.findByRole("link", { name: /Version 1/ });
    expect(link).toHaveAttribute("href", "/creator/strategies/s1/versions/v1");
  });
});

/* ═══════════════════════════════════════════════════════════════
   Instrument search
   ═══════════════════════════════════════════════════════════════ */
describe("Instrument search in VersionCreator", () => {
  it("renders the instrument search input and selector", async () => {
    await openCreator();
    expect(screen.getByLabelText("Search Instrument")).toBeInTheDocument();
    expect(screen.getByLabelText("Instrument")).toBeInTheDocument();
  });

  it("calls the instruments API with search text after debounce", async () => {
    await openCreator();
    const searchInput = screen.getByLabelText("Search Instrument");
    await userEvent.type(searchInput, "nifty");
    // Wait for debounce + API call
    await waitFor(() => {
      expect(instrumentApi.list).toHaveBeenCalledWith("nifty");
    }, { timeout: 1500 });
  });

  it("does not call the API on every keystroke — debounce coalesces rapid typing", async () => {
    await openCreator();
    const searchInput = screen.getByLabelText("Search Instrument");
    // Type rapidly using fireEvent (synchronous, no delay)
    fireEvent.change(searchInput, { target: { value: "n" } });
    fireEvent.change(searchInput, { target: { value: "ni" } });
    fireEvent.change(searchInput, { target: { value: "nif" } });
    fireEvent.change(searchInput, { target: { value: "nift" } });
    fireEvent.change(searchInput, { target: { value: "nifty" } });
    // None of the intermediate values should be called immediately
    const intermediateCalls = instrumentApi.list.mock.calls.filter(
      ([q]) => ["n", "ni", "nif", "nift"].includes(q as string)
    );
    expect(intermediateCalls.length).toBe(0);
    // Wait for debounce to fire with the final value
    await waitFor(() => {
      expect(instrumentApi.list).toHaveBeenCalledWith("nifty");
    }, { timeout: 1500 });
    // Intermediates should never have been called
    const intermediateCallsAfter = instrumentApi.list.mock.calls.filter(
      ([q]) => ["n", "ni", "nif", "nift"].includes(q as string)
    );
    expect(intermediateCallsAfter.length).toBe(0);
  });

  it("shows instrument options from API response", async () => {
    instrumentApi.list.mockResolvedValue([instrument, instrument2]);
    await openCreator();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /NIFTY 50 Index/ })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /BANKNIFTY Index/ })).toBeInTheDocument();
    });
  });

  it("shows empty selector when instrument list is empty", async () => {
    instrumentApi.list.mockResolvedValue([]);
    await openCreator();
    const select = await screen.findByLabelText("Instrument");
    expect(select).toHaveDisplayValue("Select an Instrument");
  });

  it("shows an error when instrument API fails", async () => {
    instrumentApi.list.mockRejectedValue(new ApiError(500, "Instruments unavailable"));
    // Open creator — when API fails, the select won't render; just click the button
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    const btn = await screen.findByRole("button", { name: "Create Version" });
    await userEvent.click(btn);
    expect(await screen.findByText("Instruments unavailable")).toBeInTheDocument();
  });

  it("displays selected instrument canonical identity in preview", async () => {
    instrumentApi.list.mockResolvedValue([instrument]);
    await openCreator();
    await waitFor(() => screen.getByRole("option", { name: /NIFTY 50 Index/ }));
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    expect(screen.getByText(/NSE:NIFTY_50/)).toBeInTheDocument();
  });

  it("does not expose a raw UUID entry field to the user", async () => {
    await openCreator();
    expect(screen.queryByLabelText(/Instrument UUID/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/uuid/i)).not.toBeInTheDocument();
  });
});

/* ═══════════════════════════════════════════════════════════════
   Create Version
   ═══════════════════════════════════════════════════════════════ */
describe("Create Version", () => {
  async function openCreatorWithInstruments() {
    instrumentApi.list.mockResolvedValue([instrument]);
    await openCreator();
    await waitFor(() => screen.getByRole("option", { name: /NIFTY 50 Index/ }));
  }

  it("renders the version creation form", async () => {
    await openCreatorWithInstruments();
    expect(screen.getByLabelText("Algorithm configuration")).toBeInTheDocument();
    expect(screen.getByLabelText("Backtest configuration")).toBeInTheDocument();
  });

  it("requires an Instrument to be selected", async () => {
    await openCreatorWithInstruments();
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    // Error message should appear near the instrument field
    expect(await screen.findByText(/Select an Instrument before creating/)).toBeInTheDocument();
    expect(api.createVersion).not.toHaveBeenCalled();
  });

  it("rejects invalid JSON in algorithm configuration", async () => {
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    fireEvent.change(screen.getByLabelText("Algorithm configuration"), {
      target: { value: "not json" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    expect(await screen.findByText(/must contain valid JSON/)).toBeInTheDocument();
    expect(api.createVersion).not.toHaveBeenCalled();
  });

  it("rejects a JSON array in algorithm configuration", async () => {
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    fireEvent.change(screen.getByLabelText("Algorithm configuration"), {
      target: { value: "[1, 2, 3]" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    expect(await screen.findByText(/must be a JSON object/)).toBeInTheDocument();
    expect(api.createVersion).not.toHaveBeenCalled();
  });

  it("rejects a JSON primitive in algorithm configuration", async () => {
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    fireEvent.change(screen.getByLabelText("Algorithm configuration"), {
      target: { value: "42" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    expect(await screen.findByText(/must be a JSON object/)).toBeInTheDocument();
    expect(api.createVersion).not.toHaveBeenCalled();
  });

  it("rejects invalid JSON in backtest configuration", async () => {
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    fireEvent.change(screen.getByLabelText("Backtest configuration"), {
      target: { value: "bad json" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    expect(await screen.findByText(/must contain valid JSON/)).toBeInTheDocument();
    expect(api.createVersion).not.toHaveBeenCalled();
  });

  it("accepts valid JSON objects and submits correct payload", async () => {
    api.createVersion.mockResolvedValue(version1);
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    fireEvent.change(screen.getByLabelText("Algorithm configuration"), {
      target: { value: '{"period":14}' },
    });
    fireEvent.change(screen.getByLabelText("Backtest configuration"), {
      target: { value: '{"capital":100000}' },
    });
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    await waitFor(() =>
      expect(api.createVersion).toHaveBeenCalledWith(
        "s1",
        expect.objectContaining({
          instrument_id: "i1",
          configuration: { period: 14 },
          backtest_configuration: { capital: 100000 },
        })
      )
    );
  });

  it("navigates to the newly created version after successful creation", async () => {
    api.createVersion.mockResolvedValue(version1);
    api.getVersion.mockResolvedValue(version1);
    render(
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter initialEntries={["/creator/strategies/s1"]}>
          <Routes>
            <Route path="/creator/strategies/:strategyId" element={<StrategyDetailPage />} />
            <Route
              path="/creator/strategies/:strategyId/versions/:versionId"
              element={<div data-testid="version-detail-page">Version detail</div>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    const btn = await screen.findByRole("button", { name: "Create Version" });
    await userEvent.click(btn);
    await waitFor(() => screen.getByRole("option", { name: /NIFTY 50 Index/ }));
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    await waitFor(() => expect(api.createVersion).toHaveBeenCalled());
    expect(await screen.findByTestId("version-detail-page")).toBeInTheDocument();
  });

  it("invalidates version list query after successful creation", async () => {
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    api.createVersion.mockResolvedValue(version1);
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/creator/strategies/s1"]}>
          <Routes>
            <Route path="/creator/strategies/:strategyId" element={<StrategyDetailPage />} />
            <Route path="/creator/strategies/:strategyId/versions/:versionId" element={<div />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    const btn = await screen.findByRole("button", { name: "Create Version" });
    await userEvent.click(btn);
    await waitFor(() => screen.getByRole("option", { name: /NIFTY 50 Index/ }));
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    await waitFor(() => expect(api.createVersion).toHaveBeenCalled());
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: expect.arrayContaining(["strategy-versions", "s1"]) })
      )
    );
  });

  it("displays 409 conflict error from the API", async () => {
    api.createVersion.mockRejectedValue(
      new ApiError(409, "Instrument is already used in another version")
    );
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    expect(
      await screen.findByText("Instrument is already used in another version")
    ).toBeInTheDocument();
  });

  it("displays 422 validation error from the API", async () => {
    api.createVersion.mockRejectedValue(new ApiError(422, "Instrument is inactive"));
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    expect(await screen.findByText("Instrument is inactive")).toBeInTheDocument();
  });

  it("displays a user-friendly fallback for generic errors", async () => {
    api.createVersion.mockRejectedValue(new Error("Network error"));
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    expect(await screen.findByText("Unable to create Version.")).toBeInTheDocument();
  });

  it("disables the submit button while the creation is pending", async () => {
    let resolve!: (v: unknown) => void;
    api.createVersion.mockReturnValue(new Promise((r) => { resolve = r; }));
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    expect(await screen.findByRole("button", { name: "Creating…" })).toBeDisabled();
    resolve(version1);
  });

  it("prevents duplicate submission — button disabled in-flight", async () => {
    let resolve!: (v: unknown) => void;
    api.createVersion.mockReturnValue(new Promise((r) => { resolve = r; }));
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    // Second click while pending
    await userEvent.click(screen.getByRole("button", { name: "Creating…" }));
    resolve(version1);
    await waitFor(() => expect(api.createVersion).toHaveBeenCalledTimes(1));
  });
});

/* ═══════════════════════════════════════════════════════════════
   Version detail page
   ═══════════════════════════════════════════════════════════════ */
describe("Version detail page", () => {
  it("renders the version number", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    expect(await screen.findByText("Version 1")).toBeInTheDocument();
  });

  it("renders the creation date", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    expect(await screen.findByText(/Created/)).toBeInTheDocument();
  });

  it("renders instrument metadata including name, symbol, exchange, type, and currency", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    expect(await screen.findByText("NIFTY 50 Index")).toBeInTheDocument();
    expect(screen.getByText("NSE:NIFTY_50")).toBeInTheDocument();
    expect(screen.getByText("NIFTY 50")).toBeInTheDocument();
    expect(screen.getByText("NSE")).toBeInTheDocument();
    expect(screen.getByText(/index.*non-tradeable/)).toBeInTheDocument();
    expect(screen.getByText("INR")).toBeInTheDocument();
  });

  it("renders tick size and lot size", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    await screen.findByText("NIFTY 50 Index");
    expect(screen.getByText("0.05")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });

  it("renders algorithm configuration as formatted JSON", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    await screen.findByText("Algorithm configuration");
    expect(screen.getByText(/\"period\"/)).toBeInTheDocument();
  });

  it("renders backtest configuration as formatted JSON", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    await screen.findByText("Backtest configuration");
    expect(screen.getByText(/\"capital\"/)).toBeInTheDocument();
  });

  it("handles missing instrument (legacy/unresolved) safely — no crash", async () => {
    api.getVersion.mockResolvedValue({ ...version1, instrument_id: null, instrument: null });
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    expect(await screen.findByText("legacy / unresolved")).toBeInTheDocument();
  });

  it("handles 404 — shows version not found message", async () => {
    api.getVersion.mockRejectedValue(new ApiError(404, "Not found"));
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/bad");
    expect(await screen.findByText("Strategy Version not found.")).toBeInTheDocument();
  });

  it("handles a generic API failure gracefully", async () => {
    api.getVersion.mockRejectedValue(new ApiError(500, "Service unavailable"));
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    expect(await screen.findByText("Unable to load this Version.")).toBeInTheDocument();
  });

  it("communicates immutability with a note", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    await screen.findByText("Version 1");
    expect(screen.getByRole("note")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/immutable/i);
  });

  it("does not render edit or delete buttons", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    await screen.findByText("Version 1");
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });

  it("includes a back link to the parent strategy", async () => {
    api.getVersion.mockResolvedValue(version1);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v1");
    await screen.findByText("Version 1");
    // The back link points to /creator/strategies/:strategyId
    const allLinks = screen.getAllByRole("link");
    const backLink = allLinks.find(
      (l) => l.getAttribute("href") === "/creator/strategies/s1"
    );
    expect(backLink).toBeTruthy();
  });
});

/* ═══════════════════════════════════════════════════════════════
   Accessibility
   ═══════════════════════════════════════════════════════════════ */
describe("Accessibility", () => {
  async function openCreatorWithInstruments() {
    view(<StrategyDetailPage />, "/creator/strategies/s1");
    const btn = await screen.findByRole("button", { name: "Create Version" });
    await userEvent.click(btn);
    await waitFor(() => screen.getByRole("option", { name: /NIFTY 50 Index/ }));
  }

  it("associates labels with form controls", async () => {
    await openCreatorWithInstruments();
    expect(screen.getByLabelText("Search Instrument")).toBeInTheDocument();
    expect(screen.getByLabelText("Instrument")).toBeInTheDocument();
    expect(screen.getByLabelText("Algorithm configuration")).toBeInTheDocument();
    expect(screen.getByLabelText("Backtest configuration")).toBeInTheDocument();
  });

  it("sets aria-invalid on algorithm configuration textarea when JSON is invalid", async () => {
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    fireEvent.change(screen.getByLabelText("Algorithm configuration"), {
      target: { value: "bad json" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    await screen.findByText(/must contain valid JSON/);
    expect(screen.getByLabelText("Algorithm configuration")).toHaveAttribute("aria-invalid", "true");
  });

  it("sets aria-describedby on configuration textarea to hint when no error", async () => {
    await openCreatorWithInstruments();
    expect(screen.getByLabelText("Algorithm configuration")).toHaveAttribute(
      "aria-describedby",
      "version-config-hint"
    );
  });

  it("sets aria-describedby to error id when configuration has a JSON error", async () => {
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    fireEvent.change(screen.getByLabelText("Algorithm configuration"), {
      target: { value: "bad json" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    await screen.findByText(/must contain valid JSON/);
    expect(screen.getByLabelText("Algorithm configuration")).toHaveAttribute(
      "aria-describedby",
      "version-config-error"
    );
  });

  it("exposes validation errors with alert role", async () => {
    await openCreatorWithInstruments();
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
  });

  it("disables submit button and sets aria-disabled while pending", async () => {
    let resolve!: (v: unknown) => void;
    api.createVersion.mockReturnValue(new Promise((r) => { resolve = r; }));
    await openCreatorWithInstruments();
    await userEvent.selectOptions(screen.getByLabelText("Instrument"), "i1");
    await userEvent.click(screen.getByRole("button", { name: "Create Version" }));
    const pendingBtn = await screen.findByRole("button", { name: "Creating…" });
    expect(pendingBtn).toBeDisabled();
    expect(pendingBtn).toHaveAttribute("aria-disabled", "true");
    resolve(version1);
  });
});
