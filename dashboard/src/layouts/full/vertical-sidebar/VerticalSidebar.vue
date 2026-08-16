<script setup>
import {
  ref,
  shallowRef,
  computed,
  onMounted,
  onUnmounted,
  watch,
  defineAsyncComponent,
} from 'vue';
import { useDisplay } from 'vuetify';
import { useCustomizerStore } from '../../../stores/customizer';
import { useI18n } from '@/i18n/composables';
import sidebarItems from './sidebarItem';
import NavItem from './NavItem.vue';
import { applySidebarCustomization } from '@/utils/sidebarCustomization';

const { t } = useI18n();
const ChangelogDialog = defineAsyncComponent(
  () => import('@/components/shared/ChangelogDialog.vue'),
);

const customizer = useCustomizerStore();
const { mobile } = useDisplay();

function buildSidebarMenu() {
  return applySidebarCustomization(sidebarItems);
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
  return items.filter(
    (item) => typeof item === 'string' && groupValues.has(item),
  );
}

function getInitialOpenedItems(menuItems) {
  try {
    const stored = JSON.parse(
      localStorage.getItem('sidebar_openedItems') || '[]',
    );
    return sanitizeOpenedItems(stored, menuItems);
  } catch {
    return [];
  }
}

const sidebarMenu = shallowRef(buildSidebarMenu());

// 侧边栏分组展开状态持久化
const openedItems = ref(getInitialOpenedItems(sidebarMenu.value));
watch(
  openedItems,
  (val) => {
    localStorage.setItem(
      'sidebar_openedItems',
      JSON.stringify(sanitizeOpenedItems(val, sidebarMenu.value)),
    );
  },
  { deep: true },
);

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
  window.removeEventListener(
    'sidebar-customization-changed',
    handleCustomEvent,
  );
});

const starCount = ref(null);
const STAR_COUNT_CACHE_KEY = 'astrbot_github_star_count_cache';
const STAR_COUNT_CACHE_TTL_MS = 30 * 60 * 1000;

// 更新日志对话框
const changelogDialog = ref(false);

const sidebarWidth = ref(235);
const minSidebarWidth = 200;
const maxSidebarWidth = 300;
const isResizing = ref(false);

const isMobile = mobile;
const isRailSidebar = computed(
  () => !isMobile.value && customizer.mini_sidebar,
);

watch(
  isMobile,
  (isMobileViewport) => {
    customizer.Sidebar_drawer = !isMobileViewport;
  },
  { immediate: true },
);

function openExternalLink(url) {
  if (typeof window !== 'undefined') {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}

function startSidebarResize(event) {
  isResizing.value = true;
  document.body.style.userSelect = 'none';
  document.body.style.cursor = 'ew-resize';

  // 拖拽时禁用 iframe 的 pointer-events，防止 iframe 截获 mousemove 事件导致拖拽卡住
  const iframes = document.querySelectorAll('.plugin-page-frame');
  iframes.forEach((el) => {
    el.style.pointerEvents = 'none';
  });

  const startX = event.clientX;
  const startWidth = sidebarWidth.value;

  function onMouseMoveResize(event) {
    if (!isResizing.value) return;

    const deltaX = event.clientX - startX;
    const newWidth = Math.max(
      minSidebarWidth,
      Math.min(maxSidebarWidth, startWidth + deltaX),
    );
    sidebarWidth.value = newWidth;
  }

  function onMouseUpResize() {
    isResizing.value = false;
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
    iframes.forEach((el) => {
      el.style.pointerEvents = '';
    });
    document.removeEventListener('mousemove', onMouseMoveResize);
    document.removeEventListener('mouseup', onMouseUpResize);
  }

  document.addEventListener('mousemove', onMouseMoveResize);
  document.addEventListener('mouseup', onMouseUpResize);
}

function formatNumber(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function readCachedStarCount() {
  try {
    const raw = localStorage.getItem(STAR_COUNT_CACHE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    const cachedAt = Number(parsed?.cachedAt);
    const value = Number(parsed?.value);
    if (
      !Number.isFinite(cachedAt) ||
      !Number.isFinite(value) ||
      Date.now() - cachedAt > STAR_COUNT_CACHE_TTL_MS
    ) {
      return null;
    }
    return value;
  } catch {
    return null;
  }
}

function writeCachedStarCount(value) {
  try {
    localStorage.setItem(
      STAR_COUNT_CACHE_KEY,
      JSON.stringify({
        cachedAt: Date.now(),
        value,
      }),
    );
  } catch {
    // Ignore storage failures and keep the UI non-blocking.
  }
}

async function fetchStarCount() {
  const cachedValue = readCachedStarCount();
  if (cachedValue !== null) {
    starCount.value = cachedValue;
  }

  try {
    const response = await fetch(
      'https://api.github.com/repos/Xero-Team/AstrBot',
      {
        headers: {
          Accept: 'application/vnd.github+json',
        },
      },
    );
    if (!response.ok) {
      return;
    }
    const data = await response.json();
    const nextStarCount = Number(data?.stargazers_count);
    if (Number.isFinite(nextStarCount) && nextStarCount > 0) {
      starCount.value = nextStarCount;
      writeCachedStarCount(nextStarCount);
    }
  } catch {
    // Ignore transient network failures. The GitHub button remains usable
    // without the optional star count badge.
  }
}

void fetchStarCount();

// 打开更新日志对话框
function openChangelogDialog() {
  changelogDialog.value = true;
}
</script>

<template>
  <v-navigation-drawer
    v-model="customizer.Sidebar_drawer"
    left
    elevation="0"
    rail-width="80"
    app
    class="leftSidebar"
    :width="sidebarWidth"
    :rail="isRailSidebar"
  >
    <div class="sidebar-container">
      <v-list
        v-model:opened="openedItems"
        :class="[
          'pa-4',
          'listitem',
          'sidebar-navigation',
          { 'hidden-scrollbar': isRailSidebar },
        ]"
        :open-strategy="'multiple'"
      >
        <template
          v-for="(item, i) in sidebarMenu"
          :key="item.title || item.to || `sidebar-item-${i}`"
        >
          <NavItem :item="item" class="leftPadding" :rail="isRailSidebar" />
        </template>
      </v-list>
      <div v-if="!isRailSidebar" class="sidebar-footer">
        <v-btn
          class="sidebar-footer-btn"
          size="small"
          variant="tonal"
          color="primary"
          to="/settings"
          prepend-icon="mdi-cog"
        >
          {{ t('core.navigation.settings') }}
        </v-btn>
        <v-btn
          class="sidebar-footer-btn"
          size="small"
          variant="text"
          prepend-icon="mdi-note-text-outline"
          @click="openChangelogDialog"
        >
          {{ t('core.navigation.changelog') }}
        </v-btn>
        <v-btn
          class="sidebar-footer-btn"
          size="small"
          variant="text"
          prepend-icon="mdi-github"
          @click="openExternalLink('https://github.com/Xero-Team/AstrBot')"
        >
          {{ t('core.navigation.github') }}
          <v-chip
            v-if="starCount"
            size="x-small"
            variant="outlined"
            class="ml-2 github-star-count"
            >{{ formatNumber(starCount) }}</v-chip
          >
        </v-btn>
      </div>
      <div v-else class="sidebar-footer sidebar-footer-rail">
        <v-tooltip
          location="right"
          :text="t('core.navigation.settings')"
          open-delay="180"
        >
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              class="sidebar-footer-icon-btn"
              variant="text"
              to="/settings"
              :aria-label="t('core.navigation.settings')"
            >
              <v-icon icon="mdi-cog" />
            </v-btn>
          </template>
        </v-tooltip>
        <v-tooltip
          location="right"
          :text="t('core.navigation.changelog')"
          open-delay="180"
        >
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              class="sidebar-footer-icon-btn"
              variant="text"
              :aria-label="t('core.navigation.changelog')"
              @click="openChangelogDialog"
            >
              <v-icon icon="mdi-note-text-outline" />
            </v-btn>
          </template>
        </v-tooltip>
        <v-tooltip location="right" text="GitHub" open-delay="180">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              class="sidebar-footer-icon-btn"
              variant="text"
              aria-label="GitHub"
              @click="openExternalLink('https://github.com/Xero-Team/AstrBot')"
            >
              <v-icon icon="mdi-github" />
            </v-btn>
          </template>
        </v-tooltip>
      </div>
    </div>

    <div
      v-if="!isRailSidebar && !isMobile && customizer.Sidebar_drawer"
      class="sidebar-resize-handle"
      :class="{ resizing: isResizing }"
      @mousedown="startSidebarResize"
    ></div>
  </v-navigation-drawer>

  <!-- 更新日志对话框 -->
  <ChangelogDialog v-model="changelogDialog" />
</template>

<style scoped>
.sidebar-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.sidebar-navigation {
  min-height: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.sidebar-footer {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px max(12px, env(safe-area-inset-bottom));
  border-top: 1px solid rgb(var(--v-theme-outline-variant));
  background: rgb(var(--v-theme-surface));
}

.sidebar-footer-btn {
  width: 100%;
  height: 40px;
  min-height: 40px;
  justify-content: flex-start;
  text-align: left;
}

.sidebar-footer-rail {
  align-items: center;
  padding-inline: 12px;
}

.sidebar-footer-icon-btn {
  min-width: 40px;
}

.sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  width: 4px;
  height: 100%;
  background: transparent;
  cursor: ew-resize;
  user-select: none;
  z-index: 2;
  transition: background-color 0.2s ease;
}

.sidebar-resize-handle:hover,
.sidebar-resize-handle.resizing {
  background: rgba(var(--v-theme-primary), 0.3);
}

.github-star-count {
  font-weight: 400;
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
</style>
