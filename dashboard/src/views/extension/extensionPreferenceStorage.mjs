export const PINNED_EXTENSIONS_STORAGE_KEY = "astrbot.pinnedExtensions";
// Preserve the pre-workspace preference API and keys for existing consumers.
export const SHOW_RESERVED_PLUGINS_STORAGE_KEY = "showReservedPlugins";
export const PLUGIN_LIST_VIEW_MODE_STORAGE_KEY = "pluginListViewMode";
export const PIN_UPDATES_ON_TOP_STORAGE_KEY = "pinUpdatesOnTop";

const getStorageForRead = (storageOverride) => {
  if (storageOverride === null) {
    return null;
  }
  if (storageOverride !== undefined) {
    return typeof storageOverride?.getItem === "function" ? storageOverride : null;
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

const getStorageForWrite = (storageOverride) => {
  if (storageOverride === null) {
    return null;
  }
  if (storageOverride !== undefined) {
    return typeof storageOverride?.setItem === "function" ? storageOverride : null;
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
  if (!targetStorage) return fallback;

  try {
    const saved = targetStorage.getItem(key);
    if (saved === "true") return true;
    if (saved === "false") return false;
    return fallback;
  } catch {
    return fallback;
  }
};

export const writeBooleanPreference = (key, value, storage) => {
  const targetStorage = getStorageForWrite(storage);
  if (!targetStorage) return;

  try {
    targetStorage.setItem(key, String(value));
  } catch {
    // Ignore restricted storage environments.
  }
};

const normalizePinnedExtensions = (value) => {
  if (!Array.isArray(value)) {
    return [];
  }

  const seen = new Set();
  return value
    .filter((item) => typeof item === "string" && item.trim().length > 0)
    .map((item) => item.trim())
    .filter((item) => {
      if (seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
};

export const readPinnedExtensions = (storage) => {
  const targetStorage = getStorageForRead(storage);
  if (!targetStorage) {
    return [];
  }

  try {
    const raw = targetStorage.getItem(PINNED_EXTENSIONS_STORAGE_KEY);
    return normalizePinnedExtensions(raw ? JSON.parse(raw) : []);
  } catch {
    return [];
  }
};

export const writePinnedExtensions = (names, storage) => {
  const targetStorage = getStorageForWrite(storage);
  if (!targetStorage) {
    return;
  }

  try {
    targetStorage.setItem(PINNED_EXTENSIONS_STORAGE_KEY, JSON.stringify(normalizePinnedExtensions(names)));
  } catch {
    // Ignore restricted storage environments.
  }
};
