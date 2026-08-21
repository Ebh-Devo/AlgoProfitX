import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { RequireAuth, RequireCreator } from "./guards";

const auth = vi.hoisted(() => ({ value: { isAuthenticated: false, isLoading: false } }));
vi.mock("./auth-context", () => ({ useAuth: () => auth.value }));

describe("RequireAuth", () => {
  it("redirects anonymous users to login", () => {
    render(<MemoryRouter initialEntries={["/app"]}><Routes><Route element={<RequireAuth />}><Route path="/app" element={<p>Protected</p>} /></Route><Route path="/login" element={<p>Login page</p>} /></Routes></MemoryRouter>);
    expect(screen.getByText("Login page")).toBeInTheDocument();
  });
});

describe("RequireCreator", () => {
  it("redirects authenticated non-Creators", () => {
    auth.value = { isAuthenticated: true, isLoading: false, user: { roles: ["INVESTOR"] } } as typeof auth.value;
    render(<MemoryRouter initialEntries={["/creator/strategies"]}><Routes><Route element={<RequireCreator />}><Route path="/creator/strategies" element={<p>Creator strategies</p>} /></Route><Route path="/app" element={<p>Workspace</p>} /></Routes></MemoryRouter>);
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });
});
