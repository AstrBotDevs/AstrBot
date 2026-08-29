import { expect, test } from '@playwright/test';

const dashboardPort = process.env.ASTRBOT_E2E_DASHBOARD_PORT ?? '3000';

const project = {
  project_id: 'project-1',
  title: 'Planning',
  emoji: 'P',
  created_at: '2026-08-04T12:00:00Z',
  updated_at: '2026-08-04T12:00:00Z',
};

const sessions = Array.from({ length: 120 }, (_, index) => ({
  session_id: `session-${index}`,
  display_name: `Session ${index}`,
  platform_id: 'webchat',
  created_at: '2026-08-04T12:00:00Z',
  updated_at: '2026-08-04T12:00:00Z',
}));

test('keeps the project composer visible with more than one hundred sessions', async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== 'chromium', 'Covered once in Chromium.');

  await page.addInitScript(() => {
    localStorage.setItem('token', 'project-composer-e2e');
  });
  await page.route(
    new RegExp(`^http://127\\.0\\.0\\.1:${dashboardPort}/api/v1(?:/|$)`),
    async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = {};
      if (path === '/api/v1/chat/projects') data = [project];
      if (path === '/api/v1/chat/projects/project-1/sessions') data = sessions;
      if (path === '/api/v1/chat/sessions') data = [];
      if (path === '/api/v1/providers/type/chat_completion') {
        data = [];
      }
      if (path === '/api/v1/commands') {
        data = {
          items: [],
          command_prefixes: ['/'],
          llm_access: { prefixes: ['/'] },
        };
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', message: null, data }),
      });
    },
  );

  await page.goto('/#/chat');
  await page.locator('.project-btn').click();
  await page.locator('button.project-item', { hasText: 'Planning' }).click();

  const sessionsList = page.locator('.project-sessions-list');
  const composer = page.locator('.project-composer-shell');
  await expect(sessionsList.locator('.project-session-item')).toHaveCount(120);
  await expect(sessionsList).toHaveCSS('overflow-y', 'auto');
  await expect(composer).toBeVisible();
});
