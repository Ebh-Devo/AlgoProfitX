// Build-time guard: fails the image build when the target environment and the
// API base URL disagree, so a bundle can never be built for the wrong backend.
import environments from "../environments.json" with { type: "json" };

export function checkEnvironment(appEnv, apiBaseUrl) {
  if (!Object.hasOwn(environments, appEnv ?? "")) {
    return `VITE_APP_ENV must be one of ${Object.keys(environments).join(", ")} (got '${appEnv ?? ""}')`;
  }
  const normalized = (apiBaseUrl ?? "").replace(/\/$/, "");
  if (!environments[appEnv].allowedApiBaseUrls.includes(normalized)) {
    return `VITE_API_BASE_URL '${normalized}' is not approved for the ${appEnv} environment`;
  }
  return null;
}

if (process.argv[1]?.endsWith("check-environment.mjs")) {
  const error = checkEnvironment(process.env.VITE_APP_ENV, process.env.VITE_API_BASE_URL);
  if (error) {
    console.error(`::error::${error}`);
    process.exit(1);
  }
  console.log(`Environment check passed for ${process.env.VITE_APP_ENV}.`);
}
