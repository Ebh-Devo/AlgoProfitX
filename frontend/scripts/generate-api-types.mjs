import { spawnSync } from "node:child_process";

const openApiUrl = process.env.OPENAPI_URL ?? "http://127.0.0.1:8000/openapi.json";
const pnpmCommand = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const result = spawnSync(
  pnpmCommand,
  ["exec", "openapi-typescript", openApiUrl, "-o", "src/api/generated/openapi.ts"],
  { stdio: "inherit", shell: process.platform === "win32" },
);

if (result.error) throw result.error;
process.exit(result.status ?? 1);
