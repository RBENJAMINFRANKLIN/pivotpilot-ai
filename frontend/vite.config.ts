/// <reference types="vitest" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

// The dev server proxies /api to the FastAPI backend, so the session cookie is first-party.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_PROXY ?? "http://localhost:8000", changeOrigin: true } },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], globals: true, css: false, include: ["src/**/*.test.{ts,tsx}"] },
});
