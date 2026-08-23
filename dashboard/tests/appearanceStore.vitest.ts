import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useAppearanceStore } from '@/stores/appearance';

describe('appearance store', () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it('persists browser-scoped settings and clears deleted wallpaper selections', () => {
    const store = useAppearanceStore();
    store.update({
      enabled: true,
      landscapeWallpaperId: 'a'.repeat(32),
      portraitWallpaperId: 'b'.repeat(32),
      blur: 12,
      surfaceOpacity: 0.35,
    });

    expect(store.rootStyle['--dashboard-wallpaper-blur']).toBe('12px');
    expect(store.rootStyle['--dashboard-surface-opacity']).toBe('0.35');

    store.clearWallpaper('a'.repeat(32));
    expect(store.settings.landscapeWallpaperId).toBe('');
    expect(store.settings.portraitWallpaperId).toBe('b'.repeat(32));

    setActivePinia(createPinia());
    const restored = useAppearanceStore();
    expect(restored.settings.enabled).toBe(true);
    expect(restored.settings.portraitWallpaperId).toBe('b'.repeat(32));
  });

  it('clamps non-numeric appearance fields to defaults', () => {
    localStorage.setItem(
      'astrbot:appearance:v1',
      JSON.stringify({
        enabled: true,
        blur: 'nope',
        brightness: 'x',
        dim: 'nope',
        surfaceOpacity: {},
      }),
    );
    const store = useAppearanceStore();
    expect(store.settings.blur).toBe(0);
    expect(store.settings.brightness).toBe(1);
    expect(store.settings.dim).toBe(0.5);
    expect(store.settings.surfaceOpacity).toBe(1);
  });

  it('falls back to defaults when stored appearance JSON is invalid', () => {
    localStorage.setItem('astrbot:appearance:v1', '{not-json');
    const store = useAppearanceStore();
    expect(store.settings.enabled).toBe(false);
    expect(store.settings.fit).toBe('cover');
  });

  it('resets to a non-invasive default appearance', () => {
    const store = useAppearanceStore();
    store.update({ enabled: true, surfaceOpacity: 0 });

    store.reset();

    expect(store.settings.enabled).toBe(false);
    expect(store.active).toBe(false);
    expect(store.rootStyle['--dashboard-surface-opacity']).toBe('1');
    expect(localStorage.getItem('astrbot:appearance:v1')).toBeNull();
  });
});
