import { apiRequest } from "./client";
import type { Instrument } from "./types";

export const instrumentsApi = {
  list: (search = "") => {
    const query = new URLSearchParams({ limit: "100" });
    if (search.trim()) query.set("search", search.trim());
    return apiRequest<Instrument[]>(`/instruments?${query.toString()}`);
  },
};
