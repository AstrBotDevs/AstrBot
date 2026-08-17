export const PINNED_EXTENSIONS_STORAGE_KEY = "astrbot.pinnedExtensions";
export const PLUGIN_CARD_DENSITY_STORAGE_KEY = "astrbot.pluginCardDensity";

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
    targetStorage.setItem(
      PINNED_EXTENSIONS_STORAGE_KEY,
      JSON.stringify(normalizePinnedExtensions(names)),
    );
  } catch {
    // Ignore restricted storage environments.
  }
};

/**
 * Read the saved plugin card density.
 *
 * Args:
 *   storage: Optional storage override used by tests or restricted runtimes.
 *
 * Returns:
 *   The saved density, or "detailed" when the value is unavailable or invalid.
 */
export const readPluginCardDensity = (storage) => {
  const targetStorage = getStorageForRead(storage);
  if (!targetStorage) {
    return "detailed";
  }

  try {
    const saved = targetStorage.getItem(PLUGIN_CARD_DENSITY_STORAGE_KEY);
    return ["detailed", "compact"].includes(saved) ? saved : "detailed";
  } catch {
    return "detailed";
  }
};

/**
 * Persist the plugin card density.
 *
 * Args:
 *   density: Density value to store. Unsupported values use "detailed".
 *   storage: Optional storage override used by tests or restricted runtimes.
 *
 * Returns:
 *   Nothing.
 */
export const writePluginCardDensity = (density, storage) => {
  const targetStorage = getStorageForWrite(storage);
  if (!targetStorage) {
    return;
  }

  try {
    targetStorage.setItem(
      PLUGIN_CARD_DENSITY_STORAGE_KEY,
      ["detailed", "compact"].includes(density) ? density : "detailed",
    );
  } catch {
    // Ignore restricted storage environments.
  }
};
