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
  return <section className="marketplace-page"><div className="page-heading marketplace-heading"><div><p className="eyebrow">Strategy discovery</p><h1>Marketplace</h1><p>Explore public systematic strategies with clear lifecycle and Version context. Private Creator configuration and Backtest data remain private.</p></div><div className="marketplace-signal"><span className="live-dot" /> Public strategies <strong>{query.data.length}</strong></div></div>
    <div className="card-grid marketplace-grid">
      {query.data.map((strategy) => <article className="card marketplace-card" key={strategy.id}><div className="marketplace-card-top"><span className="strategy-monogram" aria-hidden="true">{strategy.name.slice(0,2).toUpperCase()}</span><span className={`badge badge-${strategy.status}`}>{strategy.status}</span></div><div className="card-title-row"><h2>{strategy.name}</h2></div><p>{strategy.description || "A public systematic strategy awaiting a richer Creator description."}</p><div className="strategy-meta"><span><small>Published</small><strong>{displayDate(strategy.published_at)}</strong></span><span><small>Current version</small><strong>{strategy.current_version_number ? `Version ${strategy.current_version_number}` : "Not available"}</strong></span></div><Link className="card-link" to={`/marketplace/${strategy.slug}`}>Explore strategy <span aria-hidden="true">→</span></Link></article>)}
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
  return <section className="strategy-detail marketplace-detail"><Link className="back-link" to="/marketplace">← Marketplace</Link><p className="eyebrow">Public strategy profile</p><div className="card-title-row"><h1>{strategy.name}</h1><span className={`badge badge-${strategy.status}`}>{strategy.status}</span></div><p className="lead">{strategy.description || "No public description provided."}</p><div className="detail-grid"><div className="card"><p className="eyebrow">Lifecycle</p><h2>Published strategy</h2><dl className="details-list"><dt>Published</dt><dd>{displayDate(strategy.published_at)}</dd><dt>Current version</dt><dd>{strategy.current_version_number ? `Version ${strategy.current_version_number}` : "Not available"}</dd></dl></div><div className="card"><p className="eyebrow">Research context</p><h2>Know what is public</h2><p>Discoverability and lifecycle context are visible. Creator configuration and private simulation results remain protected.</p></div></div><div className="alert alert-info">Marketplace data is descriptive only. It does not include creator configuration, Backtest data, allocation advice, or live trading performance.</div></section>;
}
