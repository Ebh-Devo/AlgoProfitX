import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Archive,
  ArrowLeft,
  CheckCircle2,
  CircleDashed,
  Globe,
  PenLine,
  PlusCircle,
  Rocket,
  Search,
  Store,
  Trash2,
} from "lucide-react";
import { ApiError } from "../../api/client";
import { strategiesApi } from "../../api/strategies";
import { instrumentsApi } from "../../api/instruments";
import { queryKeys } from "../../api/queryKeys";
import type { Strategy, StrategyCreateRequest, StrategyUpdateRequest } from "../../api/types";
import { EmptyState, ErrorPanel } from "../../components/PageState";
import {
  ActionMenu,
  Alert,
  Button,
  ConfirmDialog,
  FilterChips,
  Input,
  PageHeader,
  SectionHeader,
  SkeletonGroup,
  SkeletonRows,
  Skeleton,
  StatusBadge,
  type ActionMenuItem,
} from "../../components/ui";

const VersionBacktests = lazy(async () => ({
  default: (await import("./BacktestPages")).VersionBacktests,
}));

/* ── Helpers ──────────────────────────────────────────────────── */
const date = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
    : "—";

const shortDate = (value?: string | null) =>
  value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : "—";

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof ApiError ? error.message : fallback;

type LifecycleAction = "publish" | "deploy" | "archive";

/** Which lifecycle transitions the backend allows from each status. */
const NEXT_ACTIONS: Record<Strategy["status"], LifecycleAction[]> = {
  draft: ["publish", "archive"],
  published: ["deploy", "archive"],
  deployed: ["archive"],
  archived: [],
};

/* ── Zod schema for strategy create/edit ─────────────────────── */
const strategySchema = z.object({
  name: z
    .string()
    .min(3, "Name must be at least 3 characters")
    .max(150, "Name must be at most 150 characters"),
  description: z.string().max(1000, "Description must be at most 1000 characters").optional(),
});

type StrategyFormValues = z.infer<typeof strategySchema>;

/* ── Shared strategy form ─────────────────────────────────────── */
interface StrategyFormProps {
  mode: "create" | "edit";
  initial?: Partial<StrategyFormValues>;
  submitLabel: string;
  cancelTo: string;
  onSave: (values: StrategyFormValues) => Promise<void>;
  aside: React.ReactNode;
}

function StrategyForm({ mode, initial, submitLabel, cancelTo, onSave, aside }: StrategyFormProps) {
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<StrategyFormValues>({
    resolver: zodResolver(strategySchema),
    defaultValues: {
      name: initial?.name ?? "",
      description: initial?.description ?? "",
    },
  });

  const nameField = register("name");
  const descriptionLength = watch("description")?.length ?? 0;

  const submit = handleSubmit(async (values) => {
    setApiError(null);
    try {
      await onSave(values);
    } catch (reason) {
      if (reason instanceof ApiError) {
        let hasFieldErrors = false;
        for (const fe of reason.fieldErrors) {
          const field = fe.path as keyof StrategyFormValues;
          if (field === "name" || field === "description") {
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
    <form onSubmit={submit} noValidate aria-label={mode === "create" ? "Create strategy" : "Edit strategy"}>
      <div className="form-layout">
        <div className="form-sections">
          <fieldset className="panel form-section">
            <legend className="visually-hidden">Strategy identity</legend>
            <div className="form-section-head">
              <span className="form-section-num" aria-hidden="true">1</span>
              <div>
                <h2>Strategy identity</h2>
                <p>How this strategy is named.</p>
              </div>
            </div>
            <div className="form-section-body">
              <Input
                id="strategy-name"
                label="Name"
                type="text"
                autoComplete="off"
                hint="The display name. Shown in your workspace and, once published, in the Marketplace. Its Marketplace link is created automatically."
                error={errors.name?.message}
                {...nameField}
              />

              <div className={`form-field ${errors.description ? "has-error" : ""}`}>
                <label className="form-label" htmlFor="strategy-description">
                  Description <span className="field-optional">(optional)</span>
                </label>
                <textarea
                  id="strategy-description"
                  className="input"
                  rows={4}
                  aria-describedby={errors.description ? "strategy-description-error" : "strategy-description-hint"}
                  aria-invalid={errors.description ? true : undefined}
                  {...register("description")}
                />
                <div className="field-footer">
                  {errors.description ? (
                    <p className="field-error" role="alert" id="strategy-description-error">{errors.description.message}</p>
                  ) : (
                    <p className="field-hint" id="strategy-description-hint">A short summary of the idea. Shown on the Marketplace listing once published.</p>
                  )}
                  <span className="field-counter" aria-hidden="true">{descriptionLength}/1000</span>
                </div>
              </div>
            </div>
          </fieldset>

          {apiError && <ErrorPanel title="Couldn't save the strategy">{apiError}</ErrorPanel>}

          <div className="form-actions">
            <Button type="submit" loading={isSubmitting}>{isSubmitting ? "Saving…" : submitLabel}</Button>
            <Link className="btn btn-ghost" to={cancelTo}>Cancel</Link>
          </div>
        </div>
        <aside className="form-aside">{aside}</aside>
      </div>
    </form>
  );
}

/* ── Lifecycle stepper (used on forms and detail) ─────────────── */
function LifecycleSteps({ strategy }: { strategy?: Strategy }) {
  const status = strategy?.status ?? "draft";
  const published = !!strategy?.published_at || status === "published" || status === "deployed";
  const deployed = !!strategy?.deployed_at || status === "deployed";
  const archived = status === "archived";
  const stateOf = (done: boolean, current: boolean) => (done ? "is-done" : current ? "is-current" : "is-pending");

  const steps = [
    { key: "draft", title: "Draft", state: stateOf(published || deployed || archived, status === "draft"), meta: strategy ? `Created ${shortDate(strategy.created_at)}` : "Starting point" },
    { key: "published", title: "Published", state: stateOf(deployed, status === "published"), meta: strategy?.published_at ? shortDate(strategy.published_at) : "Requires at least one Version" },
    { key: "deployed", title: "Deployed", state: stateOf(deployed, false), meta: strategy?.deployed_at ? shortDate(strategy.deployed_at) : undefined },
  ];

  return (
    <>
      <ol className="stepper" aria-label="Lifecycle progress">
        {steps.map(s => (
          <li key={s.key} className={`step ${s.state}`} aria-current={s.state === "is-current" ? "step" : undefined}>
            <span className="step-mark" aria-hidden="true">
              {s.state === "is-done" ? <CheckCircle2 size={14} /> : s.state === "is-current" ? <PenLine size={12} /> : <CircleDashed size={14} />}
            </span>
            <div>
              <p className="step-title">{s.title}{s.state === "is-done" && <span className="visually-hidden"> (complete)</span>}{s.state === "is-current" && <span className="visually-hidden"> (current)</span>}</p>
              {s.meta && <p className="step-meta">{s.meta}</p>}
            </div>
          </li>
        ))}
      </ol>
      {archived && <p className="hint-line" style={{ marginTop: "var(--space-4)" }}><Archive size={13} aria-hidden="true" /> Archived is terminal. No further actions are available.</p>}
    </>
  );
}

/* ── Strategy list page ───────────────────────────────────────── */
type StatusFilter = "all" | Strategy["status"];
type SortKey = "updated" | "created" | "name";

const SORTERS: Record<SortKey, (a: Strategy, b: Strategy) => number> = {
  updated: (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  created: (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  name: (a, b) => a.name.localeCompare(b.name),
};

function StrategyRow({ item }: { item: Strategy }) {
  const menu: ActionMenuItem[] = [{ label: "Open details", to: `/creator/strategies/${item.id}` }];
  if (item.is_public && (item.status === "published" || item.status === "deployed")) {
    menu.push({ label: "View in Marketplace", to: `/marketplace/${item.slug}`, icon: <Store size={14} aria-hidden="true" /> });
  }
  return (
    <tr>
      <td className="cell-title">
        <div className="cell-primary">
          <Link to={`/creator/strategies/${item.id}`}>{item.name}</Link>
          <small>{item.slug}</small>
          {item.description && <p>{item.description}</p>}
        </div>
      </td>
      <td data-label="Status"><StatusBadge status={item.status} /></td>
      <td data-label="Visibility" className="cell-muted">{item.is_public ? "Public" : "Private"}</td>
      <td data-label="Version" className="cell-muted">{item.current_version_id ? "Selected" : "None"}</td>
      <td data-label="Updated" className="cell-muted">{shortDate(item.updated_at)}</td>
      <td className="cell-actions">
        <div className="row-actions">
          <Link className="btn btn-sm btn-secondary" to={`/creator/strategies/${item.id}/edit`} aria-label={`Edit ${item.name}`}>Edit</Link>
          <ActionMenu label={`Actions for ${item.name}`} items={menu} />
        </div>
      </td>
    </tr>
  );
}

export function StrategyListPage() {
  const query = useQuery({
    queryKey: queryKeys.strategies,
    queryFn: strategiesApi.list,
  });
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortKey>("updated");

  const all = query.data;
  const counts = useMemo(() => {
    const c: Record<StatusFilter, number> = { all: all?.length ?? 0, draft: 0, published: 0, deployed: 0, archived: 0 };
    for (const s of all ?? []) c[s.status] += 1;
    return c;
  }, [all]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (all ?? [])
      .filter(s => status === "all" || s.status === status)
      .filter(s => !term || s.name.toLowerCase().includes(term) || s.slug.toLowerCase().includes(term))
      .sort(SORTERS[sort]);
  }, [all, search, status, sort]);

  const createAction = (
    <Link className="btn btn-primary" to="/creator/strategies/new">
      <PlusCircle size={15} aria-hidden="true" /> Create strategy
    </Link>
  );

  const header = (
    <PageHeader
      eyebrow="Creator workspace"
      title="Strategies"
      description="Create a draft, add immutable Versions, backtest them, then publish."
      actions={createAction}
    />
  );

  if (query.isLoading) {
    return (
      <div>
        {header}
        <div className="panel"><SkeletonRows label="Loading your strategies…" rows={5} /></div>
      </div>
    );
  }
  if (query.isError) {
    return (
      <div>
        {header}
        <ErrorPanel title="Strategies unavailable" onRetry={() => void query.refetch()} retrying={query.isFetching}>
          We couldn't load your strategies. Check your connection and try again.
        </ErrorPanel>
      </div>
    );
  }

  const filtering = search.trim() !== "" || status !== "all";
  const clearFilters = () => { setSearch(""); setStatus("all"); };

  return (
    <div>
      {header}

      {!all?.length ? (
        <EmptyState
          icon={<PenLine size={22} />}
          title="No strategies yet"
          action={createAction}
        >
          Create your first strategy to begin. It starts as a draft; you then add an immutable Version with an instrument and configuration.
        </EmptyState>
      ) : (
        <>
          <div className="toolbar" role="search" aria-label="Filter strategies">
            <div className="toolbar-search">
              <Input
                type="search"
                aria-label="Search strategies"
                placeholder="Search by name or slug"
                autoComplete="off"
                value={search}
                onChange={e => setSearch(e.target.value)}
                iconLeft={<Search size={15} />}
              />
            </div>
            <FilterChips<StatusFilter>
              label="Filter by status"
              value={status}
              onChange={setStatus}
              options={[
                { value: "all", label: "All", count: counts.all },
                { value: "draft", label: "Draft", count: counts.draft },
                { value: "published", label: "Published", count: counts.published },
                { value: "deployed", label: "Deployed", count: counts.deployed },
                { value: "archived", label: "Archived", count: counts.archived },
              ]}
            />
            <label className="toolbar-sort">
              Sort
              <select value={sort} onChange={e => setSort(e.target.value as SortKey)}>
                <option value="updated">Recently updated</option>
                <option value="created">Newest</option>
                <option value="name">Name A–Z</option>
              </select>
            </label>
          </div>

          <p className="result-count" role="status" aria-live="polite">
            {filtering ? `Showing ${visible.length} of ${counts.all} strategies` : `${counts.all} ${counts.all === 1 ? "strategy" : "strategies"}`}
          </p>

          {visible.length === 0 ? (
            <EmptyState
              icon={<Search size={22} />}
              title="No strategies match"
              action={<Button variant="secondary" size="sm" onClick={clearFilters}>Clear filters</Button>}
            >
              Try a different search term or status.
            </EmptyState>
          ) : (
            <div className="table-wrap is-stacked">
              <table className="data-table is-stacked">
                <caption className="visually-hidden">Your strategies</caption>
                <thead>
                  <tr>
                    <th scope="col">Strategy</th>
                    <th scope="col">Status</th>
                    <th scope="col">Visibility</th>
                    <th scope="col">Version</th>
                    <th scope="col">Updated</th>
                    <th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map(item => <StrategyRow key={item.id} item={item} />)}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ── New strategy page ────────────────────────────────────────── */
export function StrategyNewPage() {
  const navigate = useNavigate();
  const client = useQueryClient();

  return (
    <div>
      <Link className="back-crumb" to="/creator/strategies"><ArrowLeft size={14} aria-hidden="true" /> Strategies</Link>
      <PageHeader
        eyebrow="New draft"
        title="Create strategy"
        description="Name the strategy. Versions, backtests and lifecycle transitions are managed after creation."
      />
      <StrategyForm
        mode="create"
        submitLabel="Create strategy"
        cancelTo="/creator/strategies"
        onSave={async (values) => {
          const data: StrategyCreateRequest = {
            name: values.name,
            description: values.description || null,
          };
          const result = await strategiesApi.create(data);
          await client.invalidateQueries({ queryKey: queryKeys.strategies });
          navigate(`/creator/strategies/${result.id}`);
        }}
        aside={
          <section className="panel" aria-labelledby="next-steps">
            <div className="panel-body">
              <h2 id="next-steps">What happens next</h2>
              <ol className="stepper">
                <li className="step is-current"><span className="step-mark" aria-hidden="true"><PenLine size={12} /></span><div><p className="step-title">Draft created</p><p className="step-meta">You land on the strategy workspace.</p></div></li>
                <li className="step is-pending"><span className="step-mark" aria-hidden="true"><CircleDashed size={14} /></span><div><p className="step-title">Add a Version</p><p className="step-meta">Choose an instrument and JSON configuration. Versions are immutable.</p></div></li>
                <li className="step is-pending"><span className="step-mark" aria-hidden="true"><CircleDashed size={14} /></span><div><p className="step-title">Backtest</p><p className="step-meta">Run historical simulations on a Version.</p></div></li>
                <li className="step is-pending"><span className="step-mark" aria-hidden="true"><CircleDashed size={14} /></span><div><p className="step-title">Publish</p><p className="step-meta">Requires at least one Version.</p></div></li>
              </ol>
            </div>
          </section>
        }
      />
    </div>
  );
}

/* ── Edit strategy page ───────────────────────────────────────── */
function DetailSkeleton({ label }: { label: string }) {
  return (
    <div className="skeleton-page">
      <SkeletonGroup label={label}>
        <Skeleton width="40%" height="2rem" />
        <Skeleton width="60%" />
      </SkeletonGroup>
      <div className="panel"><SkeletonRows rows={3} label="Loading content…" /></div>
    </div>
  );
}

function LoadError({ error, notFound, what, onRetry }: { error: unknown; notFound: string; what: string; onRetry: () => void }) {
  const missing = error instanceof ApiError && error.status === 404;
  return (
    <div>
      <Link className="back-crumb" to="/creator/strategies"><ArrowLeft size={14} aria-hidden="true" /> Strategies</Link>
      {missing ? (
        <EmptyState icon={<CircleDashed size={22} />} title={notFound} action={<Link className="btn btn-secondary btn-sm" to="/creator/strategies">Back to strategies</Link>}>
          It may have been deleted, or the link is incorrect.
        </EmptyState>
      ) : (
        <ErrorPanel title={`${what} unavailable`} onRetry={onRetry}>We couldn't load this. Check your connection and try again.</ErrorPanel>
      )}
    </div>
  );
}

export function StrategyEditPage() {
  const { strategyId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();

  const query = useQuery({
    queryKey: queryKeys.strategy(strategyId),
    queryFn: () => strategiesApi.get(strategyId),
  });

  if (query.isLoading) return <DetailSkeleton label="Loading strategy…" />;
  if (query.isError || !query.data)
    return <LoadError error={query.error} notFound="Strategy not found." what="Strategy" onRetry={() => void query.refetch()} />;

  const strategy = query.data;

  return (
    <div>
      <Link className="back-crumb" to={`/creator/strategies/${strategyId}`}><ArrowLeft size={14} aria-hidden="true" /> {strategy.name}</Link>
      <PageHeader
        eyebrow="Edit metadata"
        title={strategy.name}
        description="Update the name or description. Lifecycle status and visibility are managed separately."
      />

      {strategy.status !== "draft" && (
        <div style={{ marginBottom: "var(--space-5)" }}>
          <div role="note">
            <Alert variant="warning">
              This strategy is currently <StatusBadge status={strategy.status} />. Editing metadata does not affect its lifecycle state or Marketplace visibility.
            </Alert>
          </div>
        </div>
      )}

      <StrategyForm
        mode="edit"
        initial={{
          name: strategy.name,
          description: strategy.description ?? "",
        }}
        submitLabel="Save changes"
        cancelTo={`/creator/strategies/${strategyId}`}
        onSave={async (values) => {
          const data: StrategyUpdateRequest = {
            name: values.name,
            description: values.description || null,
          };
          await strategiesApi.update(strategyId, data);
          await client.invalidateQueries({ queryKey: queryKeys.strategy(strategyId) });
          await client.invalidateQueries({ queryKey: queryKeys.strategies });
          navigate(`/creator/strategies/${strategyId}`);
        }}
        aside={
          <section className="panel" aria-labelledby="edit-lifecycle">
            <div className="panel-body">
              <h2 id="edit-lifecycle">Lifecycle</h2>
              <LifecycleSteps strategy={strategy} />
            </div>
          </section>
        }
      />
    </div>
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

function VersionCreator({ strategyId, onClose }: { strategyId: string; onClose: () => void }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [instrumentId, setInstrumentId] = useState("");
  const [configuration, setConfiguration] = useState("{}");
  const [backtest, setBacktest] = useState("{}");
  const [error, setError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  /* Debounce instrument search — ~300 ms */
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const instruments = useQuery({
    queryKey: queryKeys.instruments(debouncedSearch),
    queryFn: () => instrumentsApi.list(debouncedSearch),
  });

  const mutation = useMutation({
    mutationFn: () =>
      strategiesApi.createVersion(strategyId, {
        instrument_id: instrumentId,
        configuration: parseObject(configuration, "Algorithm configuration"),
        backtest_configuration: parseObject(backtest, "Backtest configuration"),
      }),
    onSuccess: async (newVersion) => {
      onClose();
      await client.invalidateQueries({ queryKey: queryKeys.versions(strategyId) });
      navigate(`/creator/strategies/${strategyId}/versions/${newVersion.id}`);
    },
    onError: (reason) => setError(errorMessage(reason, "Unable to create Version.")),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setConfigError(null);
    setBacktestError(null);

    let valid = true;

    if (!instrumentId) {
      setError("Select an Instrument before creating a Version.");
      valid = false;
    }

    try {
      parseObject(configuration, "Algorithm configuration");
    } catch (reason) {
      setConfigError(reason instanceof Error ? reason.message : "Invalid JSON.");
      valid = false;
    }

    try {
      parseObject(backtest, "Backtest configuration");
    } catch (reason) {
      setBacktestError(reason instanceof Error ? reason.message : "Invalid JSON.");
      valid = false;
    }

    if (valid) {
      mutation.mutate();
    }
  };

  const selectedInstrument = instruments.data?.find((i) => i.id === instrumentId);

  return (
    <form className="panel" onSubmit={submit} aria-label="Create Version" noValidate>
      <div className="panel-head">
        <SectionHeader
          title="Create Version"
          description="Versions are permanent once saved: choose the instrument, then supply two JSON objects."
        />
      </div>

      <fieldset className="form-section" style={{ borderBottom: "1px solid var(--border)" }}>
        <legend className="visually-hidden">Instrument</legend>
        <div className="form-section-head">
          <span className="form-section-num" aria-hidden="true">1</span>
          <div>
            <h3>Instrument</h3>
            <p>The market this Version trades. Stored canonically, separate from algorithm parameters.</p>
          </div>
        </div>
        <div className="form-section-body">
          <div className="form-field">
            <label className="form-label" htmlFor="version-instrument-search">Search Instrument</label>
            <input
              id="version-instrument-search"
              className="input"
              type="search"
              placeholder="Search name or symbol"
              value={search}
              autoComplete="off"
              aria-describedby="version-instrument-search-hint"
              onChange={(e) => setSearch(e.target.value)}
            />
            <p className="field-hint" id="version-instrument-search-hint">Results update after a short pause. Select from the list below.</p>
          </div>

          {instruments.isLoading ? (
            <SkeletonGroup label="Loading Instruments…"><Skeleton height="2.5rem" /></SkeletonGroup>
          ) : instruments.isError ? (
            <ErrorPanel title="Couldn't load Instruments" onRetry={() => void instruments.refetch()}>
              {errorMessage(instruments.error, "Unable to load Instruments.")}
            </ErrorPanel>
          ) : (
            <div className={`form-field ${error && !instrumentId ? "has-error" : ""}`}>
              <label className="form-label" htmlFor="version-instrument-select">Instrument</label>
              <select
                id="version-instrument-select"
                className="input"
                aria-label="Instrument"
                aria-required="true"
                aria-invalid={!instrumentId && !!error ? true : undefined}
                aria-describedby={!instrumentId && error ? "version-instrument-error" : undefined}
                value={instrumentId}
                onChange={(e) => setInstrumentId(e.target.value)}
              >
                <option value="">Select an Instrument</option>
                {instruments.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {item.exchange_symbol} · {item.exchange.code} · {item.instrument_type} · {item.quote_currency}
                    {item.is_tradeable ? "" : " · non-tradeable"}
                  </option>
                ))}
              </select>
              {!instrumentId && error && (
                <p className="field-error" role="alert" id="version-instrument-error">{error}</p>
              )}
            </div>
          )}

          {selectedInstrument && (
            <div className="selected-instrument">
              <strong>Selected: {selectedInstrument.name}</strong>
              <span>
                {selectedInstrument.canonical_symbol} · {selectedInstrument.exchange.code} · {selectedInstrument.instrument_type} · {selectedInstrument.quote_currency}
                {selectedInstrument.is_tradeable ? "" : " · non-tradeable"}
              </span>
            </div>
          )}
        </div>
      </fieldset>

      <fieldset className="form-section" style={{ borderBottom: "1px solid var(--border)" }}>
        <legend className="visually-hidden">Algorithm configuration</legend>
        <div className="form-section-head">
          <span className="form-section-num" aria-hidden="true">2</span>
          <div>
            <h3>Algorithm configuration</h3>
            <p>The strategy's parameters, as a JSON object.</p>
          </div>
        </div>
        <div className="form-section-body">
          <div className={`form-field ${configError ? "has-error" : ""}`}>
            <label className="form-label" htmlFor="version-configuration">Algorithm configuration</label>
            <textarea
              id="version-configuration"
              className="input json-input"
              rows={5}
              spellCheck={false}
              aria-invalid={configError ? true : undefined}
              aria-describedby={configError ? "version-config-error" : "version-config-hint"}
              value={configuration}
              onChange={(e) => setConfiguration(e.target.value)}
            />
            {configError ? (
              <p className="field-error" role="alert" id="version-config-error">{configError}</p>
            ) : (
              <p className="field-hint" id="version-config-hint">Must be a JSON object, e.g. <code>{"{ \"period\": 14 }"}</code></p>
            )}
          </div>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend className="visually-hidden">Backtest configuration</legend>
        <div className="form-section-head">
          <span className="form-section-num" aria-hidden="true">3</span>
          <div>
            <h3>Backtest configuration</h3>
            <p>Simulation settings used when this Version is backtested.</p>
          </div>
        </div>
        <div className="form-section-body">
          <div className={`form-field ${backtestError ? "has-error" : ""}`}>
            <label className="form-label" htmlFor="version-backtest-configuration">Backtest configuration</label>
            <textarea
              id="version-backtest-configuration"
              className="input json-input"
              rows={5}
              spellCheck={false}
              aria-invalid={backtestError ? true : undefined}
              aria-describedby={backtestError ? "version-backtest-error" : "version-backtest-hint"}
              value={backtest}
              onChange={(e) => setBacktest(e.target.value)}
            />
            {backtestError ? (
              <p className="field-error" role="alert" id="version-backtest-error">{backtestError}</p>
            ) : (
              <p className="field-hint" id="version-backtest-hint">Must be a JSON object, e.g. <code>{"{ \"capital\": 100000 }"}</code></p>
            )}
          </div>
        </div>
      </fieldset>

      {error && instrumentId && (
        <div className="panel-body"><ErrorPanel title="Couldn't create the Version">{error}</ErrorPanel></div>
      )}

      <div className="panel-foot">
        <Button type="submit" loading={mutation.isPending} disabled={instruments.isLoading}>
          {mutation.isPending ? "Creating…" : "Create Version"}
        </Button>
        <Button type="button" variant="ghost" disabled={mutation.isPending} onClick={onClose}>Cancel</Button>
      </div>
    </form>
  );
}

/* ── Strategy detail page ─────────────────────────────────────── */
const ACTION_COPY: Record<LifecycleAction, { label: string; pending: string }> = {
  publish: { label: "Publish", pending: "Publishing…" },
  deploy: { label: "Deploy", pending: "Deploying…" },
  archive: { label: "Archive", pending: "Archiving…" },
};

export function StrategyDetailPage() {
  const { strategyId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [confirm, setConfirm] = useState<"archive" | "delete" | null>(null);
  const [creatingVersion, setCreatingVersion] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: queryKeys.strategy(strategyId),
    queryFn: () => strategiesApi.get(strategyId),
  });

  const versions = useQuery({
    queryKey: queryKeys.versions(strategyId),
    queryFn: () => strategiesApi.listVersions(strategyId),
  });

  const lifecycle = useMutation({
    mutationFn: (action: LifecycleAction) => strategiesApi.lifecycle(strategyId, action),
    onSuccess: async () => {
      setActionError(null);
      setDialogError(null);
      setConfirm(null);
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.strategy(strategyId) }),
        client.invalidateQueries({ queryKey: queryKeys.strategies }),
        client.invalidateQueries({ queryKey: queryKeys.marketplace }),
      ]);
    },
    onError: (reason, action) => {
      const message = errorMessage(reason, "Lifecycle transition failed.");
      if (action === "archive") setDialogError(message);
      else setActionError(message);
    },
  });

  const remove = useMutation({
    mutationFn: () => strategiesApi.delete(strategyId),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.strategies });
      navigate("/creator/strategies");
    },
    onError: (reason) => setDialogError(errorMessage(reason, "Unable to delete strategy.")),
  });

  if (query.isLoading) return <DetailSkeleton label="Loading strategy…" />;
  if (query.isError || !query.data)
    return <LoadError error={query.error} notFound="Strategy not found." what="Strategy" onRetry={() => void query.refetch()} />;

  const strategy = query.data;
  const versionCount = versions.data?.length ?? 0;
  const allowed = NEXT_ACTIONS[strategy.status];
  const primary = allowed.find(a => a !== "archive");
  const canArchive = allowed.includes("archive");
  const currentVersion = strategy.current_version_id
    ? versions.data?.find((v) => v.id === strategy.current_version_id)
    : undefined;
  const busy = lifecycle.isPending || remove.isPending;

  const closeDialog = () => { setConfirm(null); setDialogError(null); };

  const menuItems: ActionMenuItem[] = [
    ...(canArchive ? [{ label: "Archive", icon: <Archive size={14} aria-hidden="true" />, onSelect: () => { setDialogError(null); setConfirm("archive" as const); } }] : []),
    { label: "Delete strategy", icon: <Trash2 size={14} aria-hidden="true" />, tone: "danger" as const, onSelect: () => { setDialogError(null); setConfirm("delete" as const); } },
  ];

  const createVersionButton = (variant: "primary" | "secondary") => (
    <Button variant={variant} size="sm" iconLeft={<PlusCircle size={14} aria-hidden="true" />} onClick={() => setCreatingVersion(true)}>
      Create Version
    </Button>
  );

  return (
    <div>
      <Link className="back-crumb" to="/creator/strategies"><ArrowLeft size={14} aria-hidden="true" /> Strategies</Link>

      <header className="page-header">
        <div className="page-header-text">
          <p className="eyebrow">Creator strategy</p>
          <div className="title-with-status">
            <h1>{strategy.name}</h1>
            <StatusBadge status={strategy.status} />
          </div>
          <p>{strategy.description || "No description provided."}</p>
        </div>
        <div className="page-header-actions">
          {primary && (
            <Button
              iconLeft={primary === "publish" ? <Globe size={15} aria-hidden="true" /> : <Rocket size={15} aria-hidden="true" />}
              loading={lifecycle.isPending && lifecycle.variables === primary}
              disabled={busy}
              onClick={() => { setActionError(null); lifecycle.mutate(primary); }}
            >
              {ACTION_COPY[primary].label}
            </Button>
          )}
          <Link className="btn btn-secondary" to={`/creator/strategies/${strategy.id}/edit`}>Edit metadata</Link>
          <ActionMenu label="More actions" triggerText="More" items={menuItems} />
        </div>
      </header>

      {actionError && (
        <div style={{ marginBottom: "var(--space-5)" }}>
          <Alert variant="error">{actionError}</Alert>
        </div>
      )}
      {strategy.status === "draft" && versions.isSuccess && versionCount === 0 && !actionError && (
        <div style={{ marginBottom: "var(--space-5)" }}>
          <Alert variant="info">A draft needs at least one Version before it can be published.</Alert>
        </div>
      )}

      <div className="detail-layout">
        <div className="detail-main">
          {creatingVersion && <VersionCreator strategyId={strategy.id} onClose={() => setCreatingVersion(false)} />}

          <section className="panel" aria-labelledby="versions-heading">
            <div className="panel-head">
              <SectionHeader
                id="versions-heading"
                title="Strategy Versions"
                count={versions.isSuccess ? versionCount : undefined}
                description="Immutable once created. Open a Version to see its configuration and backtests."
                actions={!creatingVersion && versionCount > 0 ? createVersionButton("secondary") : undefined}
              />
            </div>
            <div className="panel-body is-flush">
              {versions.isLoading ? (
                <SkeletonRows label="Loading Versions…" rows={3} />
              ) : versions.isError ? (
                <div className="panel-body">
                  <ErrorPanel title="Versions unavailable" onRetry={() => void versions.refetch()}>We couldn't load Versions. Try again.</ErrorPanel>
                </div>
              ) : !versions.data?.length ? (
                <EmptyState
                  variant="compact"
                  icon={<PlusCircle size={22} />}
                  title="No Versions yet"
                  action={!creatingVersion ? createVersionButton("primary") : undefined}
                >
                  A Version pins an instrument and configuration. Create one to backtest this strategy and to publish it.
                </EmptyState>
              ) : (
                <ul className="version-rows">
                  {versions.data.map((version) => (
                    <li key={version.id}>
                      <Link className="version-row" to={`/creator/strategies/${strategy.id}/versions/${version.id}`}>
                        <div className="version-row-main">
                          <strong>Version {version.version_number}</strong>
                          {version.instrument && <span>{version.instrument.name} · {version.instrument.exchange.code}</span>}
                        </div>
                        <div className="version-row-meta">
                          <span>{date(version.created_at)}</span>
                          {version.id === strategy.current_version_id && <span className="badge badge-info">Current</span>}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>

        <div className="detail-side">
          <section className="panel" aria-labelledby="overview-heading">
            <div className="panel-head"><SectionHeader id="overview-heading" title="Overview" /></div>
            <div className="panel-body">
              <dl className="kv">
                <dt>Slug</dt>
                <dd className="mono">{strategy.slug}</dd>
                <dt>Visibility</dt>
                <dd>{strategy.is_public ? "Public" : "Private"}</dd>
                <dt>Current Version</dt>
                <dd>{strategy.current_version_id ? (currentVersion ? `Version ${currentVersion.version_number}` : "Selected") : "None"}</dd>
                <dt>Created</dt>
                <dd>{date(strategy.created_at)}</dd>
                <dt>Updated</dt>
                <dd>{date(strategy.updated_at)}</dd>
              </dl>
            </div>
          </section>

          <section className="panel" aria-labelledby="lifecycle-heading">
            <div className="panel-head"><SectionHeader id="lifecycle-heading" title="Lifecycle" description="Transitions follow backend lifecycle rules." /></div>
            <div className="panel-body"><LifecycleSteps strategy={strategy} /></div>
          </section>
        </div>
      </div>

      <ConfirmDialog
        open={confirm === "archive"}
        title="Archive this strategy?"
        confirmLabel="Confirm archive"
        pendingLabel="Archiving…"
        pending={lifecycle.isPending}
        error={dialogError}
        onCancel={closeDialog}
        onConfirm={() => lifecycle.mutate("archive")}
      >
        <p>
          Archiving <strong>{strategy.name}</strong> is terminal and makes it private. You won't be able to publish or deploy it again.
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={confirm === "delete"}
        title="Delete this strategy?"
        confirmLabel="Delete permanently"
        pendingLabel="Deleting…"
        pending={remove.isPending}
        error={dialogError}
        onCancel={closeDialog}
        onConfirm={() => remove.mutate()}
      >
        <p>
          Confirm deletion of <strong>{strategy.name}</strong>? Deletion is permanent. There is no restore action.
        </p>
      </ConfirmDialog>
    </div>
  );
}

/* ── Strategy version page ────────────────────────────────────── */
export function StrategyVersionPage() {
  const { strategyId = "", versionId = "" } = useParams();

  const strategyQuery = useQuery({
    queryKey: queryKeys.strategy(strategyId),
    queryFn: () => strategiesApi.get(strategyId),
  });

  const query = useQuery({
    queryKey: queryKeys.version(strategyId, versionId),
    queryFn: () => strategiesApi.getVersion(strategyId, versionId),
  });

  if (query.isLoading) return <DetailSkeleton label="Loading Version…" />;
  if (query.isError || !query.data)
    return <LoadError error={query.error} notFound="Strategy Version not found." what="Version" onRetry={() => void query.refetch()} />;

  const instrument = query.data.instrument;
  const strategy = strategyQuery.data;
  const strategyName = strategy?.name;
  const isCurrent = strategy?.current_version_id === query.data.id;

  return (
    <div>
      <Link className="back-crumb" to={`/creator/strategies/${strategyId}`}>
        <ArrowLeft size={14} aria-hidden="true" /> {strategyName ?? "Strategy"}
      </Link>

      <header className="page-header">
        <div className="page-header-text">
          <p className="eyebrow">{strategyName ? `${strategyName} · ` : ""}Immutable version</p>
          <div className="title-with-status">
            <h1>Version {query.data.version_number}</h1>
            {isCurrent && <span className="badge badge-info">Current</span>}
          </div>
          <p>Created {date(query.data.created_at)}</p>
        </div>
      </header>

      <div className="page-stack">
        <div role="note"><Alert variant="info">Versions are immutable once created. There are no edit or delete actions.</Alert></div>

        <div className="detail-layout">
          <div className="detail-main">
            <section className="panel" aria-labelledby="algo-config">
              <div className="panel-head"><SectionHeader id="algo-config" title="Algorithm configuration" /></div>
              <div className="panel-body"><pre className="json-view">{JSON.stringify(query.data.configuration, null, 2)}</pre></div>
            </section>
            <section className="panel" aria-labelledby="bt-config">
              <div className="panel-head"><SectionHeader id="bt-config" title="Backtest configuration" /></div>
              <div className="panel-body"><pre className="json-view">{JSON.stringify(query.data.backtest_configuration, null, 2)}</pre></div>
            </section>
          </div>

          <div className="detail-side">
            <section className="panel" aria-labelledby="instrument-heading">
              <div className="panel-head"><SectionHeader id="instrument-heading" title="Instrument" /></div>
              <div className="panel-body">
                {instrument ? (
                  <dl className="kv">
                    <dt>Name</dt>
                    <dd>{instrument.name}</dd>
                    <dt>Canonical symbol</dt>
                    <dd className="mono">{instrument.canonical_symbol}</dd>
                    <dt>Exchange symbol</dt>
                    <dd className="mono">{instrument.exchange_symbol}</dd>
                    <dt>Exchange</dt>
                    <dd>{instrument.exchange.code}</dd>
                    <dt>Type</dt>
                    <dd>
                      {instrument.instrument_type}
                      {instrument.is_tradeable ? "" : " · non-tradeable"}
                    </dd>
                    <dt>Currency</dt>
                    <dd>{instrument.quote_currency}</dd>
                    <dt>Tick size</dt>
                    <dd>{instrument.tick_size ?? "—"}</dd>
                    <dt>Lot size</dt>
                    <dd>{instrument.lot_size ?? "—"}</dd>
                  </dl>
                ) : (
                  <div>
                    <p className="badge badge-muted">legacy / unresolved</p>
                    <p className="hint-line" style={{ marginTop: "var(--space-3)" }}>
                      This legacy Version has no resolved canonical Instrument. Its immutable configuration remains available.
                    </p>
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>

        <Suspense fallback={<SkeletonRows label="Loading Backtests…" rows={3} />}>
          <VersionBacktests strategyId={strategyId} versionId={versionId} />
        </Suspense>
      </div>
    </div>
  );
}
