<script setup>
import { ref, shallowRef, computed, onMounted, onUnmounted, watch } from 'vue';
import { useCustomizerStore } from '../../../stores/customizer';
import { useMobileDrawerStore } from '@/stores/mobileDrawer';
import { useI18n } from '@/i18n/composables';
import sidebarItems, { MORE_GROUP_KEY } from './sidebarItem';
import NavItem from './NavItem.vue';
import { applySidebarCustomization } from '@/utils/sidebarCustomization';
import { usePluginSidebarItems } from '@/composables/usePluginSidebarItems';
import { useDisplay } from 'vuetify';
import { PanelLeft, Settings } from '@lucide/vue';
import ChatUILogo from '@/components/chat/ChatUILogo.vue';
import { useCommonStore } from '@/stores/common';

const { t } = useI18n();

const customizer = useCustomizerStore();
const mobileDrawer = useMobileDrawerStore();
const commonStore = useCommonStore();
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

const { smAndDown: isMobile } = useDisplay();

const isRailSidebar = computed(
  () => !isMobile.value && customizer.mini_sidebar,
);
const botVersion = computed(() => commonStore.astrbotVersion ? `v${commonStore.astrbotVersion}` : '');

function toggleSidebar() {
  if (isMobile.value) {
    mobileDrawer.SET(false);
    return;
  }
  customizer.SET_MINI_SIDEBAR(!customizer.mini_sidebar);
}

</script>

<template>
  <v-navigation-drawer
    :model-value="isMobile ? mobileDrawer.open : true"
    @update:model-value="isMobile && mobileDrawer.SET($event)"
    :permanent="!isMobile"
    :temporary="isMobile"
    :mobile-breakpoint="0"
    elevation="0"
    rail-width="56"
    width="245"
    location="left"
    floating
    app
    class="leftSidebar"
    :rail="isRailSidebar"
  >
    <div class="sidebar-container">
      <div class="dashboard-sidebar-brand" :class="{ collapsed: isRailSidebar }" data-tauri-drag-region>
        <div v-if="!isRailSidebar" class="dashboard-sidebar-brand-title Outfit">
          <ChatUILogo class="dashboard-sidebar-brand-logo" />
          <span class="dashboard-sidebar-brand-copy">
            <span class="dashboard-sidebar-brand-name">AstrBot</span>
            <span v-if="botVersion" class="dashboard-sidebar-brand-version">{{ botVersion }}</span>
          </span>
        </div>
        <button
          v-if="isRailSidebar"
          class="dashboard-sidebar-brand-toggle dashboard-sidebar-rail-btn"
          type="button"
          :aria-label="t('core.navigation.expandSidebar')"
          @click.stop="toggleSidebar"
        >
          <span class="dashboard-sidebar-rail-icon-stack">
            <ChatUILogo class="dashboard-sidebar-brand-logo dashboard-sidebar-brand-logo--collapsed" />
            <PanelLeft :size="20" class="dashboard-sidebar-panel-toggle-icon" />
          </span>
        </button>
        <v-btn
          v-else
          class="dashboard-sidebar-brand-toggle"
          icon
          rounded="sm"
          variant="text"
          :ripple="false"
          :aria-label="t('core.navigation.collapseSidebar')"
          @click.stop="toggleSidebar"
        >
          <PanelLeft :size="20" class="dashboard-sidebar-panel-toggle-icon" />
        </v-btn>
      </div>

      <v-list :class="['dashboard-sidebar-list', 'listitem', 'flex-grow-1', { 'hidden-scrollbar': isRailSidebar }]" v-model:opened="openedItems" :open-strategy="'multiple'">
        <template v-for="(item, i) in sidebarMenu" :key="item.title || item.to || `sidebar-item-${i}`">
          <NavItem :item="item" class="leftPadding" :rail="isRailSidebar" />
        </template>
      </v-list>
      <div class="sidebar-footer">
        <v-btn class="sidebar-footer-btn" :class="{ 'sidebar-footer-icon-btn': isRailSidebar }"
          variant="text" :icon="isRailSidebar" to="/settings" :aria-label="t('core.navigation.settings')">
          <Settings :size="20" class="sidebar-footer-lucide-icon" />
          <span v-if="!isRailSidebar">{{ t('core.navigation.settings') }}</span>
          <v-tooltip v-if="isRailSidebar" activator="parent" location="right" :text="t('core.navigation.settings')" :open-delay="0" />
        </v-btn>
      </div>
    </div>
  </v-navigation-drawer>
  
</template>

<style scoped>
.leftSidebar {
  top: 0 !important;
  height: 100vh !important;
  border-right: 0 !important;
  background: rgb(var(--v-theme-surface)) !important;
  user-select: none;
}

.leftSidebar :deep(.v-navigation-drawer__content) {
  display: flex;
  height: 100%;
  flex-direction: column;
}

.sidebar-container {
  display: flex;
  height: 100%;
  flex-direction: column;
}

/* The header draws across the whole width, above the full-height sidebar. */
:global(.leftSidebar .sidebar-container) {
  /* Seat the brand's top edge at the content area's top edge, fully below the toolbar. */
  padding-top: calc(var(--astrbot-toolbar-height, 40px) - 10px);
  box-sizing: border-box;
}

/* Off macOS the sidebar owns the top-left corner, so the brand sits in the toolbar
   band itself instead of clearing it. */
:global(html:not([data-astrbot-desktop-platform='macos']) .leftSidebar .sidebar-container) {
  padding-top: 4px;
}

:global(html:not([data-astrbot-desktop-platform='macos']) .leftSidebar .dashboard-sidebar-brand) {
  min-height: var(--astrbot-toolbar-height, 40px);
}

/* On macOS the sidebar stays transparent; the shared tint is painted behind it. */
:global(html[data-astrbot-desktop-platform='macos'] .leftSidebar) {
  background: transparent !important;
}

/* Off macOS the sidebar is opaque and owns the top-left corner: it must paint
   above the header's left zone so the brand stays visible in the toolbar band. */
:global(html:not([data-astrbot-desktop-platform='macos']) .leftSidebar) {
  z-index: 1007 !important;
}

.dashboard-sidebar-brand {
  display: flex;
  min-height: 50px;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 16px 2px 24px;
}

/* Force the brand onto its own compositing layer: on the macOS vibrancy window
   the inline SVG logo can fail to paint after a webview reload. */
.dashboard-sidebar-brand .dashboard-sidebar-brand-logo {
  transform: translateZ(0);
}

.dashboard-sidebar-brand.collapsed {
  width: 56px;
  justify-content: center;
  padding: 0 0 2px;
}

.dashboard-sidebar-brand-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  color: rgb(var(--v-theme-on-surface));
  line-height: 1.05;
}

.dashboard-sidebar-brand-logo {
  display: block;
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
}

.dashboard-sidebar-brand-copy {
  display: inline-flex;
  min-width: 0;
  align-items: baseline;
  gap: 6px;
}

.dashboard-sidebar-brand-name {
  font-size: 18px;
  font-weight: 800;
}

.dashboard-sidebar-brand-version {
  color: rgba(var(--v-theme-on-surface), 0.46);
  font-size: 11px;
  font-weight: 500;
}

.dashboard-sidebar-brand-toggle {
  width: 36px;
  height: 36px;
  min-width: 36px;
  background: transparent !important;
  box-shadow: none !important;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.dashboard-sidebar-brand-toggle :deep(.v-btn__overlay) {
  opacity: 0 !important;
}

.dashboard-sidebar-brand-toggle:hover {
  background: transparent !important;
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.dashboard-sidebar-rail-btn {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
}

.dashboard-sidebar-rail-icon-stack {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
}

.dashboard-sidebar-rail-icon-stack > * {
  grid-area: 1 / 1;
}

.dashboard-sidebar-brand-logo--collapsed,
.dashboard-sidebar-panel-toggle-icon {
  transition:
    opacity 0.14s ease,
    visibility 0.14s ease;
}

.dashboard-sidebar-brand-logo--collapsed {
  width: 20px;
  height: 20px;
  opacity: 1;
  visibility: visible;
}

.dashboard-sidebar-rail-icon-stack .dashboard-sidebar-panel-toggle-icon {
  opacity: 0;
  visibility: hidden;
}

.dashboard-sidebar-brand-toggle:hover .dashboard-sidebar-brand-logo--collapsed,
.dashboard-sidebar-brand-toggle:focus-visible .dashboard-sidebar-brand-logo--collapsed {
  opacity: 0;
  visibility: hidden;
}

.dashboard-sidebar-brand-toggle:hover .dashboard-sidebar-panel-toggle-icon,
.dashboard-sidebar-brand-toggle:focus-visible .dashboard-sidebar-panel-toggle-icon {
  opacity: 1;
  visibility: visible;
}

.dashboard-sidebar-list {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 2px 16px 12px !important;
}

.leftSidebar :deep(.dashboard-nav-item) {
  min-height: 36px !important;
  margin-bottom: 2px !important;
  padding-inline-start: calc(10px + var(--indent-padding) / 2) !important;
  border-radius: 8px !important;
  color: rgba(var(--v-theme-on-surface), 0.76) !important;
}

.leftSidebar :deep(.dashboard-nav-item:hover) {
  background: rgba(var(--v-theme-on-surface), 0.05) !important;
  color: rgb(var(--v-theme-on-surface)) !important;
}

.leftSidebar :deep(.dashboard-nav-item.v-list-item--active) {
  background: rgba(var(--v-theme-primary), 0.08) !important;
  color: rgb(var(--v-theme-primary)) !important;
}

/* Expandable group headers stay un-highlighted even while the group is open. */
.leftSidebar :deep(.dashboard-nav-item.v-list-group__header),
.leftSidebar :deep(.dashboard-nav-item.v-list-group__header.v-list-item--active) {
  background: transparent !important;
}

.leftSidebar :deep(.dashboard-nav-item .v-list-item__prepend) {
  min-width: 0;
  margin-inline-end: 12px;
}

.leftSidebar :deep(.dashboard-nav-item .v-list-item__spacer) {
  width: 0;
}

.sidebar-footer {
  display: flex;
  flex: 0 0 auto;
  align-items: stretch;
  padding: 8px 16px 14px !important;
}

.sidebar-footer-btn {
  width: 100% !important;
  max-width: none !important;
  min-height: 36px !important;
  justify-content: flex-start !important;
  gap: 12px;
  padding-inline: 10px !important;
  border-radius: 8px !important;
  color: rgba(var(--v-theme-on-surface), 0.76);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0;
  margin-bottom: 0 !important;
  text-transform: none;
}

.sidebar-footer-btn:hover,
.sidebar-footer-btn.v-btn--active {
  background: rgba(var(--v-theme-on-surface), 0.08) !important;
  color: rgb(var(--v-theme-on-surface));
}

.sidebar-footer-btn :deep(.v-btn__content) {
  justify-content: flex-start;
  gap: 12px;
}

.sidebar-footer-lucide-icon {
  flex: 0 0 auto;
  stroke-width: 2;
}

.leftSidebar.v-navigation-drawer--rail .dashboard-sidebar-list {
  padding: 2px 10px 12px !important;
}

.leftSidebar.v-navigation-drawer--rail :deep(.rail-group) {
  width: 36px;
  margin: 0 auto 2px;
  padding: 0;
  background: transparent;
}

.leftSidebar.v-navigation-drawer--rail :deep(.dashboard-nav-item) {
  width: 36px !important;
  min-width: 36px !important;
  max-width: 36px !important;
  min-height: 36px !important;
  margin: 0 auto 2px !important;
  padding: 0 !important;
  grid-template-areas: "prepend" !important;
  grid-template-columns: 1fr !important;
  place-items: center;
  box-shadow: none !important;
}

/* Keep the rail flat on hover: no shadow, and hovering the active item must not
   stack an extra primary overlay that reads as a glow. */
.leftSidebar.v-navigation-drawer--rail :deep(.dashboard-nav-item:hover),
.leftSidebar.v-navigation-drawer--rail :deep(.dashboard-nav-item.v-list-item--active:hover) {
  box-shadow: none !important;
}

.leftSidebar.v-navigation-drawer--rail :deep(.dashboard-nav-item.v-list-item--active .v-list-item__overlay) {
  opacity: 0 !important;
}

/* Rail tooltips stay, but they must read as plain chips: no drop shadow. */
:global(.v-tooltip > .v-overlay__content) {
  box-shadow: none !important;
}

.leftSidebar.v-navigation-drawer--rail :deep(.dashboard-nav-item .v-list-item__prepend) {
  grid-area: prepend;
  width: 100%;
  justify-content: center;
  margin: 0;
}

.leftSidebar.v-navigation-drawer--rail :deep(.dashboard-nav-item .v-list-item__content),
.leftSidebar.v-navigation-drawer--rail :deep(.dashboard-nav-item .v-list-item__append),
.leftSidebar.v-navigation-drawer--rail :deep(.dashboard-nav-item .v-list-item__spacer) {
  display: none;
}

.leftSidebar.v-navigation-drawer--rail .sidebar-footer {
  justify-content: center;
  padding: 8px 10px 14px !important;
}

.leftSidebar.v-navigation-drawer--rail .sidebar-footer-btn {
  width: 36px !important;
  min-width: 36px !important;
  max-width: 36px !important;
  height: 36px !important;
  min-height: 36px !important;
  justify-content: center !important;
  padding: 0 !important;
}

.leftSidebar.v-navigation-drawer--rail .sidebar-footer-btn :deep(.v-btn__content) {
  justify-content: center;
}

@media (prefers-reduced-motion: reduce) {
  .dashboard-sidebar-brand-logo--collapsed,
  .dashboard-sidebar-panel-toggle-icon,
  .sidebar-footer-btn {
    transition: none !important;
  }
}
</style>
