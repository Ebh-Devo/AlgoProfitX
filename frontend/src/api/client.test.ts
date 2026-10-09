import { apiRequest } from "./client";
import { clearSession, getAccessToken, setAccessToken } from "../auth/session";

describe("authenticated API client", () => {
  it("refreshes and retries a 401 exactly once", async () => {
    setAccessToken("expired");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "expired" }), { status: 401, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "renewed" }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "user" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest<{ id: string }>("/protected")).resolves.toEqual({ id: "user" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getAccessToken()).toBe("renewed");
  });

  it("does not loop when refresh fails", async () => {
    setAccessToken("expired");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiRequest("/protected")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getAccessToken()).toBeNull();
  });

  it("deduplicates concurrent refresh requests", async () => {
    setAccessToken("expired");
    let protectedCalls = 0;
    let refreshCalls = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        await Promise.resolve();
        return new Response(JSON.stringify({ access_token: "renewed" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      protectedCalls += 1;
      return protectedCalls <= 2
        ? new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    await Promise.all([apiRequest("/one"), apiRequest("/two")]);
    expect(refreshCalls).toBe(1);
  });

  it("normalizes FastAPI validation details", async () => {
    clearSession();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: [{ loc: ["body", "email"], msg: "value is not a valid email address" }],
    }), { status: 422, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/auth/register", { method: "POST" })).rejects.toMatchObject({
      status: 422, message: "Please correct the highlighted fields.",
    });
  });

  it("sanitizes unexpected server details and surfaces only the request reference", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: "SQL password=private and stack trace",
      request_id: "request-support-123",
    }), { status: 500, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/broken", {}, false)).rejects.toMatchObject({
      status: 500,
      message: "An unexpected server error occurred. Reference: request-support-123",
      requestId: "request-support-123",
    });
  });

  it("sends refresh credentials and the readable CSRF token", async () => {
    document.cookie = "algoprofitx_csrf=csrf-safe; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: "memory-only" }), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await import("./client").then(({ refreshAccessToken }) => refreshAccessToken());
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/auth/refresh"), expect.objectContaining({
      credentials: "include",
      headers: { "X-CSRF-Token": "csrf-safe" },
    }));
    expect(window.sessionStorage.length).toBe(0);
  });

  it("keeps the structured code, message and issues of an object-shaped error detail", async () => {
    const issue = { path: "rules[0]", code: "capability_missing", message: "needs op.increase", severity: "error", layer: "capability" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: "strategy_definition_not_runnable", message: "Not runnable", issues: [issue, { nonsense: true }] } }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    )));
    await expect(apiRequest("/strategies/s/versions/v2", { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 422, message: "Not runnable", code: "strategy_definition_not_runnable", issues: [issue],
    });
  });

  it("shows the message of an object detail without issues and still handles string and list details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: "strategy_definition_version_unsupported_for_execution", message: "V2 can be backtested only." } }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    )));
    await expect(apiRequest("/strategies/s/publish", { method: "POST" })).rejects.toMatchObject({
      message: "V2 can be backtested only.", code: "strategy_definition_version_unsupported_for_execution", issues: [],
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "plain" }), { status: 400, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/x")).rejects.toMatchObject({ message: "plain", issues: [] });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ loc: ["body", "name"], msg: "bad" }] }), { status: 422, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/x")).rejects.toMatchObject({ fieldErrors: [{ path: "name", message: "bad" }] });
  });
});
