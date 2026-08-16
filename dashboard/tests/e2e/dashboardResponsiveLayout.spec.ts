import { expect, test } from '@playwright/test';

const dashboardOrigin = `http://127.0.0.1:${
  process.env.ASTRBOT_E2E_DASHBOARD_PORT ?? '3000'
}`;
const dashboardToken = 'plugin-ui-e2e-dashboard-token';

const viewports = [
  ['desktop-wide', { width: 1920, height: 1080 }],
  ['desktop', { width: 1440, height: 960 }],
  ['laptop', { width: 1280, height: 720 }],
  ['tablet-landscape', { width: 1024, height: 768 }],
  ['tablet-portrait', { width: 768, height: 1024 }],
  ['phone', { width: 390, height: 844 }],
  ['phone-narrow', { width: 360, height: 800 }],
  ['4k-ultra-hd-television', { width: 3840, height: 2160 }],
  ['1080p-full-hd-television', { width: 1920, height: 1080 }],
  ['laptop-with-hidpi-screen', { width: 1440, height: 900 }],
  ['laptop-with-mdpi-screen', { width: 1280, height: 800 }],
  ['laptop-with-touch', { width: 1280, height: 950 }],
  ['720p-hd-television', { width: 1280, height: 720 }],
  ['ipad-pro-13-inch-m4', { width: 1032, height: 1376 }],
  ['ipad-pro-12-9-inch-old', { width: 1024, height: 1366 }],
  ['galaxy-tab-s9-ultra', { width: 960, height: 1848 }],
  ['ipad-pro-11-inch-m4', { width: 834, height: 1210 }],
  ['ipad-pro-11-inch-old', { width: 834, height: 1194 }],
  ['ipad-10th-11th-gen', { width: 820, height: 1180 }],
  ['ipad', { width: 810, height: 1080 }],
  ['galaxy-tab-s9', { width: 800, height: 1280 }],
  ['ipad-mini', { width: 768, height: 1024 }],
  ['ipad-mini-6th-gen', { width: 744, height: 1133 }],
  ['galaxy-tab-s9-1138', { width: 712, height: 1138 }],
  ['iphone-16-pro-max', { width: 440, height: 956 }],
  ['iphone-14-15-16-plus', { width: 430, height: 932 }],
  ['iphone-12-13-pro-max', { width: 428, height: 926 }],
  ['iphone-air', { width: 420, height: 921 }],
  ['iphone-11-pro-max', { width: 414, height: 896 }],
  ['galaxy-note-9', { width: 414, height: 846 }],
  ['pixel-8-9-chrome', { width: 412, height: 915 }],
  ['iphone-15-16-pro', { width: 402, height: 874 }],
  ['iphone-14-15-16', { width: 393, height: 852 }],
  ['pixel-5', { width: 393, height: 851 }],
  ['iphone-12-13-pro', { width: 390, height: 844 }],
  ['galaxy-s25', { width: 384, height: 854 }],
  ['iphone-12-13-mini', { width: 375, height: 812 }],
  ['iphone-se', { width: 375, height: 667 }],
  ['galaxy-s25-780', { width: 360, height: 780 }],
  ['galaxy-s20', { width: 360, height: 800 }],
  ['galaxy-s9-s9', { width: 360, height: 740 }],
  ['galaxy-s10-s10', { width: 360, height: 760 }],
] as const;

const dashboardPages = [
  ['welcome', '/welcome'],
  ['platforms', '/platforms'],
  ['providers', '/providers'],
  ['config', '/config'],
  ['extensions', '/extension'],
  ['knowledge-base', '/knowledge-base'],
  ['chat', '/chat'],
] as const;

type Bounds = {
  bottom: number;
  height: number;
  left: number;
  right: number;
  top: number;
  width: number;
};

type LayoutMetrics = {
  blurredControls: string[];
  coveredControls: string[];
  documentWidth: number;
  landmarks: Record<string, Bounds | null>;
  viewport: { height: number; width: number };
};

async function layoutMetrics(
  page: import('@playwright/test').Page,
): Promise<LayoutMetrics> {
  return page.evaluate(() => {
    const isVisible = (element: HTMLElement) => {
      const rect = element.getBoundingClientRect();
      if (rect.width <= 1 || rect.height <= 1) return false;

      let current: HTMLElement | null = element;
      while (current) {
        const style = window.getComputedStyle(current);
        if (
          style.display === 'none' ||
          style.visibility === 'hidden' ||
          Number(style.opacity) === 0
        ) {
          return false;
        }
        if (current !== element) {
          const clipsX = ['hidden', 'clip', 'scroll', 'auto'].includes(
            style.overflowX,
          );
          const clipsY = ['hidden', 'clip', 'scroll', 'auto'].includes(
            style.overflowY,
          );
          const clip = current.getBoundingClientRect();
          if (
            (clipsX && (rect.right <= clip.left || rect.left >= clip.right)) ||
            (clipsY && (rect.bottom <= clip.top || rect.top >= clip.bottom))
          ) {
            return false;
          }
        }
        current = current.parentElement;
      }
      return true;
    };
    const bounds = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element || !isVisible(element)) return null;

      const rect = element.getBoundingClientRect();
      return {
        bottom: rect.bottom,
        height: rect.height,
        left: rect.left,
        right: rect.right,
        top: rect.top,
        width: rect.width,
      };
    };
    const label = (element: HTMLElement) =>
      element.getAttribute('aria-label') ||
      element.textContent?.trim().replaceAll(/\s+/g, ' ').slice(0, 80) ||
      element.tagName.toLowerCase();
    const ancestors = (element: HTMLElement) => {
      const chain: HTMLElement[] = [];
      let current: HTMLElement | null = element;
      while (current) {
        chain.push(current);
        current = current.parentElement;
      }
      return chain;
    };
    const controlOwner = (element: Element) =>
      element.closest(
        'button, a[href], input, select, textarea, [role="button"], [role="tab"], .v-list-item',
      );
    const isFullyWithinScrollport = (element: HTMLElement) => {
      const rect = element.getBoundingClientRect();
      let current = element.parentElement;
      while (current) {
        const style = window.getComputedStyle(current);
        const clipsX = ['hidden', 'clip', 'scroll', 'auto'].includes(
          style.overflowX,
        );
        const clipsY = ['hidden', 'clip', 'scroll', 'auto'].includes(
          style.overflowY,
        );
        if (clipsX || clipsY) {
          const clip = current.getBoundingClientRect();
          if (
            (clipsX &&
              (rect.left < clip.left - 1 || rect.right > clip.right + 1)) ||
            (clipsY &&
              (rect.top < clip.top - 1 || rect.bottom > clip.bottom + 1))
          ) {
            return false;
          }
        }
        current = current.parentElement;
      }
      return true;
    };
    const controls = Array.from(
      document.querySelectorAll<HTMLElement>(
        'button, a[href], input, select, textarea, [role="button"], [role="tab"]',
      ),
    ).filter(isVisible);
    const coveredControls: string[] = [];
    const blurredControls: string[] = [];

    for (const control of controls) {
      const rect = control.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      if (
        centerX < 0 ||
        centerX >= window.innerWidth ||
        centerY < 0 ||
        centerY >= window.innerHeight
      ) {
        continue;
      }

      const topElement = document.elementFromPoint(centerX, centerY);
      const isInteractive =
        !control.matches(':disabled') &&
        control.getAttribute('aria-disabled') !== 'true' &&
        window.getComputedStyle(control).pointerEvents !== 'none';
      if (
        isInteractive &&
        isFullyWithinScrollport(control) &&
        topElement &&
        topElement !== control &&
        !control.contains(topElement) &&
        controlOwner(topElement) !== controlOwner(control)
      ) {
        const topClass =
          topElement instanceof HTMLElement
            ? topElement.classList[0]
            : undefined;
        const topLabel = `${topElement.tagName.toLowerCase()}${
          topClass ? `.${topClass}` : ''
        }`;
        coveredControls.push(`${label(control)} <- ${topLabel}`);
      }

      const hasBlurFilter = ancestors(control).some((element) =>
        window.getComputedStyle(element).filter.includes('blur('),
      );
      if (hasBlurFilter) blurredControls.push(label(control));
    }

    const sidebar = document.querySelector<HTMLElement>('.leftSidebar');
    const sidebarIsOpen =
      sidebar?.classList.contains('v-navigation-drawer--active') ?? false;
    return {
      blurredControls,
      coveredControls,
      documentWidth: Math.max(
        document.documentElement.scrollWidth,
        document.body.scrollWidth,
      ),
      landmarks: {
        header: bounds('.top-header'),
        main: bounds('.dashboard-main'),
        page: bounds('.page-wrapper'),
        sidebar: sidebarIsOpen ? bounds('.leftSidebar') : null,
      },
      viewport: { height: window.innerHeight, width: window.innerWidth },
    };
  });
}

function expectWithinViewport(
  bounds: Bounds,
  viewport: { height: number; width: number },
  name: string,
) {
  expect(bounds.width, `${name} must have width`).toBeGreaterThan(1);
  expect(bounds.height, `${name} must have height`).toBeGreaterThan(1);
  expect(
    bounds.left,
    `${name} must not start outside the viewport`,
  ).toBeGreaterThanOrEqual(-1);
  expect(
    bounds.right,
    `${name} must not overflow horizontally`,
  ).toBeLessThanOrEqual(viewport.width + 1);
  expect(
    bounds.top,
    `${name} must not start above the viewport`,
  ).toBeGreaterThanOrEqual(-1);
}

test.describe('Dashboard responsive layout', () => {
  test('keeps core pages visible, sharp, and unobscured at standard resolutions', async ({
    browser,
    browserName,
  }) => {
    test.setTimeout(600_000);
    test.skip(
      browserName !== 'chromium',
      'Layout geometry is covered in Chromium.',
    );

    const context = await browser.newContext();
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
    const page = await context.newPage();
    await page.addInitScript((token) => {
      localStorage.setItem('themeMode', 'light');
      localStorage.setItem('token', token);
      localStorage.setItem('user', 'responsive-layout');
      localStorage.setItem('astrbot-locale', 'zh-CN');
    }, dashboardToken);

    try {
      for (const [viewportName, viewport] of viewports) {
        await page.setViewportSize(viewport);

        for (const [pageName, route] of dashboardPages) {
          await page.goto(`${dashboardOrigin}/#${route}`, {
            waitUntil: 'domcontentloaded',
          });
          await expect(page.locator('.top-header')).toBeVisible();
          await page.evaluate(async () => {
            await document.fonts.ready;
          });
          await page.waitForTimeout(500);

          const metrics = await layoutMetrics(page);
          const label = `${viewportName}/${pageName}`;
          expect(
            metrics.documentWidth,
            `${label} must not create horizontal page overflow`,
          ).toBeLessThanOrEqual(metrics.viewport.width + 1);
          expect(
            metrics.landmarks.header,
            `${label} header must be visible`,
          ).not.toBeNull();
          expect(
            metrics.landmarks.main,
            `${label} main area must be visible`,
          ).not.toBeNull();
          expect(
            metrics.landmarks.page,
            `${label} page content must be visible`,
          ).not.toBeNull();

          expectWithinViewport(
            metrics.landmarks.header!,
            metrics.viewport,
            `${label} header`,
          );
          expectWithinViewport(
            metrics.landmarks.main!,
            metrics.viewport,
            `${label} main area`,
          );
          expectWithinViewport(
            metrics.landmarks.page!,
            metrics.viewport,
            `${label} page content`,
          );
          if (metrics.landmarks.sidebar) {
            expectWithinViewport(
              metrics.landmarks.sidebar,
              metrics.viewport,
              `${label} navigation drawer`,
            );
            expect(
              metrics.landmarks.sidebar.right,
              `${label} drawer must not cover page content`,
            ).toBeLessThanOrEqual(metrics.landmarks.page!.left + 1);
          }
          expect(
            metrics.coveredControls,
            `${label} controls must not be covered by another element`,
          ).toEqual([]);
          expect(
            metrics.blurredControls,
            `${label} controls must not have a blur filter`,
          ).toEqual([]);
        }
      }
    } finally {
      await context.close();
    }
  });
});
