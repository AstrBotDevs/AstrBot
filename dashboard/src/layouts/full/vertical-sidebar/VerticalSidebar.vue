<script setup>
import { ArrowLeft, ChevronDown, ChevronRight, MessageCircle, PanelLeft, Settings } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useDisplay } from "vuetify";
import ChatUILogo from "@/components/chat/ChatUILogo.vue";
import { usePluginSidebarItems } from "@/composables/usePluginSidebarItems";
import { useI18n } from "@/i18n/composables";
import { useCommonStore } from "@/stores/common";
import { useMobileDrawerStore } from "@/stores/mobileDrawer";
import { applySidebarCustomization } from "@/utils/sidebarCustomization";
import { useCustomizerStore } from "../../../stores/customizer";
import NavItem from "./NavItem.vue";
import sidebarItems, { EXTENSION_GROUP_KEY } from "./sidebarItem";

const { t } = useI18n();

const customizer = useCustomizerStore();
const route = useRoute();
const router = useRouter();
const mobileDrawer = useMobileDrawerStore();
const commonStore = useCommonStore();
const { pluginItems, pluginGroups } = usePluginSidebarItems();

function buildSidebarMenu() {
  // Plugin pages are flattened into the extension group section.
  const tail = groupByPlugin.value ? pluginGroups.value : (pluginItems.value?.children ?? []);
  return [...applySidebarCustomization(sidebarItems), ...tail];
}

// Group plugin views by plugin under the extensions group; off by default.
const groupByPlugin = ref(localStorage.getItem("sidebar_group_by_plugin") === "1");
watch(groupByPlugin, (val) => {
  localStorage.setItem("sidebar_group_by_plugin", val ? "1" : "0");
  refreshSidebarMenu();
});

function toggleGroupByPlugin() {
  groupByPlugin.value = !groupByPlugin.value;
}

function collectGroupValues(items, values = new Set()) {
  items.forEach((item) => {
    if (item?.children && item.title) {
      values.add(item.value || item.title);
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
  return items.filter((item) => typeof item === "string" && groupValues.has(item));
}

function getInitialOpenedItems(menuItems) {
  try {
    const stored = JSON.parse(localStorage.getItem("sidebar_openedItems") || "[]");
    return sanitizeOpenedItems(stored, menuItems);
  } catch {
    return [];
  }
}

const sidebarMenu = shallowRef(buildSidebarMenu());

// Collapsed group headers, persisted across sessions.
const collapsedGroups = ref(JSON.parse(localStorage.getItem("sidebar_collapsed_groups") || "[]"));
watch(
  collapsedGroups,
  (val) => {
    localStorage.setItem("sidebar_collapsed_groups", JSON.stringify(val));
  },
  { deep: true },
);

function toggleGroup(header) {
  const idx = collapsedGroups.value.indexOf(header);
  if (idx >= 0) {
    collapsedGroups.value.splice(idx, 1);
  } else {
    collapsedGroups.value.push(header);
  }
}

// Pinned items (by `to`), lifted to the top of the sidebar; persisted locally.
const pinnedItems = ref(JSON.parse(localStorage.getItem("sidebar_pinned_items") || "[]"));
watch(
  pinnedItems,
  (val) => {
    localStorage.setItem("sidebar_pinned_items", JSON.stringify(val));
  },
  { deep: true },
);

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
    } else if (inExtension && item.children) {
      for (const child of item.children) {
        if (child.to) tos.add(child.to);
      }
    }
  }
  return tos;
});

// 侧边栏分组展开状态持久化
const openedItems = ref(getInitialOpenedItems(sidebarMenu.value));
watch(
  openedItems,
  (val) => {
    localStorage.setItem("sidebar_openedItems", JSON.stringify(sanitizeOpenedItems(val, sidebarMenu.value)));
  },
  { deep: true },
);

// 当插件项变化时（如插件启用/停用），刷新菜单
watch(pluginItems, () => {
  refreshSidebarMenu();
});

function refreshSidebarMenu() {
  sidebarMenu.value = buildSidebarMenu();
  openedItems.value = sanitizeOpenedItems(openedItems.value, sidebarMenu.value);
}

onMounted(() => window.addEventListener("sidebar-customization-changed", refreshSidebarMenu));
onBeforeUnmount(() => window.removeEventListener("sidebar-customization-changed", refreshSidebarMenu));

const { smAndDown: isMobile } = useDisplay();

const isChatNavigation = computed(
  () => customizer.chatNavigationInSidebar && (route.path === "/chat" || route.path.startsWith("/chat/")),
);
const isRailSidebar = computed(() => !isMobile.value && (isChatNavigation.value || customizer.mini_sidebar));

// Items visible in the sidebar: pinned extension items are lifted to the top
// of the extensions group; entries under a collapsed header are hidden
// (rail mode always shows everything).
const visibleMenu = computed(() => {
  const pinnedSet = new Set(pinnedItems.value);
  const extTos = extensionTos.value;
  const isOpen = (header) => (customizer.mini_sidebar && !isMobile.value) || !collapsedGroups.value.includes(header);
  const pinned = [];
  const result = [];
  let currentHeader = null;
  for (const item of sidebarMenu.value) {
    if (item.header) {
      currentHeader = item.header;
      result.push(item);
      continue;
    }
    if (item.children) {
      // Plugin group in group-by-plugin mode: lift pinned views out of it.
      const keptChildren = item.children.filter((child) => {
        if (pinnedSet.has(child.to) && extTos.has(child.to)) {
          pinned.push(child);
          return false;
        }
        return true;
      });
      if (isOpen(currentHeader) && keptChildren.length) {
        result.push({ ...item, children: keptChildren });
      }
      continue;
    }
    if (pinnedSet.has(item.to) && extTos.has(item.to)) {
      pinned.push(item);
      continue;
    }
    if (!currentHeader || isOpen(currentHeader)) {
      result.push(item);
    }
  }
  if (pinned.length) {
    const idx = result.findIndex((i) => i.header === EXTENSION_GROUP_KEY);
    if (idx >= 0 && isOpen(EXTENSION_GROUP_KEY)) {
      result.splice(idx + 1, 0, ...pinned);
    } else {
      result.push(...pinned);
    }
  }
  return result;
});
const botVersion = computed(() => (commonStore.astrbotVersion ? `v${commonStore.astrbotVersion}` : ""));

async function openChat() {
  if (isChatNavigation.value) {
    const previousRoute = sessionStorage.getItem("astrbot:last_bot_route") || "/";
    await router.push(previousRoute.startsWith("/chat") ? "/" : previousRoute);
    return;
  }
  sessionStorage.setItem("astrbot:last_bot_route", route.fullPath);
  const sessionId = sessionStorage.getItem("astrbot:last_chat_route");
  customizer.SET_CHAT_SIDEBAR_COLLAPSED(false);
  // Load the chat chunk before changing the layout so both drawers start together.
  await import("@/components/chat/Chat.vue");
  await router.push(sessionId ? `/chat/${sessionId}` : "/chat");
  if (isMobile.value) mobileDrawer.SET(true);
}

function toggleSidebar() {
  if (isChatNavigation.value) {
    void openChat();
    return;
  }
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
    :width="isRailSidebar ? 56 : 245"
    :order="0"
    location="left"
    floating
    app
    class="leftSidebar"
    :class="{ 'sidebar-page-navigation': customizer.chatNavigationInSidebar, 'navigation-rail': isRailSidebar, 'chat-navigation-rail': isChatNavigation }"
  >
    <div class="sidebar-container">
      <div class="dashboard-sidebar-brand" :class="{ collapsed: isRailSidebar }" data-tauri-drag-region>
        <div class="dashboard-sidebar-brand-title Outfit">
          <button
            class="dashboard-sidebar-logo-button"
            type="button"
            :disabled="!isRailSidebar"
            :aria-label="t(isChatNavigation ? 'core.navigation.backToNavigation' : 'core.navigation.expandSidebar')"
            @click.stop="toggleSidebar"
          >
            <ChatUILogo class="dashboard-sidebar-brand-logo" />
          </button>
          <span class="dashboard-sidebar-brand-copy"> <span class="dashboard-sidebar-brand-name">AstrBot</span> </span>
        </div>
        <v-btn
          class="dashboard-sidebar-brand-toggle"
          icon
          rounded="sm"
          variant="text"
          :ripple="false"
          :tabindex="isRailSidebar ? -1 : 0"
          :aria-hidden="isRailSidebar"
          :aria-label="t('core.navigation.collapseSidebar')"
          @click.stop="toggleSidebar"
        >
          <PanelLeft :size="20" class="dashboard-sidebar-panel-toggle-icon" />
        </v-btn>
      </div>

      <v-list
        :class="['dashboard-sidebar-list', 'listitem', 'flex-grow-1', { 'hidden-scrollbar': isRailSidebar }]"
        v-model:opened="openedItems"
        :open-strategy="'multiple'"
      >
        <v-list-item
          v-if="customizer.chatNavigationInSidebar"
          class="dashboard-nav-item sidebar-chat-entry"
          style="--indent-padding: 0px"
          :aria-label="t(isChatNavigation ? 'core.navigation.backToNavigation' : 'core.navigation.chat')"
          @click="openChat"
        >
          <template #prepend>
            <span class="sidebar-chat-icon" :class="{ 'is-back': isChatNavigation }">
              <MessageCircle :size="20" class="sidebar-chat-symbol" />
              <ArrowLeft :size="20" class="sidebar-back-symbol" />
            </span>
          </template>
          <v-list-item-title>{{ t('core.navigation.chat') }}</v-list-item-title>
          <template #append><ChevronRight :size="16" /></template>
          <v-tooltip
            v-if="isRailSidebar"
            activator="parent"
            location="right"
            :text="t(isChatNavigation ? 'core.navigation.backToNavigation' : 'core.navigation.chat')"
            :open-delay="0"
            content-class="sidebar-rail-tooltip"
          />
        </v-list-item>
        <template
          v-for="(item, i) in visibleMenu"
          :key="item.to || item.value || item.header || item.title || `sidebar-item-${i}`"
        >
          <div
            v-if="item.header"
            :inert="isRailSidebar || undefined"
            :aria-hidden="isRailSidebar"
            class="sidebar-group-header"
            :class="{ 'sidebar-group-header--toggle': item.collapsible }"
            @click="item.collapsible && toggleGroup(item.header)"
          >
            <span>{{ t(item.header) }}</span>
            <span class="sidebar-group-header-actions">
              <v-tooltip
                v-if="item.groupToggle"
                location="right"
                :text="groupByPlugin ? t('core.navigation.ungroupByPlugin') : t('core.navigation.groupByPlugin')"
                :open-delay="0"
                content-class="plugin-page-hover-card"
              >
                <template v-slot:activator="{ props: tooltipProps }">
                  <button
                    v-bind="tooltipProps"
                    type="button"
                    class="sidebar-group-header-icon"
                    :class="{ 'sidebar-group-header-icon--active': groupByPlugin }"
                    :aria-label="groupByPlugin ? t('core.navigation.ungroupByPlugin') : t('core.navigation.groupByPlugin')"
                    @click.stop="toggleGroupByPlugin"
                  >
                    <v-icon :icon="groupByPlugin ? 'mdi-view-grid' : 'mdi-view-grid-outline'" size="14" />
                  </button>
                </template>
              </v-tooltip>
              <ChevronRight
                v-if="item.collapsible && collapsedGroups.includes(item.header)"
                :size="14"
                class="sidebar-group-header-chevron"
              />
              <ChevronDown v-else-if="item.collapsible" :size="14" class="sidebar-group-header-chevron" />
            </span>
          </div>
          <NavItem
            v-else
            :item="item"
            class="leftPadding"
            :rail="isRailSidebar"
            :pinnable="extensionTos.has(item.to) || Boolean(item.children?.some((c) => extensionTos.has(c.to)))"
            :pinned-tos="pinnedItems"
            @toggle-pin="togglePin"
          />
        </template>
      </v-list>
      <div class="sidebar-footer" :inert="isChatNavigation || undefined" :aria-hidden="isChatNavigation">
        <v-btn
          class="sidebar-footer-btn"
          :class="{ 'sidebar-footer-icon-btn': isRailSidebar }"
          variant="text"
          to="/settings"
          :aria-label="t('core.navigation.settings')"
        >
          <Settings :size="20" class="sidebar-footer-lucide-icon" />
          <span class="sidebar-footer-label">{{ t('core.navigation.settings') }}</span>
          <v-tooltip
            v-if="isRailSidebar"
            activator="parent"
            location="right"
            :text="t('core.navigation.settings')"
            :open-delay="0"
            content-class="sidebar-rail-tooltip"
          />
        </v-btn>
        <div v-if="botVersion" class="sidebar-footer-version">{{ botVersion }}</div>
      </div>
    </div>
  </v-navigation-drawer>
</template>

<style scoped>
/* Match the shell's dynamic viewport sizing so the drawer's bottom (last nav entries
   and the Settings footer) stays above the mobile browsers' toolbar area. */
.leftSidebar {
  top: 0 !important;
  height: 100dvh !important;
  border-right: 0 !important;
  background: var(--astrbot-chrome-bg, rgb(var(--v-theme-surface))) !important;
  user-select: none;
}

.leftSidebar :deep(.v-navigation-drawer__content) {
  display: flex;
  height: 100%;
  flex-direction: column;
}

.sidebar-chat-entry :deep(.v-list-item-title) {
  font-size: 14px;
  font-weight: 500;
}

.sidebar-page-navigation .dashboard-sidebar-list {
  margin-top: 8px;
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

.sidebar-group-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.sidebar-group-header-icon {
  display: grid;
  place-items: center;
  padding: 2px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.sidebar-group-header:hover .sidebar-group-header-icon,
.sidebar-group-header-icon:focus-visible {
  opacity: 1;
}

.sidebar-group-header-icon--active {
  color: rgb(var(--v-theme-primary));
  opacity: 1;
}

.sidebar-container {
  display: flex;
  height: 100%;
  flex-direction: column;
}

/* The header draws across the whole width, above the full-height sidebar. */
:global(.leftSidebar .sidebar-container) {
  /* Seat the brand's top edge at the content area's top edge, fully below the toolbar. */
  padding-top: calc(var(--astrbot-toolbar-height, 42px) - 10px);
  box-sizing: border-box;
}

/* Off macOS the sidebar owns the top-left corner, so the brand sits in the toolbar
   band itself instead of clearing it. */
:global(html:not([data-astrbot-desktop-platform="macos"]) .leftSidebar .sidebar-container) {
  padding-top: 4px;
}

:global(html:not([data-astrbot-desktop-platform="macos"]) .leftSidebar .dashboard-sidebar-brand) {
  min-height: var(--astrbot-toolbar-height, 42px);
}

/* The shared tint is painted behind the sidebar; avoid stacking another layer. */
:global(html[data-astrbot-desktop-platform="macos"] .leftSidebar) {
  background: transparent !important;
}

/* A temporary (mobile) drawer floats above the page, so the vibrancy
   transparency would let content bleed through; keep it opaque instead. */
:global(html[data-astrbot-desktop-platform="macos"] .leftSidebar.v-navigation-drawer--temporary) {
  background: var(--astrbot-chrome-bg, rgb(var(--v-theme-surface))) !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16) !important;
  z-index: 1007 !important;
}

/* Off macOS the sidebar is opaque and owns the top-left corner: it must paint
   above the header's left zone so the brand stays visible in the toolbar band. */
:global(html:not([data-astrbot-desktop-platform="macos"]) .leftSidebar) {
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

.dashboard-sidebar-list {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 2px 16px 12px !important;
}

.leftSidebar :deep(.dashboard-nav-item) {
  min-height: 36px !important;
  margin-bottom: 2px !important;
  padding-inline-start: calc(10px + var(--indent-padding) / 2) !important;
  border-radius: var(--astrbot-radius-navigation) !important;
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
  width: 20px;
  justify-content: center;
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
  border-radius: var(--astrbot-radius-navigation) !important;
  color: rgba(var(--v-theme-on-surface), 0.76);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0;
  margin-bottom: 0 !important;
  text-transform: none;
}

.sidebar-footer-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.08) !important;
  color: rgb(var(--v-theme-on-surface));
}

/* Match the navigation items with a primary-colored active background and label. */
.sidebar-footer-btn.v-btn--active {
  background: rgba(var(--v-theme-primary), 0.09) !important;
  color: rgb(var(--v-theme-primary)) !important;
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

/* Preserve the DOM and grid so icons travel continuously while labels fade. */
.leftSidebar {
  --navigation-motion: 360ms cubic-bezier(0.22, 1, 0.36, 1);
  overflow: hidden;
  transition:
    width var(--navigation-motion),
    transform var(--navigation-motion);
}
.dashboard-sidebar-list,
.sidebar-footer,
.dashboard-sidebar-brand {
  transition:
    padding var(--navigation-motion),
    opacity 140ms ease,
    visibility 140ms;
}
.dashboard-sidebar-brand {
  position: relative;
  flex-shrink: 0;
  overflow: hidden;
}
.dashboard-sidebar-brand.collapsed {
  width: auto;
  justify-content: space-between;
  padding: 0 16px 2px 17px;
}
.dashboard-sidebar-brand-title {
  flex-shrink: 0;
}
.dashboard-sidebar-logo-button {
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: inherit;
  padding: 0;
  border-radius: 6px;
  cursor: pointer;
}
.dashboard-sidebar-logo-button:disabled {
  cursor: default;
}
.dashboard-sidebar-logo-button:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 4px;
}
.dashboard-sidebar-brand-toggle {
  position: absolute;
  right: 16px;
}
.dashboard-sidebar-brand-copy,
.dashboard-sidebar-brand-toggle,
.sidebar-footer-label,
.sidebar-footer-version,
.leftSidebar :deep(.dashboard-nav-item .v-list-item__content),
.leftSidebar :deep(.dashboard-nav-item .v-list-item__append) {
  white-space: nowrap;
  transition:
    opacity 140ms ease 120ms,
    transform var(--navigation-motion),
    visibility 0s;
}
.leftSidebar :deep(.dashboard-nav-item) {
  grid-template-columns: max-content minmax(0, 1fr) max-content;
  transition:
    padding var(--navigation-motion),
    background-color 150ms ease;
}
.leftSidebar :deep(.dashboard-nav-item .v-list-item__prepend) {
  flex-shrink: 0;
}
.sidebar-group-header {
  height: 40px;
  flex-shrink: 0;
  overflow: hidden;
  white-space: nowrap;
  transition:
    height var(--navigation-motion),
    padding var(--navigation-motion),
    opacity 120ms ease;
}
.sidebar-chat-icon {
  display: grid;
  place-items: center;
}
.sidebar-chat-icon > svg {
  grid-area: 1 / 1;
  transition:
    opacity 180ms ease,
    transform var(--navigation-motion);
}
.sidebar-back-symbol {
  opacity: 0;
  transform: translateX(8px);
}
.is-back .sidebar-chat-symbol {
  opacity: 0;
  transform: translateX(-8px);
}
.is-back .sidebar-back-symbol {
  opacity: 1;
  transform: translateX(0);
}
.navigation-rail .dashboard-sidebar-list {
  padding: 2px 10px 12px !important;
}
.navigation-rail :deep(.dashboard-nav-item) {
  padding-inline: 8px !important;
}
.navigation-rail .dashboard-sidebar-brand-copy,
.navigation-rail .dashboard-sidebar-brand-toggle,
.navigation-rail .sidebar-footer-label,
.navigation-rail .sidebar-footer-version,
.navigation-rail :deep(.dashboard-nav-item .v-list-item__content),
.navigation-rail :deep(.dashboard-nav-item .v-list-item__append) {
  opacity: 0;
  visibility: hidden;
  transform: translateX(-8px);
  transition-delay: 0s, 0s, 140ms;
  pointer-events: none;
}
.navigation-rail .sidebar-group-header {
  height: 12px;
  padding-block: 0;
  opacity: 0;
  pointer-events: none;
}
.navigation-rail .sidebar-footer {
  padding: 8px 10px 14px !important;
}
.navigation-rail .sidebar-footer-btn {
  padding-inline: 8px !important;
}
.sidebar-footer-btn {
  overflow: hidden;
  transition: padding var(--navigation-motion);
}
.sidebar-footer-btn :deep(.v-btn__content) {
  width: 100%;
}
.chat-navigation-rail .sidebar-footer {
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}
.chat-navigation-rail {
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08) !important;
}
:global(.sidebar-rail-tooltip) {
  box-shadow: none !important;
}
@media (prefers-reduced-motion: reduce) {
  .leftSidebar,
  .leftSidebar *,
  .leftSidebar :deep(*) {
    transition: none !important;
  }
}
</style>
