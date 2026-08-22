import { clearSession, getSession, saveSession } from "./session";

describe("browser session storage", () => {
  it("stores an access token for the current browser session only", () => {
    saveSession({ accessToken: "test-token" });
    expect(getSession()).toEqual({ accessToken: "test-token" });
    expect(window.localStorage.getItem("tradeebh.auth.session")).toBeNull();
  });

  it("clears the local session", () => {
    saveSession({ accessToken: "test-token" });
    clearSession();
    expect(getSession()).toBeNull();
  });
});
