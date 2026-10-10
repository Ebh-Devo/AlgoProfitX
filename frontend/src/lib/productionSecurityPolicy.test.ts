import {
  contentSecurityPolicyFor,
  productionCachePolicy,
  productionSecurityHeaders,
} from "./productionSecurityPolicy";

describe("production browser security contract", () => {
  it("keeps scripts strict and connectivity same-origin only", () => {
    const csp = productionSecurityHeaders["Content-Security-Policy"];
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("connect-src 'self';");
    expect(csp).toContain("style-src 'self' 'unsafe-inline'");
    expect(csp).not.toContain("script-src 'unsafe-inline'");
    expect(csp).not.toContain("'unsafe-eval'");
    expect(csp).not.toContain("http");
    expect(csp).not.toContain("*");
  });

  it("gives Development the same restrictive policy without naming any origin", () => {
    expect(contentSecurityPolicyFor("development")).toBe(contentSecurityPolicyFor("production"));
    expect(contentSecurityPolicyFor("development")).not.toContain("catalystappsail");
  });

  it("has no policy for an unknown environment", () => {
    // @ts-expect-error deliberately outside the environment union
    expect(() => contentSecurityPolicyFor("staging")).toThrow(/Unknown environment/);
  });

  it("defines hardened transport and cache behavior", () => {
    expect(productionSecurityHeaders["Strict-Transport-Security"]).toBe("max-age=31536000");
    expect(productionSecurityHeaders["Strict-Transport-Security"]).not.toContain("preload");
    expect(productionSecurityHeaders["X-Content-Type-Options"]).toBe("nosniff");
    expect(productionCachePolicy.hashedAssets).toContain("immutable");
    expect(productionCachePolicy.html).toContain("must-revalidate");
  });
});
