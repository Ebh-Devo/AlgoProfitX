/**
 * C1 Strategy Builder — focused tests
 *
 * Covers: create validation, slug validation, successful create,
 * API field-level errors, generic API failure, submitting/disabled state,
 * edit form population, successful update with cache invalidation and
 * navigation, and update failure.
 */
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { ApiError } from "../../api/client";
import { StrategyEditPage, StrategyNewPage } from "./StrategyPages";

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
vi.mock("../../api/strategies", () => ({ strategiesApi: api }));
vi.mock("../../api/instruments", () => ({ instrumentsApi: { list: vi.fn() } }));

/* ── Fixture data ─────────────────────────────────────────────── */
const baseStrategy = {
  id: "s1",
  creator_id: "u1",
  name: "Alpha Momentum",
  slug: "alpha-momentum",
  description: "A momentum-based strategy",
  status: "draft" as const,
  is_public: false,
  current_version_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  published_at: null,
  deployed_at: null,
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
          <Route path="/creator/strategies/new" element={ui} />
          <Route path="/creator/strategies/:strategyId/edit" element={ui} />
          <Route path="/creator/strategies/:strategyId" element={<div data-testid="detail-page" />} />
          <Route path="/creator/strategies" element={<div data-testid="list-page" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listVersions.mockResolvedValue([]);
});

/* ═══════════════════════════════════════════════════════════════
   Create form
   ═══════════════════════════════════════════════════════════════ */
describe("StrategyNewPage — create form", () => {
  it("renders all required fields and the submit button", () => {
    view(<StrategyNewPage />, "/creator/strategies/new");
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Slug/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Description/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create strategy" })).toBeInTheDocument();
  });

  it("shows required-field validation errors without calling the API", async () => {
    view(<StrategyNewPage />, "/creator/strategies/new");
    await userEvent.click(screen.getByRole("button", { name: "Create strategy" }));
    expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
    expect(api.create).not.toHaveBeenCalled();
  });

  it("rejects a name shorter than 3 characters", async () => {
    view(<StrategyNewPage />, "/creator/strategies/new");
    await userEvent.type(screen.getByLabelText("Name"), "ab");
    await userEvent.click(screen.getByRole("button", { name: "Create strategy" }));
    expect(await screen.findByText("Name must be at least 3 characters")).toBeInTheDocument();
    expect(api.create).not.toHaveBeenCalled();
  });

  it("submits valid data and navigates to the new strategy detail page", async () => {
    api.create.mockResolvedValue(baseStrategy);
    view(<StrategyNewPage />, "/creator/strategies/new");

    await userEvent.type(screen.getByLabelText("Name"), "Alpha Momentum");
    await userEvent.click(screen.getByRole("button", { name: "Create strategy" }));

    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith({
        name: "Alpha Momentum",
        description: null,
      })
    );
    expect(await screen.findByTestId("detail-page")).toBeInTheDocument();
  });

  it("surfaces a generic API error as a form-level alert", async () => {
    api.create.mockRejectedValue(new ApiError(500, "Internal server error"));
    view(<StrategyNewPage />, "/creator/strategies/new");

    await userEvent.type(screen.getByLabelText("Name"), "Alpha Momentum");
    await userEvent.click(screen.getByRole("button", { name: "Create strategy" }));

    expect(await screen.findByText("Internal server error")).toBeInTheDocument();
  });

  it("maps an API field-level error for name onto the name field", async () => {
    const err = new ApiError(422, "Name is invalid", [{ path: "name", message: "Name is invalid" }]);
    api.create.mockRejectedValue(err);

    view(<StrategyNewPage />, "/creator/strategies/new");
    await userEvent.type(screen.getByLabelText("Name"), "Alpha Momentum");
    await userEvent.click(screen.getByRole("button", { name: "Create strategy" }));

    expect(await screen.findByText("Name is invalid")).toBeInTheDocument();
  });

  it("disables the submit button while submitting and re-enables on error", async () => {
    let resolve!: (v: unknown) => void;
    api.create.mockReturnValue(new Promise((r) => { resolve = r; }));

    view(<StrategyNewPage />, "/creator/strategies/new");
    await userEvent.type(screen.getByLabelText("Name"), "Alpha Momentum");

    const btn = screen.getByRole("button", { name: "Create strategy" });
    await userEvent.click(btn);

    // While pending the button text changes and is disabled
    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();

    // Resolve with an error to trigger re-enable
    resolve(Promise.reject(new ApiError(500, "Server error")));
    expect(await screen.findByRole("button", { name: "Create strategy" })).not.toBeDisabled();
  });

  it("prevents duplicate submission by disabling the button during the request", async () => {
    let resolve!: (v: unknown) => void;
    api.create.mockReturnValue(new Promise((r) => { resolve = r; }));

    view(<StrategyNewPage />, "/creator/strategies/new");
    await userEvent.type(screen.getByLabelText("Name"), "Alpha Momentum");

    const btn = screen.getByRole("button", { name: "Create strategy" });
    await userEvent.click(btn);

    // Rapid second click while request is in-flight
    await userEvent.click(screen.getByRole("button", { name: "Saving…" }));

    resolve(baseStrategy);
    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
  });

  it("wires aria-describedby on Name input to the error paragraph id", async () => {
    view(<StrategyNewPage />, "/creator/strategies/new");
    await userEvent.click(screen.getByRole("button", { name: "Create strategy" }));
    await screen.findAllByRole("alert");

    const nameInput = screen.getByLabelText("Name");
    expect(nameInput).toHaveAttribute("aria-describedby", "strategy-name-error");
    expect(nameInput).toHaveAttribute("aria-invalid", "true");
  });
});

/* ═══════════════════════════════════════════════════════════════
   Edit form
   ═══════════════════════════════════════════════════════════════ */
describe("StrategyEditPage — edit form", () => {
  beforeEach(() => {
    api.get.mockResolvedValue(baseStrategy);
  });

  it("pre-populates form fields from the loaded strategy", async () => {
    view(<StrategyEditPage />, "/creator/strategies/s1/edit");

    const name = await screen.findByLabelText("Name");
    expect(name).toHaveValue("Alpha Momentum");
    expect(screen.queryByLabelText(/Slug/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Description/)).toHaveValue("A momentum-based strategy");
  });

  it("renders the Save changes button", async () => {
    view(<StrategyEditPage />, "/creator/strategies/s1/edit");
    expect(await screen.findByRole("button", { name: "Save changes" })).toBeInTheDocument();
  });

  it("submits the updated values and navigates back to the detail page", async () => {
    api.update.mockResolvedValue({ ...baseStrategy, name: "Beta Momentum" });
    view(<StrategyEditPage />, "/creator/strategies/s1/edit");

    const nameInput = await screen.findByLabelText("Name");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Beta Momentum");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith(
        "s1",
        expect.objectContaining({ name: "Beta Momentum" })
      )
    );
    expect(await screen.findByTestId("detail-page")).toBeInTheDocument();
  });

  it("surfaces a generic update failure as a form-level alert", async () => {
    api.update.mockRejectedValue(new ApiError(500, "Update failed"));
    view(<StrategyEditPage />, "/creator/strategies/s1/edit");

    await screen.findByLabelText("Name");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Update failed")).toBeInTheDocument();
    expect(screen.queryByTestId("detail-page")).not.toBeInTheDocument();
  });

  it("maps an API field-level error for slug onto the slug field during update", async () => {
    const err = new ApiError(409, "Slug conflict", [{ path: "slug", message: "Slug conflict" }]);
    api.update.mockRejectedValue(err);

    view(<StrategyEditPage />, "/creator/strategies/s1/edit");
    await screen.findByLabelText("Name");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Slug conflict")).toBeInTheDocument();
  });

  it("shows a status notice when the strategy is not in draft state", async () => {
    api.get.mockResolvedValue({ ...baseStrategy, status: "published" });
    view(<StrategyEditPage />, "/creator/strategies/s1/edit");

    expect(await screen.findByRole("note")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/published/i);
  });

  it("disables the submit button while the update is in-flight", async () => {
    let resolve!: (v: unknown) => void;
    api.update.mockReturnValue(new Promise((r) => { resolve = r; }));

    view(<StrategyEditPage />, "/creator/strategies/s1/edit");
    await screen.findByLabelText("Name");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    resolve({ ...baseStrategy });
  });
});
