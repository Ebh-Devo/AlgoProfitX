import { describe, expect, it } from "vitest";

import {
  buildBacktestConfiguration, buildConfiguration, describeEntry, parseCapital, readEmaRule, readInitialCapital,
  validateCapital, validateEmaRule,
} from "./strategyConfig";

describe("strategy configuration translation", () => {
  it("builds the unchanged API structure", () => {
    expect(buildConfiguration({ shortTerm: "3", longTerm: "9" })).toEqual({
      entry: { type: "ema_crossover", fast_period: 3, slow_period: 9 },
    });
    expect(buildBacktestConfiguration("50,000")).toEqual({ initial_capital: 50000 });
  });

  it("round-trips a stored rule into a sentence", () => {
    const stored = buildConfiguration({ shortTerm: "3", longTerm: "9" });
    const rule = readEmaRule(stored);
    expect(rule).toEqual({ fast: 3, slow: 9 });
    expect(describeEntry(rule!)).toBe("Buy when the 3-day EMA crosses above the 9-day EMA.");
  });

  it("does not describe unknown or malformed configurations", () => {
    expect(readEmaRule({ period: 14 })).toBeNull();
    expect(readEmaRule({ entry: { type: "other" } })).toBeNull();
    expect(readEmaRule({ entry: { type: "ema_crossover", fast_period: "x", slow_period: 9 } })).toBeNull();
    expect(readEmaRule(null)).toBeNull();
  });

  it("validates EMA periods in plain language", () => {
    expect(validateEmaRule({ shortTerm: "3", longTerm: "9" })).toEqual({});
    expect(validateEmaRule({ shortTerm: "9", longTerm: "9" }).shortTerm).toBe("Short-term EMA must be smaller than long-term EMA.");
    expect(validateEmaRule({ shortTerm: "12", longTerm: "9" }).shortTerm).toMatch(/smaller than long-term/);
    expect(validateEmaRule({ shortTerm: "0", longTerm: "9" }).shortTerm).toMatch(/whole number/);
    expect(validateEmaRule({ shortTerm: "2.5", longTerm: "9" }).shortTerm).toMatch(/whole number/);
    expect(validateEmaRule({ shortTerm: "3", longTerm: "" }).longTerm).toMatch(/whole number/);
  });

  it("parses and validates starting capital", () => {
    expect(parseCapital("1,25,000.50")).toBe(125000.5);
    expect(parseCapital("₹ 50000")).toBe(50000);
    expect(parseCapital("0")).toBeNull();
    expect(parseCapital("-5")).toBeNull();
    expect(parseCapital("abc")).toBeNull();
    expect(parseCapital("")).toBeNull();
    expect(validateCapital("50000")).toBeNull();
    expect(validateCapital("x")).toMatch(/greater than zero/);
  });

  it("reads initial_capital from a stored backtest configuration", () => {
    expect(readInitialCapital({ initial_capital: 50000 })).toBe("50000");
    expect(readInitialCapital({ capital: 1 })).toBeNull();
  });
});
