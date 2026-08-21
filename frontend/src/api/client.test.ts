import { apiRequest, ApiError } from "./client";
import { getSession, saveSession } from "../auth/session";

describe("typed API client", () => {
  it("clears the session when the API returns 401", async () => {
    saveSession({ accessToken: "private-token" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Invalid authentication credentials" }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    )));

    await expect(apiRequest("/auth/me")).rejects.toMatchObject({
      status: 401,
      message: "Invalid authentication credentials",
    });
    expect(getSession()).toBeNull();
  });

  it("normalizes FastAPI validation details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: [{ loc: ["body", "email"], msg: "value is not a valid email address" }],
    }), { status: 422, headers: { "Content-Type": "application/json" } })));

    await expect(apiRequest("/auth/register", { method: "POST" })).rejects.toMatchObject({
      status: 422,
      message: "Please correct the highlighted fields.",
      fieldErrors: [{ path: "email", message: "value is not a valid email address" }],
    });
  });
});
