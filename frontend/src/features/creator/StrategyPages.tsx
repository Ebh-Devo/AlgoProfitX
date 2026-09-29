import { lazy, Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { strategiesApi } from "../../api/strategies";
import { instrumentsApi } from "../../api/instruments";
import { queryKeys } from "../../api/queryKeys";
import type { Strategy, StrategyCreateRequest, StrategyUpdateRequest } from "../../api/types";
import { EmptyState, ErrorAlert, LoadingState } from "../../components/PageState";

const VersionBacktests = lazy(async () => ({
  default: (await import("./BacktestPages")).VersionBacktests,
}));

/* ── Helpers ──────────────────────────────────────────────────── */
const date = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
    : "—";

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof ApiError ? error.message : fallback;

function Status({ value }: { value: string }) {
  const map: Record<string, string> = {
    draft: "badge badge-draft",
    published: "badge badge-published",
    deployed: "badge badge-deployed",
    archived: "badge badge-archived",
  };
  return <span className={map[value] ?? "badge"}>{value}</span>;
}

/* ── Zod schema for strategy create/edit ─────────────────────── */
const strategySchema = z.object({
  name: z
    .string()
    .min(3, "Name must be at least 3 characters")
    .max(150, "Name must be at most 150 characters"),
  slug: z
    .string()
    .min(3, "Slug must be at least 3 characters")
    .max(180, "Slug must be at most 180 characters")
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Lowercase letters, numbers, and hyphens only; no leading, trailing, or consecutive hyphens"),
  description: z.string().max(1000, "Description must be at most 1000 characters").optional(),
});

type StrategyFormValues = z.infer<typeof strategySchema>;

/* ── Shared strategy form ─────────────────────────────────────── */
interface StrategyFormProps {
  initial?: Partial<StrategyFormValues>;
  submitLabel: string;
  onSave: (values: StrategyFormValues) => Promise<void>;
}

function StrategyForm({ initial, submitLabel, onSave }: StrategyFormProps) {
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<StrategyFormValues>({
    resolver: zodResolver(strategySchema),
    defaultValues: {
      name: initial?.name ?? "",
      slug: initial?.slug ?? "",
      description: initial?.description ?? "",
    },
  });

  const submit = handleSubmit(async (values) => {
    setApiError(null);
    try {
      await onSave(values);
    } catch (reason) {
      if (reason instanceof ApiError) {
        let hasFieldErrors = false;
        for (const fe of reason.fieldErrors) {
          const field = fe.path as keyof StrategyFormValues;
          if (field === "name" || field === "slug" || field === "description") {
            setError(field, { message: fe.message });
            hasFieldErrors = true;
          }
        }
        if (!hasFieldErrors) {
          setApiError(reason.message);
        }
      } else {
        setApiError("Request failed. Please try again.");
      }
    }
  });

  return (
    <form className="form-stack" onSubmit={submit} noValidate>
      {/* Name */}
      <div className={`form-field ${errors.name ? "has-error" : ""}`}>
        <label className="form-label" htmlFor="strategy-name">Name</label>
        <input
          id="strategy-name"
          className="input"
          type="text"
          autoComplete="off"
          aria-describedby={errors.name ? "strategy-name-error" : undefined}
          aria-invalid={errors.name ? true : undefined}
          {...register("name")}
        />
        {errors.name && (
          <p className="field-error" role="alert" id="strategy-name-error">
            {errors.name.message}
          </p>
        )}
      </div>

      {/* Slug */}
      <div className={`form-field ${errors.slug ? "has-error" : ""}`}>
        <label className="form-label" htmlFor="strategy-slug">Slug</label>
        <input
          id="strategy-slug"
          className="input"
          type="text"
          autoComplete="off"
          spellCheck={false}
          aria-describedby={
            errors.slug ? "strategy-slug-error" : "strategy-slug-hint"
          }
          aria-invalid={errors.slug ? true : undefined}
          {...register("slug")}
        />
        <p className="field-hint" id="strategy-slug-hint">
          Lowercase letters, numbers, and single hyphens — e.g.{" "}
          <code>india-trend-v2</code>
        </p>
        {errors.slug && (
          <p className="field-error" role="alert" id="strategy-slug-error">
            {errors.slug.message}
          </p>
        )}
      </div>

      {/* Description */}
      <div className={`form-field ${errors.description ? "has-error" : ""}`}>
        <label className="form-label" htmlFor="strategy-description">
          Description <span className="field-optional">(optional)</span>
        </label>
        <textarea
          id="strategy-description"
          className="input sb-textarea"
          rows={4}
          aria-describedby={errors.description ? "strategy-description-error" : undefined}
          aria-invalid={errors.description ? true : undefined}
          {...register("description")}
        />
        {errors.description && (
          <p className="field-error" role="alert" id="strategy-description-error">
            {errors.description.message}
          </p>
        )}
      </div>

      {apiError && (
        <div role="alert">
          <ErrorAlert>{apiError}</ErrorAlert>
        </div>
      )}

      <div>
        <button
          className="btn btn-primary"
          type="submit"
          disabled={isSubmitting}
          aria-disabled={isSubmitting}
        >
          {isSubmitting ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}

/* ── Strategy list page ───────────────────────────────────────── */
export function StrategyListPage() {
  const query = useQuery({
    queryKey: queryKeys.strategies,
    queryFn: strategiesApi.list,
  });

  if (query.isLoading) return <LoadingState label="Loading your strategies…" />;
  if (query.isError)
    return <ErrorAlert>{errorMessage(query.error, "Unable to load your strategies.")}</ErrorAlert>;

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Creator workspace</p>
          <h1>Strategies</h1>
          <p>
            Manage strategy identity and lifecycle. Create a draft, add immutable Versions, then
            publish.
          </p>
        </div>
        <Link className="btn btn-primary" to="/creator/strategies/new">
          Create strategy
        </Link>
      </div>

      {!query.data?.length ? (
        <EmptyState>No strategies yet. Create your first draft strategy to begin.</EmptyState>
      ) : (
        <div className="strategy-table-wrap">
          <table className="strategy-table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Status</th>
                <th>Current Version</th>
                <th>Published</th>
                <th>Deployed</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.name}</strong>
                    <small>{item.slug}</small>
                    <p>{item.description || "No description provided."}</p>
                  </td>
                  <td>
                    <Status value={item.status} />
                  </td>
                  <td>{item.current_version_id ? "Selected" : "—"}</td>
                  <td>{date(item.published_at)}</td>
                  <td>{date(item.deployed_at)}</td>
                  <td>
                    <div className="inline-actions">
                      <Link className="btn btn-sm btn-ghost" to={`/creator/strategies/${item.id}`}>
                        View
                      </Link>
                      <Link
                        className="btn btn-sm btn-secondary"
                        to={`/creator/strategies/${item.id}/edit`}
                      >
                        Edit
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/* ── New strategy page ────────────────────────────────────────── */
export function StrategyNewPage() {
  const navigate = useNavigate();

  return (
    <section className="form-page">
      <Link className="sb-back-link" to="/creator/strategies">
        ← Strategies
      </Link>
      <div className="sb-page-header">
        <p className="eyebrow">New draft</p>
        <h1>Create strategy</h1>
        <p className="sb-page-desc">
          Define the identity for your strategy. Lifecycle transitions and Versions are managed
          separately after creation.
        </p>
      </div>

      <div className="card sb-form-card">
        <div className="sb-form-section-label">Strategy identity</div>
        <StrategyForm
          submitLabel="Create strategy"
          onSave={async (values) => {
            const data: StrategyCreateRequest = {
              name: values.name,
              slug: values.slug,
              description: values.description || null,
            };
            const result = await strategiesApi.create(data);
            navigate(`/creator/strategies/${result.id}`);
          }}
        />
      </div>

      <div className="sb-help-block">
        <p>
          <strong>What happens next?</strong> After creation your strategy will be in{" "}
          <Status value="draft" /> state. Add at least one immutable Version before publishing to
          the Marketplace.
        </p>
      </div>
    </section>
  );
}

/* ── Edit strategy page ───────────────────────────────────────── */
export function StrategyEditPage() {
  const { strategyId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();

  const query = useQuery({
    queryKey: queryKeys.strategy(strategyId),
    queryFn: () => strategiesApi.get(strategyId),
  });

  if (query.isLoading) return <LoadingState label="Loading strategy…" />;
  if (query.isError || !query.data)
    return (
      <ErrorAlert>
        {query.error instanceof ApiError && query.error.status === 404
          ? "Strategy not found."
          : "Unable to load this strategy."}
      </ErrorAlert>
    );

  const strategy = query.data;

  return (
    <section className="form-page">
      <Link className="sb-back-link" to={`/creator/strategies/${strategyId}`}>
        ← Strategy
      </Link>
      <div className="sb-page-header">
        <p className="eyebrow">Edit metadata</p>
        <h1>{strategy.name}</h1>
        <p className="sb-page-desc">
          Update the strategy name, slug, or description. Lifecycle status and visibility are
          managed separately.
        </p>
      </div>

      {strategy.status !== "draft" && (
        <div className="alert alert-warning sb-status-notice" role="note">
          <span>
            This strategy is currently <Status value={strategy.status} />. Editing metadata does not
            affect its lifecycle state or Marketplace visibility.
          </span>
        </div>
      )}

      <div className="card sb-form-card">
        <div className="sb-form-section-label">Strategy identity</div>
        <StrategyForm
          initial={{
            name: strategy.name,
            slug: strategy.slug,
            description: strategy.description ?? "",
          }}
          submitLabel="Save changes"
          onSave={async (values) => {
            const data: StrategyUpdateRequest = {
              name: values.name,
              slug: values.slug,
              description: values.description || null,
            };
            await strategiesApi.update(strategyId, data);
            await client.invalidateQueries({ queryKey: queryKeys.strategy(strategyId) });
            await client.invalidateQueries({ queryKey: queryKeys.strategies });
            navigate(`/creator/strategies/${strategyId}`);
          }}
        />
      </div>
    </section>
  );
}

/* ── Version creator ──────────────────────────────────────────── */
function parseObject(raw: string, label: string): Record<string, unknown> {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error(`${label} must contain valid JSON.`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(`${label} must be a JSON object.`);
  return value as Record<string, unknown>;
}

function VersionCreator({ strategyId }: { strategyId: string }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [instrumentId, setInstrumentId] = useState("");
  const [configuration, setConfiguration] = useState("{}");
  const [backtest, setBacktest] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const instruments = useQuery({
    queryKey: queryKeys.instruments(search),
    queryFn: () => instrumentsApi.list(search),
    enabled: open,
  });

  const mutation = useMutation({
    mutationFn: () =>
      strategiesApi.createVersion(strategyId, {
        instrument_id: instrumentId,
        configuration: parseObject(configuration, "Configuration"),
        backtest_configuration: parseObject(backtest, "Backtest configuration"),
      }),
    onSuccess: async () => {
      setOpen(false);
      setSearch("");
      setInstrumentId("");
      setConfiguration("{}");
      setBacktest("{}");
      await client.invalidateQueries({ queryKey: queryKeys.versions(strategyId) });
    },
    onError: (reason) => setError(errorMessage(reason, "Unable to create Version.")),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      if (!instrumentId) throw new Error("Select an Instrument.");
      parseObject(configuration, "Configuration");
      parseObject(backtest, "Backtest configuration");
      mutation.mutate();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invalid JSON.");
    }
  };

  if (!open) {
    return (
      <button className="btn btn-secondary" onClick={() => setOpen(true)}>
        Create Version
      </button>
    );
  }

  return (
    <form className="card form-stack version-form" onSubmit={submit}>
      <h3>Create immutable Version</h3>

      <div className="form-field">
        <label className="form-label" htmlFor="version-instrument-search">
          Find Instrument
        </label>
        <input
          id="version-instrument-search"
          className="input"
          type="search"
          placeholder="Search name or symbol"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {instruments.isLoading ? (
        <LoadingState label="Loading Instruments…" />
      ) : instruments.isError ? (
        <ErrorAlert>{errorMessage(instruments.error, "Unable to load Instruments.")}</ErrorAlert>
      ) : (
        <div className="form-field">
          <label className="form-label" htmlFor="version-instrument-select">
            Instrument
          </label>
          <select
            id="version-instrument-select"
            className="input"
            required
            aria-label="Instrument"
            value={instrumentId}
            onChange={(e) => setInstrumentId(e.target.value)}
          >
            <option value="">Select an Instrument</option>
            {instruments.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.exchange_symbol} · {item.exchange.code} ·{" "}
                {item.instrument_type} · {item.quote_currency}
                {item.is_tradeable ? "" : " · non-tradeable"}
              </option>
            ))}
          </select>
        </div>
      )}

      <p className="field-hint">
        Instrument identity is stored canonically. Algorithm parameters remain separate below.
      </p>

      <div className="form-field">
        <label className="form-label" htmlFor="version-configuration">
          Algorithm configuration
        </label>
        <textarea
          id="version-configuration"
          className="input json-input"
          value={configuration}
          onChange={(e) => setConfiguration(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label className="form-label" htmlFor="version-backtest-configuration">
          Backtest configuration
        </label>
        <textarea
          id="version-backtest-configuration"
          className="input json-input"
          value={backtest}
          onChange={(e) => setBacktest(e.target.value)}
        />
      </div>

      {error && (
        <div role="alert">
          <ErrorAlert>{error}</ErrorAlert>
        </div>
      )}

      <div className="inline-actions">
        <button
          className="btn btn-primary"
          type="submit"
          disabled={mutation.isPending || instruments.isLoading}
        >
          Create Version
        </button>
        <button
          className="btn btn-ghost"
          type="button"
          disabled={mutation.isPending}
          onClick={() => setOpen(false)}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

/* ── Lifecycle controls ───────────────────────────────────────── */
function Lifecycle({ strategy }: { strategy: Strategy }) {
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [confirmArchive, setConfirmArchive] = useState(false);

  const mutation = useMutation({
    mutationFn: (action: "publish" | "deploy" | "archive") =>
      strategiesApi.lifecycle(strategy.id, action),
    onSuccess: async () => {
      setError(null);
      setConfirmArchive(false);
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.strategy(strategy.id) }),
        client.invalidateQueries({ queryKey: queryKeys.strategies }),
        client.invalidateQueries({ queryKey: queryKeys.marketplace }),
      ]);
    },
    onError: (reason) => setError(errorMessage(reason, "Lifecycle transition failed.")),
  });

  const actions: ("publish" | "deploy" | "archive")[] =
    strategy.status === "draft"
      ? ["publish", "archive"]
      : strategy.status === "published"
      ? ["deploy", "archive"]
      : strategy.status === "deployed"
      ? ["archive"]
      : [];

  return (
    <div className="card">
      <div className="card-title-row">
        <div>
          <h2>Lifecycle</h2>
          <p>Transitions follow backend lifecycle rules.</p>
        </div>
        <Status value={strategy.status} />
      </div>

      {actions.length ? (
        <div className="inline-actions">
          {actions.map((action) =>
            action === "archive" ? (
              confirmArchive ? (
                <span className="inline-actions" key={action}>
                  <button
                    className="btn btn-danger"
                    disabled={mutation.isPending}
                    onClick={() => mutation.mutate("archive")}
                  >
                    {mutation.isPending ? "Archiving…" : "Confirm archive"}
                  </button>
                  <button
                    className="btn btn-ghost"
                    disabled={mutation.isPending}
                    onClick={() => setConfirmArchive(false)}
                  >
                    Cancel
                  </button>
                </span>
              ) : (
                <button
                  className="btn btn-danger"
                  disabled={mutation.isPending}
                  key={action}
                  onClick={() => setConfirmArchive(true)}
                >
                  Archive
                </button>
              )
            ) : (
              <button
                className="btn btn-secondary"
                disabled={mutation.isPending}
                key={action}
                onClick={() => mutation.mutate(action)}
              >
                {action[0].toUpperCase() + action.slice(1)}
              </button>
            )
          )}
        </div>
      ) : (
        <p className="muted">Archived is terminal. No further actions are available.</p>
      )}

      {confirmArchive && (
        <p className="field-hint">
          Archiving is terminal and makes this Strategy private.
        </p>
      )}

      {error && (
        <div role="alert">
          <ErrorAlert>{error}</ErrorAlert>
        </div>
      )}
    </div>
  );
}

/* ── Strategy detail page ─────────────────────────────────────── */
export function StrategyDetailPage() {
  const { strategyId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: queryKeys.strategy(strategyId),
    queryFn: () => strategiesApi.get(strategyId),
  });

  const versions = useQuery({
    queryKey: queryKeys.versions(strategyId),
    queryFn: () => strategiesApi.listVersions(strategyId),
  });

  const remove = useMutation({
    mutationFn: () => strategiesApi.delete(strategyId),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.strategies });
      navigate("/creator/strategies");
    },
    onError: (reason) => setDeleteError(errorMessage(reason, "Unable to delete strategy.")),
  });

  if (query.isLoading) return <LoadingState label="Loading strategy…" />;
  if (query.isError || !query.data)
    return (
      <ErrorAlert>
        {query.error instanceof ApiError && query.error.status === 404
          ? "Strategy not found."
          : "Unable to load this strategy."}
      </ErrorAlert>
    );

  const strategy = query.data;
  const current = versions.data?.find((item) => item.id === strategy.current_version_id);

  return (
    <section>
      <Link className="sb-back-link" to="/creator/strategies">
        ← Strategies
      </Link>

      <div className="page-heading">
        <div>
          <p className="eyebrow">Creator strategy</p>
          <div className="card-title-row">
            <h1>{strategy.name}</h1>
            <Status value={strategy.status} />
          </div>
          <p className="lead">{strategy.description || "No description provided."}</p>
        </div>
        <Link
          className="btn btn-secondary"
          to={`/creator/strategies/${strategy.id}/edit`}
        >
          Edit metadata
        </Link>
      </div>

      <div className="detail-grid">
        <div className="card">
          <h2>Metadata</h2>
          <dl className="details-list">
            <dt>Slug</dt>
            <dd>{strategy.slug}</dd>
            <dt>Current Version</dt>
            <dd>{current ? `Version ${current.version_number}` : "None"}</dd>
            <dt>Created</dt>
            <dd>{date(strategy.created_at)}</dd>
            <dt>Updated</dt>
            <dd>{date(strategy.updated_at)}</dd>
            <dt>Published</dt>
            <dd>{date(strategy.published_at)}</dd>
            <dt>Deployed</dt>
            <dd>{date(strategy.deployed_at)}</dd>
          </dl>
        </div>

        <Lifecycle strategy={strategy} />
      </div>

      <div className="section-heading">
        <div>
          <h2>Strategy Versions</h2>
          <p>Versions are immutable once created. At least one Version is required to publish.</p>
        </div>
        <VersionCreator strategyId={strategy.id} />
      </div>

      {versions.isLoading ? (
        <LoadingState label="Loading Versions…" />
      ) : versions.isError ? (
        <ErrorAlert>{errorMessage(versions.error, "Unable to load Versions.")}</ErrorAlert>
      ) : !versions.data?.length ? (
        <EmptyState>
          No Versions yet. A draft requires at least one Version before it can be published.
        </EmptyState>
      ) : (
        <div className="card version-list">
          {versions.data.map((version) => (
            <Link
              key={version.id}
              to={`/creator/strategies/${strategy.id}/versions/${version.id}`}
            >
              <strong>Version {version.version_number}</strong>
              <span>{date(version.created_at)}</span>
              {version.id === strategy.current_version_id && (
                <span className="badge badge-published">current</span>
              )}
            </Link>
          ))}
        </div>
      )}

      <div className="danger-zone card">
        <h2>Delete strategy</h2>
        <p>Deletion is permanent. There is no restore action.</p>
        {confirm ? (
          <div>
            <p>
              Confirm deletion of <strong>{strategy.name}</strong>?
            </p>
            <div className="inline-actions">
              <button
                className="btn btn-danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                {remove.isPending ? "Deleting…" : "Delete permanently"}
              </button>
              <button
                className="btn btn-ghost"
                disabled={remove.isPending}
                onClick={() => setConfirm(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            className="btn btn-danger"
            disabled={remove.isPending}
            onClick={() => setConfirm(true)}
          >
            Delete strategy
          </button>
        )}
        {deleteError && (
          <div role="alert">
            <ErrorAlert>{deleteError}</ErrorAlert>
          </div>
        )}
      </div>
    </section>
  );
}

/* ── Strategy version page ────────────────────────────────────── */
export function StrategyVersionPage() {
  const { strategyId = "", versionId = "" } = useParams();
  const query = useQuery({
    queryKey: queryKeys.version(strategyId, versionId),
    queryFn: () => strategiesApi.getVersion(strategyId, versionId),
  });

  if (query.isLoading) return <LoadingState label="Loading Version…" />;
  if (query.isError || !query.data)
    return (
      <ErrorAlert>
        {query.error instanceof ApiError && query.error.status === 404
          ? "Strategy Version not found."
          : "Unable to load this Version."}
      </ErrorAlert>
    );

  const instrument = query.data.instrument;

  return (
    <section>
      <Link className="sb-back-link" to={`/creator/strategies/${strategyId}`}>
        ← Strategy
      </Link>
      <p className="eyebrow">Immutable strategy configuration</p>
      <h1>Version {query.data.version_number}</h1>
      <p>Created {date(query.data.created_at)}</p>

      <div className="card instrument-summary">
        <h2>Instrument</h2>
        {instrument ? (
          <dl className="details-list">
            <dt>Name</dt>
            <dd>{instrument.name}</dd>
            <dt>Canonical symbol</dt>
            <dd>{instrument.canonical_symbol}</dd>
            <dt>Exchange symbol</dt>
            <dd>{instrument.exchange_symbol}</dd>
            <dt>Exchange</dt>
            <dd>{instrument.exchange.code}</dd>
            <dt>Type</dt>
            <dd>
              {instrument.instrument_type}
              {instrument.is_tradeable ? "" : " · non-tradeable"}
            </dd>
            <dt>Currency</dt>
            <dd>{instrument.quote_currency}</dd>
            <dt>Tick / lot</dt>
            <dd>
              {instrument.tick_size ?? "—"} / {instrument.lot_size ?? "—"}
            </dd>
          </dl>
        ) : (
          <div>
            <p className="badge badge-archived">legacy / unresolved</p>
            <p>
              This legacy Version has no resolved canonical Instrument. Its immutable configuration
              remains available below.
            </p>
          </div>
        )}
      </div>

      <div className="detail-grid">
        <div className="card">
          <h2>Algorithm configuration</h2>
          <pre className="json-view">{JSON.stringify(query.data.configuration, null, 2)}</pre>
        </div>
        <div className="card">
          <h2>Backtest configuration</h2>
          <pre className="json-view">
            {JSON.stringify(query.data.backtest_configuration, null, 2)}
          </pre>
        </div>
      </div>

      <Suspense fallback={<LoadingState label="Loading Backtests…" />}>
        <VersionBacktests strategyId={strategyId} versionId={versionId} />
      </Suspense>
    </section>
  );
}
