import test from 'node:test';
import assert from 'node:assert/strict';

import {
  PINNED_EXTENSIONS_STORAGE_KEY,
  readPinnedExtensions,
  writePinnedExtensions,
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
