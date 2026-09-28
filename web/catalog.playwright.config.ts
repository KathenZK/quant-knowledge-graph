import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./catalog-e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 180000,
  expect: { timeout: 15000 },
  reporter: [["list"]],
  outputDir: ".artifacts/catalog-test-results",
  use: {
    baseURL: "http://127.0.0.1:8787",
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    screenshot: "off",
  },
  webServer: {
    command: "cd .. && .venv/bin/python -m scripts.catalog_e2e_server",
    url: "http://127.0.0.1:8787/healthz",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
