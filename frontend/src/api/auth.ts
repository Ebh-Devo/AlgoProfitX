import { apiRequest } from "./client";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "./types";

export const authApi = {
  register: (data: RegisterRequest) =>
    apiRequest<User>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  login: (data: LoginRequest) =>
    apiRequest<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(data) }),
  me: () => apiRequest<User>("/auth/me"),
  enrollCreator: () => apiRequest<User>("/auth/creator/enroll", { method: "POST" }),
};
