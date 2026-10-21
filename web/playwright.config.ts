import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "app",
      testIgnore: /auth\.setup\.ts/,
      dependencies: ["setup"],
      use: { storageState: "e2e/.auth.json" },
    },
  ],
  use: { baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5173", viewport: { width: 390, height: 844 } },
  webServer: process.env.E2E_NO_SERVER
    ? undefined
    : {
        command: "npm run preview -- --host 127.0.0.1 --port 5173",
        url: "http://127.0.0.1:5173",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
