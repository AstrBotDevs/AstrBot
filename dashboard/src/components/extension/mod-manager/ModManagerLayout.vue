<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useCommandConflicts } from '@/composables/useCommandConflicts'
import { usePluginConfigCache } from '@/composables/usePluginConfigCache'
import type { InstalledViewMode, PluginSummary } from './types'

import ModTopToolbar from './ModTopToolbar.vue'
import ResizableSplitPane from './ResizableSplitPane.vue'
import PluginDualList from './PluginDualList.vue'
import PluginWorkspace from './PluginWorkspace.vue'

const MAIN_SPLIT_RATIO_KEY = 'pluginManager.mainSplitRatio'
const RIGHT_PANE_RATIO_KEY = 'pluginManager.rightPaneRatio'

const props = defineProps<{
  plugins: PluginSummary[]
  loading?: boolean
  showReserved: boolean
  installedViewMode: InstalledViewMode
  updatableCount: number
  search: string
  updatingAll?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:search', value: string): void
  (e: 'update:showReserved', value: boolean): void
  (e: 'update:installedViewMode', mode: InstalledViewMode): void
  (e: 'install'): void
  (e: 'update-all'): void

  (e: 'action-enable', plugin: PluginSummary): void
  (e: 'action-disable', plugin: PluginSummary): void
  (e: 'action-reload', name: string): void
  (e: 'action-update', name: string): void
  (e: 'action-uninstall', name: string): void
  (e: 'action-configure', plugin: PluginSummary): void
  (e: 'action-open-readme', plugin: PluginSummary): void
  (e: 'action-open-repo', url: string): void

  (e: 'batch-enable', plugins: PluginSummary[]): void
  (e: 'batch-disable', plugins: PluginSummary[]): void
  (e: 'batch-update', names: string[]): void
  (e: 'batch-uninstall', names: string[]): void

  (e: 'config-saved', pluginName: string): void
  (e: 'request-open-legacy-handlers', plugin: PluginSummary): void
}>()

const rootRef = ref<HTMLElement | null>(null)
const mainRef = ref<HTMLElement | null>(null)
const leftRef = ref<HTMLElement | null>(null)
const rightRef = ref<HTMLElement | null>(null)

const debugLog = (...args: any[]) => {
  if (!import.meta.env.DEV) return
  // eslint-disable-next-line no-console
  console.log('[ModManagerLayout]', ...args)
}

const selectedPluginName = ref<string | null>(null)
const selectedInactiveNames = ref<string[]>([])
const selectedActiveNames = ref<string[]>([])

const mainSplitRatio = ref(0.5)
const rightPaneRatio = ref(0.5)

const cache = usePluginConfigCache()
const { conflicts, conflictStats, loading: conflictsLoading } = useCommandConflicts()

const selectedPlugin = computed<PluginSummary | null>(() => {
  const name = selectedPluginName.value
  if (!name) return null
  return (props.plugins ?? []).find((p) => p.name === name) ?? null
})

const selectedInactivePlugins = computed<PluginSummary[]>(() => {
  const names = new Set(selectedInactiveNames.value ?? [])
  return (props.plugins ?? []).filter((p) => names.has(p.name))
})

const selectedActivePlugins = computed<PluginSummary[]>(() => {
  const names = new Set(selectedActiveNames.value ?? [])
  return (props.plugins ?? []).filter((p) => names.has(p.name))
})

function parseStoredRatio(raw: string | null): number | null {
  if (!raw) return null
  const num = Number(raw)
  if (!Number.isFinite(num)) return null
  if (num <= 0 || num >= 1) return null
  return num
}

async function logLayoutSizes(reason: string) {
  if (!import.meta.env.DEV) return
  await nextTick()

  const info = {
    reason,
    pluginCount: props.plugins?.length ?? 0,
    firstPlugin: props.plugins?.[0]?.name ?? null,
    root: rootRef.value
      ? { w: rootRef.value.clientWidth, h: rootRef.value.clientHeight }
      : null,
    main: mainRef.value
      ? { w: mainRef.value.clientWidth, h: mainRef.value.clientHeight }
      : null,
    left: leftRef.value
      ? { w: leftRef.value.clientWidth, h: leftRef.value.clientHeight }
      : null,
    right: rightRef.value
      ? { w: rightRef.value.clientWidth, h: rightRef.value.clientHeight }
      : null
  }

  debugLog('layout', info)
}

onMounted(() => {
  const mainStored = parseStoredRatio(localStorage.getItem(MAIN_SPLIT_RATIO_KEY))
  if (mainStored != null) {
    mainSplitRatio.value = mainStored
  }

  const rightStored = parseStoredRatio(localStorage.getItem(RIGHT_PANE_RATIO_KEY))
  if (rightStored != null) {
    rightPaneRatio.value = rightStored
  }

  logLayoutSizes('mounted')
  window.setTimeout(() => logLayoutSizes('mounted+500ms'), 500)
})

watch(
  mainSplitRatio,
  (val) => {
    if (!Number.isFinite(val)) return
    localStorage.setItem(MAIN_SPLIT_RATIO_KEY, String(val))
  },
  { flush: 'post' }
)

watch(
  rightPaneRatio,
  (val) => {
    if (!Number.isFinite(val)) return
    localStorage.setItem(RIGHT_PANE_RATIO_KEY, String(val))
  },
  { flush: 'post' }
)

watch(
  () => ({
    loading: props.loading ?? false,
    pluginCount: props.plugins?.length ?? 0,
    firstPlugin: props.plugins?.[0]?.name ?? null
  }),
  (val) => {
    debugLog('props', val)
    logLayoutSizes('props-changed')
  },
  { immediate: true, flush: 'post' }
)

watch(
  () => selectedPluginName.value,
  (name) => {
    if (!name) return
    cache.prefetch(name)
  }
)

const cssEscape = (value: string) => {
  const escapeFn = (globalThis as any).CSS?.escape
  if (typeof escapeFn === 'function') return escapeFn(value)
  return value.replace(/["\\]/g, '\\$&')
}

async function scrollToPluginRow(name: string) {
  await nextTick()
  const selector = `[data-plugin-name="${cssEscape(name)}"]`
  const el = document.querySelector(selector) as HTMLElement | null
  if (!el) return

  el.scrollIntoView({
    behavior: 'smooth',
    block: 'center',
    inline: 'nearest'
  })
}

const handleSelectPlugin = async (name: string) => {
  if (!name) return
  selectedPluginName.value = name
  await scrollToPluginRow(name)
}

const handleActionConfigure = (plugin: PluginSummary) => {
  if (!plugin?.name) return
  selectedPluginName.value = plugin.name
  emit('action-configure', plugin)
}

const handleActionOpenReadme = (plugin: PluginSummary) => {
  if (!plugin?.name) return
  selectedPluginName.value = plugin.name
  emit('action-open-readme', plugin)
}

const handleToggleShowReserved = () => {
  emit('update:showReserved', !props.showReserved)
}

const handleOpenLegacyHandlers = () => {
  if (!selectedPlugin.value) return
  emit('request-open-legacy-handlers', selectedPlugin.value)
}

</script>

<template>
  <div ref="rootRef" class="mod-manager-layout d-flex flex-column">
    <div class="mod-manager-layout__top">
      <ModTopToolbar
        :search="search"
        :show-reserved="showReserved"
        :updatable-count="updatableCount"
        :updating-all="updatingAll"
        :installed-view-mode="installedViewMode"
        :selected-plugin="selectedPlugin"
        @update:search="emit('update:search', $event)"
        @toggle-show-reserved="handleToggleShowReserved"
        @install="emit('install')"
        @update-all="emit('update-all')"
        @set-view-mode="emit('update:installedViewMode', $event)"
        @open-legacy-handlers="handleOpenLegacyHandlers"
      />
    </div>

    <div ref="mainRef" class="mod-manager-layout__main d-flex flex-grow-1" style="min-height: 0">
      <ResizableSplitPane
        v-model="mainSplitRatio"
        direction="horizontal"
        :min-ratio="0.125"
        :max-ratio="0.875"
        class="mod-manager-layout__split"
      >
        <template #first>
          <div ref="leftRef" class="mod-manager-layout__left">
            <PluginDualList
              :plugins="plugins"
              :selected-plugin-name="selectedPluginName"
              :conflict-stats="conflictStats"
              :loading="loading"
              @select-plugin="handleSelectPlugin"
              @update:selectedInactive="selectedInactiveNames = $event"
              @update:selectedActive="selectedActiveNames = $event"
              @action-enable="emit('action-enable', $event)"
              @action-disable="emit('action-disable', $event)"
              @batch-enable="emit('batch-enable', $event)"
              @batch-disable="emit('batch-disable', $event)"
              @batch-update="emit('batch-update', $event)"
              @batch-uninstall="emit('batch-uninstall', $event)"
              @action-configure="handleActionConfigure"
              @action-open-readme="handleActionOpenReadme"
              @action-reload="emit('action-reload', $event)"
              @action-update="emit('action-update', $event)"
              @action-uninstall="emit('action-uninstall', $event)"
              @action-open-repo="emit('action-open-repo', $event)"
            />
          </div>
        </template>

        <template #second>
          <div ref="rightRef" class="mod-manager-layout__right">
            <PluginWorkspace
              :plugins="plugins"
              :selected-plugin-name="selectedPluginName"
              :split-ratio="rightPaneRatio"
              :conflicts="conflicts"
              :conflicts-loading="conflictsLoading"
              :show-reserved="showReserved"
              @update:splitRatio="rightPaneRatio = $event"
              @select-plugin="handleSelectPlugin"
              @action-update="emit('action-update', $event)"
              @config-saved="emit('config-saved', $event)"
            />
          </div>
        </template>
      </ResizableSplitPane>
    </div>

  </div>
</template>

<style scoped>
.mod-manager-layout {
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
  flex: 1 1 auto;
}

.mod-manager-layout__top {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 0 8px 12px;
}

.mod-manager-layout__main {
  padding: 0 8px;
  align-items: stretch;
}

.mod-manager-layout__split {
  flex: 1 1 auto;
  min-height: 0;
}

.mod-manager-layout__left {
  min-width: 190px;
  min-height: 0;
  align-self: stretch;
  display: flex;
  flex-direction: column;
}

.mod-manager-layout__right {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  align-self: stretch;
  display: flex;
  flex-direction: column;
}

.mod-manager-layout__left :deep(.plugin-dual-list) {
  flex: 1 1 auto;
  min-height: 0;
}

.mod-manager-layout__right :deep(.plugin-workspace) {
  flex: 1 1 auto;
  min-height: 0;
}
</style>