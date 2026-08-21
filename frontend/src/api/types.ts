import type { components } from "./generated/openapi";

export type User = components["schemas"]["UserResponse"];
export type MarketplaceStrategy = components["schemas"]["MarketplaceStrategyResponse"];
export type TokenResponse = components["schemas"]["TokenResponse"];

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}
