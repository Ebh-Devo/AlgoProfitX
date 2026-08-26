import { apiRequest } from "./client";
import type { Instrument } from "./types";

export type InstrumentFilters = { search?: string; exchange?: string; instrumentType?: "equity" | "index"; isTradeable?: boolean; isActive?: boolean; limit?: number; offset?: number };

export const instrumentsApi = {
  list: (filters: InstrumentFilters | string = {}) => {
    const values = typeof filters === "string" ? { search: filters, limit: 100 } : filters;
    const query = new URLSearchParams({ limit: String(values.limit ?? 20), offset: String(values.offset ?? 0) });
    if (values.search?.trim()) query.set("search", values.search.trim());
    if (values.exchange) query.set("exchange", values.exchange);
    if (values.instrumentType) query.set("instrument_type", values.instrumentType);
    if (values.isTradeable !== undefined) query.set("is_tradeable", String(values.isTradeable));
    if (values.isActive !== undefined) query.set("is_active", String(values.isActive));
    return apiRequest<Instrument[]>(`/instruments?${query.toString()}`);
  },
  get: (id: string) => apiRequest<Instrument>(`/instruments/${encodeURIComponent(id)}`),
};
