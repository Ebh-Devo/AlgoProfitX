import {
  contentSecurityPolicyFor,
  productionCachePolicy,
  productionSecurityHeaders,
} from "./productionSecurityPolicy";

describe("production browser security contract", () => {
  it("keeps scripts strict and API connectivity explicit", () => {
    const csp = productionSecurityHeaders["Content-Security-Policy"];
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("connect-src 'self' https://api.algoprofitx.com;");
    expect(csp).toContain("style-src 'self' 'unsafe-inline'");
    expect(csp).not.toContain("script-src 'unsafe-inline'");
    expect(csp).not.toContain("'unsafe-eval'");
    expect(csp).not.toContain("catalystappsail");
  });

  it("limits the Development CSP to the exact Development API origin", () => {
    const csp = contentSecurityPolicyFor("development");
    expect(csp).toContain(
      "connect-src 'self' https://algoprofitx-api-50045554365.development.catalystappsail.in;",
    );
    expect(csp).not.toContain("api.algoprofitx.com");
    expect(csp).not.toContain("*");
    expect(csp).not.toContain("script-src 'unsafe-inline'");
    expect(csp).not.toContain("'unsafe-eval'");
  });

  it("defines hardened transport and cache behavior", () => {
    expect(productionSecurityHeaders["Strict-Transport-Security"]).toBe("max-age=31536000");
    expect(productionSecurityHeaders["Strict-Transport-Security"]).not.toContain("preload");
    expect(productionSecurityHeaders["X-Content-Type-Options"]).toBe("nosniff");
    expect(productionCachePolicy.hashedAssets).toContain("immutable");
    expect(productionCachePolicy.html).toContain("must-revalidate");
  });
});
