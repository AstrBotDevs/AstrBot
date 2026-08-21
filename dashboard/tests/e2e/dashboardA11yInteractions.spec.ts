import { expect, test } from '@playwright/test';

test.describe('Dashboard keyboard and responsive interactions', () => {
  test.skip(({ browserName }) => browserName !== 'chromium');

  test('menu and dialog activators preserve keyboard focus on Escape', async ({
    page,
  }) => {
    await page.route('**/api/v1/stats/versions', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          message: '',
          data: {
            webui_version: '4.1.0',
            astrbot_version: '4.0.0',
            astrbot_code_version: '4.0.0',
          },
        }),
      });
    });

    await page.goto('/#/auth/login');
    const themeToggle = page.locator('.auth-appearance-menu__toggle');
    await expect(themeToggle).toBeVisible();

    await themeToggle.focus();
    await page.keyboard.press('Tab');
    await themeToggle.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.auth-appearance-menu__card')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.auth-appearance-menu__card')).toBeHidden();
    await expect(themeToggle).toBeFocused();

    const dialogActivator = page.locator('.version-help-btn');
    await expect(dialogActivator).toBeVisible();
    await dialogActivator.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.version-dialog-card')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.version-dialog-card')).toBeHidden();
    await expect(dialogActivator).toBeFocused();
  });

  test('the navigation drawer opens from the mobile application bar', async ({
    page,
  }) => {
    await page.context().addCookies([
      {
        name: 'astrbot_dashboard_jwt',
        value: 'plugin-ui-e2e-dashboard-token',
        domain: '127.0.0.1',
        path: '/api/v1',
        httpOnly: true,
        sameSite: 'Strict',
        secure: false,
      },
    ]);
    await page.addInitScript(() => {
      localStorage.setItem('token', 'plugin-ui-e2e-dashboard-token');
      localStorage.setItem('user', 'a11y-e2e');
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/#/platforms', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/#\/platforms/);
    const header = page.getByRole('banner');
    await expect(header).toBeVisible({ timeout: 15_000 });

    const menuButton = header.getByRole('button').first();
    await expect(menuButton).toBeVisible();
    await menuButton.click();
    await expect(page.locator('.leftSidebar')).toHaveClass(
      /v-navigation-drawer--active/,
    );
  });

  test('keeps the remaining sidebar footer actions in the desktop drawer viewport', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.setItem('token', 'plugin-ui-e2e-dashboard-token');
      localStorage.setItem('user', 'a11y-e2e');
    });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto('/#/platforms', { waitUntil: 'domcontentloaded' });

    const footerActions = page.locator('.leftSidebar .sidebar-footer-btn');
    await expect(footerActions).toHaveCount(3);
    for (let index = 0; index < 3; index += 1) {
      await expect(footerActions.nth(index)).toBeInViewport();
    }

    const footerMetrics = await footerActions.evaluateAll((actions) =>
      actions.map((action) => {
        const icon = action.querySelector('.v-icon');
        return {
          fontSize: getComputedStyle(action).fontSize,
          height: action.clientHeight,
          iconFontSize: icon ? getComputedStyle(icon).fontSize : null,
          width: action.clientWidth,
        };
      }),
    );
    expect(footerMetrics).toHaveLength(3);
    expect(footerMetrics[1]).toEqual(footerMetrics[0]);
    expect(footerMetrics[2]).toEqual(footerMetrics[0]);
  });

  test('keeps changelog and update dialogs opaque over Dashboard content', async ({
    page,
  }, testInfo) => {
    testInfo.setTimeout(60_000);
    await page.addInitScript(() => {
      localStorage.setItem('token', 'plugin-ui-e2e-dashboard-token');
      localStorage.setItem('user', 'a11y-e2e');
      localStorage.setItem('astrbot-locale', 'zh-CN');
    });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto('/#/platforms', { waitUntil: 'domcontentloaded' });
    const header = page.getByRole('banner');
    await expect(header).toBeVisible();
    const application = page.locator('.v-application');
    await application.evaluate((element) => {
      element.classList.add('dashboard-appearance-active');
      element.style.setProperty('--dashboard-surface-opacity', '0.35');
    });
    await expect(application).toHaveClass(/dashboard-appearance-active/);

    const footerActions = page.locator('.leftSidebar .sidebar-footer-btn');
    await footerActions.nth(1).click();
    const changelogDialog = page.locator(
      '.v-overlay__content > .changelog-dialog',
    );
    await expect(changelogDialog).toBeVisible();
    expect(
      await changelogDialog.evaluate(
        (element) => getComputedStyle(element).backgroundColor,
      ),
    ).not.toMatch(/^rgba\(/);

    await page.keyboard.press('Escape');
    await expect(changelogDialog).toBeHidden();

    await header.getByRole('button').last().click();
    await page.getByText('更新 AstrBot', { exact: true }).click();
    const updateDialog = page.locator(
      '.v-overlay__content > .update-status-dialog',
    );
    await expect(updateDialog).toBeVisible();
    expect(
      await updateDialog.evaluate(
        (element) => getComputedStyle(element).backgroundColor,
      ),
    ).not.toMatch(/^rgba\(/);
  });
});
