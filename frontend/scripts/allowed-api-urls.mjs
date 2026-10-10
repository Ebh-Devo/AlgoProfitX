// Build-time lookup used by vite.config.ts: a bundle receives only its own environment's approved
// API base URL(s), never the other environments' origins.
import { readFileSync, rmSync } from "node:fs";
import { join } from "node:path";

const table = JSON.parse(readFileSync(new URL("../environments.json", import.meta.url), "utf8"));

export function allowedApiBaseUrlsFor(appEnv) {
  if (!appEnv || !Object.hasOwn(table, appEnv)) {
    throw new Error(`VITE_APP_ENV must be one of ${Object.keys(table).join(", ")} to build (got '${appEnv ?? ""}')`);
  }
  return [...table[appEnv].allowedApiBaseUrls];
}

export function webOriginFor(appEnv) {
  allowedApiBaseUrlsFor(appEnv); // validates the environment name
  return table[appEnv].webOrigin;
}

/**
 * Vite plugin: stamps this environment's own web origin into index.html (no other origin appears in
 * the page) and keeps the legacy Cloudflare Pages `_headers` file (which names a staging API origin and
 * is not used by the Catalyst web server) out of every build output.
 */
export function environmentBuildPlugin(appEnv) {
  const origin = webOriginFor(appEnv);
  let outDir = "dist";
  return {
    name: "algoprofitx-environment-build",
    apply: "build",
    configResolved(config) {
      outDir = config.build.outDir;
    },
    transformIndexHtml(html) {
      return html.replaceAll("__WEB_ORIGIN__", origin);
    },
    writeBundle(options) {
      rmSync(join(options.dir ?? outDir, "_headers"), { force: true });
    },
  };
}
