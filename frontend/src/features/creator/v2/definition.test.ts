import type { DefinitionVocabulary } from "../../../api/types";
import { buildV2Request, defaultForm, groupIssues, summarizeDefinition } from "./definition";

const vocab: DefinitionVocabulary = {
  definition_schema_version: 2, timeframes: ["1d"], evaluation_modes: ["bar_close"], fill_models: ["same_bar_close"],
  position: { roles: ["core"], max_core_positions: 1, max_legs_per_position: 1, instrument_kinds: ["primary"], leg_sides: ["buy", "sell"], sizing_units: ["shares"] },
  operations: ["close", "open"], condition_kinds: ["compare", "cross", "all", "any", "not", "edge"], compare_operators: ["gt", "gte", "lt", "lte"],
  cross_directions: ["above", "below"], edge_directions: ["rising"], operand_kinds: ["price", "constant", "indicator"],
  price_fields: ["open", "high", "low", "close", "volume"], indicator_source_fields: ["open", "high", "low", "close"],
  indicators: [{ key: "ema@1", name: "ema", version: 1, params: [{ name: "period", type: "integer", required: true, minimum: 1, maximum: 5000 }], outputs: ["value"] }],
  supports_rule_limits: false, supports_risk_rules: false, capabilities: [],
};

describe("buildV2Request", () => {
  it("builds an explicit V2 document with no hidden defaults", () => {
    const result = buildV2Request(vocab, defaultForm(vocab));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.configuration).toMatchObject({ schema: "algoprofitx.strategy-definition", schema_version: 2, timeframe: "1d", evaluation: "bar_close" });
    expect(Object.keys(result.configuration.positions as object)).toEqual(["main"]);
    expect(result.configuration.rules).toHaveLength(2);
    expect(result.backtestConfiguration).toEqual({ initial_capital: 50000, timeframe: "1d", fill_model: "same_bar_close" });
  });

  it("stamps the definition timeframe on every indicator", () => {
    const result = buildV2Request(vocab, defaultForm(vocab));
    const json = JSON.stringify(result.ok && result.configuration.rules);
    expect(json).toContain('"timeframe":"1d"');
  });

  it("reports unusable inputs instead of guessing", () => {
    const result = buildV2Request(vocab, { ...defaultForm(vocab), shares: "", capital: "abc" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    const text = result.problems.map((p) => p.message).join(" ");
    expect(text).toMatch(/shares/);
    expect(text).toMatch(/capital/i);
  });
});

describe("summarizeDefinition", () => {
  it("returns null for documents that are not V2-shaped rather than guessing", () => {
    expect(summarizeDefinition({ entry: { type: "ema_crossover", fast_period: 3, slow_period: 9 } })).toBeNull();
    expect(summarizeDefinition(null)).toBeNull();
    expect(summarizeDefinition({ positions: {}, rules: [{ id: "x", when: { kind: "mystery" }, then: [] }] })).toBeNull();
  });

  it("round-trips a built document into matching sentences", () => {
    const built = buildV2Request(vocab, { ...defaultForm(vocab), legSide: "sell", shares: "1" });
    if (!built.ok) throw new Error("expected a buildable form");
    const summary = summarizeDefinition(built.configuration);
    expect(summary?.position).toBe("One short position of 1 share in the selected instrument.");
    expect(summary?.rules.map((r) => r.text)).toEqual([
      "When EMA(9) crosses above EMA(21), open a short position.",
      "When EMA(9) crosses below EMA(21), close the short position.",
    ]);
  });
});

describe("groupIssues", () => {
  it("groups by the part of the strategy the issue is about", () => {
    const base = { code: "c", message: "m", severity: "error" as const };
    const groups = groupIssues([
      { ...base, path: "rules[2].then[0]", layer: "semantic" }, { ...base, path: "positions.main.sizing", layer: "position" },
      { ...base, path: "timeframe", layer: "environment" }, { ...base, path: "", layer: "capability" },
    ]);
    expect(groups.map((g) => g.section)).toEqual(["Rule 3", "Position configuration", "Execution environment", "Supported capabilities"]);
  });
});
