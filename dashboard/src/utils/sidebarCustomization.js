import { EXTENSION_GROUP_KEY, SYSTEM_GROUP_KEY } from "@/layouts/full/vertical-sidebar/sidebarItem";

const STORAGE_KEY = "astrbot_sidebar_customization";
const LEGACY_MORE_GROUP_KEY = "core.navigation.groups.more";

// These aliases follow the legacy redirects in MainRoutes.
const LEGACY_ITEM_KEYS = {
  "core.navigation.sessionManagement": "core.navigation.config",
  "core.navigation.conversation": "core.navigation.data",
  "core.navigation.console": "core.navigation.data",
  "core.navigation.trace": "core.navigation.data",
  "core.navigation.dashboard": "core.navigation.data",
};

export function getSidebarCustomization() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch (error) {
    console.error("Error reading sidebar customization:", error);
    return null;
  }
}

export function setSidebarCustomization(config) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  } catch (error) {
    console.error("Error saving sidebar customization:", error);
  }
}

export function clearSidebarCustomization() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error("Error clearing sidebar customization:", error);
  }
}

/**
 * Resolve saved title lists against either flat section headers or a legacy
 * nested More group. Header objects are structural and never become item keys.
 */
export function resolveSidebarItems(defaultItems, customization, options = {}) {
  const { cloneItems = false, assembleMoreGroup = false } = options;
  const copyItem = (item) => (cloneItems ? { ...item } : item);
  const all = new Map();
  const defaultMain = [];
  const defaultMore = [];
  const headers = new Map();
  let legacyMoreGroup;
  let section = defaultMain;

  const collect = (item, keys) => {
    if (typeof item.title !== "string" || !item.title) return;
    all.set(item.title, copyItem(item));
    if (!keys.includes(item.title)) keys.push(item.title);
  };

  for (const item of defaultItems) {
    if (item.header === SYSTEM_GROUP_KEY || item.header === EXTENSION_GROUP_KEY) {
      headers.set(item.header, copyItem(item));
      section = item.header === EXTENSION_GROUP_KEY ? defaultMore : defaultMain;
      continue;
    }
    if (item.title === LEGACY_MORE_GROUP_KEY && Array.isArray(item.children)) {
      legacyMoreGroup = item;
      item.children.forEach((child) => collect(child, defaultMore));
      continue;
    }
    collect(item, section);
  }

  const normalizeKeys = (keys) => {
    const result = [];
    const seen = new Set();
    for (const key of Array.isArray(keys) ? keys : []) {
      if (typeof key !== "string") continue;
      const migrated = all.has(key) ? key : LEGACY_ITEM_KEYS[key] || key;
      if (!all.has(migrated) || seen.has(migrated)) continue;
      seen.add(migrated);
      result.push(migrated);
    }
    return result;
  };

  const hasCustomization = Boolean(customization);
  const mainKeys = hasCustomization ? normalizeKeys(customization.mainItems) : [...defaultMain];
  let moreKeys = hasCustomization ? normalizeKeys(customization.moreItems) : [...defaultMore];

  // A saved item may appear in only one section; the main section wins.
  const mainSet = new Set(mainKeys);
  moreKeys = moreKeys.filter((key) => !mainSet.has(key));
  const used = new Set([...mainKeys, ...moreKeys]);
  const mainItems = mainKeys.map((key) => all.get(key));
  const moreItems = moreKeys.map((key) => all.get(key));

  if (hasCustomization) {
    // New default entries remain discoverable without resetting saved order.
    for (const key of defaultMain) {
      if (!used.has(key)) {
        mainItems.push(all.get(key));
        used.add(key);
      }
    }
    for (const key of defaultMore) {
      if (!used.has(key)) {
        moreItems.push(all.get(key));
        used.add(key);
      }
    }
  }

  let merged;
  if (assembleMoreGroup) {
    if (headers.size > 0) {
      const systemHeader = headers.get(SYSTEM_GROUP_KEY);
      const extensionHeader = headers.get(EXTENSION_GROUP_KEY);
      merged = [
        ...(systemHeader ? [systemHeader] : []),
        ...mainItems,
        ...(extensionHeader ? [extensionHeader] : []),
        ...moreItems,
      ];
    } else if (moreItems.length > 0) {
      merged = [
        ...mainItems,
        {
          ...(legacyMoreGroup || { title: LEGACY_MORE_GROUP_KEY, icon: "mdi-dots-horizontal" }),
          children: [...moreItems],
        },
      ];
    } else {
      merged = [...mainItems];
    }
  }

  return {
    mainItems,
    moreItems,
    merged,
    normalizedMainKeys: [...mainKeys],
    normalizedMoreKeys: [...moreKeys],
  };
}

/** Apply customization without changing the default sidebar objects. */
export function applySidebarCustomization(defaultItems) {
  const customization = getSidebarCustomization();
  const { merged, normalizedMainKeys, normalizedMoreKeys } = resolveSidebarItems(defaultItems, customization, {
    cloneItems: true,
    assembleMoreGroup: true,
  });

  if (customization) {
    const rawMainKeys = Array.isArray(customization.mainItems) ? customization.mainItems : [];
    const rawMoreKeys = Array.isArray(customization.moreItems) ? customization.moreItems : [];
    if (
      JSON.stringify(rawMainKeys) !== JSON.stringify(normalizedMainKeys) ||
      JSON.stringify(rawMoreKeys) !== JSON.stringify(normalizedMoreKeys)
    ) {
      setSidebarCustomization({ mainItems: normalizedMainKeys, moreItems: normalizedMoreKeys });
    }
  }

  return merged || defaultItems;
}
