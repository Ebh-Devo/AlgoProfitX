import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define:
    mode === "test"
      ? {
          "import.meta.env.VITE_API_BASE_URL": JSON.stringify(
            "http://api.test/api/v1",
          ),
        }
      : {},
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
}));
