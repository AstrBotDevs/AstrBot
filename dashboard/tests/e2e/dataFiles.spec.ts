import { expect, test } from '@playwright/test';

test.describe('runtime data file manager', () => {
  test.skip(({ browserName }) => browserName !== 'chromium');

  test('browses and edits a text file in the isolated runtime root', async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    await page.addInitScript(() => {
      localStorage.setItem('token', 'plugin-ui-e2e-dashboard-token');
      localStorage.setItem('user', 'plugin-ui-e2e');
      localStorage.setItem('astrbot-locale', 'en-US');
    });
    const entry = {
      name: 'notes.md',
      path: 'workspaces/notes.md',
      type: 'file',
      size: 5,
      modified_at: '2026-08-19T00:00:00Z',
      category: 'text',
      language: 'markdown',
      readable: true,
      writable: true,
      deletable: true,
      downloadable: true,
      protected: false,
    };
    await page.route('**/api/v1/data-files/tree*', async (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          message: '',
          data: { path: '', entries: [entry], truncated: false },
        }),
      }),
    );
    await page.route('**/api/v1/data-files/content/**', async (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(
          route.request().method() === 'GET'
            ? {
                status: 'ok',
                message: '',
                data: { ...entry, content: 'hello', etag: 'sha256:test' },
              }
            : {
                status: 'ok',
                message: '',
                data: { path: entry.path, etag: 'sha256:next', size: 5 },
              },
        ),
      }),
    );
    await page.goto('/#/data');
    await expect(
      page.getByRole('heading', { name: 'Data Files' }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: entry.path })).toBeVisible();
    await page.getByRole('button', { name: entry.path }).click();
    await expect(page.locator('.monaco-editor')).toBeVisible();
    expect(
      pageErrors.filter((message) => message.includes('UNKNOWN service')),
    ).toEqual([]);
  });
});
