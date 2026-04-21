export const SHOW_RESERVED_PLUGINS_STORAGE_KEY = "showReservedPlugins";
export const PLUGIN_LIST_VIEW_MODE_STORAGE_KEY = "pluginListViewMode";
export const PIN_UPDATES_ON_TOP_STORAGE_KEY = "pinUpdatesOnTop";

const hasStorageMethod = (storage, methodName) =>
  storage != null && typeof storage[methodName] === "function";

/**
 * Resolve the storage backend for preference helpers.
 * Pass `null` to explicitly disable storage access in callers/tests.
 */
const resolveStorage = (storage, methodName) => {
  if (storage === null) {
    return null;
  }
  if (storage !== undefined) {
    return hasStorageMethod(storage, methodName) ? storage : null;
  }
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const localStorage = window.localStorage ?? null;
    return hasStorageMethod(localStorage, methodName) ? localStorage : null;
  } catch {
    return null;
  }
};

export const readBooleanPreference = (key, fallback, storage) => {
  const targetStorage = resolveStorage(storage, "getItem");
  if (!targetStorage) {
    return fallback;
  }

  try {
    const saved = targetStorage.getItem(key);
    if (saved === "true") {
      return true;
    }
    if (saved === "false") {
      return false;
    }
    return fallback;
  } catch {
    return fallback;
  }
};

export const writeBooleanPreference = (key, value, storage) => {
  const targetStorage = resolveStorage(storage, "setItem");
  if (!targetStorage) {
    return;
  }

  try {
    targetStorage.setItem(key, String(value));
  } catch {
    // Ignore restricted storage environments.
  }
};
