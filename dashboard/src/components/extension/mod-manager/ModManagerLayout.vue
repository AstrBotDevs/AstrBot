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
  failedMessage?: string
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

const shouldAutoFitMainSplit = ref(false)
const hasAutoFitMainSplit = ref(false)

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

function clampRatio(ratio: number, min: number, max: number): number {
  const lo = Math.min(min, max)
  const hi = Math.max(min, max)
  if (!Number.isFinite(ratio)) return lo
  return Math.min(hi, Math.max(lo, ratio))
}

type MeasuredPaneInfo = {
  splitContainerWidth: number
  dividerHalfWidth: number
  desiredLeftWidth: number
}

function measureDesiredLeftPaneWidth(): MeasuredPaneInfo | null {
  const splitContainer =
    (mainRef.value?.querySelector('.resizable-split-pane') as HTMLElement | null) ?? null
  const leftRoot = leftRef.value

  if (!splitContainer || !leftRoot) return null

  const splitContainerWidth = splitContainer.clientWidth
  if (!Number.isFinite(splitContainerWidth) || splitContainerWidth <= 0) return null

  const anyRowRoot =
    (leftRoot.querySelector(
      'tbody tr td .plugin-mini-avatar'
    ) as HTMLElement | null)?.closest('td')?.querySelector('div.d-flex.align-center') ??
    null

  if (!anyRowRoot) return null

  const anyNameCell = (leftRoot.querySelector('tbody tr td .plugin-mini-avatar') as HTMLElement | null)
    ?.closest('td') as HTMLElement | null
  if (!anyNameCell) return null

  const nameCellStyle = window.getComputedStyle(anyNameCell)
  const nameCellPadding =
    (Number.parseFloat(nameCellStyle.paddingLeft) || 0) +
    (Number.parseFloat(nameCellStyle.paddingRight) || 0)

  const firstRow = leftRoot.querySelector('tbody tr') as HTMLElement | null
  const firstRowCells = firstRow?.querySelectorAll('td') ?? null
  const indexCellWidth =
    firstRowCells && firstRowCells.length >= 1
      ? firstRowCells[0].getBoundingClientRect().width
      : 0
  const selectCellWidth =
    firstRowCells && firstRowCells.length >= 2
      ? firstRowCells[1].getBoundingClientRect().width
      : 0

  const rowRoots = Array.from(
    leftRoot.querySelectorAll('tbody tr td .plugin-mini-avatar')
  )
    .map(
      (el) =>
        (el as HTMLElement).closest('td')?.querySelector('div.d-flex.align-center') as HTMLElement | null
    )
    .filter((el): el is HTMLElement => Boolean(el))

  if (rowRoots.length === 0) return null

  const measureNaturalTextWidth = (el: HTMLElement): number => {
    const text = el.textContent ?? ''
    if (!text) return 0

    const body = document.body
    if (!body) {
      return el.scrollWidth
    }

    const style = window.getComputedStyle(el)
    const span = document.createElement('span')
    span.textContent = text
    span.style.position = 'absolute'
    span.style.left = '-99999px'
    span.style.top = '0'
    span.style.visibility = 'hidden'
    span.style.whiteSpace = 'nowrap'
    span.style.font = style.font
    span.style.letterSpacing = style.letterSpacing
    span.style.textTransform = style.textTransform
    span.style.padding = '0'
    span.style.margin = '0'
    span.style.border = '0'

    body.appendChild(span)
    const width = span.getBoundingClientRect().width
    span.remove()

    if (!Number.isFinite(width) || width <= 0) return 0
    return width
  }

  let maxRequiredNameCellContentWidth = 0
  for (const root of rowRoots) {
    const textEl = root.querySelector('.text-truncate') as HTMLElement | null
    if (!textEl) continue

    const rootWidth = root.getBoundingClientRect().width
    const textWidth = textEl.getBoundingClientRect().width
    const otherWidth = Math.max(0, rootWidth - textWidth)

    const naturalTextWidth = measureNaturalTextWidth(textEl)
    if (!Number.isFinite(naturalTextWidth) || naturalTextWidth <= 0) continue

    const required = otherWidth + naturalTextWidth
    if (required > maxRequiredNameCellContentWidth) {
      maxRequiredNameCellContentWidth = required
    }
  }

  if (!Number.isFinite(maxRequiredNameCellContentWidth) || maxRequiredNameCellContentWidth <= 0) return null

  const wrapper = leftRoot.querySelector('.v-data-table__wrapper') as HTMLElement | null
  const scrollBarWidth = wrapper ? Math.max(0, wrapper.offsetWidth - wrapper.clientWidth) : 0

  const desiredTableWidth =
    Math.ceil(indexCellWidth + selectCellWidth + nameCellPadding + maxRequiredNameCellContentWidth) +
    scrollBarWidth

  const dividerHalfWidth = 6

  return {
    splitContainerWidth,
    dividerHalfWidth,
    desiredLeftWidth: desiredTableWidth
  }
}

async function tryAutoFitMainSplitRatio(reason: string) {
  if (!shouldAutoFitMainSplit.value || hasAutoFitMainSplit.value) return
  if ((props.plugins?.length ?? 0) === 0) return

  await nextTick()

  const measured = measureDesiredLeftPaneWidth()
  if (!measured) return

  const minRatio = 0.125
  const maxRatio = 0.875

  const ratio =
    (measured.desiredLeftWidth + measured.dividerHalfWidth) / measured.splitContainerWidth

  mainSplitRatio.value = clampRatio(ratio, minRatio, maxRatio)
  hasAutoFitMainSplit.value = true

  debugLog('autoFitMainSplit', { reason, measured, ratio: mainSplitRatio.value })
  logLayoutSizes('autoFitMainSplit')
}

onMounted(() => {
  const mainStoredRaw = localStorage.getItem(MAIN_SPLIT_RATIO_KEY)
  const mainStored = parseStoredRatio(mainStoredRaw)
  if (mainStored != null) {
    mainSplitRatio.value = mainStored
  } else {
    shouldAutoFitMainSplit.value = true
  }

  const rightStored = parseStoredRatio(localStorage.getItem(RIGHT_PANE_RATIO_KEY))
  if (rightStored != null) {
    rightPaneRatio.value = rightStored
  }

  logLayoutSizes('mounted')
  window.setTimeout(() => logLayoutSizes('mounted+500ms'), 500)

  void tryAutoFitMainSplitRatio('mounted')
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
    void tryAutoFitMainSplitRatio('props-changed')
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
        :failed-message="failedMessage"
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