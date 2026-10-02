// Utility for managing sidebar customization in localStorage
const STORAGE_KEY = 'astrbot_sidebar_customization';

/**
 * Get the customized sidebar configuration from localStorage
 * @returns {Object|null} The customization config or null if not set
 */
export function getSidebarCustomization() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch (error) {
    console.error('Error reading sidebar customization:', error);
    return null;
  }
}

/**
 * Save the sidebar customization to localStorage
 * @param {Object} config - The customization configuration
 * @param {Array} config.mainItems - System section title keys
 * @param {Array} config.moreItems - Extension section title keys
 * @param {number} config.version - Layout schema version (2 for sections)
 */
export function setSidebarCustomization(config) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  } catch (error) {
    console.error('Error saving sidebar customization:', error);
  }
}

/**
 * Clear the sidebar customization (reset to default)
 */
export function clearSidebarCustomization() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Error clearing sidebar customization:', error);
  }
}

/**
 * Resolve navigable items and optionally assemble the customized menu.
 * @param {Array} defaultItems - Default sidebar structure
 * @param {Object|null} customization - Saved mainItems/moreItems title keys
 * @param {Object} options
 * @param {boolean} [options.cloneItems=false] - Clone items to avoid mutating defaults
 * @param {boolean} [options.assembleMoreGroup=false] - Assemble the complete menu
 * @returns {{ mainItems: Array, moreItems: Array, merged?: Array }}
 */
import { MORE_GROUP_KEY, EXTENSION_GROUP_KEY } from "@/layouts/full/vertical-sidebar/sidebarItem";

export function resolveSidebarItems(defaultItems, customization, options = {}) {
  const { cloneItems = false, assembleMoreGroup = false } = options;

  const normalizeKeys = (keys = []) => {
    const list = Array.isArray(keys) ? keys : [];
    const deduped = [];
    const seen = new Set();

    list.forEach((key) => {
      if (typeof key !== 'string') return;
      if (seen.has(key)) return;
      seen.add(key);
      deduped.push(key);
    });

    return deduped;
  };

  const all = new Map();
  const defaultMain = [];
  const defaultMore = [];
  const defaultMoreGroup = defaultItems.find(item => item.children && item.title === MORE_GROUP_KEY);
  let inExtension = false;

  // Section headers are layout metadata, not customizable navigation items.
  defaultItems.forEach(item => {
    if (item.header) inExtension = item.header === EXTENSION_GROUP_KEY;
    if (item.header || item.divider || !item.title) return;
    if (item.children && item.title === MORE_GROUP_KEY) {
      item.children.forEach(child => {
        all.set(child.title, cloneItems ? { ...child } : child);
        defaultMore.push(child.title);
      });
    } else {
      all.set(item.title, cloneItems ? { ...item } : item);
      (inExtension ? defaultMore : defaultMain).push(item.title);
    }
  });

  const hasCustomization = Boolean(customization);
  let mainKeys = hasCustomization ? normalizeKeys(customization.mainItems || []) : [...defaultMain];
  let moreKeys = hasCustomization ? normalizeKeys(customization.moreItems || []) : [...defaultMore];

  if (hasCustomization && customization.version !== 2) {
    // Legacy main mixed both sections; keep original extension membership.
    const extensionKeys = new Set(defaultMore);
    moreKeys = [...mainKeys.filter(title => extensionKeys.has(title)), ...moreKeys];
    mainKeys = mainKeys.filter(title => !extensionKeys.has(title));
    moreKeys = normalizeKeys(moreKeys);
  }

  if (hasCustomization) {
    mainKeys = mainKeys.filter(title => all.has(title));
    moreKeys = moreKeys.filter(title => all.has(title));
  }

  if (hasCustomization) {
    // System takes precedence when an item appears in both lists.
    const mainSet = new Set(mainKeys);
    moreKeys = moreKeys.filter(title => !mainSet.has(title));
  }

  const used = hasCustomization
    ? new Set([...mainKeys, ...moreKeys])
    : new Set(defaultMain.concat(defaultMore));

  const mainItems = mainKeys
    .map(title => all.get(title))
    .filter(Boolean);

  if (hasCustomization) {
    // Keep newly added default items accessible.
    defaultMain.forEach(title => {
      if (!used.has(title)) {
        const item = all.get(title);
        if (item) mainItems.push(item);
      }
    });
  }

  const moreItems = moreKeys
    .map(title => all.get(title))
    .filter(Boolean);

  if (hasCustomization) {
    // Keep newly added extension items in their default section.
    defaultMore.forEach(title => {
      if (!used.has(title)) {
        const item = all.get(title);
        if (item) moreItems.push(item);
      }
    });
  }

  let merged;
  if (assembleMoreGroup) {
    const headers = defaultItems.filter(item => item.header);
    if (headers.length) {
      // Section membership comes from the saved lists, never from list position.
      merged = [];
      headers.forEach(header => {
        merged.push(cloneItems ? { ...header } : header);
        merged.push(...(header.header === EXTENSION_GROUP_KEY ? moreItems : mainItems));
      });
    } else if (moreItems.length > 0) {
      merged = [
        ...mainItems,
        {
          title: MORE_GROUP_KEY,
          icon: defaultMoreGroup?.icon || 'mdi-dots-horizontal',
          children: moreItems
        }
      ];
    } else {
      merged = [...mainItems];
    }
  }

  return {
    mainItems,
    moreItems,
    merged,
    normalizedMainKeys: mainItems.map(item => item.title),
    normalizedMoreKeys: moreItems.map(item => item.title)
  };
}

/**
 * Apply saved customization to the default sidebar.
 * @param {Array} defaultItems - Default sidebar structure
 * @returns {Array} Customized structure without mutating the input
 */
export function applySidebarCustomization(defaultItems) {
  const customization = getSidebarCustomization();
  const {
    merged,
    normalizedMainKeys,
    normalizedMoreKeys
  } = resolveSidebarItems(defaultItems, customization, {
    cloneItems: true,
    assembleMoreGroup: true
  });

  if (customization) {
    const rawMainKeys = Array.isArray(customization.mainItems) ? customization.mainItems : [];
    const rawMoreKeys = Array.isArray(customization.moreItems) ? customization.moreItems : [];
    const hasChanged =
      customization.version !== 2 ||
      JSON.stringify(rawMainKeys) !== JSON.stringify(normalizedMainKeys) ||
      JSON.stringify(rawMoreKeys) !== JSON.stringify(normalizedMoreKeys);

    if (hasChanged) {
      setSidebarCustomization({
        version: 2,
        mainItems: normalizedMainKeys,
        moreItems: normalizedMoreKeys
      });
    }
  }

  return merged || defaultItems;
}
