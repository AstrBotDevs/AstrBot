import test from 'node:test';
import assert from 'node:assert/strict';

import * as hashRouteTabs from '../src/utils/hashRouteTabs.mjs';
import { EXTENSION_ROUTE_NAME } from '../src/router/routeConstants.mjs';

const { createTabRouteLocation, getValidHashTab } = hashRouteTabs;

test('getValidHashTab returns the tab name for a valid route hash', () => {
  const validTabs = ['installed', 'market', 'mcp'];

  assert.equal(getValidHashTab('#market', validTabs), 'market');
});

test('getValidHashTab rejects empty and unknown hashes', () => {
  const validTabs = ['installed', 'market', 'mcp'];

  assert.equal(getValidHashTab('', validTabs), null);
  assert.equal(getValidHashTab('#unknown', validTabs), null);
});

test('getValidHashTab uses the last hash segment when multiple hashes are present', () => {
  const validTabs = ['installed', 'market', 'mcp'];

  assert.equal(getValidHashTab('#/extension#foo#installed', validTabs), 'installed');
});

test('createTabRouteLocation preserves the current path and query', () => {
  const query = { open_config: 'sample-plugin', page: '2' };
  const location = createTabRouteLocation(
    {
      path: '/extension',
      query,
    },
    'market',
  );

  assert.deepEqual(location, {
    path: '/extension',
    query: { open_config: 'sample-plugin', page: '2' },
    hash: '#market',
  });
  assert.notEqual(location.query, query);
});

test('createTabRouteLocation falls back to the extension route name', () => {
  const location = createTabRouteLocation(undefined, 'installed');

  assert.deepEqual(location, {
    name: EXTENSION_ROUTE_NAME,
    query: {},
    hash: '#installed',
  });
});

test('createTabRouteLocation prefers route name and preserves params', () => {
  const params = { pluginId: 'demo-plugin' };
  const location = createTabRouteLocation(
    {
      name: 'ExtensionDetails',
      path: '/extension/demo-plugin',
      params,
      query: { tab: 'details' },
    },
    'market',
  );

  assert.deepEqual(location, {
    name: 'ExtensionDetails',
    params: { pluginId: 'demo-plugin' },
    query: { tab: 'details' },
    hash: '#market',
  });
  assert.notEqual(location.params, params);
});

test('createTabRouteLocation omits params for path-based routes', () => {
  const params = { pluginId: 'demo-plugin' };
  const location = createTabRouteLocation(
    {
      path: '/extension/demo-plugin',
      params,
    },
    'installed',
  );

  assert.deepEqual(location, {
    path: '/extension/demo-plugin',
    query: {},
    hash: '#installed',
  });
  assert.equal(location.params, undefined);
});

test('replaceTabRoute catches rejected router updates', async () => {
  assert.equal(typeof hashRouteTabs.replaceTabRoute, 'function');

  const error = new Error('blocked');
  let logged;
  const router = {
    replace: async () => {
      throw error;
    },
  };
  const logger = {
    warn: (message, cause) => {
      logged = { message, cause };
    },
  };

  const result = await hashRouteTabs.replaceTabRoute(
    router,
    { name: EXTENSION_ROUTE_NAME, query: { page: '1' } },
    'installed',
    logger,
  );

  assert.equal(result, false);
  assert.deepEqual(logged, {
    message: 'Failed to update extension tab route:',
    cause: error,
  });
});
