import { apiRequest } from "./client";
import type { Backtest, BacktestAnalytics, BacktestCreateRequest, Strategy, StrategyCreateRequest, StrategyUpdateRequest, StrategyVersion, StrategyVersionCreateRequest } from "./types";

const root = "/api/v1/strategies";

export const strategiesApi = {
  list: () => apiRequest<Strategy[]>(root),
  get: (id: string) => apiRequest<Strategy>(`${root}/${id}`),
  create: (data: StrategyCreateRequest) => apiRequest<Strategy>(root, { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: StrategyUpdateRequest) => apiRequest<Strategy>(`${root}/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (id: string) => apiRequest<void>(`${root}/${id}`, { method: "DELETE" }),
  lifecycle: (id: string, action: "publish" | "deploy" | "archive") => apiRequest<Strategy>(`${root}/${id}/${action}`, { method: "POST" }),
  listVersions: (id: string) => apiRequest<StrategyVersion[]>(`${root}/${id}/versions`),
  getVersion: (id: string, versionId: string) => apiRequest<StrategyVersion>(`${root}/${id}/versions/${versionId}`),
  createVersion: (id: string, data: StrategyVersionCreateRequest) => apiRequest<StrategyVersion>(`${root}/${id}/versions`, { method: "POST", body: JSON.stringify(data) }),
  listBacktests: (id: string, versionId: string) => apiRequest<Backtest[]>(`${root}/${id}/versions/${versionId}/backtests`),
  getBacktest: (id: string, versionId: string, backtestId: string) => apiRequest<Backtest>(`${root}/${id}/versions/${versionId}/backtests/${backtestId}`),
  createBacktest: (id: string, versionId: string, data: BacktestCreateRequest) => apiRequest<Backtest>(`${root}/${id}/versions/${versionId}/backtests`, { method: "POST", body: JSON.stringify(data) }),
  executeBacktest: (id: string, versionId: string, backtestId: string) => apiRequest<Backtest>(`${root}/${id}/versions/${versionId}/backtests/${backtestId}/execute`, { method: "POST" }),
  getBacktestAnalytics: (id: string, versionId: string, backtestId: string) => apiRequest<BacktestAnalytics>(`${root}/${id}/versions/${versionId}/backtests/${backtestId}/analytics`),
};
