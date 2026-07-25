import { defineConfig, devices } from '@playwright/test';

const spikePort = 6190;
const dashboardPort = 3000;
const backendPort = 6185;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,
  use: {
    baseURL: `http://127.0.0.1:${dashboardPort}`,
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
  webServer: [
    {
      command: `uv run python ../tests/e2e/plugin_ui_test_server.py --backend-port ${backendPort} --spike-port ${spikePort}`,
      url: `http://127.0.0.1:${backendPort}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: `pnpm exec vite --host 127.0.0.1 --port ${dashboardPort} --strictPort`,
      url: `http://127.0.0.1:${dashboardPort}/auth/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
