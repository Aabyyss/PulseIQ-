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
