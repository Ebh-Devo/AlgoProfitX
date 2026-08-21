import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { authApi } from "../api/auth";
import type { LoginRequest, User } from "../api/types";
import { clearSession, getSession, saveSession, subscribeToSession } from "./session";

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<User>;
  logout: () => void;
  enrollCreator: () => Promise<User>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState(getSession);
  useEffect(() => subscribeToSession(() => setSession(getSession())), []);

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: authApi.me,
    enabled: Boolean(session),
    retry: false,
  });

  const value = useMemo<AuthContextValue>(() => ({
    user: meQuery.data ?? null,
    isAuthenticated: Boolean(session && meQuery.data),
    isLoading: Boolean(session) && meQuery.isLoading,
    login: async (credentials) => {
      const token = await authApi.login(credentials);
      saveSession({ accessToken: token.access_token });
      return queryClient.fetchQuery({ queryKey: ["auth", "me"], queryFn: authApi.me });
    },
    logout: () => {
      clearSession();
      queryClient.removeQueries({ queryKey: ["auth", "me"] });
    },
    enrollCreator: async () => {
      const user = await authApi.enrollCreator();
      queryClient.setQueryData(["auth", "me"], user);
      return user;
    },
  }), [meQuery.data, meQuery.isLoading, queryClient, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
