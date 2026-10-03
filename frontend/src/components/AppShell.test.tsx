import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppShell } from "./AppShell";

const auth = vi.hoisted(() => ({
  value: {
    user: null as { roles: string[] } | null,
    isAuthenticated: false,
    logout: vi.fn(),
  },
}));
vi.mock("../auth/auth-context", () => ({ useAuth: () => auth.value }));

const primaryNav = () => screen.getByRole("navigation", { name: "Primary navigation" });

describe("AppShell", () => {
  it("represents both Creator and Investor navigation for dual-role users", () => {
    auth.value = { user: { roles: ["INVESTOR", "CREATOR"] }, isAuthenticated: true, logout: vi.fn() };
    render(<MemoryRouter><AppShell /></MemoryRouter>);
    expect(screen.getByText("Creator")).toBeInTheDocument();
    expect(screen.getByText("Investor")).toBeInTheDocument();
    expect(within(primaryNav()).getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(within(primaryNav()).getByRole("link", { name: "Instruments" })).toBeInTheDocument();
    expect(within(primaryNav()).getByRole("link", { name: "Strategies" })).toBeInTheDocument();
    expect(within(primaryNav()).getByRole("link", { name: "Allocations" })).toBeInTheDocument();
    expect(within(primaryNav()).getByRole("link", { name: "Executions" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AlgoProfitX home" })).toHaveTextContent("AlgoProfitX");
  });

  it("handles mobile drawer toggle and Escape key accessibility", () => {
    auth.value = { user: { roles: ["INVESTOR"] }, isAuthenticated: true, logout: vi.fn() };
    render(<MemoryRouter><AppShell /></MemoryRouter>);

    const menuBtn = screen.getByRole("button", { name: "Open menu" });
    expect(menuBtn).toHaveAttribute("aria-expanded", "false");

    // Open drawer
    fireEvent.click(menuBtn);
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");

    // Close with Escape key
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
