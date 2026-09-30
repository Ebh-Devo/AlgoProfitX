import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { z } from "zod";

import { authApi } from "../../api/auth";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/auth-context";
import { ErrorAlert } from "../../components/PageState";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui";

const loginSchema = z.object({
  email:    z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});
const registerSchema = z.object({
  email:     z.string().email("Enter a valid email address."),
  password:  z.string().min(8, "Password must contain at least 8 characters."),
  full_name: z.string().max(150).optional(),
});
type LoginValues    = z.infer<typeof loginSchema>;
type RegisterValues = z.infer<typeof registerSchema>;

function applyFieldErrors<T extends Record<string, unknown>>(
  error: ApiError,
  setError: ReturnType<typeof useForm<T>>["setError"],
) {
  error.fieldErrors.forEach(({ path, message }) => {
    if (path) setError(path as never, { message });
  });
}

function PasswordStrength({ password }: { password: string }) {
  const score =
    [/.{8,}/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/]
      .filter(re => re.test(password)).length;
  const labels = ["", "Weak", "Fair", "Good", "Strong"];
  if (!password) return null;
  return (
    <div className={`password-strength strength-${score}`} aria-live="polite">
      <div className="strength-bar">
        <span /><span /><span /><span />
      </div>
      <span className="strength-label">{labels[score]}</span>
    </div>
  );
}

function PasswordInput({
  label,
  autoComplete,
  error,
  hint,
  showStrength,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & {
  label: React.ReactNode;
  error?: string;
  hint?: string;
  showStrength?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  const value = (rest.value ?? "") as string;

  return (
    <div className="password-field-wrap">
      <Input
        label={label}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        error={error}
        hint={hint}
        iconRight={
          <button
            type="button"
            className="password-toggle"
            aria-label={visible ? "Hide password" : "Show password"}
            onClick={() => setVisible(v => !v)}
          >
            {visible ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
          </button>
        }
        {...rest}
      />
      {showStrength && <PasswordStrength password={value} />}
    </div>
  );
}

export function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const navigate     = useNavigate();
  const location     = useLocation();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  /* Success flash passed from RegisterPage */
  const registered = (location.state as { registered?: boolean } | null)?.registered;

  if (!isLoading && isAuthenticated) {
    const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
    return <Navigate to={from || "/app"} replace />;
  }

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
    <section className="auth-card card">
      <h1>Log in</h1>
      <p>Access your AlgoProfitX workspace.</p>

      {registered && (
        <div className="alert alert-success registration-success" role="status">
          <strong>Account created successfully.</strong> Please log in to continue.
        </div>
      )}
      {error && <ErrorAlert>{error}</ErrorAlert>}

      <form onSubmit={submit} noValidate>
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />

        <PasswordInput
          label="Password"
          autoComplete="current-password"
          error={form.formState.errors.password?.message}
          {...form.register("password")}
        />

        <p style={{ fontSize: "var(--text-sm)", textAlign: "right", margin: 0 }}>
          <span style={{ color: "var(--faint)", cursor: "default" }}>Forgot password?</span>
        </p>

        <Button type="submit" loading={form.formState.isSubmitting} style={{ width: "100%", marginTop: "var(--s2)" }}>
          Log in
        </Button>
      </form>

      <p>New to AlgoProfitX? <Link to="/register">Create an account</Link>.</p>
    </section>
  );
}

export function RegisterPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/app" replace />;
  }
  const password = form.watch("password") ?? "";

  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      await authApi.register({ ...values, full_name: values.full_name || undefined });
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (reason) {
      if (reason instanceof ApiError) {
        applyFieldErrors(reason, form.setError);
        setError(reason.message);
      } else setError("Unable to create the account. Please try again.");
    }
  });

  return (
    <section className="auth-card card">
      <h1>Create account</h1>
      <p>New accounts begin with the Investor role.</p>

      {error && <ErrorAlert>{error}</ErrorAlert>}

      <form onSubmit={submit} noValidate>
        <Input
          label={<>Name <span style={{ color: "var(--faint)", fontWeight: 400 }}>(optional)</span></>}
          autoComplete="name"
          error={form.formState.errors.full_name?.message}
          {...form.register("full_name")}
        />

        <Input
          label="Email"
          type="email"
          autoComplete="email"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />

        <PasswordInput
          label="Password"
          autoComplete="new-password"
          hint="At least 8 characters."
          showStrength
          value={password}
          error={form.formState.errors.password?.message}
          {...form.register("password")}
        />

        <Button type="submit" loading={form.formState.isSubmitting} style={{ width: "100%", marginTop: "var(--s2)" }}>
          Create account
        </Button>
      </form>

      <p>Already registered? <Link to="/login">Log in</Link>.</p>
    </section>
  );
}
