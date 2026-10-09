import type { components } from "./generated/openapi";

export type User = components["schemas"]["UserResponse"];
export type MarketplaceStrategy = components["schemas"]["MarketplaceStrategyResponse"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type Strategy = components["schemas"]["StrategyResponse"];
export type StrategyCreateRequest = components["schemas"]["StrategyCreateRequest"];
export type StrategyUpdateRequest = components["schemas"]["StrategyUpdateRequest"];
export type StrategyVersion = components["schemas"]["StrategyVersionResponse"];
export type StrategyVersionCreateRequest = components["schemas"]["StrategyVersionCreateRequest"];
export type StrategyVersionV2CreateRequest = components["schemas"]["StrategyVersionV2CreateRequest"];
export type DefinitionIssue = components["schemas"]["DefinitionIssue"];
export type DefinitionValidateRequest = components["schemas"]["DefinitionValidateRequest"];
export type DefinitionValidation = components["schemas"]["DefinitionValidationResponse"];
export type DefinitionVocabulary = components["schemas"]["DefinitionVocabularyResponse"];
export type VocabularyIndicator = components["schemas"]["VocabularyIndicator"];
export type VocabularyParam = components["schemas"]["VocabularyParam"];
export type Instrument = components["schemas"]["InstrumentResponse"];
export type Backtest = components["schemas"]["BacktestResponse"];
export type BacktestCreateRequest = components["schemas"]["BacktestCreateRequest"];
export type BacktestAnalytics = components["schemas"]["BacktestAnalyticsResponse"];
export type Allocation = components["schemas"]["AllocationResponse"];
export type AllocationCreateRequest = components["schemas"]["AllocationCreateRequest"];
export type AllocationUpdateRequest = components["schemas"]["AllocationUpdateRequest"];
export type ExecutionIntent = components["schemas"]["ExecutionIntentResponse"];
export type ExecutionIntentCreateRequest = components["schemas"]["ExecutionIntentCreateRequest"];

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}
