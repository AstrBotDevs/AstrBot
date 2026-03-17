<script setup lang="ts">
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import type { PluginPanelTab, PluginSummary } from './types'

import PluginInfoPanel from './PluginInfoPanel.vue'
import PluginConfigPanel from './PluginConfigPanel.vue'
import PluginOverviewPanel from './PluginOverviewPanel.vue'
import PluginChangelogPanel from './PluginChangelogPanel.vue'
import GlobalPanel from './GlobalPanel.vue'

const props = defineProps<{
  tab: PluginPanelTab
  plugin: PluginSummary | null
}>()

const emit = defineEmits<{
  (e: 'dock'): void
  (e: 'action-update', name: string): void
  (e: 'config-saved', pluginName: string): void
}>()

const { tm } = useModuleI18n('features/extension')

const tabLabel = computed(() => {
  const key = `modManager.panelTabs.${props.tab}`
  return tm(key) || props.tab
})

const pluginName = computed(() => props.plugin?.name || '')
const repoUrl = computed(() => props.plugin?.repo || null)

const openRepoInNewTab = (url: string) => {
  if (!url) return
  window.open(url, '_blank')
}

// --- Drag-to-dock with floating ghost (Chrome-like) ---
const DRAG_START_THRESHOLD = 5

function onHeaderPointerDown(e: PointerEvent) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  const startX = e.clientX
  const startY = e.clientY
  const header = e.currentTarget as HTMLElement
  let dragging = false
  let ghost: HTMLElement | null = null
  let targetTabBar: HTMLElement | null = null

  const createGhost = () => {
    ghost = header.cloneNode(true) as HTMLElement
    ghost.style.cssText = `
      position: fixed;
      z-index: 9999;
      pointer-events: none;
      opacity: 0.85;
      box-shadow: 0 4px 16px rgba(0,0,0,0.18);
      border-radius: 8px;
      background: rgb(var(--v-theme-surface));
      padding: 6px 16px;
      white-space: nowrap;
      transition: transform 0.08s ease;
      transform: scale(1.02);
      max-width: 200px;
      overflow: hidden;
    `
    document.body.appendChild(ghost)
    // Find the tab bar for hit detection
    targetTabBar = document.querySelector('.plugin-panel__tab-bar')
  }

  const moveGhost = (cx: number, cy: number) => {
    if (!ghost) return
    ghost.style.left = `${cx - ghost.offsetWidth / 2}px`
    ghost.style.top = `${cy - ghost.offsetHeight / 2}px`

    // Highlight tab bar when hovering over it (visual drop zone cue)
    if (targetTabBar) {
      const rect = targetTabBar.getBoundingClientRect()
      const isOver = cx >= rect.left && cx <= rect.right && cy >= rect.top && cy <= rect.bottom + 20
      targetTabBar.classList.toggle('plugin-panel__tab-bar--drop-target', isOver)
    }
  }

  const removeGhost = () => {
    if (ghost) {
      ghost.remove()
      ghost = null
    }
    if (targetTabBar) {
      targetTabBar.classList.remove('plugin-panel__tab-bar--drop-target')
      targetTabBar = null
    }
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
    if (!dragging) return

    // Determine if released over the tab bar area
    if (targetTabBar) {
      const rect = targetTabBar.getBoundingClientRect()
      // Generous hit zone: tab bar rect + 20px below
      const isOver =
        ev.clientX >= rect.left &&
        ev.clientX <= rect.right &&
        ev.clientY >= rect.top &&
        ev.clientY <= rect.bottom + 20
      if (isOver) {
        emit('dock')
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
</script>

<template>
  <v-card class="h-100 d-flex flex-column detached-pane" rounded="lg" variant="outlined">
    <div
      class="detached-pane__header d-flex align-center px-4 py-2"
      @pointerdown.prevent="onHeaderPointerDown"
    >
      <v-icon size="18" class="mr-2 text-medium-emphasis">mdi-drag-horizontal</v-icon>
      <span class="text-subtitle-2 font-weight-medium">{{ tabLabel }}</span>
      <v-spacer />
      <v-tooltip location="top">
        <template #activator="{ props: tipProps }">
          <v-btn
            v-bind="tipProps"
            icon
            size="x-small"
            variant="text"
            @click.stop="emit('dock')"
          >
            <v-icon size="18">mdi-arrow-collapse-up</v-icon>
          </v-btn>
        </template>
        <span>收回到标签栏</span>
      </v-tooltip>
    </div>

    <v-divider />

    <div class="detached-pane__body flex-grow-1" style="min-height: 0">
      <!-- Info tab -->
      <div v-if="tab === 'info'" class="detached-pane__content pa-3">
        <PluginInfoPanel
          v-if="plugin"
          :plugin="plugin"
          @action-update="emit('action-update', plugin.name)"
          @open-repo="openRepoInNewTab"
        />
      </div>

      <!-- Config tab -->
      <div v-else-if="tab === 'config'" class="detached-pane__content pa-3">
        <PluginConfigPanel
          :pluginName="pluginName"
          :active="true"
          @saved="(name) => emit('config-saved', name)"
          @error="() => {}"
        />
      </div>

      <!-- Overview / docs tab -->
      <div v-else-if="tab === 'overview'" class="detached-pane__content pa-3">
        <PluginOverviewPanel
          :pluginName="pluginName"
          :repoUrl="repoUrl"
          :active="true"
        />
      </div>

      <!-- Changelog tab -->
      <div v-else-if="tab === 'changelog'" class="detached-pane__content pa-3">
        <PluginChangelogPanel :pluginName="pluginName" :active="true" />
      </div>

      <!-- Reserved / extension area tab -->
      <div v-else-if="tab === 'reserved'" class="detached-pane__content">
        <GlobalPanel />
      </div>
    </div>
  </v-card>
</template>

<style scoped>
.detached-pane__header {
  cursor: grab;
  user-select: none;
  touch-action: none;
  min-height: 40px;
}

.detached-pane__header:active {
  cursor: grabbing;
}

.detached-pane__body {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.detached-pane__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}
</style>
