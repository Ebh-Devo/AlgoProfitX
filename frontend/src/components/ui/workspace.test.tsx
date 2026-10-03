import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { useState } from "react";

import { ActionMenu, ActivityFeed, ConfirmDialog, FilterChips, StatusBadge, relativeTime } from ".";
import { ErrorPanel } from "../PageState";

describe("ActionMenu", () => {
  const setup = (onSelect = vi.fn()) =>
    render(
      <MemoryRouter>
        <ActionMenu
          label="Actions for Alpha"
          items={[
            { label: "Open details", to: "/x" },
            { label: "Archive", onSelect },
            { label: "Delete", onSelect, tone: "danger" },
          ]}
        />
      </MemoryRouter>,
    );

  it("exposes menu semantics and moves focus into the menu on open", async () => {
    setup();
    const trigger = screen.getByRole("button", { name: "Actions for Alpha" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menu", { name: "Actions for Alpha" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Open details" })).toHaveFocus();
  });

  it("supports arrow keys and closes with Escape, restoring focus to the trigger", async () => {
    setup();
    const trigger = screen.getByRole("button", { name: "Actions for Alpha" });
    await userEvent.click(trigger);
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(screen.getByRole("menuitem", { name: "Archive" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "End" });
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("runs the selected action and closes", async () => {
    const onSelect = vi.fn();
    setup(onSelect);
    await userEvent.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Archive" }));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("ConfirmDialog", () => {
  function Harness({ onConfirm }: { onConfirm: () => void }) {
    const [open, setOpen] = useState(true);
    return (
      <ConfirmDialog open={open} title="Delete it?" confirmLabel="Delete permanently" onConfirm={onConfirm} onCancel={() => setOpen(false)}>
        <p>This cannot be undone.</p>
      </ConfirmDialog>
    );
  }

  it("names the dialog, lists Cancel before the destructive action, and only confirms on click", async () => {
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);
    const dialog = screen.getByRole("dialog", { name: "Delete it?" });
    const buttons = dialog.querySelectorAll("button");
    expect(buttons[0]).toHaveTextContent("Cancel");
    expect(buttons[1]).toHaveTextContent("Delete permanently");
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("disables both actions and shows the pending label while pending", () => {
    render(
      <ConfirmDialog open title="Archive?" confirmLabel="Confirm archive" pendingLabel="Archiving…" pending onConfirm={vi.fn()} onCancel={vi.fn()}>
        body
      </ConfirmDialog>,
    );
    expect(screen.getByRole("button", { name: "Archiving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("surfaces an error inside the dialog as an alert", () => {
    render(
      <ConfirmDialog open title="Delete?" confirmLabel="Delete" error="Strategy is in use" onConfirm={vi.fn()} onCancel={vi.fn()}>
        body
      </ConfirmDialog>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Strategy is in use");
  });
});

describe("FilterChips", () => {
  it("marks the selected option with aria-pressed and reports changes", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips label="Filter by status" value="all" onChange={onChange} options={[{ value: "all", label: "All", count: 3 }, { value: "draft", label: "Draft", count: 1 }]} />,
    );
    expect(screen.getByRole("group", { name: "Filter by status" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^All/ })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: /^Draft/ }));
    expect(onChange).toHaveBeenCalledWith("draft");
  });
});

describe("StatusBadge", () => {
  it("always renders the status as text, not just colour or icon", () => {
    render(<>{["draft", "published", "deployed", "archived", "running", "failed"].map(s => <StatusBadge key={s} status={s} />)}</>);
    for (const s of ["draft", "published", "deployed", "archived", "running", "failed"]) {
      expect(screen.getByText(s)).toBeInTheDocument();
    }
  });
});

describe("ActivityFeed", () => {
  it("renders an ordered list with machine-readable times", () => {
    render(<ActivityFeed label="Recent activity" entries={[{ id: "1", icon: null, title: "Published Alpha", at: "2026-01-01T00:00:00Z" }]} />);
    const list = screen.getByRole("list", { name: "Recent activity" });
    expect(list.tagName).toBe("OL");
    expect(list.querySelector("time")).toHaveAttribute("datetime", "2026-01-01T00:00:00Z");
  });

  it("formats relative time", () => {
    const now = Date.parse("2026-06-10T12:00:00Z");
    expect(relativeTime("2026-06-10T11:59:40Z", now)).toBe("Just now");
    expect(relativeTime("2026-06-10T11:30:00Z", now)).toBe("30m ago");
    expect(relativeTime("2026-06-10T07:00:00Z", now)).toBe("5h ago");
    expect(relativeTime("2026-06-08T12:00:00Z", now)).toBe("2d ago");
    expect(relativeTime("2026-05-01T12:00:00Z", now)).toBe("1mo ago");
  });
});

describe("ErrorPanel", () => {
  it("is an alert with a retry control", async () => {
    const onRetry = vi.fn();
    render(<ErrorPanel title="Strategies unavailable" onRetry={onRetry}>Try again later.</ErrorPanel>);
    expect(screen.getByRole("alert")).toHaveTextContent("Strategies unavailable");
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
