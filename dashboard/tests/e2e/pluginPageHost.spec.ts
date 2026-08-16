import { expect, request as requestFactory, test } from '@playwright/test';

const dashboardOrigin = `http://127.0.0.1:${
  process.env.ASTRBOT_E2E_DASHBOARD_PORT ?? '3000'
}`;
const dashboardToken = 'plugin-ui-e2e-dashboard-token';

async function authenticate(page: import('@playwright/test').Page) {
  await page.context().addCookies([
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
  await page.addInitScript((token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', 'plugin-ui-e2e');
    localStorage.setItem('astrbot-locale', 'en-US');
  }, dashboardToken);
}

async function openPluginPageFromDetail(page: import('@playwright/test').Page) {
  await authenticate(page);
  await page.goto(`${dashboardOrigin}/#/extension/astrbot_plugin_palette`);
  await expect(page.getByTestId('plugin-component-group-page')).toContainText(
    'Pages',
  );
  await expect(
    page.getByText('Palette Settings', { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId('plugin-component-group-hook')).toHaveCount(0);
  await page.getByTestId('open-plugin-page-settings').click();
  await expect(page).toHaveURL(
    /#\/extension\/io\.github\.example\.palette\/pages\/settings$/,
  );
  const frame = page.frameLocator('[data-testid="plugin-page-frame"]');
  await expect(
    frame.getByRole('heading', { name: 'Palette Settings' }),
  ).toBeVisible();
  return frame;
}

test('Plugin Page Host isolates the iframe and completes the Action and file flows', async ({
  page,
}) => {
  const frame = await openPluginPageFromDetail(page);
  const iframe = page.getByTestId('plugin-page-frame');
  await expect(iframe).toHaveAttribute('sandbox', 'allow-scripts');
  await expect(iframe).not.toHaveAttribute('sandbox', /allow-same-origin/);
  await expect(iframe).toHaveAttribute('referrerpolicy', 'no-referrer');
  await expect(iframe).toHaveAttribute('allow', '');

  await expect(frame.getByTestId('page-security')).toContainText(
    'parent-blocked',
  );
  await expect(frame.getByTestId('page-security')).toContainText(
    'storage-blocked',
  );
  await expect(frame.getByTestId('page-security')).toContainText(
    'cookie-blocked',
  );
  await expect(frame.getByTestId('page-security')).toContainText('api-blocked');
  await expect(frame.getByTestId('page-context')).toHaveText(
    'en-US:light:generation-1',
  );

  await frame.getByTestId('invoke-json').click();
  await expect(frame.getByTestId('action-result')).toHaveText(
    '{"enabled":true,"source":"e2e"}',
  );
  await frame.getByTestId('invoke-error').click();
  await expect(frame.getByTestId('action-result')).toHaveText(
    'invalid_request',
  );

  await frame.getByTestId('upload-file').setInputFiles({
    name: 'palette.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
      'base64',
    ),
  });
  await expect(frame.getByTestId('action-result')).toHaveText(
    '{"uploaded":true}',
  );

  await frame.getByTestId('preview-file').click();
  await expect(frame.getByTestId('action-result')).toHaveText('palette.png');
  await expect(frame.getByTestId('preview-image')).toHaveAttribute(
    'src',
    /^blob:/,
  );

  const downloadPromise = page.waitForEvent('download');
  await frame.getByTestId('download-file').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('palette.png');

  await page.reload();
  await expect(
    page
      .frameLocator('[data-testid="plugin-page-frame"]')
      .getByRole('heading', {
        name: 'Palette Settings',
      }),
  ).toBeVisible();
});

test('raw Page and File handles require their exact HttpOnly cookies while bundles stay public', async ({
  page,
}) => {
  const viteDeepLink = await page.request.get(
    '/extension/io.github.example.palette/pages/settings',
  );
  expect(viteDeepLink.ok()).toBeTruthy();
  expect(await viteDeepLink.text()).toContain('id="app"');

  await openPluginPageFromDetail(page);
  const anonymous = await requestFactory.newContext({
    baseURL: dashboardOrigin,
  });
  try {
    const shell = await anonymous.get(
      '/api/plugin-pages/v1/sessions/host-session/',
    );
    expect(shell.status()).toBe(401);
    const inlineFile = await anonymous.get(
      '/api/plugin-files/v1/inline-ticket',
    );
    expect(inlineFile.status()).toBe(401);

    const bundle = await anonymous.get(
      `/api/plugin-pages/v1/bundles/${'a'.repeat(64)}/app.js`,
      { headers: { Origin: 'null' } },
    );
    expect(bundle.ok()).toBeTruthy();
    const bundleText = await bundle.text();
    expect(bundleText).not.toContain(dashboardToken);
    expect(bundleText).not.toContain('plugin-ui-e2e');

    const credentialedBundle = await anonymous.get(
      `/api/plugin-pages/v1/bundles/${'a'.repeat(64)}/app.js`,
      { headers: { Cookie: 'astrbot_plugin_page=leaked' } },
    );
    expect(credentialedBundle.status()).toBe(403);
  } finally {
    await anonymous.dispose();
  }
});

test('unexpected iframe navigation and logout destroy the Page instance', async ({
  page,
}) => {
  const frame = await openPluginPageFromDetail(page);
  await page.route('https://example.com/**', (route) => route.abort());
  await frame.getByTestId('navigate-external').click();
  await expect(page.getByTestId('plugin-page-frame')).toHaveCount(0);
  await expect(page.getByTestId('plugin-page-error')).toContainText(
    'secure container',
  );

  await page.reload();
  await expect(
    page
      .frameLocator('[data-testid="plugin-page-frame"]')
      .getByRole('heading', {
        name: 'Palette Settings',
      }),
  ).toBeVisible();
  await page.context().clearCookies();
  await page
    .frameLocator('[data-testid="plugin-page-frame"]')
    .getByTestId('invoke-json')
    .click();
  await expect(page).toHaveURL(/#\/auth\/login$/);
  await expect(page.getByTestId('plugin-page-frame')).toHaveCount(0);
});
