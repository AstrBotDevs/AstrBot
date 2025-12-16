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
 * @param {Object|null} customization - 用户定制（mainItems/moreItems）
 * @param {Object} options
 * @param {boolean} [options.cloneItems=false] - 是否克隆条目以避免外部引用被修改
 * @param {boolean} [options.assembleMoreGroup=false] - 是否组装带更多分组的整体数组
 * @returns {{ mainItems: Array, moreItems: Array, merged?: Array }}
 */
export function resolveSidebarItems(defaultItems, customization, options = {}) {
  const { cloneItems = false, assembleMoreGroup = false } = options;

  const all = new Map();
  const defaultMain = [];
  const defaultMore = [];

  // 收集所有条目，按 title 建索引
  defaultItems.forEach(item => {
    if (item.children) {
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
  const mainKeys = hasCustomization ? customization.mainItems || [] : defaultMain;
  const moreKeys = hasCustomization ? customization.moreItems || [] : defaultMore;
  const used = hasCustomization ? new Set([...mainKeys, ...moreKeys]) : new Set(defaultMain.concat(defaultMore));

  const mainItems = mainKeys
    .map(title => all.get(title))
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
    .map(title => all.get(title))
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
    const children = cloneItems ? moreItems.map(item => ({ ...item })) : [...moreItems];
    if (children.length > 0) {
      merged = [
        ...mainItems,
        {
          title: 'core.navigation.groups.more',
          icon: 'mdi-dots-horizontal',
          children
        }
      ];
    } else {
      merged = [...mainItems];
    }
  }

  return { mainItems, moreItems, merged };
}

/**
 * 应用侧边栏定制，返回包含更多分组的完整结构
 * @param {Array} defaultItems - 默认侧边栏结构
 * @returns {Array} 自定义后的结构（新数组，不修改入参）
 */
export function applySidebarCustomization(defaultItems) {
  const customization = getSidebarCustomization();
  const { merged } = resolveSidebarItems(defaultItems, customization, {
    cloneItems: true,
    assembleMoreGroup: true
  });
  return merged || defaultItems;
}
