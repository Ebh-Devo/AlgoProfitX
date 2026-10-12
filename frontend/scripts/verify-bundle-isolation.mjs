// Inspect a built bundle: it may contain only its own environment's approved API URL, and no other
// environment's origin or any API upstream origin (the browser only ever talks to its web origin).
//   node scripts/verify-bundle-isolation.mjs <development|production> [distDir]
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import environments from "../environments.json" with { type: "json" };

// Origins from retired hosting plans that must never ship in any Catalyst bundle.
const LEGACY_ORIGINS = ["https://api-staging.algoprofitx.com", "https://staging.algoprofitx.com"];

export function forbiddenStrings(appEnv, table = environments) {
  const own = table[appEnv];
  const ownAllowed = new Set([own.webOrigin, ...own.allowedApiBaseUrls]);
  const forbidden = new Set(LEGACY_ORIGINS);
  for (const [name, env] of Object.entries(table)) {
    // Upstream API origins are server-side only, for every environment including this one.
    for (const origin of env.allowedUpstreamApiOrigins) forbidden.add(origin);
    if (name === appEnv) continue;
    for (const value of [env.webOrigin, ...env.allowedApiBaseUrls]) {
      if (!ownAllowed.has(value)) forbidden.add(value);
    }
  }
  return [...forbidden].filter((value) => !ownAllowed.has(value));
}

export function inspectContents(appEnv, files, table = environments) {
  const problems = [];
  for (const [name, text] of files) {
    for (const needle of forbiddenStrings(appEnv, table)) {
      if (text.includes(needle)) problems.push(`${name} contains '${needle}'`);
    }
  }
  if (files.some(([name]) => /(^|[\/])_headers$/.test(name))) {
    problems.push("legacy Cloudflare _headers file is present in the bundle");
  }
  const own = table[appEnv].allowedApiBaseUrls;
  const js = files.filter(([name]) => name.endsWith(".js"));
  if (!own.every((url) => js.some(([, text]) => text.includes(url)))) {
    problems.push(`bundle does not contain this environment's approved API URL (${own.join(", ")})`);
  }
  return problems;
}

function readTree(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) files.push(...readTree(path));
    else if (/\.(js|css|html|json|map|webmanifest|txt)$|^_headers$/.test(entry)) files.push([path, readFileSync(path, "utf8")]);
  }
  return files;
}

if (process.argv[1]?.endsWith("verify-bundle-isolation.mjs")) {
  const [appEnv, directory = "dist"] = process.argv.slice(2);
  if (!Object.hasOwn(environments, appEnv ?? "")) {
    console.error(`::error::usage: verify-bundle-isolation.mjs <${Object.keys(environments).join("|")}> [distDir]`);
    process.exit(2);
  }
  const problems = inspectContents(appEnv, readTree(directory));
  if (problems.length) {
    for (const problem of problems) console.error(`::error::${problem}`);
    process.exit(1);
  }
  console.log(`Bundle isolation verified for ${appEnv} (${directory}).`);
}
