import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { LoginPage } from "./AuthPages";

const login = vi.hoisted(() => vi.fn());
const auth = vi.hoisted(() => ({ value: { login } }));
vi.mock("../../auth/auth-context", () => ({ useAuth: () => auth.value }));

describe("LoginPage", () => {
  it("submits credentials through the session login action", async () => {
    login.mockResolvedValue({ email: "investor@example.test", roles: ["INVESTOR"] });
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText("Email"), "investor@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "TestPassword123");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(login).toHaveBeenCalledWith({
      email: "investor@example.test",
      password: "TestPassword123",
    });
  });
});
