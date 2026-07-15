<script setup>
import { ref, shallowRef, computed, onMounted, onUnmounted, watch } from 'vue';
import { useCustomizerStore } from '../../../stores/customizer';
import { useI18n } from '@/i18n/composables';
import sidebarItems, { MORE_GROUP_KEY } from './sidebarItem';
import NavItem from './NavItem.vue';
import { applySidebarCustomization } from '@/utils/sidebarCustomization';
import { usePluginSidebarItems } from '@/composables/usePluginSidebarItems';

const { t } = useI18n();

const customizer = useCustomizerStore();
const { pluginItems } = usePluginSidebarItems();

function buildSidebarMenu() {
  const base = applySidebarCustomization(sidebarItems);
  if (!pluginItems.value?.children?.length) return base;

  const result = [];

  for (const item of base) {
    if (item.title === MORE_GROUP_KEY) {
      result.push(pluginItems.value);
      result.push(item);
    } else {
      result.push(item);
    }
  }

  if (!base.some((item) => item.title === MORE_GROUP_KEY)) {
    result.push(pluginItems.value);
  }

  return result;
}

function collectGroupValues(items, values = new Set()) {
  items.forEach((item) => {
    if (item?.children && item.title) {
      values.add(item.title);
      collectGroupValues(item.children, values);
    }
  });
  return values;
}

function sanitizeOpenedItems(items, menuItems) {
  if (!Array.isArray(items)) {
    return [];
  }

  const groupValues = collectGroupValues(menuItems);
  return items.filter((item) => typeof item === 'string' && groupValues.has(item));
}

function getInitialOpenedItems(menuItems) {
  try {
    const stored = JSON.parse(localStorage.getItem('sidebar_openedItems') || '[]');
    return sanitizeOpenedItems(stored, menuItems);
  } catch {
    return [];
  }
}

const sidebarMenu = shallowRef(buildSidebarMenu());

// 侧边栏分组展开状态持久化
const openedItems = ref(getInitialOpenedItems(sidebarMenu.value));
watch(openedItems, (val) => {
  localStorage.setItem('sidebar_openedItems', JSON.stringify(sanitizeOpenedItems(val, sidebarMenu.value)));
}, { deep: true });

// 当插件项变化时（如插件启用/停用），刷新菜单
watch(pluginItems, () => {
  sidebarMenu.value = buildSidebarMenu();
  openedItems.value = sanitizeOpenedItems(openedItems.value, sidebarMenu.value);
});

function refreshSidebarMenu() {
  sidebarMenu.value = buildSidebarMenu();
  openedItems.value = sanitizeOpenedItems(openedItems.value, sidebarMenu.value);
}

// Apply customization on mount and listen for storage changes
const handleStorageChange = (e) => {
  if (e.key === 'astrbot_sidebar_customization') {
    refreshSidebarMenu();
  }
};

const handleCustomEvent = () => {
  refreshSidebarMenu();
};

onMounted(() => {
  window.addEventListener('storage', handleStorageChange);
  window.addEventListener('sidebar-customization-changed', handleCustomEvent);
});

onUnmounted(() => {
  window.removeEventListener('storage', handleStorageChange);
  window.removeEventListener('sidebar-customization-changed', handleCustomEvent);
});

const sidebarWidth = ref(235);
const minSidebarWidth = 200;
const maxSidebarWidth = 300;
const isResizing = ref(false);

const isMobile = window.innerWidth < 768;
const isRailSidebar = computed(() => !isMobile && customizer.mini_sidebar);
if (isMobile) {
  customizer.Sidebar_drawer = false;
} else {
  customizer.Sidebar_drawer = true;
}

function startSidebarResize(event) {
  isResizing.value = true;
  document.body.style.userSelect = 'none';
  document.body.style.cursor = 'ew-resize';

  // 拖拽时禁用 iframe 的 pointer-events，防止 iframe 截获 mousemove 事件导致拖拽卡住
  const iframes = document.querySelectorAll('.plugin-page-frame');
  iframes.forEach((el) => { el.style.pointerEvents = 'none'; });

  const startX = event.clientX;
  const startWidth = sidebarWidth.value;

  function onMouseMoveResize(event) {
    if (!isResizing.value) return;

    const deltaX = event.clientX - startX;
    const newWidth = Math.max(minSidebarWidth, Math.min(maxSidebarWidth, startWidth + deltaX));
    sidebarWidth.value = newWidth;
  }

  function onMouseUpResize() {
    isResizing.value = false;
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
    iframes.forEach((el) => { el.style.pointerEvents = ''; });
    document.removeEventListener('mousemove', onMouseMoveResize);
    document.removeEventListener('mouseup', onMouseUpResize);
  }

  document.addEventListener('mousemove', onMouseMoveResize);
  document.addEventListener('mouseup', onMouseUpResize);
}

</script>

<template>
  <v-navigation-drawer
    left
    v-model="customizer.Sidebar_drawer"
    elevation="0"
    rail-width="80"
    app
    class="leftSidebar"
    :width="sidebarWidth"
    :rail="isRailSidebar"
  >
    <div class="sidebar-container">
      <div v-if="!isRailSidebar" class="sidebar-brand">
        <img
          class="sidebar-brand-logo"
          src="@/assets/images/plugin_icon.png"
          alt="AstrBot logo"
        >
        <div class="sidebar-brand-copy">
          <span class="sidebar-brand-title">AstrBot</span>
          <span class="sidebar-brand-subtitle">WebUI</span>
        </div>
      </div>

      <v-list :class="['pa-4', 'listitem', 'flex-grow-1', { 'hidden-scrollbar': isRailSidebar }]" v-model:opened="openedItems" :open-strategy="'multiple'">
        <template v-for="(item, i) in sidebarMenu" :key="item.title || item.to || `sidebar-item-${i}`">
          <NavItem :item="item" class="leftPadding" :rail="isRailSidebar" />
        </template>
      </v-list>
      <div class="sidebar-footer">
        <v-btn class="sidebar-footer-btn" :class="{ 'sidebar-footer-icon-btn': isRailSidebar }" :size="isRailSidebar ? 'default' : 'small'"
          variant="text" to="/settings"
          :prepend-icon="isRailSidebar ? undefined : 'mdi-cog'" :aria-label="t('core.navigation.settings')">
          <v-icon v-if="isRailSidebar" icon="mdi-cog" />
          <template v-else>{{ t('core.navigation.settings') }}</template>
          <v-tooltip v-if="isRailSidebar" activator="parent" location="right" :text="t('core.navigation.settings')" open-delay="180" />
        </v-btn>
      </div>
    </div>
    
    <div 
      v-if="!isRailSidebar && !isMobile && customizer.Sidebar_drawer"
      class="sidebar-resize-handle"
      @mousedown="startSidebarResize"
      :class="{ 'resizing': isResizing }"
    >
    </div>
  </v-navigation-drawer>
  
</template>

<style scoped>
.sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  width: 4px;
  height: 100%;
  background: transparent;
  cursor: ew-resize;
  user-select: none;
  z-index: 1000;
  transition: background-color 0.2s ease;
}

.sidebar-resize-handle:hover,
.sidebar-resize-handle.resizing {
  background: rgba(var(--v-theme-primary), 0.3);
}

.sidebar-resize-handle::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 30px;
  background: rgba(var(--v-theme-on-surface), 0.3);
  border-radius: 1px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.sidebar-resize-handle:hover::before,
.sidebar-resize-handle.resizing::before {
  opacity: 1;
}

/* 确保侧边栏容器支持相对定位 */
.leftSidebar .v-navigation-drawer__content {
  position: relative;
}

.leftSidebar:not(.v-navigation-drawer--rail) .sidebar-footer {
  align-items: stretch;
  padding: 10px 16px 16px !important;
  border-top: 1px solid rgba(var(--v-theme-borderLight), 0.35);
}

.leftSidebar:not(.v-navigation-drawer--rail) .sidebar-footer-btn {
  width: 100% !important;
  max-width: none !important;
  min-height: 40px;
  justify-content: flex-start !important;
  border-radius: 12px !important;
  color: rgba(var(--v-theme-on-surface), 0.76);
  font-weight: 500;
  letter-spacing: 0;
  padding-inline: 12px !important;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;
}

.leftSidebar:not(.v-navigation-drawer--rail) .sidebar-footer-btn:hover,
.leftSidebar:not(.v-navigation-drawer--rail) .sidebar-footer-btn.v-btn--active {
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.09);
}

.leftSidebar:not(.v-navigation-drawer--rail) .sidebar-footer-btn :deep(.v-btn__content) {
  justify-content: flex-start;
  gap: 8px;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 64px;
  padding: 14px 18px 10px;
  border-bottom: 1px solid rgba(var(--v-theme-borderLight), 0.35);
  flex-shrink: 0;
}

.sidebar-brand-logo {
  width: 36px;
  height: 36px;
  object-fit: contain;
  flex: 0 0 auto;
}

.sidebar-brand-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.1;
}

.sidebar-brand-title {
  color: rgb(var(--v-theme-on-surface));
  font-size: 18px;
  font-weight: 800;
  white-space: nowrap;
}

.sidebar-brand-subtitle {
  margin-top: 3px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
</style>
