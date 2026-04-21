export const SHOW_RESERVED_PLUGINS_STORAGE_KEY = "showReservedPlugins";
export const PLUGIN_LIST_VIEW_MODE_STORAGE_KEY = "pluginListViewMode";
export const PIN_UPDATES_ON_TOP_STORAGE_KEY = "pinUpdatesOnTop";

/**
 * Resolve the storage backend for reading preferences.
 * Pass `null` to explicitly disable storage access in callers/tests.
 */
const getStorageForRead = (storageOverride) => {
  if (storageOverride === null) {
    return null;
  }
  if (storageOverride !== undefined) {
    return typeof storageOverride?.getItem === "function"
      ? storageOverride
      : null;
  }
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const localStorage = window.localStorage ?? null;
    return typeof localStorage?.getItem === "function" ? localStorage : null;
  } catch {
    return null;
  }
};

/**
 * Resolve the storage backend for writing preferences.
 * Pass `null` to explicitly disable storage access in callers/tests.
 */
const getStorageForWrite = (storageOverride) => {
  if (storageOverride === null) {
    return null;
  }
  if (storageOverride !== undefined) {
    return typeof storageOverride?.setItem === "function"
      ? storageOverride
      : null;
  }
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const localStorage = window.localStorage ?? null;
    return typeof localStorage?.setItem === "function" ? localStorage : null;
  } catch {
    return null;
  }
};

export const readBooleanPreference = (key, fallback, storage) => {
  const targetStorage = getStorageForRead(storage);
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
  const targetStorage = getStorageForWrite(storage);
  if (!targetStorage) {
    return;
  }

  try {
    targetStorage.setItem(key, String(value));
  } catch {
    // Ignore restricted storage environments.
  }
};
