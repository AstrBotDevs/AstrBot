<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PluginPanelTab, PluginSummary } from './types'

import ResizableSplitPane from './ResizableSplitPane.vue'
import PluginPanel from './PluginPanel.vue'
import DetachedTabPane from './DetachedTabPane.vue'

const DETACHED_TAB_KEY = 'pluginManager.detachedTab'

const props = defineProps<{
  plugins: PluginSummary[]
  selectedPluginName: string | null
  splitRatio: number
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

// Detached tab state with localStorage persistence
const validTabs: PluginPanelTab[] = ['info', 'config', 'overview', 'changelog', 'reserved']

function loadDetachedTab(): PluginPanelTab | null {
  try {
    const stored = localStorage.getItem(DETACHED_TAB_KEY)
    if (stored && validTabs.includes(stored as PluginPanelTab)) {
      return stored as PluginPanelTab
    }
  } catch {
    // localStorage unavailable
  }
  return null
}

const detachedTab = ref<PluginPanelTab | null>(loadDetachedTab())

watch(detachedTab, (val) => {
  try {
    if (val) {
      localStorage.setItem(DETACHED_TAB_KEY, val)
    } else {
      localStorage.removeItem(DETACHED_TAB_KEY)
    }
  } catch {
    // localStorage unavailable
  }
})

// Whether to show the split (four-pane) layout
const isSplit = computed(() => detachedTab.value !== null && selectedPlugin.value !== null)

function handleDetach(tab: PluginPanelTab) {
  detachedTab.value = tab
}

function handleDock() {
  detachedTab.value = null
}
</script>

<template>
  <div class="plugin-workspace">
    <!-- Three-pane mode: PluginPanel fills the entire right side -->
    <PluginPanel
      v-if="!isSplit"
      :plugin="selectedPlugin"
      :excluded-tab="null"
      @action-update="emit('action-update', $event)"
      @config-saved="emit('config-saved', $event)"
      @detach-tab="handleDetach"
    />

    <!-- Four-pane mode: PluginPanel top + DetachedTabPane bottom -->
    <ResizableSplitPane
      v-else
      v-model="splitRatioModel"
      direction="vertical"
    >
      <template #first>
        <PluginPanel
          :plugin="selectedPlugin"
          :excluded-tab="detachedTab"
          @action-update="emit('action-update', $event)"
          @config-saved="emit('config-saved', $event)"
          @detach-tab="handleDetach"
        />
      </template>

      <template #second>
        <DetachedTabPane
          :tab="detachedTab!"
          :plugin="selectedPlugin"
          @dock="handleDock"
          @action-update="emit('action-update', $event)"
          @config-saved="emit('config-saved', $event)"
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