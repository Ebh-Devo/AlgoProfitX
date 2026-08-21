import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./guards";

const auth = vi.hoisted(() => ({ value: { isAuthenticated: false, isLoading: false } }));
vi.mock("./auth-context", () => ({ useAuth: () => auth.value }));

describe("RequireAuth", () => {
  it("redirects anonymous users to login", () => {
    render(<MemoryRouter initialEntries={["/app"]}><Routes><Route element={<RequireAuth />}><Route path="/app" element={<p>Protected</p>} /></Route><Route path="/login" element={<p>Login page</p>} /></Routes></MemoryRouter>);
    expect(screen.getByText("Login page")).toBeInTheDocument();
  });
});
