import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { marketplaceApi } from "../../api/marketplace";
import { queryKeys } from "../../api/queryKeys";
import { EmptyState, ErrorAlert, LoadingState } from "../../components/PageState";

function displayDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : "Not recorded";
}

export function MarketplaceListPage() {
  const query = useQuery({ queryKey: queryKeys.marketplaceList(20, 0), queryFn: () => marketplaceApi.list(20, 0) });
  if (query.isLoading) return <LoadingState label="Loading marketplace strategies…" />;
  if (query.isError) return <ErrorAlert>{query.error instanceof ApiError ? query.error.message : "Marketplace is unavailable."}</ErrorAlert>;
  if (!query.data?.length) return <EmptyState>No published public strategies are available yet.</EmptyState>;
  return <section><div className="page-heading"><div><p className="eyebrow">Strategy discovery</p><h1>Marketplace</h1><p>Discover published strategies. Strategy configuration and private Backtest data are never shown here.</p></div></div>
    <div className="card-grid">
      {query.data.map((strategy) => <article className="card" key={strategy.id}><div className="card-title-row"><h2>{strategy.name}</h2><span className={`badge badge-${strategy.status}`}>{strategy.status}</span></div><p>{strategy.description || "No public description provided."}</p><dl className="details-list compact"><dt>Published</dt><dd>{displayDate(strategy.published_at)}</dd><dt>Current version</dt><dd>{strategy.current_version_number ?? "Not available"}</dd></dl><Link className="button button-secondary" to={`/marketplace/${strategy.slug}`}>View strategy</Link></article>)}
    </div>
  </section>;
}

export function MarketplaceDetailPage() {
  const { slug = "" } = useParams();
  const query = useQuery({ queryKey: queryKeys.marketplaceDetail(slug), queryFn: () => marketplaceApi.getBySlug(slug), enabled: Boolean(slug) });
  if (query.isLoading) return <LoadingState label="Loading strategy…" />;
  if (query.isError) {
    const message = query.error instanceof ApiError && query.error.status === 404 ? "This marketplace strategy is not available." : "Unable to load this strategy.";
    return <ErrorAlert>{message}</ErrorAlert>;
  }
  const strategy = query.data;
  if (!strategy) return null;
  return <section className="strategy-detail"><Link className="back-link" to="/marketplace">← Marketplace</Link><p className="eyebrow">Public strategy</p><div className="card-title-row"><h1>{strategy.name}</h1><span className={`badge badge-${strategy.status}`}>{strategy.status}</span></div><p className="lead">{strategy.description || "No public description provided."}</p><div className="card"><dl className="details-list"><dt>Published</dt><dd>{displayDate(strategy.published_at)}</dd><dt>Current version</dt><dd>{strategy.current_version_number ?? "Not available"}</dd></dl></div><div className="alert alert-info">Marketplace data is descriptive only. It does not include creator configuration, Backtest data, allocation advice, or live trading performance.</div></section>;
}
