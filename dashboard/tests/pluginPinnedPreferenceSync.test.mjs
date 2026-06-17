import test from 'node:test';
import assert from 'node:assert/strict';

import {
  normalizePinnedExtensions,
  resolvePinnedExtensionNames,
} from '../src/views/extension/pluginPinnedPreferenceSync.mjs';

test('normalizePinnedExtensions filters empty, non-string, and duplicate items', () => {
  const input = ['alpha', ' beta ', 'alpha', '', null, undefined, 1, 'beta'];
  assert.deepEqual(normalizePinnedExtensions(input), ['alpha', 'beta']);
});

test('normalizePinnedExtensions returns empty array for non-array input', () => {
  assert.deepEqual(normalizePinnedExtensions(null), []);
  assert.deepEqual(normalizePinnedExtensions({ key: 'value' }), []);
  assert.deepEqual(normalizePinnedExtensions('alpha,beta'), []);
});

test('resolvePinnedExtensionNames prefers remote list when present', () => {
  const result = resolvePinnedExtensionNames({
    localNames: ['local-a', 'local-b'],
    remoteNames: ['remote-a', 'remote-b'],
    preferenceExists: true,
  });

  assert.deepEqual(result.names, ['remote-a', 'remote-b']);
  assert.equal(result.shouldMigrate, false);
});

test('resolvePinnedExtensionNames migrates local list when remote record is missing', () => {
  const result = resolvePinnedExtensionNames({
    localNames: ['local-a', 'local-b', 'local-a', ''],
    remoteNames: [],
    preferenceExists: false,
  });

  assert.deepEqual(result.names, ['local-a', 'local-b']);
  assert.equal(result.shouldMigrate, true);
  assert.deepEqual(result.migrateNames, ['local-a', 'local-b']);
});

test('resolvePinnedExtensionNames keeps empty remote record instead of migrating local list', () => {
  const result = resolvePinnedExtensionNames({
    localNames: ['local-a', 'local-b'],
    remoteNames: [],
    preferenceExists: true,
  });

  assert.deepEqual(result.names, []);
  assert.equal(result.shouldMigrate, false);
});

test('resolvePinnedExtensionNames returns empty list when both sides are empty', () => {
  const result = resolvePinnedExtensionNames({
    localNames: [],
    remoteNames: [],
    preferenceExists: false,
  });

  assert.deepEqual(result.names, []);
  assert.equal(result.shouldMigrate, false);
});

test('resolvePinnedExtensionNames ignores dirty missing remote data and falls back to local', () => {
  const result = resolvePinnedExtensionNames({
    localNames: ['local-a'],
    remoteNames: ['', null, 1],
    preferenceExists: false,
  });

  assert.deepEqual(result.names, ['local-a']);
  assert.equal(result.shouldMigrate, true);
  assert.deepEqual(result.migrateNames, ['local-a']);
});

test('resolvePinnedExtensionNames does not migrate when remote existence is unknown', () => {
  const result = resolvePinnedExtensionNames({
    localNames: ['local-a'],
    remoteNames: [],
    preferenceExists: undefined,
  });

  assert.deepEqual(result.names, []);
  assert.equal(result.shouldMigrate, false);
});

test('resolvePinnedExtensionNames treats dirty existing remote data as empty record', () => {
  const result = resolvePinnedExtensionNames({
    localNames: ['local-a'],
    remoteNames: ['', null, 1],
    preferenceExists: true,
  });

  assert.deepEqual(result.names, []);
  assert.equal(result.shouldMigrate, false);
});
