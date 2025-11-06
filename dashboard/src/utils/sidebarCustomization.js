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

  const { mainItems, moreItems } = customization;
  
  // Create a map of all items by title for quick lookup
  // Deep clone items to avoid mutating originals
  const allItemsMap = new Map();
  defaultItems.forEach(item => {
    if (item.children) {
      // If it's the "More" group, add children to map
      item.children.forEach(child => {
        allItemsMap.set(child.title, { ...child });
      });
    } else {
      allItemsMap.set(item.title, { ...item });
    }
  });

  const customizedItems = [];
  
  // Add main items in custom order
  mainItems.forEach(title => {
    const item = allItemsMap.get(title);
    if (item) {
      customizedItems.push(item);
    }
  });

  // If there are items in moreItems, create the "More Features" group
  if (moreItems && moreItems.length > 0) {
    const moreGroup = {
      title: 'core.navigation.groups.more',
      icon: 'mdi-dots-horizontal',
      children: []
    };
    
    moreItems.forEach(title => {
      const item = allItemsMap.get(title);
      if (item) {
        moreGroup.children.push(item);
      }
    });
    
    customizedItems.push(moreGroup);
  }

  return customizedItems;
}
