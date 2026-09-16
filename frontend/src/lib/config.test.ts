import { validateApiBaseUrl } from "./config";

describe("frontend API configuration", () => {
  it("accepts the canonical production API URL", () => {
    expect(validateApiBaseUrl("https://api.algoprofitx.com/api/v1", true)).toBe("https://api.algoprofitx.com/api/v1");
  });

  it("accepts the same-origin production API proxy", () => {
    expect(validateApiBaseUrl("https://www.algoprofitx.com/api/v1", true)).toBe("https://www.algoprofitx.com/api/v1");
  });

  it("accepts the approved staging API URL in a production build", () => {
    expect(validateApiBaseUrl("https://api-staging.algoprofitx.com/api/v1", true)).toBe("https://api-staging.algoprofitx.com/api/v1");
  });

  it.each([
    "http://localhost:8000/api/v1",
    "http://127.0.0.1:8000/api/v1",
    "http://api.algoprofitx.com/api/v1",
    "https://example.com/api/v1",
  ])("rejects unsafe production API target %s", (value) => {
    expect(() => validateApiBaseUrl(value, true)).toThrow(/Production VITE_API_BASE_URL/);
  });

  it("keeps localhost development valid", () => {
    expect(validateApiBaseUrl("http://127.0.0.1:8000/api/v1", false)).toBe("http://127.0.0.1:8000/api/v1");
  });

  it("rejects browser-visible URL credentials", () => {
    expect(() => validateApiBaseUrl("https://user:secret@api.algoprofitx.com/api/v1", false)).toThrow(/credentials/);
  });
});
