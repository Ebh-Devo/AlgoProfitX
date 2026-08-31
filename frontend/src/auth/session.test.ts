import { clearSession, getAccessToken, setAccessToken } from "./session";

describe("in-memory browser session", () => {
  it("never stores new access tokens in browser storage", () => {
    setAccessToken("test-token");
    expect(getAccessToken()).toBe("test-token");
    expect(window.sessionStorage.length).toBe(0);
    expect(window.localStorage.length).toBe(0);
  });

  it("removes current and legacy persisted sessions", () => {
    window.sessionStorage.setItem("algoprofitx.auth.session", "old");
    window.sessionStorage.setItem("tradeebh.auth.session", "legacy");
    setAccessToken("memory-token");
    expect(window.sessionStorage.length).toBe(0);
  });

  it("clears the in-memory session", () => {
    setAccessToken("test-token"); clearSession();
    expect(getAccessToken()).toBeNull();
  });
});
