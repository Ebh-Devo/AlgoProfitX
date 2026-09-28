import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import { ApiError } from "../../api/client";
import { MarketplaceDetailPage, MarketplaceListPage } from "./MarketplacePages";

const api = vi.hoisted(() => ({ list: vi.fn(), getBySlug: vi.fn() }));
vi.mock("../../api/marketplace", () => ({ marketplaceApi: api }));

function renderWithQuery(ui: ReactNode, initialEntries = ["/"]) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const strategy1 = {
  id: "id-1",
  slug: "trend-momentum",
  name: "Trend Momentum",
  description: "Algorithmic trend following strategy for equities",
  status: "published",
  published_at: "2025-01-01T00:00:00Z",
  current_version_id: "version-1",
  current_version_number: 2,
};

const strategy2 = {
  id: "id-2",
  slug: "mean-reversion",
  name: "Mean Reversion",
  description: "Statistical mean reversion strategy for indices",
  status: "deployed",
  published_at: "2025-02-01T00:00:00Z",
  current_version_id: "version-2",
  current_version_number: 1,
};

describe("Marketplace pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders anonymous marketplace results", async () => {
    api.list.mockResolvedValue([strategy1]);
    renderWithQuery(<MarketplaceListPage />);
    expect(await screen.findByRole("heading", { name: "Trend Momentum" })).toBeInTheDocument();
    expect(screen.getByText("Current version")).toBeInTheDocument();
    expect(screen.getByText("Public strategies")).toBeInTheDocument();
  });

  it("filters strategies by search input", async () => {
    api.list.mockResolvedValue([strategy1, strategy2]);
    renderWithQuery(<MarketplaceListPage />);

    expect(await screen.findByRole("heading", { name: "Trend Momentum" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Mean Reversion" })).toBeInTheDocument();

    const searchInput = screen.getByLabelText(/search strategies/i);
    await userEvent.type(searchInput, "mean");

    expect(screen.queryByRole("heading", { name: "Trend Momentum" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Mean Reversion" })).toBeInTheDocument();
  });

  it("filters strategies by status select", async () => {
    api.list.mockResolvedValue([strategy1, strategy2]);
    renderWithQuery(<MarketplaceListPage />);

    expect(await screen.findByRole("heading", { name: "Trend Momentum" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Mean Reversion" })).toBeInTheDocument();

    const statusSelect = screen.getByLabelText(/filter by status/i);
    await userEvent.selectOptions(statusSelect, "deployed");

    expect(screen.queryByRole("heading", { name: "Trend Momentum" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Mean Reversion" })).toBeInTheDocument();
  });

  it("shows empty state when search returns no match and allows resetting filters", async () => {
    api.list.mockResolvedValue([strategy1]);
    renderWithQuery(<MarketplaceListPage />);

    expect(await screen.findByRole("heading", { name: "Trend Momentum" })).toBeInTheDocument();

    const searchInput = screen.getByLabelText(/search strategies/i);
    await userEvent.type(searchInput, "nonexistent");

    expect(screen.getByText("No strategies match your criteria")).toBeInTheDocument();

    const resetButton = screen.getByRole("button", { name: /reset filters/i });
    await userEvent.click(resetButton);

    expect(await screen.findByRole("heading", { name: "Trend Momentum" })).toBeInTheDocument();
  });

  it("surfaces API error when marketplace request fails", async () => {
    api.list.mockRejectedValue(new ApiError(500, "Server failed to load marketplace"));
    renderWithQuery(<MarketplaceListPage />);

    expect(await screen.findByText("Server failed to load marketplace")).toBeInTheDocument();
  });

  it("renders public strategy detail without private configuration", async () => {
    api.getBySlug.mockResolvedValue(strategy1);
    renderWithQuery(
      <Routes>
        <Route path="/marketplace/:slug" element={<MarketplaceDetailPage />} />
      </Routes>,
      ["/marketplace/trend-momentum"]
    );

    expect(await screen.findByRole("heading", { name: "Trend Momentum" })).toBeInTheDocument();
    expect(screen.getByText(/does not include creator configuration/i)).toBeInTheDocument();
    expect(screen.getByText("Verified Transparency")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /marketplace/i })).toBeInTheDocument();
  });

  it("renders 404 message when strategy detail is not found", async () => {
    api.getBySlug.mockRejectedValue(new ApiError(404, "Not Found"));
    renderWithQuery(
      <Routes>
        <Route path="/marketplace/:slug" element={<MarketplaceDetailPage />} />
      </Routes>,
      ["/marketplace/missing-slug"]
    );

    expect(await screen.findByText("This marketplace strategy is not available.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to marketplace/i })).toBeInTheDocument();
  });
});

