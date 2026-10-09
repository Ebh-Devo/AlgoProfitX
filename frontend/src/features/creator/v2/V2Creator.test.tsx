/**
 * Strategy V2 creator (Phase 7B-2): version choice, vocabulary-driven controls, stateless validation,
 * dedicated V2 creation, structured errors, and the backtest-only lifecycle boundary.
 */
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "../../../api/client";
import { StrategyDetailPage, StrategyVersionPage } from "../StrategyPages";

const api = vi.hoisted(() => ({
  get: vi.fn(), listVersions: vi.fn(), getVersion: vi.fn(), createVersion: vi.fn(), lifecycle: vi.fn(),
  getDefinitionVocabulary: vi.fn(), validateDefinition: vi.fn(), createVersionV2: vi.fn(),
  listBacktests: vi.fn(), createBacktest: vi.fn(),
}));
const instrumentApi = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("../../../api/strategies", () => ({ strategiesApi: api }));
vi.mock("../../../api/instruments", () => ({ instrumentsApi: instrumentApi }));

const exchange = { id: "e1", code: "NSE", name: "NSE", country_code: "IN", timezone: "Asia/Kolkata", default_currency: "INR", calendar_code: "XNSE", is_active: true };
const instrument = {
  id: "i1", canonical_symbol: "NSE:REF", exchange_symbol: "REF", name: "Reference Equity", instrument_type: "equity", quote_currency: "INR",
  tick_size: 0.05, lot_size: 1, is_tradeable: true, isin: null, is_synthetic: true, is_active: true,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", exchange,
};
const strategy = {
  id: "s1", creator_id: "u1", name: "Trend", slug: "trend", description: "", status: "draft" as const, is_public: false,
  current_version_id: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", published_at: null, deployed_at: null,
};

const vocabulary = {
  definition_schema_version: 2 as const,
  timeframes: ["1d"], evaluation_modes: ["bar_close"], fill_models: ["same_bar_close"],
  position: { roles: ["core"], max_core_positions: 1, max_legs_per_position: 1, instrument_kinds: ["primary"], leg_sides: ["buy", "sell"], sizing_units: ["shares"] },
  operations: ["close", "open"],
  condition_kinds: ["compare", "cross", "all", "any", "not", "edge"],
  compare_operators: ["gt", "gte", "lt", "lte"], cross_directions: ["above", "below"], edge_directions: ["rising"],
  operand_kinds: ["price", "constant", "indicator"], price_fields: ["open", "high", "low", "close", "volume"],
  indicator_source_fields: ["open", "high", "low", "close"],
  indicators: [{ key: "ema@1", name: "ema", version: 1, params: [{ name: "period", type: "integer", required: true, minimum: 1, maximum: 5000 }], outputs: ["value"] }],
  supports_rule_limits: false, supports_risk_rules: false, capabilities: ["indicator.ema@1", "op.close", "op.open"],
};

const runnable = { definition_schema_version: 2 as const, valid: true, savable: true, runnable: true, issues: [], required_capabilities: ["op.open"], unsupported_capabilities: [] };

const v2Version = {
  id: "v9", strategy_id: "s1", instrument_id: "i1", instrument, version_number: 3, definition_schema_version: 2,
  configuration: {
    schema: "algoprofitx.strategy-definition", schema_version: 2, timeframe: "1d", evaluation: "bar_close",
    positions: { main: { role: "core", hedges: null, legs: [{ id: "leg-1", instrument: { kind: "primary" }, side: "buy", quantity: 1 }], sizing: { unit: "shares", value: 10 } } },
    rules: [
      { id: "rule-1", when: { kind: "cross", dir: "above", left: { kind: "indicator", name: "ema", version: 1, params: { period: 9 }, source: { kind: "price", field: "close" }, timeframe: "1d", output: "value" }, right: { kind: "indicator", name: "ema", version: 1, params: { period: 21 }, source: { kind: "price", field: "close" }, timeframe: "1d", output: "value" } }, then: [{ op: "open", position: "main" }] },
      { id: "rule-2", when: { kind: "cross", dir: "below", left: { kind: "indicator", name: "ema", version: 1, params: { period: 9 }, source: { kind: "price", field: "close" }, timeframe: "1d", output: "value" }, right: { kind: "indicator", name: "ema", version: 1, params: { period: 21 }, source: { kind: "price", field: "close" }, timeframe: "1d", output: "value" } }, then: [{ op: "close", position: "main" }] },
    ],
  },
  backtest_configuration: { initial_capital: 50000, timeframe: "1d", fill_model: "same_bar_close" },
  created_at: "2026-01-03T00:00:00Z",
};

function view(ui: React.ReactNode, path = "/creator/strategies/s1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/creator/strategies/:strategyId" element={ui} />
          <Route path="/creator/strategies/:strategyId/versions/:versionId" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue(strategy);
  api.listVersions.mockResolvedValue([]);
  api.listBacktests.mockResolvedValue([]);
  api.getDefinitionVocabulary.mockResolvedValue(vocabulary);
  instrumentApi.list.mockResolvedValue([instrument]);
});

const v2Form = () => within(screen.getByRole("form", { name: "Create Strategy V2 Version" }));

async function openV2() {
  view(<StrategyDetailPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Create Version" }));
  await userEvent.click(await screen.findByRole("radio", { name: /Strategy V2/ }));
  await screen.findByRole("form", { name: "Create Strategy V2 Version" });
  await v2Form().findByLabelText("Instrument");
}

const pickInstrument = async () => userEvent.selectOptions(await v2Form().findByLabelText("Instrument"), "i1");

async function validateRunnable() {
  api.validateDefinition.mockResolvedValue(runnable);
  await pickInstrument();
  await userEvent.click(screen.getByRole("button", { name: "Validate" }));
  await screen.findByText("Runnable in the current environment", { selector: "strong" });
}

describe("Definition version choice", () => {
  it("offers V1 and V2 explicitly, with V1 as the unchanged default", async () => {
    view(<StrategyDetailPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Create Version" }));
    const v1 = await screen.findByRole("radio", { name: /Strategy V1/ });
    expect(v1).toBeChecked();
    expect(screen.getByRole("radio", { name: /Strategy V2/ })).not.toBeChecked();
    expect(screen.getByRole("form", { name: "Create Version" })).toBeInTheDocument();
    expect(api.getDefinitionVocabulary).not.toHaveBeenCalled();
  });

  it("loads the vocabulary only once V2 is chosen and keeps the V1 form separate", async () => {
    await openV2();
    expect(api.getDefinitionVocabulary).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("form", { name: "Create Version" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Strategy V1/ }));
    expect(screen.getByRole("form", { name: "Create Version" })).toBeInTheDocument();
    expect(api.validateDefinition).not.toHaveBeenCalled();
    expect(api.createVersionV2).not.toHaveBeenCalled();
  });
});

describe("Vocabulary-driven controls", () => {
  it("offers only what the vocabulary advertises", async () => {
    api.getDefinitionVocabulary.mockResolvedValue({ ...vocabulary, operations: ["close", "increase", "open", "reduce"] });
    await openV2();
    const timeframe = screen.getByLabelText("Timeframe");
    expect(within(timeframe).getAllByRole("option").map((o) => o.textContent)).toEqual(["Daily (1d)"]);
    const fill = screen.getByLabelText("Fill model");
    expect(within(fill).getAllByRole("option")).toHaveLength(1);
    const [firstIndicator] = screen.getAllByLabelText(/^Indicator/);
    expect(within(firstIndicator).getAllByRole("option").map((o) => o.textContent)).toEqual(["EMA (version 1)"]);
    const [action] = v2Form().getAllByLabelText(/^Action/);
    expect(within(action).getAllByRole("option").map((o) => o.textContent)).toEqual(["Close the position", "Open a position"]);
    expect(screen.queryByText(/increase|reduce/i)).not.toBeInTheDocument();
  });

  it("does not offer indicators the vocabulary does not list", async () => {
    api.getDefinitionVocabulary.mockResolvedValue({ ...vocabulary, indicators: [], operand_kinds: ["price", "constant", "indicator"] });
    await openV2();
    expect(screen.queryByLabelText(/^Indicator/)).not.toBeInTheDocument();
    const [kind] = screen.getAllByLabelText(/^Value type/);
    expect(within(kind).queryByRole("option", { name: "Indicator" })).not.toBeInTheDocument();
  });

  it("shows a recoverable error and no hardcoded fallback when the vocabulary fails", async () => {
    api.getDefinitionVocabulary.mockRejectedValueOnce(new ApiError(503, "Service unavailable"));
    view(<StrategyDetailPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Create Version" }));
    await userEvent.click(await screen.findByRole("radio", { name: /Strategy V2/ }));
    expect(await screen.findByText("Couldn't load what Strategy V2 can do")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Validate" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Timeframe")).not.toBeInTheDocument();
    api.getDefinitionVocabulary.mockResolvedValue(vocabulary);
    await userEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByRole("button", { name: "Validate" })).toBeInTheDocument();
  });

  it("describes each rule in plain language that matches the controls", async () => {
    await openV2();
    expect(screen.getByText("When EMA(9) crosses above EMA(21), open a long position.")).toBeInTheDocument();
    expect(screen.getByText("When EMA(9) crosses below EMA(21), close the long position.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Direction"), "sell");
    expect(screen.getByText("When EMA(9) crosses above EMA(21), open a short position.")).toBeInTheDocument();
  });

  it("shows only the fields relevant to the selected condition", async () => {
    await openV2();
    const [condition] = screen.getAllByLabelText(/^Condition/);
    await userEvent.selectOptions(condition, "compare");
    expect(screen.getAllByLabelText(/^Comparison/).length).toBeGreaterThan(0);
    await userEvent.selectOptions(screen.getAllByLabelText(/^Condition/)[0], "edge");
    expect(screen.getByLabelText(/^Trigger when it/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getAllByLabelText(/^Condition/)[0], "all");
    expect(screen.getAllByRole("button", { name: /Add a condition/ }).length).toBeGreaterThan(0);
  });
});

describe("Validation", () => {
  it("sends the explicit V2 request and writes nothing", async () => {
    await openV2();
    await validateRunnable();
    expect(api.validateDefinition).toHaveBeenCalledTimes(1);
    const request = api.validateDefinition.mock.calls[0][0];
    expect(request.definition_schema_version).toBe(2);
    expect(request.configuration).toMatchObject({ schema: "algoprofitx.strategy-definition", schema_version: 2, timeframe: "1d", evaluation: "bar_close" });
    expect(request.configuration.positions.main.sizing).toEqual({ unit: "shares", value: 10 });
    expect(request.configuration.positions.main.legs[0]).toMatchObject({ side: "buy", quantity: 1, instrument: { kind: "primary" } });
    expect(request.configuration.rules[0].when.left).toMatchObject({ kind: "indicator", name: "ema", version: 1, params: { period: 9 }, timeframe: "1d", output: "value" });
    expect(request.backtest_configuration).toEqual({ initial_capital: 50000, timeframe: "1d", fill_model: "same_bar_close" });
    expect(api.createVersionV2).not.toHaveBeenCalled();
    expect(api.createVersion).not.toHaveBeenCalled();
    expect(api.createBacktest).not.toHaveBeenCalled();
    const verdicts = screen.getByRole("list", { name: "Verdict" });
    expect(within(verdicts).getAllByText("Yes")).toHaveLength(3);
  });

  it("requires an instrument and numeric fields before calling the server", async () => {
    await openV2();
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("Select an instrument before validating.")).toBeInTheDocument();
    await pickInstrument();
    await userEvent.clear(screen.getByLabelText("Number of shares"));
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText(/Position size: enter the number of shares/)).toBeInTheDocument();
    expect(api.validateDefinition).not.toHaveBeenCalled();
  });

  it("groups issues by section and distinguishes errors from warnings", async () => {
    api.validateDefinition.mockResolvedValue({
      definition_schema_version: 2, valid: false, savable: false, runnable: false, required_capabilities: [], unsupported_capabilities: [],
      issues: [
        { path: "rules[0].when.left.params.period", code: "param_out_of_range", message: "period must be between 1 and 5000", severity: "error", layer: "semantic" },
        { path: "backtest_configuration.timeframe", code: "timeframe_unsupported", message: "timeframe '5m' is not supported", severity: "error", layer: "environment" },
        { path: "rules[1]", code: "rule_never_fires", message: "this rule can never fire", severity: "warning", layer: "semantic" },
      ],
    });
    await openV2();
    await pickInstrument();
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("This definition has problems to fix")).toBeInTheDocument();
    const rule1 = screen.getByRole("region", { name: "Rule 1" });
    expect(within(rule1).getByText("period must be between 1 and 5000")).toBeInTheDocument();
    expect(within(rule1).getByText("Error")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Execution environment" })).getByText("timeframe '5m' is not supported")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Rule 2" })).getByText("Warning")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Version" })).toBeDisabled();
    expect(within(screen.getByRole("list", { name: "Verdict" })).getAllByText("No")).toHaveLength(3);
  });

  it("does not present a savable but non-runnable definition as runnable", async () => {
    api.validateDefinition.mockResolvedValue({
      definition_schema_version: 2, valid: false, savable: true, runnable: false, required_capabilities: ["op.increase", "op.open"], unsupported_capabilities: ["op.increase"],
      issues: [{ path: "", code: "capability_missing", message: "operation: op.increase", severity: "error", layer: "capability" }],
    });
    await openV2();
    await pickInstrument();
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("Well-formed, but not runnable yet")).toBeInTheDocument();
    expect(screen.queryByText("Runnable in the current environment", { selector: "strong" })).not.toBeInTheDocument();
    const unsupported = screen.getByRole("group", { name: "Unsupported capabilities" });
    expect(within(unsupported).getByText("op.increase")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Version" })).toBeDisabled();
    expect(api.createVersionV2).not.toHaveBeenCalled();
  });

  it("keeps the form when validation fails unexpectedly, and allows trying again", async () => {
    api.validateDefinition.mockRejectedValueOnce(new ApiError(500, "An unexpected server error occurred."));
    await openV2();
    await pickInstrument();
    await userEvent.clear(screen.getByLabelText("Number of shares"));
    await userEvent.type(screen.getByLabelText("Number of shares"), "25");
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("An unexpected server error occurred.")).toBeInTheDocument();
    expect(screen.getByLabelText("Number of shares")).toHaveValue("25");
    expect(v2Form().getByLabelText("Instrument")).toHaveValue("i1");
    api.validateDefinition.mockResolvedValue(runnable);
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("Runnable in the current environment", { selector: "strong" })).toBeInTheDocument();
  });

  it("can be triggered from the keyboard", async () => {
    api.validateDefinition.mockResolvedValue(runnable);
    await openV2();
    await pickInstrument();
    screen.getByRole("button", { name: "Validate" }).focus();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("list", { name: "Verdict" })).toBeInTheDocument();
  });

  it("invalidates the verdict when the strategy is edited afterwards", async () => {
    await openV2();
    await validateRunnable();
    expect(screen.getByRole("button", { name: "Save Version" })).toBeEnabled();
    await userEvent.type(screen.getByLabelText("Number of shares"), "5");
    expect(screen.getByRole("button", { name: "Save Version" })).toBeDisabled();
    expect(screen.getByText(/Validate again to enable saving/)).toBeInTheDocument();
  });
});

describe("Saving a V2 Version", () => {
  it("uses the dedicated V2 endpoint with the explicit schema version", async () => {
    api.createVersionV2.mockResolvedValue(v2Version);
    await openV2();
    await validateRunnable();
    await userEvent.click(screen.getByRole("button", { name: "Save Version" }));
    await waitFor(() => expect(api.createVersionV2).toHaveBeenCalledTimes(1));
    const [strategyId, body] = api.createVersionV2.mock.calls[0];
    expect(strategyId).toBe("s1");
    expect(body).toMatchObject({ definition_schema_version: 2, instrument_id: "i1", backtest_configuration: { initial_capital: 50000, timeframe: "1d", fill_model: "same_bar_close" } });
    expect(body.configuration.schema_version).toBe(2);
    expect(api.createVersion).not.toHaveBeenCalled();
  });

  it("cannot create duplicate Versions from repeated clicks", async () => {
    let resolve!: (value: unknown) => void;
    api.createVersionV2.mockReturnValue(new Promise((r) => { resolve = r; }));
    await openV2();
    await validateRunnable();
    const save = screen.getByRole("button", { name: "Save Version" });
    await userEvent.dblClick(save);
    await userEvent.click(save);
    expect(api.createVersionV2).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    resolve(v2Version);
  });

  it("shows the backend's structured refusal and saves nothing", async () => {
    api.createVersionV2.mockRejectedValue(new ApiError(422, "definition cannot run", [], undefined, {
      code: "strategy_definition_not_runnable",
      issues: [{ path: "", code: "capability_missing", message: "operation: op.increase", severity: "error", layer: "capability" }],
    }));
    await openV2();
    await validateRunnable();
    await userEvent.click(screen.getByRole("button", { name: "Save Version" }));
    expect(await screen.findByText(/cannot run in the current environment\. Nothing was saved/)).toBeInTheDocument();
    expect(screen.getAllByText("operation: op.increase").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Number of shares")).toHaveValue("10");
    expect(screen.getByRole("button", { name: "Save Version" })).toBeEnabled();
  });

  it("surfaces a version-number conflict as retryable, not as success", async () => {
    api.createVersionV2.mockRejectedValue(new ApiError(409, "version conflict"));
    await openV2();
    await validateRunnable();
    await userEvent.click(screen.getByRole("button", { name: "Save Version" }));
    expect(await screen.findByText(/Another Version was created at the same time\. Nothing was saved/)).toBeInTheDocument();
  });
});

describe("Version identity and lifecycle", () => {
  it("labels versions from the persisted schema version and blocks publish for V2", async () => {
    api.listVersions.mockResolvedValue([v2Version]);
    view(<StrategyDetailPage />);
    expect(await screen.findByText("Strategy V2")).toBeInTheDocument();
    const publish = await screen.findByRole("button", { name: "Publish" });
    expect(publish).toBeDisabled();
    expect(screen.getByText("Publish is not available for Strategy V2")).toBeInTheDocument();
    expect(screen.getByText(/current execution adapter does not support it/)).toBeInTheDocument();
    await userEvent.click(publish);
    expect(api.lifecycle).not.toHaveBeenCalled();
  });

  it("blocks deploy when the current Version is V2", async () => {
    api.get.mockResolvedValue({ ...strategy, status: "published", current_version_id: "v9" });
    api.listVersions.mockResolvedValue([v2Version]);
    view(<StrategyDetailPage />);
    expect(await screen.findByText("Deploy is not available for Strategy V2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deploy" })).toBeDisabled();
  });

  it("leaves publish enabled for V1 Versions", async () => {
    api.listVersions.mockResolvedValue([{ ...v2Version, id: "v1", definition_schema_version: 1, configuration: { entry: { type: "ema_crossover", fast_period: 3, slow_period: 9 } } }]);
    view(<StrategyDetailPage />);
    expect(await screen.findByRole("button", { name: "Publish" })).toBeEnabled();
    expect(screen.queryByText(/not available for Strategy V2/)).not.toBeInTheDocument();
  });

  it("shows a saved V2 Version in words, with its schema version and a backtest-only notice", async () => {
    api.getVersion.mockResolvedValue(v2Version);
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v9");
    expect(await screen.findByText("Strategy V2")).toBeInTheDocument();
    const rules = screen.getByRole("list", { name: "Strategy rules" });
    expect(within(rules).getByText(/When EMA\(9\) crosses above EMA\(21\), open a long position\./)).toBeInTheDocument();
    expect(within(rules).getByText(/When EMA\(9\) crosses below EMA\(21\), close the long position\./)).toBeInTheDocument();
    expect(screen.getByText("Backtest only")).toBeInTheDocument();
    expect(screen.getByText(/simulation parameter, not a deposit/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Run Backtest" }, { timeout: 5000 })).toBeInTheDocument();
  });

  it("never infers V2 from the shape of a V1 version's JSON", async () => {
    api.getVersion.mockResolvedValue({ ...v2Version, definition_schema_version: 1 });
    view(<StrategyVersionPage />, "/creator/strategies/s1/versions/v9");
    expect((await screen.findAllByText("Strategy V1")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("list", { name: "Strategy rules" })).not.toBeInTheDocument();
    expect(screen.queryByText("Backtest only")).not.toBeInTheDocument();
  });
});
