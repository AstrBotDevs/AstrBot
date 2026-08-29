import { expect, test } from '@playwright/test';

test('an unauthenticated user is redirected to the login form before entering the dashboard', async ({
  page,
  browserName,
}) => {
  test.skip(
    browserName !== 'chromium',
    'Normal authentication flow is covered in Chromium.',
  );

  await page.goto('/#/dashboard');

  await expect(page).toHaveURL(/#\/auth\/login$/);
  const loginForm = page.locator('.login-form');
  await expect(loginForm).toBeVisible();

  const inputs = loginForm.locator('input');
  await inputs.nth(0).fill('astrbot');
  await inputs.nth(1).fill('not-a-real-password');
  await expect(loginForm.locator('.login-btn')).toBeEnabled();
});
