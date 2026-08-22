import { apiRequest } from "./client";
import type { MarketplaceStrategy } from "./types";

export const marketplaceApi = {
  list: (limit = 20, offset = 0) =>
    apiRequest<MarketplaceStrategy[]>(`/marketplace/strategies?limit=${limit}&offset=${offset}`),
  getBySlug: (slug: string) =>
    apiRequest<MarketplaceStrategy>(`/marketplace/strategies/${encodeURIComponent(slug)}`),
};
