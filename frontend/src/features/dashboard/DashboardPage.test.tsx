import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
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

  const asUser = (roles: string[], email = "c@example.com") => {
    auth.value = { user: { email, roles }, isAuthenticated: true, isLoading: false, logout: vi.fn() };
  };
  const strategy = (over: Record<string, unknown> = {}) => ({
    id: "s1", name: "Momentum Alpha", slug: "momentum-alpha", status: "published", creator_id: "u1", description: null,
    is_public: true, current_version_id: null, created_at: "2026-01-01T00:00:00Z", updated_at: new Date().toISOString(),
    published_at: "2026-01-02T00:00:00Z", deployed_at: null, ...over,
  });
  const intent = (over: Record<string, unknown> = {}) => ({
    id: "e1", strategy_name: "Momentum Alpha", strategy_version_number: 2, notional_amount_snapshot: "50000", currency_snapshot: "INR",
    status: "completed", created_at: "2026-02-01T00:00:00Z", started_at: "2026-02-01T00:01:00Z", completed_at: "2026-02-01T00:02:00Z", ...over,
  });

  it("shows a skeleton status while auth is resolving", () => {
    auth.value = { user: null, isAuthenticated: false, isLoading: true, logout: vi.fn() };
    renderWithProviders(<DashboardPage />);
    expect(screen.getAllByRole("status").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/loading your dashboard/i)).toBeInTheDocument();
  });

  it("renders the page header with a primary New strategy action for creators", async () => {
    asUser(["CREATOR"]);
    renderWithProviders(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /new strategy/i })[0]).toHaveAttribute("href", "/creator/strategies/new");
  });

  it("summarises strategies by status using real counts", async () => {
    asUser(["CREATOR"]);
    listStrategies.mockResolvedValue([
      strategy({ id: "a", status: "deployed" }),
      strategy({ id: "b", status: "published" }),
      strategy({ id: "c", name: "Draft One", status: "draft" }),
      strategy({ id: "d", name: "Old", status: "archived" }),
    ]);
    renderWithProviders(<DashboardPage />);
    const group = await screen.findByRole("group", { name: "Strategy summary" });
    expect(group).toHaveTextContent(/Total\s*4/);
    expect(group).toHaveTextContent(/Deployed\s*1/);
    expect(group).toHaveTextContent(/Published\s*1/);
    expect(group).toHaveTextContent(/Drafts\s*1/);
    expect(group).toHaveTextContent("1 archived");
  });

  it("shows a first-use empty state with a create CTA when there are no strategies", async () => {
    asUser(["CREATOR"]);
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText("No strategies yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /create your first strategy/i })).toHaveAttribute("href", "/creator/strategies/new");
    expect(screen.getByText("No activity yet")).toBeInTheDocument();
  });

  it("lists recent strategies with a text status badge", async () => {
    asUser(["CREATOR"]);
    listStrategies.mockResolvedValue([strategy()]);
    renderWithProviders(<DashboardPage />);
    const section = (await screen.findByRole("heading", { name: "Strategies", level: 2 })).closest("section")!;
    expect(await within(section).findByText("Momentum Alpha")).toBeInTheDocument();
    expect(section).toHaveTextContent("published");
  });

  it("derives recent activity from real timestamps, newest first", async () => {
    asUser(["CREATOR"]);
    listStrategies.mockResolvedValue([
      strategy({ id: "x", name: "Old Idea", created_at: "2026-01-01T00:00:00Z", published_at: null, status: "draft", updated_at: "2026-01-01T00:00:00Z" }),
      strategy({ id: "y", name: "Fresh Idea", created_at: "2026-03-01T00:00:00Z", published_at: "2026-03-02T00:00:00Z", deployed_at: "2026-03-03T00:00:00Z", status: "deployed" }),
    ]);
    renderWithProviders(<DashboardPage />);
    const feed = await screen.findByRole("list", { name: "Recent activity" });
    const items = feed.querySelectorAll("li");
    expect(items[0]).toHaveTextContent("Deployed Fresh Idea");
    expect(items[1]).toHaveTextContent("Published Fresh Idea");
    expect(items[items.length - 1]).toHaveTextContent("Created draft Old Idea");
  });

  it("shows a friendly, recoverable error instead of the raw backend message", async () => {
    asUser(["CREATOR"]);
    listStrategies.mockRejectedValueOnce(new Error("pg: connection refused 10.0.0.4"));
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText(/couldn.t load your strategies/i)).toBeInTheDocument();
    expect(screen.queryByText(/connection refused/i)).not.toBeInTheDocument();
    listStrategies.mockResolvedValue([strategy()]);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.getAllByText("Momentum Alpha").length).toBeGreaterThan(0));
  });

  it("shows paper-execution counts and recent intents for investors", async () => {
    asUser(["INVESTOR"], "inv@example.com");
    listAllocations.mockResolvedValue([{ id: "a1", status: "active", strategy_name: "Momentum Alpha", strategy_version_number: 2, notional_amount: "50000", currency: "INR", created_at: "2026-01-15T00:00:00Z" }]);
    listExecutionIntents.mockResolvedValue([intent(), intent({ id: "e2", status: "failed" })]);
    renderWithProviders(<DashboardPage />);
    const group = await screen.findByRole("group", { name: "Execution summary" });
    expect(group).toHaveTextContent(/Active allocations\s*1/);
    expect(group).toHaveTextContent(/Execution intents\s*2/);
    expect(group).toHaveTextContent(/Completed\s*1/);
    expect(group).toHaveTextContent(/Failed\s*1/);
    const feed = await screen.findByRole("list", { name: "Recent activity" });
    expect(feed).toHaveTextContent(/Paper execution failed for Momentum Alpha/);
  });

  it("shows an empty execution state for an investor with no intents", async () => {
    asUser(["INVESTOR"], "inv@example.com");
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText(/no execution intents/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /go to allocations/i })).toBeInTheDocument();
  });

  it("shows the workspace setup state for a user with no roles", async () => {
    asUser([], "new@example.com");
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText(/set up your workspace/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /enroll as creator/i })).toBeInTheDocument();
  });

  it("states that execution is simulated and never implies live trading", async () => {
    asUser(["CREATOR"]);
    renderWithProviders(<DashboardPage />);
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(/simulation only/i);
    expect(note).toHaveTextContent(/no orders are placed with a broker/i);
  });

  it("offers quick actions for the user's roles plus marketplace and instruments", async () => {
    asUser(["CREATOR", "INVESTOR"]);
    renderWithProviders(<DashboardPage />);
    const quick = (await screen.findByRole("heading", { name: "Quick actions" })).closest("section")!;
    for (const name of [/create strategy/i, /view strategies/i, /allocations/i, /view executions/i, /browse marketplace/i, /instruments/i]) {
      expect(within(quick).getByRole("link", { name })).toBeInTheDocument();
    }
  });
});

/* ═══════════════════════════════════════════════════════════════
   Contextual guidance (PR #26) — derived from real fields only
   ═══════════════════════════════════════════════════════════════ */
import { buildAttention, pickNextStep } from "./DashboardPage";

describe("dashboard guidance", () => {
  const strat = (over: Record<string, unknown> = {}) => ({
    id: "s1", name: "Alpha", slug: "alpha", status: "draft", current_version_id: null, is_public: false,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", published_at: null, deployed_at: null, ...over,
  }) as never;
  const run = (over: Record<string, unknown> = {}) => ({ id: "e1", strategy_name: "Alpha", status: "completed", ...over }) as never;

  it("flags drafts without a Version and failed or in-progress executions", () => {
    const items = buildAttention([strat(), strat({ id: "s2" })], [run({ status: "failed" }), run({ id: "e2", status: "running" })]);
    expect(items.map(i => i.key)).toEqual(["failed-executions", "active-executions", "drafts-without-version"]);
    expect(items[2].label).toMatch(/2 drafts have no Version/);
  });

  it("reports nothing when nothing needs attention", () => {
    expect(buildAttention([strat({ status: "published", current_version_id: "v1" })], [run()])).toEqual([]);
  });

  it("suggests adding a Version for a draft without one, linking to that strategy", () => {
    const step = pickNextStep(true, false, [strat()], [], []);
    expect(step?.stage).toBe("version");
    expect(step?.action.to).toBe("/creator/strategies/s1");
  });

  it("does not duplicate the empty-state call to action for a creator with no strategies", () => {
    expect(pickNextStep(true, false, [], [], [])).toBeNull();
  });

  it("points an investor with no allocations at the marketplace, and prioritises failures", () => {
    expect(pickNextStep(false, true, [], [], [])?.action.to).toBe("/marketplace");
    expect(pickNextStep(false, true, [], [{} as never], [run({ status: "failed" })])?.action.to).toBe("/investor/execution-intents/e1");
  });

  it("renders the next step and attention list for a creator with an unversioned draft", async () => {
    auth.value = { user: { email: "c@example.com", roles: ["CREATOR"] }, isAuthenticated: true, isLoading: false, logout: vi.fn() };
    listStrategies.mockResolvedValue([strat()]);
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByRole("region", { name: "Suggested next step" })).toHaveTextContent("Continue building");
    expect(screen.getByRole("heading", { name: /Needs attention/ })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Where you are in the workflow" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh data" })).toBeInTheDocument();
  });
});
