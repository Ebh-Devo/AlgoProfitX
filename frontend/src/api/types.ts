import type { components } from "./generated/openapi";

export type User = components["schemas"]["UserResponse"];
export type MarketplaceStrategy = components["schemas"]["MarketplaceStrategyResponse"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type Strategy = components["schemas"]["StrategyResponse"];
export type StrategyCreateRequest = components["schemas"]["StrategyCreateRequest"];
export type StrategyUpdateRequest = components["schemas"]["StrategyUpdateRequest"];
export type StrategyVersion = components["schemas"]["StrategyVersionResponse"];
export type StrategyVersionCreateRequest = components["schemas"]["StrategyVersionCreateRequest"];

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}
