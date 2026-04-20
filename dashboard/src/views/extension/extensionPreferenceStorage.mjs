export const SHOW_RESERVED_PLUGINS_STORAGE_KEY = "showReservedPlugins";
export const PLUGIN_LIST_VIEW_MODE_STORAGE_KEY = "pluginListViewMode";
export const PIN_UPDATES_ON_TOP_STORAGE_KEY = "pinUpdatesOnTop";

const resolveStorage = (storage) => {
  if (storage !== undefined) {
    return storage;
  }
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage ?? null;
  } catch {
    return null;
  }
};

export const readBooleanPreference = (key, fallback, storage) => {
  const targetStorage = resolveStorage(storage);
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
  const targetStorage = resolveStorage(storage);
  if (!targetStorage) {
    return;
  }

  try {
    targetStorage.setItem(key, String(value));
  } catch {
    // Ignore restricted storage environments.
  }
};
