import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { PUBLIC_NAV } from "../../components/layout/PublicNav";
import { HeroVisual } from "./HeroVisual";
import { HomePage } from "./HomePage";
import { ProductPreview } from "./ProductPreview";
import { WorkflowExplorer } from "./WorkflowExplorer";

const auth = vi.hoisted(() => ({ value: { user: null as { roles: string[] } | null, isAuthenticated: false, logout: vi.fn() } }));
vi.mock("../../auth/auth-context", () => ({ useAuth: () => auth.value }));

const shell = (path = "/") => render(<MemoryRouter initialEntries={[path]}><AppShell /></MemoryRouter>);
const targets = () => PUBLIC_NAV.flatMap(e => [e.to, ...(e.children ?? []).map(c => c.to)]).filter(Boolean) as string[];

describe("public header navigation", () => {
  beforeEach(() => { auth.value = { user: null, isAuthenticated: false, logout: vi.fn() }; });
  const nav = () => screen.getByRole("navigation", { name: "Primary navigation" });

  it("offers the expanded public navigation with Log in and Get Started", () => {
    shell();
    for (const name of ["Platform", "Resources"]) expect(within(nav()).getByRole("button", { name })).toHaveAttribute("aria-expanded", "false");
    for (const name of ["Marketplace", "How It Works", "Instruments", "About"]) expect(within(nav()).getByRole("link", { name })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Get Started" })).toHaveAttribute("href", "/register");
  });

  it("opens a dropdown by click and keyboard, moves with arrows and closes on Escape returning focus", async () => {
    shell();
    const trigger = within(nav()).getByRole("button", { name: "Platform" });
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(within(nav()).getByRole("link", { name: /Backtesting/ })).toHaveAttribute("href", "/#stage-backtest");
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    trigger.focus();
    await userEvent.keyboard("{ArrowDown}");
    await act(async () => { await new Promise(r => setTimeout(r, 5)); });
    expect(within(nav()).getByRole("link", { name: /Strategies/ })).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(within(nav()).getByRole("link", { name: /Backtesting/ })).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("flags destinations that do not exist as coming soon instead of linking to them", async () => {
    shell();
    await userEvent.click(within(nav()).getByRole("button", { name: "Resources" }));
    expect(within(nav()).queryByRole("link", { name: /Documentation/ })).not.toBeInTheDocument();
    expect(within(nav()).getByText("Coming soon")).toBeInTheDocument();
    const known = ["/marketplace", "/instruments", "/register", "/login"];
    for (const t of targets()) expect(t.startsWith("/#") || known.includes(t)).toBe(true);
  });

  it("every in-page anchor used by the header exists on the landing page", () => {
    const { container } = render(<MemoryRouter><HomePage /></MemoryRouter>);
    for (const a of targets().filter(t => t.startsWith("/#"))) {
      const id = a.slice(2);
      const target = id.startsWith("stage-") ? "how-it-works" : id;
      expect(container.querySelector(`#${target}`), a).not.toBeNull();
    }
  });

  it("mobile drawer groups navigation, shows coming-soon items without links and closes on selection", async () => {
    shell();
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const drawer = screen.getByRole("dialog", { name: "Mobile navigation" });
    expect(within(drawer).getByRole("group", { name: "Platform" })).toBeInTheDocument();
    expect(within(drawer).getByText("Documentation")).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(within(drawer).getByRole("link", { name: /FAQ/ }));
    expect(screen.getByRole("button", { name: "Open menu" })).toBeInTheDocument();
  });

  it("authenticated visitors keep their product links", () => {
    auth.value = { user: { roles: ["CREATOR"] }, isAuthenticated: true, logout: vi.fn() };
    shell();
    expect(within(nav()).getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(within(nav()).queryByRole("button", { name: "Platform" })).not.toBeInTheDocument();
  });
});

describe("hero visual", () => {
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("is labelled conceptual and contains no figures", () => {
    const { container } = render(<HeroVisual />);
    expect(screen.getByRole("figure", { name: /conceptual illustration.*no market data/i })).toBeInTheDocument();
    expect(container.textContent ?? "").not.toMatch(/\d+(\.\d+)?%|₹|\$|live|order filled/i);
  });

  it("advances the highlighted stage over time and pauses while hovered", () => {
    vi.useFakeTimers();
    const { container } = render(<HeroVisual />);
    const active = () => container.querySelector(".hv-node.is-active .hv-label")?.textContent;
    expect(active()).toBe("Create");
    act(() => { vi.advanceTimersByTime(2300); });
    expect(active()).toBe("Research");
    fireEvent.pointerEnter(screen.getByRole("figure"));
    act(() => { vi.advanceTimersByTime(6000); });
    expect(active()).toBe("Research");
  });

  it("does not animate when the user prefers reduced motion", () => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false, onchange: null }));
    const { container } = render(<HeroVisual />);
    act(() => { vi.advanceTimersByTime(10000); });
    expect(container.querySelector(".hv-node.is-active")).toBeNull();
    expect(container.querySelector(".hv-pulse")).toBeNull();
  });
});

describe("workflow explorer propagation and deep links", () => {
  it("marks earlier stages done and the connector into the active stage as leading", async () => {
    render(<MemoryRouter><WorkflowExplorer /></MemoryRouter>);
    await userEvent.click(screen.getByRole("tab", { name: /Publish/ }));
    const tabs = screen.getAllByRole("tab");
    expect(tabs.slice(0, 4).every(t => t.classList.contains("is-done"))).toBe(true);
    expect(tabs[3]).toHaveClass("is-leading");
    expect(screen.getByRole("link", { name: /Browse listed strategies/ })).toHaveAttribute("href", "/marketplace");
  });

  it("honours /#stage-<id> and changes the call to action per stage", () => {
    render(<MemoryRouter initialEntries={["/#stage-backtest"]}><WorkflowExplorer /></MemoryRouter>);
    expect(screen.getByRole("tab", { name: /Backtest/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: /Run a backtest/ })).toHaveAttribute("href", "/register");
  });
});

describe("product preview", () => {
  it("shows the sample workspace and switches tabs by keyboard without fabricating figures", async () => {
    const { container } = render(<ProductPreview />);
    expect(screen.getByRole("group", { name: /sample name, no real data/i })).toBeInTheDocument();
    expect(screen.getAllByText("EMA Trend Follower").length).toBeGreaterThan(0);
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Backtest complete");
    screen.getByRole("tab", { name: "Overview" }).focus();
    await userEvent.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Backtest" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent(/real backtest runs/i);
    expect(container.textContent).not.toMatch(/\d+(\.\d+)?%|₹/);
  });
});
