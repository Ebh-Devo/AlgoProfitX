import { clearSession, getSession, saveSession } from "./session";

describe("browser session storage", () => {
  it("stores an access token for the current browser session only", () => {
    saveSession({ accessToken: "test-token" });
    expect(getSession()).toEqual({ accessToken: "test-token" });
    expect(window.localStorage.getItem("algoprofitx.auth.session")).toBeNull();
  });

  it("reads a legacy branded session without logging out existing users", () => {
    window.sessionStorage.setItem("tradeebh.auth.session", JSON.stringify({ accessToken: "legacy-token" }));
    expect(getSession()).toEqual({ accessToken: "legacy-token" });
    clearSession();
  });

  it("clears the local session", () => {
    saveSession({ accessToken: "test-token" });
    clearSession();
    expect(getSession()).toBeNull();
  });
});
