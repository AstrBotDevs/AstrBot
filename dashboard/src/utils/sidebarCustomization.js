// Utility for managing sidebar customization in localStorage
const STORAGE_KEY = 'astrbot_sidebar_customization';

/**
 * @typedef {Object} SidebarCustomization
 * @property {string[]} [mainItems] - Ordered titles of the main sidebar items
 * @property {string[]} [moreItems] - Ordered titles of the "more" group items
 * @property {Object<string, string[]>} [subItems] - Ordered sub-route values per parent title
 * @property {string[]} [promotedSubRoutes] - Sub-route values lifted to first-level sidebar items
 */

/**
 * Get the customized sidebar configuration from localStorage
 * @returns {SidebarCustomization|null} The customization config or null if not set
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
 * @param {Array} config.mainItems - Array of item titles for main sidebar
 * @param {Array} config.moreItems - Array of item titles for "More Features" group
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
 * 解析侧边栏默认项与用户定制，返回主区/更多区及可选的合并结果
 * @param {Array} defaultItems - 默认侧边栏结构
 * @param {Object|null} customization - 用户定制（mainItems/moreItems/subItems）
 * @param {Object} options
 * @param {boolean} [options.cloneItems=false] - 是否克隆条目以避免外部引用被修改
 * @param {boolean} [options.assembleMoreGroup=false] - 是否组装带更多分组的整体数组
 * @returns {{ mainItems: Array, moreItems: Array, merged?: Array }}
 */
import { MORE_GROUP_KEY } from "@/layouts/full/vertical-sidebar/sidebarItem";
import { SIDEBAR_SUB_ITEMS, getSubRoutePath } from "@/utils/sidebarSubItems";

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

  // 收集所有条目，按 title 建索引；header 项不参与排序
  defaultItems.forEach(item => {
    if (item.header) return;
    if (item.children && item.title === MORE_GROUP_KEY) {
      item.children.forEach(child => {
        all.set(child.title, cloneItems ? { ...child } : child);
        defaultMore.push(child.title);
      });
    } else {
      all.set(item.title, cloneItems ? { ...item } : item);
      defaultMain.push(item.title);
    }
  });

  const hasCustomization = Boolean(customization);
  let mainKeys = hasCustomization ? normalizeKeys(customization.mainItems || []) : [...defaultMain];
  let moreKeys = hasCustomization ? normalizeKeys(customization.moreItems || []) : [...defaultMore];

  // Promoted sub-routes (labelKey titles) are first-level items too; they are
  // not part of the default item map, so keep them in the lists by their key.
  // They carry their real route so the sidebar item is navigable and its
  // active state matches the page.
  const promotedByKey = new Map();
  const promotedByValue = new Map();
  Object.entries(SIDEBAR_SUB_ITEMS).forEach(([parentTitle, subs]) => {
    subs.forEach(sub => {
      promotedByKey.set(sub.labelKey, {
        title: sub.labelKey,
        icon: sub.icon,
        parentTitle,
        to: getSubRoutePath(parentTitle, sub.value)
      });
      promotedByValue.set(sub.value, sub.labelKey);
    });
  });

  if (hasCustomization) {
    // Older storage kept promoted items only in promotedSubRoutes; insert
    // them right after their parent so they still render until re-saved.
    const present = new Set([...mainKeys, ...moreKeys]);
    (customization.promotedSubRoutes || []).forEach((value) => {
      const labelKey = promotedByValue.get(value);
      if (!labelKey || present.has(labelKey)) return;
      present.add(labelKey);
      const def = promotedByKey.get(labelKey);
      const parentIdx = mainKeys.indexOf(def.parentTitle);
      if (parentIdx >= 0) mainKeys.splice(parentIdx + 1, 0, labelKey);
      else mainKeys.push(labelKey);
    });
  }

  if (hasCustomization) {
    mainKeys = mainKeys.filter(title => all.has(title) || promotedByKey.has(title));
    moreKeys = moreKeys.filter(title => all.has(title) || promotedByKey.has(title));
  }

  if (hasCustomization) {
    // 如果同一项同时出现在主区与更多区，主区优先。
    const mainSet = new Set(mainKeys);
    moreKeys = moreKeys.filter(title => !mainSet.has(title));
  }

  const used = hasCustomization
    ? new Set([...mainKeys, ...moreKeys])
    : new Set(defaultMain.concat(defaultMore));

  const mainItems = mainKeys
    .map(title => all.get(title) || promotedByKey.get(title))
    .filter(Boolean);

  if (hasCustomization) {
    // 补充新增默认主区项
    defaultMain.forEach(title => {
      if (!used.has(title)) {
        const item = all.get(title);
        if (item) mainItems.push(item);
      }
    });
  }

  const moreItems = moreKeys
    .map(title => all.get(title) || promotedByKey.get(title))
    .filter(Boolean);

  if (hasCustomization) {
    // 补充新增默认更多区项
    defaultMore.forEach(title => {
      if (!used.has(title)) {
        const item = all.get(title);
        if (item) moreItems.push(item);
      }
    });
  }

  let merged;
  if (assembleMoreGroup) {
    // Rebuild the array in default order so group headers keep their original
    // positions, while non-header items follow the customized ordering.
    // mainItems always covers every default non-header item (customized ones
    // first, untouched defaults appended), so each segment stays complete.
    const result = [];
    const placed = new Set();

    // Group the default non-header items into segments between headers so a
    // promoted sub-route lands in the same segment as its parent.
    const segments = [];
    let segmentTitles = new Set();
    defaultItems.forEach(item => {
      if (item.header) {
        if (segmentTitles.size > 0) segments.push(segmentTitles);
        segmentTitles = new Set();
      } else {
        segmentTitles.add(item.title);
      }
    });
    if (segmentTitles.size > 0) segments.push(segmentTitles);

    let segmentIndex = -1;
    const flushSegment = () => {
      segmentIndex += 1;
      const current = segments[segmentIndex];
      mainItems.forEach(item => {
        if (placed.has(item.title)) return;
        const inSegment = current?.has(item.title) ?? false;
        const promoted = promotedByKey.get(item.title);
        const matches = inSegment || Boolean(promoted && current?.has(promoted.parentTitle));
        if (matches) {
          result.push(item);
          placed.add(item.title);
        }
      });
    };

    defaultItems.forEach(item => {
      if (item.header) {
        result.push(cloneItems ? { ...item } : item);
        flushSegment();
      }
    });
    flushSegment();

    const children = cloneItems ? moreItems.map(item => ({ ...item })) : [...moreItems];
    if (children.length > 0) {
      result.push({
        title: MORE_GROUP_KEY,
        icon: defaultMoreGroup?.icon || 'mdi-dots-horizontal',
        children
      });
    }
    merged = result;
  }

  return {
    mainItems,
    moreItems,
    merged,
    normalizedMainKeys: [...mainKeys],
    normalizedMoreKeys: [...moreKeys]
  };
}

/**
 * 应用侧边栏定制，返回包含更多分组的完整结构
 * @param {Array} defaultItems - 默认侧边栏结构
 * @returns {Array} 自定义后的结构（新数组，不修改入参）
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
      JSON.stringify(rawMainKeys) !== JSON.stringify(normalizedMainKeys) ||
      JSON.stringify(rawMoreKeys) !== JSON.stringify(normalizedMoreKeys);

    if (hasChanged) {
      setSidebarCustomization({
        mainItems: normalizedMainKeys,
        moreItems: normalizedMoreKeys,
        subItems: customization.subItems,
        promotedSubRoutes: customization.promotedSubRoutes
      });
    }
  }

  return merged || defaultItems;
}

/**
 * 解析父菜单项二级条目的顺序：用户定制的 value 顺序优先，未知/未列出项按默认顺序补尾
 * @param {string} parentTitle - 父菜单项 title（i18n key）
 * @param {Array} defaultSubItems - 默认子项列表（来自 SIDEBAR_SUB_ITEMS）
 * @param {Object|null} customization - 用户定制（subItems）
 * @returns {Array} 按定制排序的子项数组（不修改入参）
 */
export function resolveSubItemOrder(parentTitle, defaultSubItems, customization) {
  const custom = customization?.subItems?.[parentTitle];
  if (!Array.isArray(custom) || custom.length === 0) {
    return [...defaultSubItems];
  }

  const byValue = new Map(defaultSubItems.map(item => [item.value, item]));
  const ordered = [];
  const seen = new Set();

  custom.forEach(value => {
    if (typeof value !== 'string' || seen.has(value)) return;
    const item = byValue.get(value);
    if (item) {
      ordered.push(item);
      seen.add(value);
    }
  });

  defaultSubItems.forEach(item => {
    if (!seen.has(item.value)) {
      ordered.push(item);
      seen.add(item.value);
    }
  });

  return ordered;
}
