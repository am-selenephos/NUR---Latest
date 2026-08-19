import { defineConfig, devices } from "@playwright/test";

// One consistent origin for the whole flow: the browser loads the REAL
// production build from `vite preview` on :4173, and the API must be started
// with WEB_ORIGIN=http://localhost:4173 so CORS matches (see ci.yml `e2e`).
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:4173",
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium-desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "chromium-mobile", use: { ...devices["Pixel 5"] } },
    { name: "webkit-mobile", use: { ...devices["iPhone 13"] } },
    { name: "webkit-tablet", use: { ...devices["iPad (gen 7)"] } },
    { name: "webkit-desktop", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: {
    command: "npm run build && npm run preview -- --port 4173 --strictPort",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      VITE_API_BASE_URL: process.env.VITE_API_BASE_URL ?? "http://localhost:8000",
      VITE_NUR_ENABLE_OMEGA_RESEARCH: process.env.VITE_NUR_ENABLE_OMEGA_RESEARCH ?? "true",
      NUR_ENABLE_OMEGA_RESEARCH: process.env.NUR_ENABLE_OMEGA_RESEARCH ?? "true",
    },
  },
});
