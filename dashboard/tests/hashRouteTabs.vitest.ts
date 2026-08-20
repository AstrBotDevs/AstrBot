import { describe, expect, it, vi } from 'vitest';
import {
  createTabRouteLocation,
  getValidHashTab,
  replaceTabRoute,
} from '@/utils/hashRouteTabs';

const VALID_TABS = ['installed', 'market', 'mcp', 'skills', 'components'];

describe('hashRouteTabs', () => {
  it('accepts only declared extension tabs', () => {
    expect(getValidHashTab('#market', VALID_TABS)).toBe('market');
    expect(getValidHashTab('skills', VALID_TABS)).toBe('skills');
    expect(getValidHashTab('#unknown', VALID_TABS)).toBeNull();
    expect(getValidHashTab('', VALID_TABS)).toBeNull();
  });

  it('preserves the current route identity when switching tabs', () => {
    expect(
      createTabRouteLocation(
        {
          name: 'Extensions',
          query: { q: 'search' },
          params: { pluginId: 'p' },
        },
        'mcp',
      ),
    ).toEqual({
      name: 'Extensions',
      params: { pluginId: 'p' },
      query: { q: 'search' },
      hash: '#mcp',
    });
  });

  it('replaces the tab hash and reports router failures without throwing', async () => {
    const replace = vi.fn().mockResolvedValue(undefined);
    expect(
      await replaceTabRoute(
        { replace } as never,
        { name: 'Extensions' },
        'installed',
      ),
    ).toBe(true);
    expect(replace).toHaveBeenCalledWith({
      name: 'Extensions',
      query: {},
      hash: '#installed',
    });

    const warn = vi.fn();
    const failingReplace = vi
      .fn()
      .mockRejectedValue(new Error('navigation aborted'));
    expect(
      await replaceTabRoute(
        { replace: failingReplace } as never,
        { path: '/extension' },
        'market',
        { warn },
      ),
    ).toBe(false);
    expect(warn).toHaveBeenCalled();
  });
});
