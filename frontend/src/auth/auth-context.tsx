import { createContext, useContext, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { authApi } from "../api/auth";
import type { LoginRequest, User } from "../api/types";

interface AuthContextValue {
  user: User | null; isAuthenticated: boolean; isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<User>;
  logout: () => Promise<void>;
  enrollCreator: () => Promise<User>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const meQuery = useQuery({ queryKey: ["auth", "me"], queryFn: authApi.restore, retry: false });
  const value = useMemo<AuthContextValue>(() => ({
    user: meQuery.data ?? null,
    isAuthenticated: Boolean(meQuery.data),
    isLoading: meQuery.isLoading,
    login: async (credentials) => {
      await authApi.login(credentials);
      return queryClient.fetchQuery({ queryKey: ["auth", "me"], queryFn: authApi.me });
    },
    logout: async () => {
      try { await authApi.logout(); }
      finally { queryClient.removeQueries({ queryKey: ["auth", "me"] }); }
    },
    enrollCreator: async () => {
      const user = await authApi.enrollCreator(); queryClient.setQueryData(["auth", "me"], user); return user;
    },
  }), [meQuery.data, meQuery.isLoading, queryClient]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
