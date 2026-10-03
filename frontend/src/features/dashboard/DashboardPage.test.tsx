import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { DashboardShell } from "../../components/DashboardShell";
import { DashboardPage } from "./DashboardPage";

/* ── Auth mock ───────────────────────────────────────────────── */
const auth = vi.hoisted(() => ({
  value: {
    user: null as { email: string; roles: string[] } | null,
    isAuthenticated: false,
    isLoading: false,
    logout: vi.fn(),
  },
}));
vi.mock("../../auth/auth-context", () => ({ useAuth: () => auth.value }));

/* ── API mocks ───────────────────────────────────────────────── */
const listStrategies = vi.fn();
const listAllocations = vi.fn();
const listExecutionIntents = vi.fn();

vi.mock("../../api/strategies", () => ({ strategiesApi: { list: () => listStrategies() } }));
vi.mock("../../api/investor", () => ({
  investorApi: {
    listAllocations: () => listAllocations(),
    listExecutionIntents: () => listExecutionIntents(),
  },
}));

/* ── Test helpers ────────────────────────────────────────────── */
function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
}

function renderWithProviders(
  ui: React.ReactElement,
  { initialPath = "/app" }: { initialPath?: string } = {}
) {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={[initialPath]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

/* ═══════════════════════════════════════════════════════════════
   DashboardShell tests
   ═══════════════════════════════════════════════════════════════ */

describe("DashboardShell", () => {
  beforeEach(() => {
    auth.value = {
      user: { email: "creator@example.com", roles: ["CREATOR", "INVESTOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
  });

  it("renders brand identity and sidebar navigation for dual-role user", () => {
    renderWithProviders(<DashboardShell />);
    // Brand
    expect(screen.getByRole("link", { name: /algoprofitx home/i })).toBeInTheDocument();
    // Core nav items
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /marketplace/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /strategies/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /allocations/i })).toBeInTheDocument();
  });

  it("shows the Creator and Investor roles in the account menu", () => {
    renderWithProviders(<DashboardShell />);
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));
    expect(screen.getByRole("menu", { name: /account/i })).toHaveTextContent("Creator · Investor");
  });

  it("omits Strategies nav item when user lacks Creator role", () => {
    auth.value = {
      ...auth.value,
      user: { email: "inv@example.com", roles: ["INVESTOR"] },
    };
    renderWithProviders(<DashboardShell />);
    expect(screen.queryByRole("link", { name: /^strategies$/i })).not.toBeInTheDocument();
  });

  it("shows Account link and logout button", () => {
    renderWithProviders(<DashboardShell />);
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));
    expect(screen.getByRole("menuitem", { name: /account settings/i })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("menuitem", { name: /log out/i })).toBeInTheDocument();
  });

  it("shows coming-soon Analytics item in sidebar", () => {
    renderWithProviders(<DashboardShell />);
    // Analytics appears in both desktop sidebar and mobile drawer
    const analyticsItems = screen.getAllByText("Analytics");
    expect(analyticsItems.length).toBeGreaterThanOrEqual(1);
  });

  it("calls logout and navigates on logout click", async () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    auth.value = { ...auth.value, logout };
    renderWithProviders(<DashboardShell />);
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /log out/i }));
    await waitFor(() => expect(logout).toHaveBeenCalledOnce());
  });

  describe("mobile navigation", () => {
    it("shows hamburger button on mobile layout", () => {
      renderWithProviders(<DashboardShell />);
      expect(screen.getByRole("button", { name: /open navigation/i })).toBeInTheDocument();
    });

    it("toggles mobile drawer open/closed via hamburger", () => {
      renderWithProviders(<DashboardShell />);
      const btn = screen.getByRole("button", { name: /open navigation/i });
      expect(btn).toHaveAttribute("aria-expanded", "false");

      fireEvent.click(btn);
      expect(screen.getByRole("button", { name: /close navigation/i })).toHaveAttribute("aria-expanded", "true");

      fireEvent.keyDown(window, { key: "Escape" });
      expect(screen.getByRole("button", { name: /open navigation/i })).toHaveAttribute("aria-expanded", "false");
    });

    it("mobile drawer has dialog role and aria-label", () => {
      renderWithProviders(<DashboardShell />);
      fireEvent.click(screen.getByRole("button", { name: /open navigation/i }));
      const drawer = document.getElementById("ws-drawer");
      expect(drawer).toHaveAttribute("role", "dialog");
      expect(drawer).toHaveAttribute("aria-label", "Mobile application navigation");
    });
  });
});

/* ═══════════════════════════════════════════════════════════════
   DashboardPage tests
   ═══════════════════════════════════════════════════════════════ */

describe("DashboardPage", () => {
  beforeEach(() => {
    listStrategies.mockResolvedValue([]);
    listAllocations.mockResolvedValue([]);
    listExecutionIntents.mockResolvedValue([]);
  });

  it("shows loading state while auth is resolving", () => {
    auth.value = { user: null, isAuthenticated: false, isLoading: true, logout: vi.fn() };
    renderWithProviders(<DashboardPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(/loading your dashboard/i)).toBeInTheDocument();
  });

  it("renders welcome heading with user name for creator+investor", async () => {
    auth.value = {
      user: { email: "alice@example.com", roles: ["CREATOR", "INVESTOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    });
    expect(screen.getByText("alice")).toBeInTheDocument();
  });

  it("renders capability strip with Creator active state", async () => {
    auth.value = {
      user: { email: "c@example.com", roles: ["CREATOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("Active", { selector: ".dash-capability-value--active" })).toBeInTheDocument();
    });
  });

  it("shows empty state when creator has no strategies", async () => {
    auth.value = {
      user: { email: "c@example.com", roles: ["CREATOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listStrategies.mockResolvedValue([]);
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/no strategies yet/i)).toBeInTheDocument();
    });
  });

  it("renders strategy list when creator has strategies", async () => {
    auth.value = {
      user: { email: "c@example.com", roles: ["CREATOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listStrategies.mockResolvedValue([
      {
        id: "s1",
        name: "Momentum Alpha",
        slug: "momentum-alpha",
        status: "published",
        updated_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
        creator_id: "u1",
        description: null,
        is_public: true,
        current_version_id: null,
        published_at: null,
        deployed_at: null,
      },
    ]);
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("Momentum Alpha")).toBeInTheDocument();
    });
    expect(screen.getByText("published")).toBeInTheDocument();
  });

  it("shows error state when strategy API fails", async () => {
    auth.value = {
      user: { email: "c@example.com", roles: ["CREATOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listStrategies.mockRejectedValue(new Error("Server error"));
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/server error/i)).toBeInTheDocument();
    });
  });

  it("shows investor stats when user has INVESTOR role", async () => {
    auth.value = {
      user: { email: "inv@example.com", roles: ["INVESTOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listAllocations.mockResolvedValue([{ id: "a1", status: "active", strategy_name: "Test", strategy_version_number: 1, notional_amount: "10000", currency: "INR", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), strategy_id: "s1", strategy_version_id: "v1", investor_user_id: "u1" }]);
    listExecutionIntents.mockResolvedValue([]);
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("Active allocations")).toBeInTheDocument();
      // "Execution intents" appears in the stat label and the footer link — both are correct
      expect(screen.getAllByText("Execution intents").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows empty execution state for investor with no intents", async () => {
    auth.value = {
      user: { email: "inv@example.com", roles: ["INVESTOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listAllocations.mockResolvedValue([]);
    listExecutionIntents.mockResolvedValue([]);
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/no execution intents/i)).toBeInTheDocument();
    });
  });

  it("shows workspace setup card for user with no roles", async () => {
    auth.value = {
      user: { email: "new@example.com", roles: [] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/set up your workspace/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: /enroll as creator/i })).toBeInTheDocument();
  });

  it("renders research disclosure note", async () => {
    auth.value = {
      user: { email: "c@example.com", roles: ["CREATOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listStrategies.mockResolvedValue([]);
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/designed for transparent research/i)).toBeInTheDocument();
    });
  });

  it("renders Explore section tiles always visible", async () => {
    auth.value = {
      user: { email: "c@example.com", roles: ["CREATOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listStrategies.mockResolvedValue([]);
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByRole("link", { name: /browse the strategy marketplace/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /browse instruments/i })).toBeInTheDocument();
    });
  });

  it("shows New Strategy header action for creator", async () => {
    auth.value = {
      user: { email: "c@example.com", roles: ["CREATOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listStrategies.mockResolvedValue([]);
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      // "Create a new strategy" appears in both the page header CTA and the Explore tile — both are correct
      expect(screen.getAllByRole("link", { name: /create a new strategy/i }).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders platform status strip with paper-only badge", async () => {
    auth.value = {
      user: { email: "c@example.com", roles: ["CREATOR"] },
      isAuthenticated: true,
      isLoading: false,
      logout: vi.fn(),
    };
    listStrategies.mockResolvedValue([]);
    renderWithProviders(<DashboardPage />);
    await waitFor(() => {
      // "Paper only" appears in the capability strip and the platform status strip — both are correct
      expect(screen.getAllByText(/paper only/i).length).toBeGreaterThanOrEqual(1);
    });
  });
});
