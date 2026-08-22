import { render, screen } from "@testing-library/react";
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

describe("AppShell", () => {
  it("represents both Creator and Investor navigation for dual-role users", () => {
    auth.value = { user: { roles: ["INVESTOR", "CREATOR"] }, isAuthenticated: true, logout: vi.fn() };
    render(<MemoryRouter><AppShell /></MemoryRouter>);
    expect(screen.getByText("Creator")).toBeInTheDocument();
    expect(screen.getByText("Investor")).toBeInTheDocument();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Strategies" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Allocations" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Executions" })).toBeInTheDocument();
  });
});
