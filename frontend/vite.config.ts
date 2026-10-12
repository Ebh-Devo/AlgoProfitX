import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { allowedApiBaseUrlsFor, environmentBuildPlugin } from "./scripts/allowed-api-urls.mjs";

export default defineConfig(({ mode, command }) => {
  const appEnv = loadEnv(mode, ".", "VITE_").VITE_APP_ENV ?? undefined;
  return {
  plugins: [react(), ...(command === "build" ? [environmentBuildPlugin(appEnv)] : [])],
  build: { sourcemap: false },
  define: {
    // Only this environment's approved API URL(s) enter the bundle; a missing/unknown VITE_APP_ENV
    // fails the build instead of guessing.
    __ALLOWED_API_BASE_URLS__: JSON.stringify(
      command === "build" ? allowedApiBaseUrlsFor(appEnv) : [],
    ),
    ...(mode === "test"
      ? {
          "import.meta.env.VITE_API_BASE_URL": JSON.stringify("http://api.test/api/v1"),
          "import.meta.env.PROD": JSON.stringify(false),
        }
      : {}),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
};
});
