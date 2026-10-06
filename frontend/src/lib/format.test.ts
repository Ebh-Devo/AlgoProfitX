import { describe, expect, it } from "vitest";

import { UNAVAILABLE, formatCurrency, formatInteger, formatNumber, formatPercentage } from "./format";

describe("formatCurrency", () => {
  it("rounds to two decimals with INR symbol", () => {
    expect(formatCurrency(64761.9048)).toBe("₹64,761.90");
    expect(formatCurrency("14761.9048")).toBe("₹14,761.90");
    expect(formatCurrency(50000)).toBe("₹50,000.00");
  });
  it("uses Indian digit grouping for large values", () => {
    expect(formatCurrency(125000)).toBe("₹1,25,000.00");
    expect(formatCurrency("100000000")).toBe("₹10,00,00,000.00");
  });
  it("handles zero, negatives and signs", () => {
    expect(formatCurrency(0)).toBe("₹0.00");
    expect(formatCurrency(-1234.567)).toBe("-₹1,234.57");
    expect(formatCurrency(-0.001)).toBe("₹0.00");
    expect(formatCurrency(125, { signed: true })).toBe("+₹125.00");
    expect(formatCurrency(-125, { signed: true })).toBe("-₹125.00");
    expect(formatCurrency(0, { signed: true })).toBe("₹0.00");
  });
  it("never turns missing values into zero", () => {
    for (const v of [null, undefined, "", "abc", NaN]) expect(formatCurrency(v)).toBe(UNAVAILABLE);
  });
});

describe("formatPercentage", () => {
  it("limits to two decimals", () => {
    expect(formatPercentage(29.5238, { signed: true })).toBe("+29.52%");
    expect(formatPercentage("29.52380952")).toBe("29.52%");
    expect(formatPercentage(-3.5)).toBe("-3.50%");
    expect(formatPercentage(0)).toBe("0.00%");
  });
  it("converts 0–1 ratios", () => {
    expect(formatPercentage(1, { ratio: true })).toBe("100.00%");
    expect(formatPercentage("0.75", { ratio: true })).toBe("75.00%");
  });
  it("keeps missing values unavailable", () => {
    expect(formatPercentage(null, { ratio: true })).toBe(UNAVAILABLE);
    expect(formatPercentage(undefined)).toBe(UNAVAILABLE);
  });
});

describe("formatNumber / formatInteger", () => {
  it("formats decimal metrics to two places", () => {
    expect(formatNumber(1.25)).toBe("1.25");
    expect(formatNumber("14.7619")).toBe("14.76");
    expect(formatNumber(0)).toBe("0.00");
    expect(formatNumber(null)).toBe(UNAVAILABLE);
  });
  it("shows integers without decimals", () => {
    expect(formatInteger(1)).toBe("1");
    expect(formatInteger(25)).toBe("25");
    expect(formatInteger(1234)).toBe("1,234");
    expect(formatInteger(0)).toBe("0");
    expect(formatInteger(undefined)).toBe(UNAVAILABLE);
  });
});
