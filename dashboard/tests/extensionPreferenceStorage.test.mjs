import assert from "node:assert/strict";
import test from "node:test";

import {
  PIN_UPDATES_ON_TOP_STORAGE_KEY,
  PINNED_EXTENSIONS_STORAGE_KEY,
  PLUGIN_LIST_VIEW_MODE_STORAGE_KEY,
  SHOW_RESERVED_PLUGINS_STORAGE_KEY,
  readBooleanPreference,
  readPinnedExtensions,
  writeBooleanPreference,
  writePinnedExtensions,
} from "../src/views/extension/extensionPreferenceStorage.mjs";

test("pre-workspace preference keys remain compatible", () => {
  assert.equal(PIN_UPDATES_ON_TOP_STORAGE_KEY, "pinUpdatesOnTop");
  assert.equal(SHOW_RESERVED_PLUGINS_STORAGE_KEY, "showReservedPlugins");
  assert.equal(PLUGIN_LIST_VIEW_MODE_STORAGE_KEY, "pluginListViewMode");
});

test("readBooleanPreference preserves fallback for absent or invalid values", () => {
  for (const saved of [null, "", "1", "invalid", "TRUE"]) {
    const storage = { getItem: () => saved };
    for (const fallback of [true, false]) {
      assert.equal(readBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, fallback, storage), fallback);
    }
  }
});

test("boolean preferences round-trip independently of pinned extension names", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  writePinnedExtensions(["alpha"], storage);
  for (const value of [true, false]) {
    writeBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, value, storage);
    assert.equal(readBooleanPreference(PIN_UPDATES_ON_TOP_STORAGE_KEY, !value, storage), value);
    assert.deepEqual(readPinnedExtensions(storage), ["alpha"]);
  }
});

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
      return key === PINNED_EXTENSIONS_STORAGE_KEY ? JSON.stringify(["alpha", "beta", "alpha", "", 1]) : null;
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

  assert.deepEqual(writes, [[PINNED_EXTENSIONS_STORAGE_KEY, JSON.stringify(["alpha", "beta"])]]);
});

test("writePinnedExtensions ignores unavailable storage", () => {
  assert.doesNotThrow(() => writePinnedExtensions(["alpha"], null));
  assert.doesNotThrow(() => writePinnedExtensions(["alpha"], {}));
});
