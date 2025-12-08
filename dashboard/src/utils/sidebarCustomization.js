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
 * Apply customization to sidebar items
 * @param {Array} defaultItems - Default sidebar items array
 * @returns {Array} Customized sidebar items array (new array, doesn't mutate input)
 */
export function applySidebarCustomization(defaultItems) {
  const customization = getSidebarCustomization();
  if (!customization) {
    return defaultItems;
  }

  const { mainItems = [], moreItems = [] } = customization;
  
  const all = new Map();
  const defaultMain = [];
  const defaultMore = [];
  defaultItems.forEach(item => {
    if (item.children) {
      item.children.forEach(child => {
        all.set(child.title, { ...child });
        defaultMore.push(child.title);
      });
    } else {
      all.set(item.title, { ...item });
      defaultMain.push(item.title);
    }
  });

  const customizedItems = [];
  const used = new Set([...mainItems, ...moreItems]);
  
  // 按用户顺序还原主区
  mainItems.forEach(title => all.get(title) && customizedItems.push(all.get(title)));
  // 追加新增的默认主区项
  defaultMain.forEach(title => !used.has(title) && customizedItems.push(all.get(title)));

  // 更多区：用户配置 + 新增默认
  const mergedMore = [...moreItems];
  defaultMore.forEach(title => { if (!used.has(title)) mergedMore.push(title); });

  if (mergedMore.length > 0) {
    const moreGroup = {
      title: 'core.navigation.groups.more',
      icon: 'mdi-dots-horizontal',
      children: []
    };
    
    mergedMore.forEach(title => all.get(title) && moreGroup.children.push(all.get(title)));
    
    customizedItems.push(moreGroup);
  }

  return customizedItems;
}
