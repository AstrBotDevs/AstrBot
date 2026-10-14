import test from 'node:test';
import assert from 'node:assert/strict';

import {
  PINNED_EXTENSIONS_STORAGE_KEY,
  PLUGIN_CARD_DENSITY,
  PLUGIN_CARD_DENSITY_STORAGE_KEY,
  readPinnedExtensions,
  readPluginCardDensity,
  writePinnedExtensions,
  writePluginCardDensity,
} from '../src/views/extension/extensionPreferenceStorage.mjs';

test('readPinnedExtensions uses the legacy pinned extension storage key', () => {
  assert.equal(PINNED_EXTENSIONS_STORAGE_KEY, 'astrbot.pinnedExtensions');
});

test('readPinnedExtensions parses stored pinned extension names', () => {
  const storage = {
    getItem(key) {
      return key === PINNED_EXTENSIONS_STORAGE_KEY
        ? JSON.stringify(['alpha', 'beta', 'alpha', '', 1])
        : null;
    },
  };

  assert.deepEqual(readPinnedExtensions(storage), ['alpha', 'beta']);
});

test('readPinnedExtensions returns an empty array when storage access fails', () => {
  const storage = {
    getItem() {
      throw new Error('SecurityError');
    },
  };

  assert.deepEqual(readPinnedExtensions(storage), []);
});

test('writePinnedExtensions stores normalized pinned extension names', () => {
  const writes = [];
  const storage = {
    setItem(key, value) {
      writes.push([key, value]);
    },
  };

  writePinnedExtensions(['alpha', 'beta', 'alpha', '', null], storage);

  assert.deepEqual(writes, [
    [PINNED_EXTENSIONS_STORAGE_KEY, JSON.stringify(['alpha', 'beta'])],
  ]);
});

test('writePinnedExtensions ignores unavailable storage', () => {
  assert.doesNotThrow(() => writePinnedExtensions(['alpha'], null));
  assert.doesNotThrow(() => writePinnedExtensions(['alpha'], {}));
});

test('readPluginCardDensity restores a saved compact mode', () => {
  const storage = {
    getItem(key) {
      return key === PLUGIN_CARD_DENSITY_STORAGE_KEY
        ? PLUGIN_CARD_DENSITY.COMPACT
        : null;
    },
  };

  assert.equal(readPluginCardDensity(storage), PLUGIN_CARD_DENSITY.COMPACT);
});

test('readPluginCardDensity falls back for invalid or unavailable storage', () => {
  assert.equal(
    readPluginCardDensity({
      getItem() {
        return 'unsupported';
      },
    }),
    PLUGIN_CARD_DENSITY.DETAILED,
  );
  assert.equal(readPluginCardDensity(null), PLUGIN_CARD_DENSITY.DETAILED);
  assert.equal(
    readPluginCardDensity({
      getItem() {
        throw new Error('SecurityError');
      },
    }),
    PLUGIN_CARD_DENSITY.DETAILED,
  );
});

test('writePluginCardDensity stores a supported mode', () => {
  const writes = [];
  const storage = {
    setItem(key, value) {
      writes.push([key, value]);
    },
  };

  writePluginCardDensity(PLUGIN_CARD_DENSITY.COMPACT, storage);

  assert.deepEqual(writes, [
    [PLUGIN_CARD_DENSITY_STORAGE_KEY, PLUGIN_CARD_DENSITY.COMPACT],
  ]);
});

test('writePluginCardDensity normalizes invalid values and storage failures', () => {
  const writes = [];
  const storage = {
    setItem(key, value) {
      writes.push([key, value]);
      throw new Error('QuotaExceededError');
    },
  };

  assert.doesNotThrow(() => writePluginCardDensity('unsupported', storage));
  assert.deepEqual(writes, [
    [PLUGIN_CARD_DENSITY_STORAGE_KEY, PLUGIN_CARD_DENSITY.DETAILED],
  ]);
  assert.doesNotThrow(() =>
    writePluginCardDensity(PLUGIN_CARD_DENSITY.COMPACT, null),
  );
});
