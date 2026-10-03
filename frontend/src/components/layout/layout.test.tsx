import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Tabs } from "../ui/Tabs";
import { AccountMenu } from "./AccountMenu";
import { buildCrumbs } from "./breadcrumbs";

describe("buildCrumbs", () => {
  it("labels the dashboard as the current page", () => {
    expect(buildCrumbs("/app")).toEqual([{ label: "Dashboard" }]);
  });

  it("folds routing prefixes and names opaque ids", () => {
    const crumbs = buildCrumbs("/creator/strategies/s1/versions/v1/backtests/b1");
    expect(crumbs.map(c => c.label)).toEqual(["Dashboard", "Strategies", "Details", "Version", "Backtest"]);
    expect(crumbs[1].to).toBe("/creator/strategies");
    expect(crumbs.at(-1)?.to).toBeUndefined();
  });
});

describe("AccountMenu", () => {
  it("opens, moves with arrow keys and closes on Escape", () => {
    render(<MemoryRouter><AccountMenu email="a@b.co" roles={["Investor"]} onLogout={vi.fn()} /></MemoryRouter>);
    const trigger = screen.getByRole("button", { name: /account menu/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const [first, second] = screen.getAllByRole("menuitem");
    expect(first).toHaveFocus();
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(second).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("calls onLogout", () => {
    const onLogout = vi.fn();
    render(<MemoryRouter><AccountMenu email="a@b.co" roles={[]} onLogout={onLogout} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /log out/i }));
    expect(onLogout).toHaveBeenCalledOnce();
  });
});

describe("Tabs", () => {
  it("switches panels with click and arrow keys", () => {
    render(<Tabs label="Sections" items={[{ id: "a", label: "A", content: "Panel A" }, { id: "b", label: "B", content: "Panel B" }]} />);
    expect(screen.getByRole("tab", { name: "A" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Panel A")).toBeVisible();
    fireEvent.keyDown(screen.getByRole("tab", { name: "A" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "B" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Panel B")).toBeInTheDocument();
  });
});
