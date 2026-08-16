import { defineConfig, devices } from '@playwright/test';

const spikePort = Number(process.env.ASTRBOT_E2E_SPIKE_PORT ?? 6190);
const dashboardPort = Number(process.env.ASTRBOT_E2E_DASHBOARD_PORT ?? 3000);
const backendPort = Number(process.env.ASTRBOT_E2E_BACKEND_PORT ?? 6185);
const useIsolatedPorts = [
  'ASTRBOT_E2E_SPIKE_PORT',
  'ASTRBOT_E2E_DASHBOARD_PORT',
  'ASTRBOT_E2E_BACKEND_PORT',
].some((name) => process.env[name] !== undefined);
const reuseExistingServer = !process.env.CI && !useIsolatedPorts;

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
      command: `uv run python ../tests/e2e/plugin_ui_test_server.py --backend-port ${backendPort} --spike-port ${spikePort} --dashboard-port ${dashboardPort}`,
      url: `http://127.0.0.1:${backendPort}/health`,
      reuseExistingServer,
      timeout: 30_000,
    },
    {
      command: `pnpm exec vite --host 127.0.0.1 --port ${dashboardPort} --strictPort`,
      url: `http://127.0.0.1:${dashboardPort}/auth/login`,
      env: {
        ASTRBOT_DASHBOARD_API_PORT: String(backendPort),
      },
      reuseExistingServer,
      timeout: 60_000,
    },
  ],
});
