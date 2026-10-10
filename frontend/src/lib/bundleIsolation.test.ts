import environments from "../../environments.json";
import { forbiddenStrings, inspectContents } from "../../scripts/verify-bundle-isolation.mjs";

const DEV_API = environments.development.allowedApiBaseUrls[0];
const PROD_API = environments.production.allowedApiBaseUrls[0];
const js = (...parts: string[]): Array<[string, string]> => [["assets/index.js", parts.join(" ")]];

describe("bundle isolation inspection", () => {
  it("accepts a bundle carrying only its own approved API URL", () => {
    expect(inspectContents("production", js(PROD_API))).toEqual([]);
    expect(inspectContents("development", js(DEV_API))).toEqual([]);
  });

  it("rejects the other environment's origin or API URL", () => {
    expect(inspectContents("production", js(PROD_API, DEV_API)).length).toBeGreaterThan(0);
    expect(inspectContents("production", js(PROD_API, environments.development.webOrigin)).length).toBeGreaterThan(0);
    expect(inspectContents("development", js(DEV_API, PROD_API)).length).toBeGreaterThan(0);
    expect(inspectContents("development", js(DEV_API, environments.production.webOrigin)).length).toBeGreaterThan(0);
  });

  it("never allows an API upstream origin in a browser bundle", () => {
    for (const [name, env] of Object.entries(environments)) {
      for (const upstream of env.allowedUpstreamApiOrigins) {
        const own = name === "production" ? PROD_API : DEV_API;
        expect(inspectContents(name, js(own, upstream)).length).toBeGreaterThan(0);
      }
    }
  });

  it("rejects retired hosting origins and the legacy _headers file", () => {
    expect(inspectContents("production", js(PROD_API, "https://api-staging.algoprofitx.com")).length).toBeGreaterThan(0);
    const files: Array<[string, string]> = [...js(PROD_API), ["dist/_headers", "/*"]];
    expect(inspectContents("production", files)).toContain("legacy Cloudflare _headers file is present in the bundle");
  });

  it("requires the approved API URL to actually be present", () => {
    expect(inspectContents("production", js("nothing here")).join(" ")).toMatch(/does not contain/);
  });

  it("derives the forbidden set from the table without self-conflicts", () => {
    for (const name of Object.keys(environments)) {
      const own = environments[name as keyof typeof environments];
      const forbidden = forbiddenStrings(name);
      expect(forbidden).not.toContain(own.webOrigin);
      expect(forbidden.some((value: string) => own.allowedApiBaseUrls.includes(value))).toBe(false);
    }
  });
});
