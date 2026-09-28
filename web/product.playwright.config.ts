import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./product-e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 420000,
  expect: { timeout: 20000 },
  reporter: [["list"]],
  outputDir: ".artifacts/product-test-results",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.QUANTGRAPH_PRODUCT_URL || "http://127.0.0.1:8785",
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    screenshot: "off",
  },
});
