import { apiRequest } from "./client";
import type { Allocation, AllocationCreateRequest, AllocationUpdateRequest, ExecutionIntent, ExecutionIntentCreateRequest } from "./types";

export const investorApi = {
  listAllocations: () => apiRequest<Allocation[]>("/allocations"),
  getAllocation: (id: string) => apiRequest<Allocation>(`/allocations/${id}`),
  createAllocation: (data: AllocationCreateRequest) => apiRequest<Allocation>("/allocations", { method: "POST", body: JSON.stringify(data) }),
  updateAllocation: (id: string, data: AllocationUpdateRequest) => apiRequest<Allocation>(`/allocations/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteAllocation: (id: string) => apiRequest<void>(`/allocations/${id}`, { method: "DELETE" }),
  createExecutionIntent: (allocationId: string, data: ExecutionIntentCreateRequest = {}) => apiRequest<ExecutionIntent>(`/allocations/${allocationId}/execution-intents`, { method: "POST", body: JSON.stringify(data) }),
  listExecutionIntents: () => apiRequest<ExecutionIntent[]>("/execution-intents"),
  getExecutionIntent: (id: string) => apiRequest<ExecutionIntent>(`/execution-intents/${id}`),
  executeIntent: (id: string) => apiRequest<ExecutionIntent>(`/execution-intents/${id}/execute`, { method: "POST" }),
};
