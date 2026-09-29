import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "personal.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: [["list"]],
  outputDir: "../.artifacts/acceptance/personal-browser-results",
  use: {
    baseURL: "http://127.0.0.1:8792",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 1000 },
  },
  webServer: {
    command: "../.venv/bin/python e2e/serve_personal.py",
    url: "http://127.0.0.1:8792/health",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
