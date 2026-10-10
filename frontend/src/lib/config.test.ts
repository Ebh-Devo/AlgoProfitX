import { parseAppEnvironment, validateApiBaseUrl } from "./config";
import environments from "../../environments.json";
// @ts-expect-error plain ESM build script without type declarations
import { checkEnvironment } from "../../scripts/check-environment.mjs";

const DEV_API = "https://algoprofitx-web-50045554365.development.catalystappsail.in/api/v1";
const PROD_API = "https://www.algoprofitx.com/api/v1";
const LEGACY_CROSS_ORIGIN_API = "https://api.algoprofitx.com/api/v1";
const allowed = (env: "development" | "production") => environments[env].allowedApiBaseUrls;
const STAGING_API = "https://api-staging.algoprofitx.com/api/v1";

describe("frontend API configuration (same-origin)", () => {
  it("accepts the same-origin Production API URL for a production build", () => {
    expect(validateApiBaseUrl(PROD_API, true, allowed("production"))).toBe(PROD_API);
    expect(validateApiBaseUrl(`${PROD_API}/`, true, allowed("production"))).toBe(PROD_API);
  });

  it("accepts the same-origin Development API URL for a development build", () => {
    expect(validateApiBaseUrl(DEV_API, true, allowed("development"))).toBe(DEV_API);
  });

  it("allows exactly one API URL per environment", () => {
    expect(environments.production.allowedApiBaseUrls).toEqual([PROD_API]);
    expect(environments.development.allowedApiBaseUrls).toEqual([DEV_API]);
  });

  it("never lets a production build target Development, or the reverse", () => {
    expect(() => validateApiBaseUrl(DEV_API, true, allowed("production"))).toThrow(/Production VITE_API_BASE_URL/);
    expect(() => validateApiBaseUrl(PROD_API, true, allowed("development"))).toThrow(/Production VITE_API_BASE_URL/);
  });

  it.each([LEGACY_CROSS_ORIGIN_API, STAGING_API])(
    "rejects cross-origin API URL %s in either environment",
    (url) => {
      expect(() => validateApiBaseUrl(url, true, allowed("production"))).toThrow(/Production VITE_API_BASE_URL/);
      expect(() => validateApiBaseUrl(url, true, allowed("development"))).toThrow(/Production VITE_API_BASE_URL/);
    },
  );

  it("requires a built bundle to declare its environment", () => {
    expect(() => validateApiBaseUrl(PROD_API, true)).toThrow(/target environment/);
    expect(() => validateApiBaseUrl(PROD_API, true, [])).toThrow(/target environment/);
    for (const bad of [undefined, "", "staging", "Production", "DEVELOPMENT"]) {
      expect(() => parseAppEnvironment(bad)).toThrow(/VITE_APP_ENV/);
    }
    expect(parseAppEnvironment("development")).toBe("development");
    expect(parseAppEnvironment("production")).toBe("production");
  });

  it.each([
    "http://localhost:8000/api/v1",
    "http://127.0.0.1:8000/api/v1",
    "http://www.algoprofitx.com/api/v1",
    "https://example.com/api/v1",
    "https://www.algoprofitx.com.evil.example/api/v1",
    "https://algoprofitx-web-50045554365.catalystappsail.in/api/v1",
  ])("rejects unsafe API target %s in either environment", (value) => {
    expect(() => validateApiBaseUrl(value, true, allowed("production"))).toThrow(/Production VITE_API_BASE_URL/);
    expect(() => validateApiBaseUrl(value, true, allowed("development"))).toThrow(/Production VITE_API_BASE_URL/);
  });

  it("keeps localhost development valid", () => {
    expect(validateApiBaseUrl("http://127.0.0.1:8000/api/v1", false)).toBe("http://127.0.0.1:8000/api/v1");
  });

  it("rejects browser-visible URL credentials", () => {
    expect(() => validateApiBaseUrl("https://user:secret@www.algoprofitx.com/api/v1", false)).toThrow(/credentials/);
  });
});

describe("environment table", () => {
  it("uses exact HTTPS origins with no wildcards or credentials", () => {
    for (const env of Object.values(environments)) {
      const urls = [env.webOrigin, ...env.allowedApiBaseUrls, ...env.allowedUpstreamApiOrigins];
      for (const url of urls) {
        const parsed = new URL(url);
        expect(parsed.protocol).toBe("https:");
        expect(url).not.toContain("*");
        expect(parsed.username + parsed.password + parsed.search + parsed.hash).toBe("");
      }
    }
  });

  it("makes every allowed API URL same-origin with its web origin", () => {
    for (const env of Object.values(environments)) {
      for (const url of env.allowedApiBaseUrls) {
        expect(url).toBe(`${env.webOrigin}/api/v1`);
      }
    }
  });

  it("keeps Development and Production disjoint", () => {
    const dev = environments.development;
    const prod = environments.production;
    expect(dev.webOrigin).not.toBe(prod.webOrigin);
    expect(dev.allowedApiBaseUrls.some((url) => prod.allowedApiBaseUrls.includes(url))).toBe(false);
    expect(dev.allowedUpstreamApiOrigins.some((o) => prod.allowedUpstreamApiOrigins.includes(o))).toBe(false);
    expect(dev.allowedUpstreamApiOrigins.every((o) => o.includes(".development."))).toBe(true);
    expect(prod.allowedUpstreamApiOrigins.some((o) => o.includes(".development."))).toBe(false);
  });

  it("pins the verified Development and Production origins", () => {
    expect(environments.development.webOrigin).toBe("https://algoprofitx-web-50045554365.development.catalystappsail.in");
    expect(environments.development.allowedUpstreamApiOrigins).toEqual([
      "https://algoprofitx-api-50045554365.development.catalystappsail.in",
    ]);
    expect(environments.production.webOrigin).toBe("https://www.algoprofitx.com");
  });

  it("contains no credentials or tokens", () => {
    expect(JSON.stringify(environments)).not.toMatch(/token|secret|password|apikey/i);
  });
});

describe("build-time environment guard", () => {
  it("accepts matching environment and API URL", () => {
    expect(checkEnvironment("development", DEV_API)).toBeNull();
    expect(checkEnvironment("production", PROD_API)).toBeNull();
  });

  it("rejects mismatches and cross-origin URLs", () => {
    expect(checkEnvironment("production", DEV_API)).toMatch(/not approved for the production/);
    expect(checkEnvironment("development", PROD_API)).toMatch(/not approved for the development/);
    expect(checkEnvironment("production", LEGACY_CROSS_ORIGIN_API)).toMatch(/not approved/);
  });

  it.each([undefined, "", "staging", "toString", "__proto__"])("rejects unknown environment %s", (value) => {
    expect(checkEnvironment(value, PROD_API)).toMatch(/VITE_APP_ENV/);
  });
});
