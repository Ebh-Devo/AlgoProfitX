import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { LoginPage, RegisterPage } from "./AuthPages";
import { ApiError } from "../../api/client";

/* ── Shared mocks ──────────────────────────────────────────────── */
const login = vi.hoisted(() => vi.fn());
const auth  = vi.hoisted(() => ({
  value: {
    login,
    isAuthenticated: false,
    isLoading: false,
    user: null,
  },
}));
vi.mock("../../auth/auth-context", () => ({ useAuth: () => auth.value }));

const register = vi.hoisted(() => vi.fn());
vi.mock("../../api/auth", () => ({
  authApi: { register },
}));

function renderLogin(initialPath = "/login") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login"    element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/app"      element={<p>Dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <Routes>
        <Route path="/login"    element={<p>Login page</p>} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/app"      element={<p>Dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  auth.value = { login, isAuthenticated: false, isLoading: false, user: null };
  login.mockReset();
  register.mockReset();
});

/* ══════════════════════════════════════════════════════════════
   LoginPage
   ══════════════════════════════════════════════════════════════ */
describe("LoginPage", () => {
  it("renders the login form", () => {
    renderLogin();
    expect(screen.getByRole("heading", { name: /log in/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /log in/i })).toBeInTheDocument();
  });

  it("submits credentials through the session login action", async () => {
    login.mockResolvedValue({ email: "investor@example.test", roles: ["INVESTOR"] });
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "investor@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "TestPassword123");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    expect(login).toHaveBeenCalledWith({
      email: "investor@example.test",
      password: "TestPassword123",
    });
  });

  it("redirects to /app after successful login", async () => {
    login.mockResolvedValue({ email: "u@example.test", roles: ["INVESTOR"] });
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "u@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "Password1!");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
  });

  it("shows a top-level error on invalid credentials", async () => {
    login.mockRejectedValue(new ApiError(401, "Invalid email or password"));
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "bad@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "wrongpass");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Invalid email or password"),
    );
  });

  it("shows a generic error on unexpected failure", async () => {
    login.mockRejectedValue(new Error("Network error"));
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "u@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "SomePass1!");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/unable to log in/i),
    );
  });

  it("shows validation error for invalid email", async () => {
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "not-an-email");
    await userEvent.type(screen.getByLabelText("Password"), "pass");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() =>
      expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument(),
    );
    expect(login).not.toHaveBeenCalled();
  });

  it("shows validation error when password is empty", async () => {
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "u@example.test");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() =>
      expect(screen.getByText("Password is required.")).toBeInTheDocument(),
    );
    expect(login).not.toHaveBeenCalled();
  });

  it("disables the submit button while submitting", async () => {
    let resolve!: () => void;
    login.mockReturnValue(new Promise<void>(r => { resolve = r; }));
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "u@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "Password1!");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /log in/i })).toBeDisabled(),
    );
    resolve();
  });

  it("shows registration success flash when arriving from registration", () => {
    render(
      <MemoryRouter initialEntries={[{ pathname: "/login", state: { registered: true } }]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText(/account created successfully/i)).toBeInTheDocument();
  });

  it("redirects authenticated users away from the login page", () => {
    auth.value = { ...auth.value, isAuthenticated: true };
    renderLogin();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });
});

/* ══════════════════════════════════════════════════════════════
   RegisterPage
   ══════════════════════════════════════════════════════════════ */
describe("RegisterPage", () => {
  it("renders the registration form", () => {
    renderRegister();
    expect(screen.getByRole("heading", { name: /create account/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });

  it("submits valid registration data", async () => {
    register.mockResolvedValue({ id: "u1", email: "new@example.test", roles: ["INVESTOR"] });
    renderRegister();
    await userEvent.type(screen.getByLabelText(/name/i), "New User");
    await userEvent.type(screen.getByLabelText("Email"), "new@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "Secure123!");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(register).toHaveBeenCalledWith({
        full_name: "New User",
        email: "new@example.test",
        password: "Secure123!",
      }),
    );
  });

  it("navigates to login with registered flag after successful registration", async () => {
    register.mockResolvedValue({ id: "u1", email: "new@example.test", roles: ["INVESTOR"] });
    renderRegister();
    await userEvent.type(screen.getByLabelText("Email"), "new@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "Secure123!");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument());
  });

  it("shows a top-level error when account already exists", async () => {
    register.mockRejectedValue(new ApiError(409, "Email is already registered"));
    renderRegister();
    await userEvent.type(screen.getByLabelText("Email"), "existing@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "Secure123!");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Email is already registered"),
    );
  });

  it("shows a generic error on unexpected failure", async () => {
    register.mockRejectedValue(new Error("Network error"));
    renderRegister();
    await userEvent.type(screen.getByLabelText("Email"), "u@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "Secure123!");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/unable to create the account/i),
    );
  });

  it("shows validation error when email is invalid", async () => {
    renderRegister();
    await userEvent.type(screen.getByLabelText("Email"), "bad-email");
    await userEvent.type(screen.getByLabelText("Password"), "Secure123!");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument(),
    );
    expect(register).not.toHaveBeenCalled();
  });

  it("shows validation error when password is too short", async () => {
    renderRegister();
    await userEvent.type(screen.getByLabelText("Email"), "u@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(screen.getByText("Password must contain at least 8 characters.")).toBeInTheDocument(),
    );
    expect(register).not.toHaveBeenCalled();
  });

  it("disables the submit button while submitting", async () => {
    let resolve!: () => void;
    register.mockReturnValue(new Promise<void>(r => { resolve = r; }));
    renderRegister();
    await userEvent.type(screen.getByLabelText("Email"), "u@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "Secure123!");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /create account/i })).toBeDisabled(),
    );
    resolve();
  });

  it("redirects authenticated users away from the register page", () => {
    auth.value = { ...auth.value, isAuthenticated: true };
    renderRegister();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });
});
