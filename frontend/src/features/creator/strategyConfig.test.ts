import { describe, expect, it } from "vitest";

import {
  DEFAULT_EMA_RULE, DEFAULT_EXIT_RULE, buildBacktestConfiguration, buildConfiguration, describeEntry, describeExit, readExitRule, parseCapital, readEmaRule, readInitialCapital,
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

  it("defaults entry and exit to 3-day over 9-day EMA", () => {
    expect(DEFAULT_EMA_RULE).toEqual({ shortTerm: "3", longTerm: "9" });
    expect(DEFAULT_EXIT_RULE).toEqual({ shortTerm: "3", longTerm: "9" });
  });

  it("serializes and reads back an exit rule", () => {
    const stored = buildConfiguration({ shortTerm: "3", longTerm: "9" }, { shortTerm: "5", longTerm: "20" });
    expect(stored).toEqual({
      entry: { type: "ema_crossover", fast_period: 3, slow_period: 9 },
      exit: { type: "ema_crossover", direction: "below", fast_period: 5, slow_period: 20 },
    });
    expect(readEmaRule(stored)).toEqual({ fast: 3, slow: 9 });
    const exit = readExitRule(JSON.parse(JSON.stringify(stored)));
    expect(exit).toEqual({ fast: 5, slow: 20 });
    expect(describeExit(exit!)).toBe("Sell when the 5-day EMA crosses below the 20-day EMA.");
  });

  it("treats entry-only configurations as having no exit rule", () => {
    const legacy = buildConfiguration({ shortTerm: "3", longTerm: "9" });
    expect(legacy).not.toHaveProperty("exit");
    expect(readEmaRule(legacy)).toEqual({ fast: 3, slow: 9 });
    expect(readExitRule(legacy)).toBeNull();
    expect(readExitRule(null)).toBeNull();
    expect(readExitRule({ exit: { type: "ema_crossover", direction: "above", fast_period: 3, slow_period: 9 } })).toBeNull();
    expect(readExitRule({ exit: { type: "ema_crossover", direction: "below", fast_period: "x", slow_period: 9 } })).toBeNull();
  });

  it("validates exit periods with the same plain-language rules", () => {
    expect(validateEmaRule(DEFAULT_EXIT_RULE)).toEqual({});
    expect(validateEmaRule({ shortTerm: "9", longTerm: "3" }).shortTerm).toMatch(/smaller than long-term/);
    expect(validateEmaRule({ shortTerm: "-1", longTerm: "3" }).shortTerm).toMatch(/whole number/);
  });
});
