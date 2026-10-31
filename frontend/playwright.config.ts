import { defineConfig } from "@playwright/test";

// Expects the backend on :8000 and the Vite dev server on :5173 (see README "Run locally").
// Set E2E_START_SERVERS=1 to have Playwright start both for you.
const start = process.env.E2E_START_SERVERS === "1";
// A browser test clicks through the app in seconds from one IP; raise the per-IP limits for it.
const E2E_LIMITS = { RATE_LIMIT_DEFAULT_PER_MINUTE: "5000", RATE_LIMIT_UPLOAD_PER_MINUTE: "500", RATE_LIMIT_AI_PER_MINUTE: "500",
  RATE_LIMIT_AUTH_PER_MINUTE: "500", RATE_LIMIT_GUEST_CREATE_PER_HOUR: "5000" };

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5173", screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: start
    ? [
        { command: "cd ../backend && .venv/bin/python -m app.cli init && .venv/bin/uvicorn app.main:app --port 8000", env: E2E_LIMITS, url: "http://localhost:8000/health", reuseExistingServer: true, timeout: 120_000 },
        { command: "npx vite --port 5173", url: "http://localhost:5173", reuseExistingServer: true, timeout: 120_000 },
      ]
    : undefined,
});
