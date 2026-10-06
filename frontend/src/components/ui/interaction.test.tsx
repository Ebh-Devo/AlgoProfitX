import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { InlineStatus, NextStep, RefreshIndicator, Reveal, ToastProvider, useToast } from ".";
import { WorkflowExplorer, STAGES } from "../../features/home/WorkflowExplorer";

function Trigger() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.success("Saved", "All good")}>ok</button>
      <button onClick={() => toast.error("Failed")}>bad</button>
    </>
  );
}

describe("Toast", () => {
  it("announces success politely and clears it automatically", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      render(<ToastProvider><Trigger /></ToastProvider>);
      await userEvent.click(screen.getByText("ok"));
      expect(screen.getByRole("status")).toHaveTextContent("Saved");
      act(() => { vi.advanceTimersByTime(5000); });
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    } finally { vi.useRealTimers(); }
  });

  it("keeps errors as alerts until dismissed", async () => {
    render(<ToastProvider><Trigger /></ToastProvider>);
    await userEvent.click(screen.getByText("bad"));
    expect(screen.getByRole("alert")).toHaveTextContent("Failed");
    await userEvent.click(screen.getByRole("button", { name: /Dismiss: Failed/ }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("is a harmless no-op without a provider", async () => {
    render(<Trigger />);
    await userEvent.click(screen.getByText("ok"));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("RefreshIndicator", () => {
  it("reports refreshing and disables the refresh button meanwhile", () => {
    const { rerender } = render(<RefreshIndicator refreshing updatedAt={Date.now()} onRefresh={() => {}} />);
    expect(screen.getByText("Refreshing…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh data" })).toBeDisabled();
    rerender(<RefreshIndicator refreshing={false} updatedAt={Date.now()} onRefresh={() => {}} />);
    expect(screen.getByText(/^Updated /)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh data" })).toBeEnabled();
  });

  it("says so plainly when a refresh failed but older data remains", () => {
    render(<RefreshIndicator refreshing={false} stale updatedAt={Date.now()} />);
    expect(screen.getByText(/Couldn't refresh/)).toBeInTheDocument();
  });
});

describe("InlineStatus and NextStep", () => {
  it("pairs state with text, and errors are alerts", () => {
    const { rerender } = render(<InlineStatus state="pending" pending="Saving…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Saving…");
    rerender(<InlineStatus state="error" error="Could not save" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not save");
  });

  it("renders a single suggested action with its context", () => {
    render(<NextStep context="Draft · no Version yet" title="Next: create a Version" action={<a href="/x">Go</a>}>Explain</NextStep>);
    const region = screen.getByRole("region", { name: "Suggested next step" });
    expect(region).toHaveTextContent("Draft · no Version yet");
    expect(region).toHaveTextContent("Next: create a Version");
    expect(screen.getByRole("link", { name: "Go" })).toBeInTheDocument();
  });
});

describe("Reveal", () => {
  it("renders content as visible when IntersectionObserver is unavailable", () => {
    render(<Reveal><p>content</p></Reveal>);
    expect(screen.getByText("content").parentElement).toHaveClass("is-in");
  });
});

describe("WorkflowExplorer", () => {
  const renderIt = () => render(<MemoryRouter><WorkflowExplorer /></MemoryRouter>);

  it("exposes every stage as a tab with the first selected", () => {
    renderIt();
    expect(screen.getAllByRole("tab")).toHaveLength(STAGES.length);
    expect(screen.getByRole("tab", { name: /Create/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Step 1 of 7");
  });

  it("moves between stages with arrow keys and click, wrapping at the ends", async () => {
    renderIt();
    screen.getByRole("tab", { name: /Create/ }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /Version/ })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: /Paper execute/ })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /Create/ })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("tab", { name: /Backtest/ }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent(/simulat/i);
  });

  it("never claims live trading, broker execution or returns", () => {
    const copy = STAGES.map(s => `${s.summary} ${s.you} ${s.get} ${s.boundary}`).join(" ");
    expect(copy).not.toMatch(/live (trading|execution|data)/i);
    expect(copy).not.toMatch(/%|guarantee|profit(able)? returns/i);
    expect(STAGES.find(s => s.id === "execute")?.boundary).toMatch(/no broker orders/i);
  });
});
