import components from "./components.css?raw";
import research from "./research.css?raw";

/** Numeric figures use the site sans font with tabular numerals; mono is reserved for code and identifiers. */
const rule = (css: string, selector: string) => {
  const start = css.indexOf(selector);
  expect(start, `${selector} should exist`).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf("}", start));
};

describe("numeric typography", () => {
  it.each([
    [research, ".rs-metric strong"],
    [components, ".data-table .num"],
    [components, ".badge-financial"],
    [components, ".stat-value"],
  ])("%#: %s stays on the sans font with tabular numerals", (css, selector) => {
    const body = rule(css, selector);
    expect(body).not.toMatch(/font-mono|monospace/);
    expect(body).toMatch(/tabular-nums/);
  });
});
