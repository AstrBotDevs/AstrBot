import { mount } from '@vue/test-utils';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import FloatingActionStack from '@/components/ui/FloatingActionStack.vue';
import {
  applyUserThemeColors,
  astrBotThemes,
  themeNames,
} from '@/design/theme';

const semanticRoles = [
  'primary',
  'secondary',
  'background',
  'surface',
  'surface-variant',
  'on-surface',
  'on-surface-variant',
  'outline',
  'outline-variant',
  'success',
  'warning',
  'error',
  'info',
];

describe('AstrBot theme system', () => {
  it('defines the required semantic roles in both themes', () => {
    for (const theme of Object.values(astrBotThemes)) {
      for (const role of semanticRoles) {
        expect(theme.colors?.[role]).toBeTruthy();
      }
    }
    expect(themeNames).toEqual({
      light: 'AstrBotLight',
      dark: 'AstrBotDark',
    });
  });

  it('applies user colors to the registry without legacy theme aliases', () => {
    const themes = structuredClone(astrBotThemes);
    applyUserThemeColors(themes, '#123456', '#654321');

    for (const name of Object.values(themeNames)) {
      expect(themes[name].colors?.primary).toBe('#123456');
      expect(themes[name].colors?.secondary).toBe('#654321');
    }
    expect(Object.keys(themes)).toEqual(Object.values(themeNames));
  });

  it('groups fixed actions in a semantic, safe-area-ready stack', () => {
    const wrapper = mount(FloatingActionStack, {
      props: { label: 'Plugin actions' },
      slots: { default: '<button type="button">Install</button>' },
    });

    expect(wrapper.get('[role="group"]').attributes('aria-label')).toBe(
      'Plugin actions',
    );
    expect(wrapper.text()).toContain('Install');
  });

  it('keeps wallpaper opacity scoped to application surfaces', () => {
    const wallpaperLayer = readFileSync(
      'src/components/appearance/DashboardWallpaperLayer.vue',
      'utf8',
    );

    expect(wallpaperLayer).toContain(
      '.dashboard-appearance-active .page-wrapper {',
    );
    expect(wallpaperLayer).toContain(
      'background-color: var(--dashboard-wallpaper-surface);',
    );
    expect(wallpaperLayer).not.toMatch(
      /\.dashboard-appearance-active \.v-(?:card|app-bar|navigation-drawer)/,
    );
    expect(wallpaperLayer).not.toContain(
      '.dashboard-appearance-active .top-header',
    );
  });
});
