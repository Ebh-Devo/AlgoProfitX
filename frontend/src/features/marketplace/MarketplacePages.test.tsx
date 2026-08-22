import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import { MarketplaceDetailPage, MarketplaceListPage } from "./MarketplacePages";

const api = vi.hoisted(() => ({ list: vi.fn(), getBySlug: vi.fn() }));
vi.mock("../../api/marketplace", () => ({ marketplaceApi: api }));

function renderWithQuery(ui: ReactNode, initialEntries = ["/"]) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter></QueryClientProvider>);
}

const strategy = { id: "id-1", slug: "trend", name: "Trend", description: "Public strategy", status: "published", published_at: "2025-01-01T00:00:00Z", current_version_id: "version-1", current_version_number: 2 };

describe("Marketplace pages", () => {
  it("renders anonymous marketplace results", async () => {
    api.list.mockResolvedValue([strategy]);
    renderWithQuery(<MarketplaceListPage />);
    expect(await screen.findByRole("heading", { name: "Trend" })).toBeInTheDocument();
    expect(screen.getByText("Current version")).toBeInTheDocument();
  });

  it("renders public strategy detail without private configuration", async () => {
    api.getBySlug.mockResolvedValue(strategy);
    renderWithQuery(
      <Routes><Route path="/marketplace/:slug" element={<MarketplaceDetailPage />} /></Routes>,
      ["/marketplace/trend"],
    );
    expect(await screen.findByRole("heading", { name: "Trend" })).toBeInTheDocument();
    expect(screen.getByText(/does not include creator configuration/i)).toBeInTheDocument();
  });
});
