import assert from "node:assert/strict";
import test from "node:test";

import {
  PINNED_EXTENSIONS_STORAGE_KEY,
  PIN_UPDATES_ON_TOP_STORAGE_KEY,
  readBooleanPreference,
  readPinnedExtensions,
  writeBooleanPreference,
  writePinnedExtensions,
} from "../src/views/extension/extensionPreferenceStorage.mjs";

test("readBooleanPreference returns fallback when storage access throws", () => {
  const storage = {
    getItem() {
      throw new Error("SecurityError");
    },
  };

  assert.equal(readBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, true, storage), true);
});

test("readBooleanPreference parses stored boolean strings", () => {
  const storage = {
    getItem(key) {
      return key === PIN_UPDATES_ON_TOP_STORAGE_KEY ? "false" : null;
    },
  };

  assert.equal(readBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, true, storage), false);
});

test("readBooleanPreference treats explicit null storage as unavailable", () => {
  assert.equal(readBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, true, null), true);
});

test("readBooleanPreference treats invalid storage overrides as unavailable", () => {
  assert.equal(readBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, true, {}), true);
});

test("writeBooleanPreference stores boolean strings and swallows storage errors", () => {
  const writes = [];
  const storage = {
    setItem(key, value) {
      writes.push([key, value]);
      throw new Error("QuotaExceededError");
    },
  };

  assert.doesNotThrow(() => writeBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, true, storage));
  assert.deepEqual(writes, [[PIN_UPDATES_ON_TOP_STORAGE_KEY, "true"]]);
});

test("writeBooleanPreference ignores explicit null storage", () => {
  assert.doesNotThrow(() => writeBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, true, null));
});

test("writeBooleanPreference ignores invalid storage overrides", () => {
  assert.doesNotThrow(() => writeBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, true, {}));
});

test("readPinnedExtensions uses the legacy pinned extension storage key", () => {
  assert.equal(PINNED_EXTENSIONS_STORAGE_KEY, "astrbot.pinnedExtensions");
});

test("readPinnedExtensions parses stored pinned extension names", () => {
  const storage = {
    getItem(key) {
      return key === PINNED_EXTENSIONS_STORAGE_KEY
        ? JSON.stringify(["alpha", "beta", "alpha", "", 1])
        : null;
    },
  };

  assert.deepEqual(readPinnedExtensions(storage), ["alpha", "beta"]);
});

test("readPinnedExtensions returns an empty array when storage access fails", () => {
  const storage = {
    getItem() {
      throw new Error("SecurityError");
    },
  };

  assert.deepEqual(readPinnedExtensions(storage), []);
});

test("writePinnedExtensions stores normalized pinned extension names", () => {
  const writes = [];
  const storage = {
    setItem(key, value) {
      writes.push([key, value]);
    },
  };

  writePinnedExtensions(["alpha", "beta", "alpha", "", null], storage);

  assert.deepEqual(writes, [
    [PINNED_EXTENSIONS_STORAGE_KEY, JSON.stringify(["alpha", "beta"])],
  ]);
});

test("writePinnedExtensions ignores unavailable storage", () => {
  assert.doesNotThrow(() => writePinnedExtensions(["alpha"], null));
  assert.doesNotThrow(() => writePinnedExtensions(["alpha"], {}));
});
