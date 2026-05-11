<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { usePluginConfigCache } from '@/composables/usePluginConfigCache'
import { useModuleI18n } from '@/i18n/composables'
import type { PluginPanelTab, PluginSummary } from './types'

import PluginInfoPanel from './PluginInfoPanel.vue'
import PluginConfigPanel from './PluginConfigPanel.vue'
import PluginOverviewPanel from './PluginOverviewPanel.vue'
import PluginChangelogPanel from './PluginChangelogPanel.vue'
import PluginWelcomePanel from './PluginWelcomePanel.vue'
import GlobalPanel from './GlobalPanel.vue'

const props = defineProps<{
  plugin: PluginSummary | null
  activeTab?: PluginPanelTab
  excludedTab?: PluginPanelTab | null
}>()

const emit = defineEmits<{
  (e: 'update:activeTab', tab: PluginPanelTab): void
  (e: 'action-update', name: string): void
  (e: 'config-saved', pluginName: string): void
  (e: 'detach-tab', tab: PluginPanelTab): void
}>()

const cache = usePluginConfigCache()
const { tm } = useModuleI18n('features/extension')

// All tab definitions in display order
const allTabs: { value: PluginPanelTab; labelKey: string }[] = [
  { value: 'info', labelKey: 'modManager.panelTabs.info' },
  { value: 'config', labelKey: 'modManager.panelTabs.config' },
  { value: 'overview', labelKey: 'modManager.panelTabs.overview' },
  { value: 'changelog', labelKey: 'modManager.panelTabs.changelog' },
  { value: 'reserved', labelKey: 'modManager.panelTabs.reserved' },
]

// Visible tabs (excluding currently detached tab)
const visibleTabs = computed(() =>
  allTabs.filter((t) => t.value !== props.excludedTab)
)

const normalizeTab = (tab: PluginPanelTab | undefined): PluginPanelTab => {
  // Forward-compat: legacy behavior tab merged into info
  if (tab === 'behavior') return 'info'
  const resolved = tab ?? 'info'
  // If the resolved tab is excluded, fall back to first visible
  if (resolved === props.excludedTab && visibleTabs.value.length > 0) {
    return visibleTabs.value[0].value
  }
  return resolved
}

const localActiveTab = ref<PluginPanelTab>(normalizeTab(props.activeTab))

const hasPlugin = computed(() => Boolean(props.plugin))
const pluginName = computed(() => props.plugin?.name || '')
const repoUrl = computed(() => props.plugin?.repo || null)

const isTabActive = (tab: PluginPanelTab) => localActiveTab.value === tab

const setActiveTab = (tab: PluginPanelTab) => {
  const next = normalizeTab(tab)
  if (localActiveTab.value === next) return
  localActiveTab.value = next
  emit('update:activeTab', next)
}

const openRepoInNewTab = (url: string) => {
  if (!url) return
  window.open(url, '_blank')
}

// --- Drag-to-detach with floating ghost (Chrome-like) ---
const tabBarRef = ref<HTMLElement | null>(null)
const isDraggingTab = ref(false)

const DRAG_START_THRESHOLD = 5 // px to enter drag mode

function onTabPointerDown(tab: PluginPanelTab, e: PointerEvent) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  const startX = e.clientX
  const startY = e.clientY
  const target = (e.currentTarget as HTMLElement)
  let dragging = false
  let ghost: HTMLElement | null = null

  const createGhost = () => {
    ghost = target.cloneNode(true) as HTMLElement
    ghost.style.cssText = `
      position: fixed;
      z-index: 9999;
      pointer-events: none;
      opacity: 0.85;
      box-shadow: 0 4px 16px rgba(0,0,0,0.18);
      border-radius: 8px;
      background: rgb(var(--v-theme-surface));
      padding: 6px 16px;
      font-size: 14px;
      white-space: nowrap;
      transition: transform 0.08s ease;
      transform: scale(1.05);
    `
    document.body.appendChild(ghost)
    target.style.opacity = '0.35'
    isDraggingTab.value = true
  }

  const moveGhost = (cx: number, cy: number) => {
    if (!ghost) return
    ghost.style.left = `${cx - ghost.offsetWidth / 2}px`
    ghost.style.top = `${cy - ghost.offsetHeight / 2}px`
  }

  const removeGhost = () => {
    if (ghost) {
      ghost.remove()
      ghost = null
    }
    target.style.opacity = ''
    isDraggingTab.value = false
  }

  const onMove = (ev: PointerEvent) => {
    const dx = ev.clientX - startX
    const dy = ev.clientY - startY
    if (!dragging && Math.sqrt(dx * dx + dy * dy) > DRAG_START_THRESHOLD) {
      dragging = true
      createGhost()
    }
    if (dragging) {
      moveGhost(ev.clientX, ev.clientY)
    }
  }

  const onUp = (ev: PointerEvent) => {
    cleanup()
    if (!dragging) return // Was a normal click, let v-tabs handle it

    // Determine if released below the tab bar
    const tabBar = tabBarRef.value
    if (tabBar) {
      const rect = tabBar.getBoundingClientRect()
      if (ev.clientY > rect.bottom) {
        // Released below tab bar → detach
        emit('detach-tab', tab)
      }
    }
    removeGhost()
  }

  const onCancel = () => {
    cleanup()
    removeGhost()
  }

  const cleanup = () => {
    document.removeEventListener('pointermove', onMove)
    document.removeEventListener('pointerup', onUp)
    document.removeEventListener('pointercancel', onCancel)
  }

  document.addEventListener('pointermove', onMove)
  document.addEventListener('pointerup', onUp)
  document.addEventListener('pointercancel', onCancel)
}

function handleDetachClick(tab: PluginPanelTab) {
  emit('detach-tab', tab)
}

watch(
  () => props.activeTab,
  (val) => {
    if (!val) return
    const next = normalizeTab(val)
    if (next !== localActiveTab.value) {
      localActiveTab.value = next
    }
  }
)

// When excluded tab changes, ensure current tab is still valid
watch(
  () => props.excludedTab,
  () => {
    if (localActiveTab.value === props.excludedTab) {
      const fallback = visibleTabs.value[0]?.value ?? 'info'
      setActiveTab(fallback)
    }
  }
)

watch(
  () => props.plugin?.name,
  (name, prev) => {
    if (!name) return
    if (name !== prev) {
      // Switch to info tab when selecting a new plugin
      setActiveTab('info')
      // Prefetch config (non-blocking)
      cache.prefetch(name)
    }
  },
  { immediate: true }
)
</script>

<template>
  <v-card class="h-100 d-flex flex-column plugin-panel" rounded="lg" variant="outlined">
    <PluginWelcomePanel v-if="!hasPlugin" />

    <template v-else>
      <div ref="tabBarRef" class="plugin-panel__tab-bar d-flex align-center">
        <v-tabs v-model="localActiveTab" color="primary" density="comfortable" class="flex-grow-1">
          <v-tab
            v-for="tab in visibleTabs"
            :key="tab.value"
            :value="tab.value"
            @pointerdown="onTabPointerDown(tab.value, $event)"
          >
            {{ tm(tab.labelKey) }}
          </v-tab>
        </v-tabs>

        <!-- Detach button for current active tab -->
        <v-tooltip location="bottom">
          <template #activator="{ props: tipProps }">
            <v-btn
              v-bind="tipProps"
              icon
              size="x-small"
              variant="text"
              class="mr-2"
              @click="handleDetachClick(localActiveTab)"
            >
              <v-icon size="18">mdi-arrow-expand-down</v-icon>
            </v-btn>
          </template>
          <span>弹出到底部面板</span>
        </v-tooltip>
      </div>

      <v-divider />

      <v-window v-model="localActiveTab" class="flex-grow-1 plugin-panel__window" style="min-height: 0">
        <v-window-item v-if="excludedTab !== 'info'" value="info" class="h-100">
          <div class="plugin-panel__tab plugin-panel__tab--no-scroll pa-3">
            <PluginInfoPanel
              v-if="plugin"
              :plugin="plugin"
              @action-update="emit('action-update', plugin.name)"
              @open-repo="openRepoInNewTab"
            />
          </div>
        </v-window-item>

        <v-window-item v-if="excludedTab !== 'config'" value="config" class="h-100">
          <div class="plugin-panel__tab pa-3">
            <PluginConfigPanel
              :pluginName="pluginName"
              :active="isTabActive('config')"
              @saved="(name) => emit('config-saved', name)"
              @error="() => {}"
            />
          </div>
        </v-window-item>

        <v-window-item v-if="excludedTab !== 'overview'" value="overview" class="h-100">
          <div class="plugin-panel__tab pa-3">
            <PluginOverviewPanel
              :pluginName="pluginName"
              :repoUrl="repoUrl"
              :active="isTabActive('overview')"
            />
          </div>
        </v-window-item>

        <v-window-item v-if="excludedTab !== 'changelog'" value="changelog" class="h-100">
          <div class="plugin-panel__tab pa-3">
            <PluginChangelogPanel :pluginName="pluginName" :active="isTabActive('changelog')" />
          </div>
        </v-window-item>

        <v-window-item v-if="excludedTab !== 'reserved'" value="reserved" class="h-100">
          <div class="plugin-panel__tab">
            <GlobalPanel />
          </div>
        </v-window-item>
      </v-window>
    </template>
  </v-card>
</template>

<style scoped>
.plugin-panel__tab-bar {
  flex: 0 0 auto;
}

.plugin-panel__window {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.plugin-panel__window :deep(.v-window__container) {
  min-height: 0;
  height: 100%;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.plugin-panel__window :deep(.v-window-item) {
  min-height: 0;
  height: 100%;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.plugin-panel__tab {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}

.plugin-panel__tab--no-scroll {
  overflow: hidden;
}
</style>

<!-- Global styles for drag-drop visual feedback (manipulated by external JS) -->
<style>
.plugin-panel__tab-bar--drop-target {
  background: rgba(var(--v-theme-primary), 0.10);
  box-shadow: inset 0 -3px 0 0 rgb(var(--v-theme-primary));
  transition: background 0.15s ease, box-shadow 0.15s ease;
}
</style>