import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { HomePage } from "./router";

describe("AlgoProfitX landing page", () => {
  it("communicates the product workflow with primary discovery actions", () => {
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: /turn trading ideas into testable strategies/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start building/i })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: /explore marketplace/i })).toHaveAttribute("href", "/marketplace");
    expect(screen.getByText("Paper execute")).toBeInTheDocument();
    expect(screen.getByText(/not live performance/i)).toBeInTheDocument();
    expect(screen.getByText("1d · INR")).toBeInTheDocument();
    expect(screen.getByText("EMA crossover · NSE · 1d")).toBeInTheDocument();
    expect(screen.queryByText(/1h/)).not.toBeInTheDocument();
  });
});
