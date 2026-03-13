import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createTabRouteLocation,
  getValidHashTab,
} from '../src/utils/hashRouteTabs.mjs';

test('getValidHashTab returns the tab name for a valid route hash', () => {
  const validTabs = ['installed', 'market', 'mcp'];

  assert.equal(getValidHashTab('#market', validTabs), 'market');
});

test('getValidHashTab rejects empty and unknown hashes', () => {
  const validTabs = ['installed', 'market', 'mcp'];

  assert.equal(getValidHashTab('', validTabs), null);
  assert.equal(getValidHashTab('#unknown', validTabs), null);
});

test('createTabRouteLocation preserves the current path and query', () => {
  const location = createTabRouteLocation(
    {
      path: '/extension',
      query: { open_config: 'sample-plugin', page: '2' },
    },
    'market',
  );

  assert.deepEqual(location, {
    path: '/extension',
    query: { open_config: 'sample-plugin', page: '2' },
    hash: '#market',
  });
});
