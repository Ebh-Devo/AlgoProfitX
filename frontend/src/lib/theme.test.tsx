import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AccountMenu } from "../components/layout/AccountMenu";
import { ThemeProvider, useTheme } from "../components/theme/ThemeProvider";
import { ThemeCycleButton, ThemeSelector } from "../components/theme/ThemeSelector";
import { THEME_STORAGE_KEY, readStoredPreference, resolveTheme } from "./theme";

type Listener = () => void;

/** Controllable prefers-color-scheme: dark media query. */
function mockSystem(initialDark: boolean) {
  let dark = initialDark;
  const listeners = new Set<Listener>();
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    get matches() { return query.includes("dark") ? dark : !dark; },
    media: query,
    addEventListener: (_: string, l: Listener) => listeners.add(l),
    removeEventListener: (_: string, l: Listener) => listeners.delete(l),
  })) as unknown as typeof window.matchMedia;
  return { setDark(next: boolean) { dark = next; listeners.forEach(l => l()); } };
}

const theme = () => document.documentElement.dataset.theme;

function Probe() {
  const { preference, resolved } = useTheme();
  return <output data-testid="probe">{preference}/{resolved}</output>;
}

function renderApp() {
  return render(<ThemeProvider><Probe /><ThemeSelector /><ThemeCycleButton /></ThemeProvider>);
}

beforeEach(() => { document.documentElement.removeAttribute("data-theme"); mockSystem(true); });

describe("theme preference", () => {
  it("defaults to dark when nothing is stored", () => {
    renderApp();
    expect(screen.getByTestId("probe")).toHaveTextContent("dark/dark");
    expect(theme()).toBe("dark");
  });

  it("falls back to dark for an invalid stored value", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "neon");
    expect(readStoredPreference()).toBe("dark");
  });

  it("applies an explicit Light and Dark regardless of the OS", () => {
    mockSystem(true);
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    const { unmount } = renderApp();
    expect(theme()).toBe("light");
    unmount();
    mockSystem(false);
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderApp();
    expect(theme()).toBe("dark");
  });

  it("follows the OS in System mode, live", () => {
    const system = mockSystem(false);
    window.localStorage.setItem(THEME_STORAGE_KEY, "system");
    renderApp();
    expect(theme()).toBe("light");
    act(() => system.setDark(true));
    expect(theme()).toBe("dark");
    expect(screen.getByTestId("probe")).toHaveTextContent("system/dark");
    expect(resolveTheme("system")).toBe("dark");
  });

  it("switches live and persists the choice", () => {
    renderApp();
    fireEvent.click(screen.getByRole("radio", { name: /light/i }));
    expect(theme()).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    fireEvent.click(screen.getByRole("radio", { name: /dark/i }));
    expect(theme()).toBe("dark");
    fireEvent.click(screen.getByRole("radio", { name: /system/i }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("system");
    expect(screen.getByRole("radio", { name: /system/i })).toHaveAttribute("aria-checked", "true");
  });

  it("survives a remount (reload) with the stored preference", () => {
    const first = renderApp();
    fireEvent.click(screen.getByRole("radio", { name: /light/i }));
    first.unmount();
    document.documentElement.removeAttribute("data-theme");
    renderApp();
    expect(theme()).toBe("light");
    expect(screen.getByRole("radio", { name: /light/i })).toHaveAttribute("aria-checked", "true");
  });

  it("cycles System → Light → Dark from the compact button", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "system");
    renderApp();
    const button = () => screen.getByRole("button", { name: /^theme:/i });
    expect(button()).toHaveAccessibleName("Theme: System. Switch to Light");
    fireEvent.click(button());
    expect(theme()).toBe("light");
    fireEvent.click(button());
    expect(screen.getByTestId("probe")).toHaveTextContent("dark/dark");
  });

  it("syncs a preference changed in another tab", () => {
    renderApp();
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    fireEvent(window, new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "light" }));
    expect(theme()).toBe("light");
  });
});

describe("account menu appearance", () => {
  it("offers System, Light and Dark and applies the choice", () => {
    render(<MemoryRouter><ThemeProvider><AccountMenu email="a@b.co" roles={[]} onLogout={vi.fn()} /></ThemeProvider></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: /account menu/i }));
    expect(screen.getAllByRole("menuitemradio").map(r => r.textContent?.replace("✓", "").trim())).toEqual(["System", "Light", "Dark"]);
    expect(screen.getByRole("menuitemradio", { name: /dark/i })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("menuitemradio", { name: /light/i }));
    expect(theme()).toBe("light");
    expect(screen.getByRole("menuitemradio", { name: /light/i })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });
});
