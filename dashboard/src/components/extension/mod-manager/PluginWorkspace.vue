<script setup lang="ts">
import { computed } from 'vue'
import type { CommandConflictGroup, PluginSummary } from './types'

import ResizableSplitPane from './ResizableSplitPane.vue'
import PluginPanel from './PluginPanel.vue'
import GlobalPanel from './GlobalPanel.vue'

const props = defineProps<{
  plugins: PluginSummary[]
  selectedPluginName: string | null
  splitRatio: number
  conflicts: CommandConflictGroup[]
  conflictsLoading?: boolean
  showReserved: boolean
}>()

const emit = defineEmits<{
  (e: 'update:splitRatio', ratio: number): void
  (e: 'select-plugin', name: string): void
  (e: 'action-update', name: string): void
  (e: 'config-saved', pluginName: string): void
}>()

const selectedPlugin = computed<PluginSummary | null>(() => {
  const name = props.selectedPluginName
  if (!name) return null
  return (props.plugins ?? []).find((p) => p.name === name) ?? null
})

const splitRatioModel = computed<number>({
  get: () => props.splitRatio,
  set: (ratio) => emit('update:splitRatio', ratio)
})

const handleSelectPlugin = (name: string) => {
  if (!name) return
  emit('select-plugin', name)
}
</script>

<template>
  <div class="plugin-workspace">
    <ResizableSplitPane v-model="splitRatioModel" direction="vertical">
      <template #first>
        <PluginPanel
          :plugin="selectedPlugin"
          @action-update="emit('action-update', $event)"
          @config-saved="emit('config-saved', $event)"
        />
      </template>

      <template #second>
        <GlobalPanel
          :plugins="plugins"
          :conflicts="conflicts"
          :loading="conflictsLoading"
          :show-reserved="showReserved"
          @select-plugin="handleSelectPlugin"
        />
      </template>
    </ResizableSplitPane>
  </div>
</template>

<style scoped>
.plugin-workspace {
  height: 100%;
  min-height: 0;
  width: 100%;
  min-width: 0;
}
</style>