import { expect, test } from '@playwright/test';

const dashboardOrigin = `http://127.0.0.1:${
  process.env.ASTRBOT_E2E_DASHBOARD_PORT ?? '3000'
}`;
const dashboardPages = [
  ['welcome', '/welcome'],
  ['platforms', '/platforms'],
  ['providers', '/providers'],
  ['config', '/config'],
  ['extensions', '/extension'],
  ['knowledge-base', '/knowledge-base'],
  ['chat', '/chat'],
] as const;
const viewports = [
  ['desktop', { width: 1440, height: 960 }],
  ['mobile', { width: 390, height: 844 }],
] as const;
const dashboardToken = 'plugin-ui-e2e-dashboard-token';

async function captureBaseline({
  browser,
  viewport,
  themeMode,
  route,
  snapshotName,
  authenticated,
}: {
  browser: import('@playwright/test').Browser;
  viewport: { width: number; height: number };
  themeMode: 'light' | 'dark';
  route: string;
  snapshotName: string;
  authenticated: boolean;
}) {
  const context = await browser.newContext({ viewport });
  if (authenticated) {
    await context.addCookies([
      {
        name: 'astrbot_dashboard_jwt',
        value: dashboardToken,
        domain: '127.0.0.1',
        path: '/api/v1',
        httpOnly: true,
        sameSite: 'Strict',
        secure: false,
      },
    ]);
  }

  const page = await context.newPage();
  await page.addInitScript(
    ({ mode, token }) => {
      localStorage.setItem('themeMode', mode);
      if (token) {
        localStorage.setItem('token', token);
        localStorage.setItem('user', 'visual-baseline');
        localStorage.setItem('astrbot-locale', 'zh-CN');
      }
    },
    { mode: themeMode, token: authenticated ? dashboardToken : null },
  );

  try {
    await page.goto(`${dashboardOrigin}/#${route}`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(
      page.locator(authenticated ? '.top-header' : '.auth-card'),
    ).toBeVisible();
    await page.waitForTimeout(200);
    await expect(page).toHaveScreenshot(snapshotName, {
      animations: 'disabled',
      fullPage: false,
      caret: 'hide',
      maxDiffPixelRatio: 0.02,
    });
  } finally {
    await context.close();
  }
}

test.describe('Dashboard visual baselines', () => {
  test('keeps primary operational pages stable in light and dark modes', async ({
    browser,
    browserName,
  }) => {
    test.setTimeout(180_000);
    test.skip(browserName !== 'chromium', 'Visual baseline uses Chromium.');

    for (const [viewportName, viewport] of viewports) {
      for (const themeMode of ['light', 'dark'] as const) {
        await captureBaseline({
          browser,
          viewport,
          themeMode,
          route: '/auth/login',
          snapshotName: `login-${themeMode}-${viewportName}.png`,
          authenticated: false,
        });

        for (const [name, route] of dashboardPages) {
          await captureBaseline({
            browser,
            viewport,
            themeMode,
            route,
            snapshotName: `${name}-${themeMode}-${viewportName}.png`,
            authenticated: true,
          });
        }
      }
    }
  });
});
