import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { HomePage } from "../features/home/HomePage";

describe("AlgoProfitX landing page", () => {
  it("communicates the product workflow with primary discovery actions", () => {
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.getByRole("heading", { level: 1, name: /turn a trading idea into a strategy you can test/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start building/i })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: /explore marketplace/i })).toHaveAttribute("href", "/marketplace");
    expect(screen.getByText("Paper execute")).toBeInTheDocument();
    expect(screen.getByText(/not live performance/i)).toBeInTheDocument();
    expect(screen.getByText(/live broker connectivity is not available/i)).toBeInTheDocument();
    expect(screen.getByText(/layout preview/i)).toBeInTheDocument();
  });
});
