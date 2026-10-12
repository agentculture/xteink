import { defineConfig, devices } from "@playwright/test";

// End-to-end flows against a running `docker compose up` stack.
// Env: XTEINK_E2E_URL (main app, default http://127.0.0.1:18780),
//      XTEINK_E2E_DEVICE_URL (device app, default http://127.0.0.1:18781),
//      XTEINK_E2E_KEY (a seeded API key; required, see e2e/global-setup.ts).
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  globalSetup: "./e2e/global-setup.ts",
  // One worker: every spec shares the server's library and device list.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  outputDir: "./e2e/.results",
  use: {
    baseURL: process.env.XTEINK_E2E_URL ?? "http://127.0.0.1:18780",
    screenshot: "only-on-failure",
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
