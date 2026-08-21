import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "./auth-context";
import { CREATOR_ROLE, hasRole } from "./roles";

export function RequireAuth() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading) return <p className="page-state">Loading your account…</p>;
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location }} />;
  return <Outlet />;
}

export function RequireCreator() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <p className="page-state">Loading your account…</p>;
  if (!hasRole(user, CREATOR_ROLE)) return <Navigate to="/app" replace />;
  return <Outlet />;
}
