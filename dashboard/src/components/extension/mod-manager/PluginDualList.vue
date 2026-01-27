<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ConflictStats, PluginSummary } from './types'
import ResizableSplitPane from './ResizableSplitPane.vue'
import PluginListTable from './PluginListTable.vue'

const LIST_SPLIT_RATIO_KEY = 'pluginManager.dualListRatio'

function parseStoredRatio(raw: string | null): number | null {
  if (!raw) return null
  const num = Number(raw)
  if (!Number.isFinite(num)) return null
  if (num <= 0 || num >= 1) return null
  return num
}

const props = defineProps<{
  plugins: PluginSummary[]
  selectedPluginName: string | null
  conflictStats: ConflictStats
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'select-plugin', name: string): void
  (e: 'update:selectedInactive', names: string[]): void
  (e: 'update:selectedActive', names: string[]): void
  (e: 'action-enable', plugin: PluginSummary): void
  (e: 'action-disable', plugin: PluginSummary): void
  (e: 'action-configure', plugin: PluginSummary): void
  (e: 'action-open-readme', plugin: PluginSummary): void
  (e: 'action-reload', name: string): void
  (e: 'action-update', name: string): void
  (e: 'action-uninstall', name: string): void
  (e: 'action-open-repo', url: string): void
  (e: 'batch-enable', plugins: PluginSummary[]): void
  (e: 'batch-disable', plugins: PluginSummary[]): void
  (e: 'batch-update', names: string[]): void
  (e: 'batch-uninstall', names: string[]): void
}>()

const selectedInactiveNames = ref<string[]>([])
const selectedActiveNames = ref<string[]>([])

const splitRatio = ref(parseStoredRatio(localStorage.getItem(LIST_SPLIT_RATIO_KEY)) ?? 0.5)

watch(
  splitRatio,
  (val) => {
    if (!Number.isFinite(val)) return
    localStorage.setItem(LIST_SPLIT_RATIO_KEY, String(val))
  },
  { flush: 'post' }
)

watch(
  selectedInactiveNames,
  (val) => emit('update:selectedInactive', val ?? []),
  { deep: true }
)
watch(
  selectedActiveNames,
  (val) => emit('update:selectedActive', val ?? []),
  { deep: true }
)

const inactivePlugins = computed(() => (props.plugins ?? []).filter((p) => !p.activated))
const activePlugins = computed(() => (props.plugins ?? []).filter((p) => p.activated))

const handleRowClick = (name: string) => emit('select-plugin', name)

const handlePrimaryInactive = (plugin: PluginSummary) => emit('action-enable', plugin)
const handlePrimaryActive = (plugin: PluginSummary) => emit('action-disable', plugin)
</script>

<template>
  <div class="plugin-dual-list">
    <ResizableSplitPane
      v-model="splitRatio"
      direction="vertical"
      :min-ratio="0.15"
      :max-ratio="0.85"
    >
      <template #first>
        <div class="plugin-dual-list__pane">
          <PluginListTable
            title="已激活插件"
            mode="active"
            :items="activePlugins"
            :selected-names="selectedActiveNames"
            :selected-plugin-name="selectedPluginName"
            :conflict-stats="conflictStats"
            :loading="loading"
            @update:selected-names="selectedActiveNames = $event"
            @row-click="handleRowClick"
            @action-primary="handlePrimaryActive"
            @batch-primary="emit('batch-disable', $event)"
            @batch-update="emit('batch-update', $event)"
            @batch-uninstall="emit('batch-uninstall', $event)"
            @clear-selection="selectedActiveNames = []"
            @action-configure="emit('action-configure', $event)"
            @action-open-readme="emit('action-open-readme', $event)"
            @action-reload="emit('action-reload', $event)"
            @action-update="emit('action-update', $event)"
            @action-uninstall="emit('action-uninstall', $event)"
            @action-open-repo="emit('action-open-repo', $event)"
          />
        </div>
      </template>

      <template #second>
        <div class="plugin-dual-list__pane">
          <PluginListTable
            title="未激活插件"
            mode="inactive"
            :items="inactivePlugins"
            :selected-names="selectedInactiveNames"
            :selected-plugin-name="selectedPluginName"
            :conflict-stats="conflictStats"
            :loading="loading"
            @update:selected-names="selectedInactiveNames = $event"
            @row-click="handleRowClick"
            @action-primary="handlePrimaryInactive"
            @batch-primary="emit('batch-enable', $event)"
            @batch-update="emit('batch-update', $event)"
            @batch-uninstall="emit('batch-uninstall', $event)"
            @clear-selection="selectedInactiveNames = []"
            @action-configure="emit('action-configure', $event)"
            @action-open-readme="emit('action-open-readme', $event)"
            @action-reload="emit('action-reload', $event)"
            @action-update="emit('action-update', $event)"
            @action-uninstall="emit('action-uninstall', $event)"
            @action-open-repo="emit('action-open-repo', $event)"
          />
        </div>
      </template>
    </ResizableSplitPane>
  </div>
</template>

<style scoped>
.plugin-dual-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.plugin-dual-list__pane {
  height: 100%;
  min-height: 0;
}
</style>