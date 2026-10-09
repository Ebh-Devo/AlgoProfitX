import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Code,
  RotateCcw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { marketplaceApi } from "../../api/marketplace";
import { queryKeys } from "../../api/queryKeys";
import { useOptionalAuth } from "../../auth/auth-context";
import { EmptyState, ErrorAlert, LoadingState } from "../../components/PageState";
import { StatusBadge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";

function displayDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value))
    : "Not recorded";
}

export function MarketplaceListPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("published_desc");

  const query = useQuery({
    queryKey: queryKeys.marketplaceList(100, 0),
    queryFn: () => marketplaceApi.list(100, 0),
  });

  const isFiltered = Boolean(searchQuery.trim() || statusFilter !== "all" || sortBy !== "published_desc");

  const resetFilters = () => {
    setSearchQuery("");
    setStatusFilter("all");
    setSortBy("published_desc");
  };

  const filteredStrategies = useMemo(() => {
    if (!query.data) return [];
    const q = searchQuery.trim().toLowerCase();

    return query.data
      .filter((strategy) => {
        const matchesSearch =
          !q ||
          strategy.name.toLowerCase().includes(q) ||
          (strategy.description?.toLowerCase().includes(q) ?? false) ||
          strategy.slug.toLowerCase().includes(q);

        const matchesStatus =
          statusFilter === "all" || strategy.status.toLowerCase() === statusFilter.toLowerCase();

        return matchesSearch && matchesStatus;
      })
      .sort((a, b) => {
        if (sortBy === "published_desc") {
          const timeA = a.published_at ? new Date(a.published_at).getTime() : 0;
          const timeB = b.published_at ? new Date(b.published_at).getTime() : 0;
          return timeB - timeA;
        }
        if (sortBy === "published_asc") {
          const timeA = a.published_at ? new Date(a.published_at).getTime() : 0;
          const timeB = b.published_at ? new Date(b.published_at).getTime() : 0;
          return timeA - timeB;
        }
        if (sortBy === "name_asc") {
          return a.name.localeCompare(b.name);
        }
        if (sortBy === "name_desc") {
          return b.name.localeCompare(a.name);
        }
        if (sortBy === "version_desc") {
          return (b.current_version_number ?? 0) - (a.current_version_number ?? 0);
        }
        return 0;
      });
  }, [query.data, searchQuery, statusFilter, sortBy]);

  if (query.isLoading) return <LoadingState label="Loading marketplace strategies…" />;
  if (query.isError)
    return (
      <ErrorAlert>
        {query.error instanceof ApiError ? query.error.message : "Marketplace is unavailable."}
      </ErrorAlert>
    );

  return (
    <section className="marketplace-page">
      <div className="page-heading marketplace-heading">
        <div>
          <p className="eyebrow">Strategy discovery</p>
          <h1>Marketplace</h1>
          <p>
            Explore public systematic strategies with verified lifecycle and version history.
            Private Creator configuration and Backtest data remain protected.
          </p>
        </div>
        <div className="marketplace-signal">
          <span className="live-dot" /> Public strategies{" "}
          <strong>{query.data ? query.data.length : 0}</strong>
        </div>
      </div>

      <form
        className="marketplace-filters"
        onSubmit={(e) => e.preventDefault()}
        aria-label="Strategy search and filters"
      >
        <div className="form-field">
          <Input
            label="Search strategies"
            type="search"
            placeholder="Search by name, description, or slug..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            iconLeft={<Search size={16} />}
          />
        </div>

        <label>
          Status
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
          >
            <option value="all">All statuses</option>
            <option value="published">Published</option>
            <option value="deployed">Deployed</option>
            <option value="draft">Draft</option>
            <option value="archived">Archived</option>
          </select>
        </label>

        <label>
          Sort by
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            aria-label="Sort strategies"
          >
            <option value="published_desc">Newest published</option>
            <option value="published_asc">Oldest published</option>
            <option value="name_asc">Name (A–Z)</option>
            <option value="name_desc">Name (Z–A)</option>
            <option value="version_desc">Highest version</option>
          </select>
        </label>

        {isFiltered && (
          <Button
            type="button"
            variant="ghost"
            size="md"
            onClick={resetFilters}
            className="reset-filters-btn"
            iconLeft={<RotateCcw size={14} />}
          >
            Reset
          </Button>
        )}
      </form>

      {!query.data?.length ? (
        <EmptyState title="No public strategies available">
          No published public strategies are available yet.
        </EmptyState>
      ) : filteredStrategies.length === 0 ? (
        <div>
          <EmptyState title="No strategies match your criteria">
            Try broadening your search terms or clearing your status filters.
          </EmptyState>
          <div style={{ marginTop: "1.25rem", textAlign: "center" }}>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={resetFilters}
              iconLeft={<RotateCcw size={14} />}
            >
              Reset filters
            </Button>
          </div>
        </div>
      ) : (
        <div className="card-grid marketplace-grid">
          {filteredStrategies.map((strategy) => (
            <article className="card marketplace-card" key={strategy.id}>
              <div className="marketplace-card-top">
                <span className="strategy-monogram" aria-hidden="true">
                  {strategy.name.slice(0, 2).toUpperCase()}
                </span>
                <StatusBadge status={strategy.status} />
              </div>
              <div className="card-title-row">
                <h2>{strategy.name}</h2>
              </div>
              <span className="strategy-slug">
                <Code size={12} aria-hidden="true" /> {strategy.slug}
              </span>
              <p>
                {strategy.description ||
                  "A public systematic strategy on AlgoProfitX with verified lifecycle status."}
              </p>
              <div className="strategy-meta">
                <span>
                  <small>Published</small>
                  <strong>{displayDate(strategy.published_at)}</strong>
                </span>
                <span>
                  <small>Current version</small>
                  <strong>
                    {strategy.current_version_number
                      ? `Version ${strategy.current_version_number}`
                      : "Not available"}
                  </strong>
                </span>
              </div>
              <Link className="card-link" to={`/marketplace/${strategy.slug}`}>
                Explore strategy <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function MarketplaceDetailPage() {
  const { slug = "" } = useParams();
  const auth = useOptionalAuth();
  const user = auth?.user ?? null;

  const query = useQuery({
    queryKey: queryKeys.marketplaceDetail(slug),
    queryFn: () => marketplaceApi.getBySlug(slug),
    enabled: Boolean(slug),
  });

  if (query.isLoading) return <LoadingState label="Loading strategy…" />;
  if (query.isError) {
    const message =
      query.error instanceof ApiError && query.error.status === 404
        ? "This marketplace strategy is not available."
        : "Unable to load this strategy.";
    return (
      <section className="strategy-detail marketplace-detail">
        <Link className="back-link" to="/marketplace">
          <ArrowLeft size={16} aria-hidden="true" /> Back to Marketplace
        </Link>
        <ErrorAlert>{message}</ErrorAlert>
      </section>
    );
  }

  const strategy = query.data;
  if (!strategy) return null;

  const isInvestor = user?.roles.includes("INVESTOR");
  const isCreator = user?.roles.includes("CREATOR");

  return (
    <section className="strategy-detail marketplace-detail">
      <Link className="back-link" to="/marketplace">
        <ArrowLeft size={16} aria-hidden="true" /> Marketplace
      </Link>
      <p className="eyebrow">Public strategy profile</p>
      <div className="card-title-row">
        <h1>{strategy.name}</h1>
        <StatusBadge status={strategy.status} />
      </div>

      <span className="strategy-slug" style={{ marginBottom: "1rem" }}>
        <Code size={13} aria-hidden="true" /> slug: {strategy.slug}
      </span>

      <p className="lead">
        {strategy.description || "No public description provided for this strategy."}
      </p>

      <Card variant="elevated" as="section" className="bt-feature" aria-labelledby="bt-feature-title">
        <CardHeader>
          <p className="eyebrow">Simulation</p>
          <h2 id="bt-feature-title">Backtest &amp; Performance</h2>
        </CardHeader>
        <CardBody>
          <p>
            Configure a simulated Backtest for {strategy.current_version_number ? `Version ${strategy.current_version_number}` : "this strategy"} and review
            performance, trades and assumptions in one workspace.
          </p>
          <p className="field-hint">
            Backtest results for Marketplace strategies are not yet available, and no performance is shown on this profile. A backtest is a simulation, not live or paper trading.
          </p>
          <Link className="button" to={`/marketplace/${encodeURIComponent(strategy.slug)}/backtest`}>
            Open Backtest workspace <ArrowRight size={14} aria-hidden="true" />
          </Link>
        </CardBody>
      </Card>

      <div className="detail-grid">
        <Card variant="elevated">
          <CardHeader>
            <p className="eyebrow">Lifecycle & Version</p>
            <h2>Strategy Metadata</h2>
          </CardHeader>
          <CardBody>
            <dl className="details-list">
              <dt>Status</dt>
              <dd>
                <StatusBadge status={strategy.status} />
              </dd>
              <dt>Published</dt>
              <dd>{displayDate(strategy.published_at)}</dd>
              <dt>Current version</dt>
              <dd>
                {strategy.current_version_number
                  ? `Version ${strategy.current_version_number}`
                  : "Not available"}
              </dd>
              <dt>Version Identifier</dt>
              <dd>
                {strategy.current_version_id
                  ? strategy.current_version_id.slice(0, 8)
                  : "Not available"}
              </dd>
            </dl>
          </CardBody>
        </Card>

        <Card variant="elevated">
          <CardHeader>
            <p className="eyebrow">Research context</p>
            <h2>Verified Transparency</h2>
          </CardHeader>
          <CardBody>
            <p>
              Discoverability and lifecycle context are public. Creator configuration, trade logic,
              and private simulation data remain protected.
            </p>
            <ul className="detail-context-list">
              <li>
                <CheckCircle2 size={16} aria-hidden="true" />
                <span>Lifecycle status is shown as recorded by the platform</span>
              </li>
              <li>
                <CheckCircle2 size={16} aria-hidden="true" />
                <span>Versions are immutable and numbered by the platform</span>
              </li>
              <li>
                <ShieldCheck size={16} aria-hidden="true" />
                <span>Protected creator source code & execution logic</span>
              </li>
            </ul>
            <p className="field-hint">
              Publication is not an endorsement. No performance, rating or independent verification is claimed on this page.
            </p>
          </CardBody>
        </Card>

        <Card variant="elevated">
          <CardHeader>
            <p className="eyebrow">Execution</p>
            <h2>Strategy Allocation</h2>
          </CardHeader>
          <CardBody>
            <p style={{ marginBottom: "1.5rem" }}>
              Paper allocate to this strategy or manage strategy definitions in your Creator workspace.
            </p>
            {isInvestor ? (
              <Link className="button" to="/investor/allocations">
                Create Allocation
              </Link>
            ) : isCreator ? (
              <Link className="button button-secondary" to="/creator/strategies">
                Manage My Strategies
              </Link>
            ) : (
              <Link className="button" to="/login">
                Log in to Allocate
              </Link>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="alert alert-info" style={{ marginTop: "2rem" }}>
        Marketplace data is descriptive only. It does not include creator configuration, Backtest data, allocation advice, or live trading performance.
      </div>
    </section>
  );
}


