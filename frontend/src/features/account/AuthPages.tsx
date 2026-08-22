import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { authApi } from "../../api/auth";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/auth-context";
import { ErrorAlert } from "../../components/PageState";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});
const registerSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(8, "Password must contain at least 8 characters."),
  full_name: z.string().max(150).optional(),
});
type LoginValues = z.infer<typeof loginSchema>;
type RegisterValues = z.infer<typeof registerSchema>;

function applyFieldErrors<T extends Record<string, unknown>>(
  error: ApiError,
  setError: ReturnType<typeof useForm<T>>["setError"],
) {
  error.fieldErrors.forEach(({ path, message }) => {
    if (path) setError(path as never, { message });
  });
}

function AuthFrame({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children: ReactNode;
}) {
  return (
    <div className="auth-layout">
      <aside className="auth-aside">
        <p className="eyebrow">TradeEBH</p>
        <h2>{title}</h2>
        <p className="lead">{body}</p>
        <ul className="auth-points">
          <li><strong>Investor from day one</strong>Discover published strategies and paper allocations.</li>
          <li><strong>Creator when you are ready</strong>Enrollment keeps your existing investor role.</li>
          <li><strong>Reference infrastructure</strong>Synthetic NSE/INR data only — never live capital.</li>
        </ul>
      </aside>
      {children}
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      await login(values);
      const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      navigate(from || "/app", { replace: true });
    } catch (reason) {
      if (reason instanceof ApiError) {
        applyFieldErrors(reason, form.setError);
        setError(reason.message);
      } else setError("Unable to log in. Please try again.");
    }
  });

  return (
    <AuthFrame title="Return to your workspace." body="Access creator tools, marketplace discovery, and paper execution from one account.">
      <section className="auth-card card">
        <h1>Log in</h1>
        <p>Access your TradeEBH workspace.</p>
        {error && <ErrorAlert>{error}</ErrorAlert>}
        <form onSubmit={submit} noValidate>
          <label>Email<input type="email" autoComplete="email" {...form.register("email")} /></label>
          {form.formState.errors.email && <small>{form.formState.errors.email.message}</small>}
          <label>Password<input type="password" autoComplete="current-password" {...form.register("password")} /></label>
          {form.formState.errors.password && <small>{form.formState.errors.password.message}</small>}
          <button className="button" disabled={form.formState.isSubmitting}>Log in</button>
        </form>
        <p>New to TradeEBH? <Link to="/register">Create an account</Link>.</p>
      </section>
    </AuthFrame>
  );
}

export function RegisterPage() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });
  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      await authApi.register({ ...values, full_name: values.full_name || undefined });
      navigate("/login", { replace: true });
    } catch (reason) {
      if (reason instanceof ApiError) {
        applyFieldErrors(reason, form.setError);
        setError(reason.message);
      } else setError("Unable to create the account. Please try again.");
    }
  });
  return (
    <AuthFrame title="Open an investor workspace." body="Create an account to browse strategies and pin paper allocations. Live trading is not part of this MVP.">
      <section className="auth-card card">
        <h1>Create account</h1>
        <p>New accounts begin with the Investor role.</p>
        {error && <ErrorAlert>{error}</ErrorAlert>}
        <form onSubmit={submit} noValidate>
          <label>Name (optional)<input autoComplete="name" {...form.register("full_name")} /></label>
          {form.formState.errors.full_name && <small>{form.formState.errors.full_name.message}</small>}
          <label>Email<input type="email" autoComplete="email" {...form.register("email")} /></label>
          {form.formState.errors.email && <small>{form.formState.errors.email.message}</small>}
          <label>Password<input type="password" autoComplete="new-password" {...form.register("password")} /></label>
          {form.formState.errors.password && <small>{form.formState.errors.password.message}</small>}
          <button className="button" disabled={form.formState.isSubmitting}>Create account</button>
        </form>
        <p>Already registered? <Link to="/login">Log in</Link>.</p>
      </section>
    </AuthFrame>
  );
}
