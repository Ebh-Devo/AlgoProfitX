import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AlgorithmSummary } from "./ConfigViews";

const entry = { type: "ema_crossover", fast_period: 3, slow_period: 9 };

describe("AlgorithmSummary", () => {
  it("renders both entry and exit rules", () => {
    render(<AlgorithmSummary configuration={{ entry, exit: { ...entry, direction: "below" } }} />);
    expect(screen.getByText("Buy when the 3-day EMA crosses above the 9-day EMA.")).toBeInTheDocument();
    expect(screen.getByText("Sell when the 3-day EMA crosses below the 9-day EMA.")).toBeInTheDocument();
  });

  it("renders a short configuration with its selected actions", () => {
    render(
      <AlgorithmSummary
        configuration={{
          entry: { ...entry, action: "sell", direction: "below" },
          exit: { ...entry, action: "buy", direction: "above" },
        }}
      />,
    );
    expect(screen.getByText("Sell when the 3-day EMA crosses below the 9-day EMA.")).toBeInTheDocument();
    expect(screen.getByText("Buy when the 3-day EMA crosses above the 9-day EMA.")).toBeInTheDocument();
  });

  it("renders an entry-only (older) configuration without inventing an exit", () => {
    render(<AlgorithmSummary configuration={{ entry }} />);
    expect(screen.getByText("Buy when the 3-day EMA crosses above the 9-day EMA.")).toBeInTheDocument();
    expect(screen.queryByText(/^Sell when/)).not.toBeInTheDocument();
    expect(screen.getByText(/No exit rule/)).toBeInTheDocument();
  });
});
