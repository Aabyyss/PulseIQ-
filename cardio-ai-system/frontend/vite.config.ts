/// <reference types="vitest/config" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src")
    }
  },
  // Unit tests (`npm run test`) cover the logic that no other check reaches:
  // extraction patterns, session/retry behaviour, request shaping and PDF
  // layout. jsdom is the environment because the session layer touches
  // localStorage and the PDF writer measures text through the DOM API.
  test: {
    environment: "jsdom",
    // An explicit non-opaque origin: without one jsdom refuses storage access, and
    // the session tests would be exercising a missing `localStorage` instead of
    // the code that writes to it.
    environmentOptions: { jsdom: { url: "http://localhost:5173" } },
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["./src/test-setup.ts"],
    restoreMocks: true
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (incomingPath) => incomingPath.replace(/^\/api/, "")
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true
      }
    }
  }
});
