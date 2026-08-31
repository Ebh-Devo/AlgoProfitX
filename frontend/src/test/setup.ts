import "@testing-library/jest-dom/vitest";

afterEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
  document.cookie = "algoprofitx_csrf=; Max-Age=0; Path=/";
  vi.restoreAllMocks();
});
