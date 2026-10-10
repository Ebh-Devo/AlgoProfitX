import { parseAppEnvironment, validateApiBaseUrl } from "./config";
import environments from "../../environments.json";
// @ts-expect-error plain ESM build script without type declarations
import { checkEnvironment } from "../../scripts/check-environment.mjs";

const DEV_API = "https://algoprofitx-api-50045554365.development.catalystappsail.in/api/v1";
const PROD_API = "https://api.algoprofitx.com/api/v1";
const STAGING_API = "https://api-staging.algoprofitx.com/api/v1";

describe("frontend API configuration", () => {
  it("accepts the canonical production API URL for a production build", () => {
    expect(validateApiBaseUrl(PROD_API, true, "production")).toBe(PROD_API);
  });

  it("allows exactly one Production API URL", () => {
    expect(environments.production.allowedApiBaseUrls).toEqual([PROD_API]);
  });

  it("rejects the Development and staging API URLs in a production build", () => {
    for (const url of [DEV_API, STAGING_API]) {
      expect(() => validateApiBaseUrl(url, true, "production")).toThrow(/Production VITE_API_BASE_URL/);
    }
    expect(checkEnvironment("production", STAGING_API)).toMatch(/not approved for the production/);
    expect(checkEnvironment("production", DEV_API)).toMatch(/not approved for the production/);
  });

  it("rejects the staging API URL in a development build", () => {
    expect(() => validateApiBaseUrl(STAGING_API, true, "development")).toThrow(/Production VITE_API_BASE_URL/);
  });

  it("accepts the Development API URL for a development build", () => {
    expect(validateApiBaseUrl(DEV_API, true, "development")).toBe(DEV_API);
    expect(validateApiBaseUrl(`${DEV_API}/`, true, "development")).toBe(DEV_API);
  });

  it("never lets a production build target Development", () => {
    expect(() => validateApiBaseUrl(DEV_API, true, "production")).toThrow(/Production VITE_API_BASE_URL/);
  });

  it("never lets a development build target Production", () => {
    expect(() => validateApiBaseUrl(PROD_API, true, "development")).toThrow(/Production VITE_API_BASE_URL/);
  });

  it("requires a built bundle to declare its environment", () => {
    expect(() => validateApiBaseUrl(PROD_API, true)).toThrow(/target environment/);
    for (const bad of [undefined, "", "staging", "Production", "DEVELOPMENT"]) {
      expect(() => parseAppEnvironment(bad)).toThrow(/VITE_APP_ENV/);
    }
    expect(parseAppEnvironment("development")).toBe("development");
    expect(parseAppEnvironment("production")).toBe("production");
  });

  it.each([
    "http://localhost:8000/api/v1",
    "http://127.0.0.1:8000/api/v1",
    "http://api.algoprofitx.com/api/v1",
    "https://example.com/api/v1",
    "https://algoprofitx-api-50045554365.catalystappsail.in/api/v1",
    "https://algoprofitx-api-50045554365.development.catalystappsail.in.evil.example/api/v1",
  ])("rejects unsafe API target %s in either environment", (value) => {
    expect(() => validateApiBaseUrl(value, true, "production")).toThrow(/Production VITE_API_BASE_URL/);
    expect(() => validateApiBaseUrl(value, true, "development")).toThrow(/Production VITE_API_BASE_URL/);
  });

  it("keeps localhost development valid", () => {
    expect(validateApiBaseUrl("http://127.0.0.1:8000/api/v1", false)).toBe("http://127.0.0.1:8000/api/v1");
  });

  it("rejects browser-visible URL credentials", () => {
    expect(() => validateApiBaseUrl("https://user:secret@api.algoprofitx.com/api/v1", false)).toThrow(/credentials/);
  });
});

describe("environment table", () => {
  it("uses exact HTTPS origins with no wildcards or credentials", () => {
    for (const env of Object.values(environments)) {
      for (const url of [env.frontendOrigin, env.apiOrigin, ...env.allowedApiBaseUrls]) {
        const parsed = new URL(url);
        expect(parsed.protocol).toBe("https:");
        expect(url).not.toContain("*");
        expect(parsed.username + parsed.password + parsed.search + parsed.hash).toBe("");
      }
    }
  });

  it("keeps Development and Production allow-lists disjoint", () => {
    const dev = new Set(environments.development.allowedApiBaseUrls);
    expect(environments.production.allowedApiBaseUrls.some((url) => dev.has(url))).toBe(false);
    expect(environments.development.apiOrigin).not.toBe(environments.production.apiOrigin);
  });

  it("pins the verified Development AppSail origins and the Production domains", () => {
    expect(environments.development.apiOrigin).toBe("https://algoprofitx-api-50045554365.development.catalystappsail.in");
    expect(environments.development.frontendOrigin).toBe("https://algoprofitx-web-50045554365.development.catalystappsail.in");
    expect(environments.production.apiOrigin).toBe("https://api.algoprofitx.com");
    expect(environments.production.allowedApiBaseUrls).toContain(PROD_API);
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

  it("rejects mismatches in both directions", () => {
    expect(checkEnvironment("production", DEV_API)).toMatch(/not approved for the production/);
    expect(checkEnvironment("development", PROD_API)).toMatch(/not approved for the development/);
  });

  it.each([undefined, "", "staging", "toString", "__proto__"])("rejects unknown environment %s", (value) => {
    expect(checkEnvironment(value, PROD_API)).toMatch(/VITE_APP_ENV/);
  });
});
