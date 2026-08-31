import { apiRequest, refreshAccessToken } from "./client";
import { clearSession, setAccessToken } from "../auth/session";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "./types";

export const authApi = {
  register: (data: RegisterRequest) =>
    apiRequest<User>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  login: async (data: LoginRequest) => {
    const token = await apiRequest<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(data) });
    setAccessToken(token.access_token);
    return token;
  },
  restore: async () => { await refreshAccessToken(); return apiRequest<User>("/auth/me"); },
  logout: async () => {
    try { await apiRequest<void>("/auth/logout", { method: "POST" }, false); }
    finally { clearSession(); }
  },
  me: () => apiRequest<User>("/auth/me"),
  enrollCreator: () => apiRequest<User>("/auth/creator/enroll", { method: "POST" }),
};
