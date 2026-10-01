<script setup>
import { ref, shallowRef, computed, watch } from 'vue';
import { useCustomizerStore } from '../../../stores/customizer';
import { useMobileDrawerStore } from '@/stores/mobileDrawer';
import { useI18n } from '@/i18n/composables';
import sidebarItems, { EXTENSION_GROUP_KEY } from './sidebarItem';
import NavItem from './NavItem.vue';
import { usePluginSidebarItems } from '@/composables/usePluginSidebarItems';
import { useDisplay } from 'vuetify';
import { ChevronDown, ChevronRight, PanelLeft, Settings } from '@lucide/vue';
import ChatUILogo from '@/components/chat/ChatUILogo.vue';
import { useCommonStore } from '@/stores/common';

const { t } = useI18n();

const customizer = useCustomizerStore();
const mobileDrawer = useMobileDrawerStore();
const commonStore = useCommonStore();
const { pluginItems } = usePluginSidebarItems();

function buildSidebarMenu() {
  // Plugin pages are flattened into the extension group section.
  const pluginChildren = pluginItems.value?.children ?? [];
  return [...sidebarItems, ...pluginChildren];
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

// Collapsed group headers, persisted across sessions.
const collapsedGroups = ref(JSON.parse(localStorage.getItem('sidebar_collapsed_groups') || '[]'));
watch(collapsedGroups, (val) => {
  localStorage.setItem('sidebar_collapsed_groups', JSON.stringify(val));
}, { deep: true });

function toggleGroup(header) {
  const idx = collapsedGroups.value.indexOf(header);
  if (idx >= 0) {
    collapsedGroups.value.splice(idx, 1);
  } else {
    collapsedGroups.value.push(header);
  }
}

// Pinned items (by `to`), lifted to the top of the sidebar; persisted locally.
const pinnedItems = ref(JSON.parse(localStorage.getItem('sidebar_pinned_items') || '[]'));
watch(pinnedItems, (val) => {
  localStorage.setItem('sidebar_pinned_items', JSON.stringify(val));
}, { deep: true });

function togglePin(item) {
  const idx = pinnedItems.value.indexOf(item.to);
  if (idx >= 0) {
    pinnedItems.value.splice(idx, 1);
  } else {
    pinnedItems.value.push(item.to);
  }
}

// `to` values of items under the extensions group header (incl. plugin pages).
const extensionTos = computed(() => {
  const tos = new Set();
  let inExtension = false;
  for (const item of sidebarMenu.value) {
    if (item.header) {
      inExtension = item.header === EXTENSION_GROUP_KEY;
    } else if (inExtension && item.to) {
      tos.add(item.to);
    }
  }
  return tos;
});

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

const { smAndDown: isMobile } = useDisplay();

const isRailSidebar = computed(
  () => !isMobile.value && customizer.mini_sidebar,
);

// Items visible in the sidebar: pinned extension items are lifted to the top
// of the extensions group; entries under a collapsed header are hidden
// (rail mode always shows everything).
const visibleMenu = computed(() => {
  const pinnedSet = new Set(pinnedItems.value);
  const pinned = sidebarMenu.value.filter(
    (item) => !item.header && pinnedSet.has(item.to) && extensionTos.value.has(item.to),
  );
  const result = [];
  let currentHeader = null;
  for (const item of sidebarMenu.value) {
    if (item.header) {
      currentHeader = item.header;
      result.push(item);
      if (
        item.header === EXTENSION_GROUP_KEY
        && (isRailSidebar.value || !collapsedGroups.value.includes(item.header))
      ) {
        result.push(...pinned);
      }
    } else if (pinnedSet.has(item.to) && extensionTos.value.has(item.to)) {
      continue;
    } else if (isRailSidebar.value || !currentHeader || !collapsedGroups.value.includes(currentHeader)) {
      result.push(item);
    }
  }
  return result;
});
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
        <template v-for="(item, i) in visibleMenu" :key="item.header || item.title || item.to || `sidebar-item-${i}`">
          <div
            v-if="item.header"
            v-show="!isRailSidebar"
            class="sidebar-group-header"
            :class="{ 'sidebar-group-header--toggle': item.collapsible }"
            @click="item.collapsible && toggleGroup(item.header)"
          >
            <span>{{ t(item.header) }}</span>
            <ChevronRight
              v-if="item.collapsible && collapsedGroups.includes(item.header)"
              :size="14"
              class="sidebar-group-header-chevron"
            />
            <ChevronDown
              v-else-if="item.collapsible"
              :size="14"
              class="sidebar-group-header-chevron"
            />
          </div>
          <NavItem
            v-else
            :item="item"
            class="leftPadding"
            :rail="isRailSidebar"
            :pinnable="extensionTos.has(item.to)"
            :pinned="pinnedItems.includes(item.to)"
            @toggle-pin="togglePin"
          />
        </template>
      </v-list>
      <div class="sidebar-footer">
        <v-btn class="sidebar-footer-btn" :class="{ 'sidebar-footer-icon-btn': isRailSidebar }"
          variant="text" :icon="isRailSidebar" to="/settings" :aria-label="t('core.navigation.settings')">
          <Settings :size="20" class="sidebar-footer-lucide-icon" />
          <span v-if="!isRailSidebar">{{ t('core.navigation.settings') }}</span>
          <v-tooltip
            v-if="isRailSidebar"
            activator="parent"
            location="right"
            :text="t('core.navigation.settings')"
            :open-delay="0"
            content-class="sidebar-rail-tooltip"
          />
        </v-btn>
        <div v-if="!isRailSidebar && botVersion" class="sidebar-footer-version">{{ botVersion }}</div>
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

.sidebar-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 10px 8px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  line-height: 16px;
  text-transform: uppercase;
  user-select: none;
}

.sidebar-group-header:first-child {
  padding-top: 4px;
}

.sidebar-group-header--toggle {
  cursor: pointer;
}

.sidebar-group-header--toggle:hover {
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.sidebar-group-header-chevron {
  flex: 0 0 auto;
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

/* A temporary (mobile) drawer floats above the page, so the vibrancy
   transparency would let content bleed through; keep it opaque instead. */
:global(html[data-astrbot-desktop-platform='macos'] .leftSidebar.v-navigation-drawer--temporary) {
  background: rgb(var(--v-theme-surface)) !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16) !important;
  z-index: 1007 !important;
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
  flex-direction: column;
  align-items: stretch;
  padding: 8px 16px 14px !important;
}

.sidebar-footer-version {
  margin-top: 2px;
  padding-inline: 10px;
  text-align: left;
  color: rgba(var(--v-theme-on-surface), 0.46);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.sidebar-footer-btn {
  width: 100% !important;
  max-width: none !important;
  min-height: 36px !important;
  justify-content: flex-start !important;
  gap: 0;
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

/* Icon-to-label spacing matches the nav items above (10px); the v-btn grid
   gap stays 0 so the gear lines up with the nav icons. */
.sidebar-footer-btn :deep(.v-btn__content) {
  justify-content: flex-start;
  gap: 10px;
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
:global(.sidebar-rail-tooltip) {
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
