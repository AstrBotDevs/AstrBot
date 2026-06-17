<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.2 -->
<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed } from 'vue'
import { useSpcodeGitDiff } from '@/composables/useSpcodeGitDiff'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import { useModuleI18n } from '@/i18n/composables'
import GitDiffBodyContent from '@/components/chat/message_list_comps/GitDiffBodyContent.vue'

const { tm } = useModuleI18n('features/chat')
const props = defineProps<{
  modelValue: boolean
  isDark?: boolean
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const composable = useSpcodeGitDiff()
const spcodeStatus = useSpcodeProjectStatus()
const expandedSet = ref<Set<string>>(new Set())

const isFetching = ref(false)
async function onManualRefresh(): Promise<void> {
  if (isFetching.value) return
  isFetching.value = true
  try { await composable.refresh() } finally { isFetching.value = false }
}

watch(() => props.modelValue, async (open) => {
  if (open) {
    isFetching.value = true
    try { await composable.refresh() } finally { isFetching.value = false }
    composable.startPolling(10_000)
  } else {
    composable.stopPolling()
  }
}, { immediate: true })

watch(() => spcodeStatus.status.value.loaded, (loaded) => {
  if (!loaded) emit('update:modelValue', false)
})

onBeforeUnmount(() => composable.dispose())

function toggleFile(path: string): void {
  const next = new Set(expandedSet.value)
  if (next.has(path)) next.delete(path); else next.add(path)
  expandedSet.value = next
}

const MIN_WIDTH = 320
const MAX_WIDTH = 1200
const DEFAULT_WIDTH = 420
const sidebarWidth = ref(DEFAULT_WIDTH)
const isResizing = ref(false)

function startResize(e: MouseEvent): void {
  isResizing.value = true
  const startX = e.clientX
  const startW = sidebarWidth.value
  const onMove = (ev: MouseEvent): void => {
    const next = startW + (ev.clientX - startX)
    sidebarWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next))
  }
  const onUp = (): void => {
    isResizing.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

const directoryPath = computed(() => {
  const s = composable.state.value
  if (s.kind === 'ok') return s.snapshot.meta.directory
  if (s.kind === 'error' && s.previousSnapshot) return s.previousSnapshot.meta.directory
  return null
})

const isTruncated = computed(() => {
  const s = composable.state.value
  if (s.kind === 'ok') return s.snapshot.meta.truncated
  if (s.kind === 'error' && s.previousSnapshot) return s.previousSnapshot.meta.truncated
  return false
})

const truncatedShown = computed(() => {
  const s = composable.state.value
  if (s.kind === 'ok') return s.snapshot.meta.truncatedAtBytes
  if (s.kind === 'error' && s.previousSnapshot) return s.previousSnapshot.meta.truncatedAtBytes
  return 0
})

const truncatedMax = computed(() => {
  const s = composable.state.value
  if (s.kind === 'ok') return s.snapshot.meta.maxBytes
  if (s.kind === 'error' && s.previousSnapshot) return s.previousSnapshot.meta.maxBytes
  return 0
})
</script>

<template>
  <transition name="slide-left">
    <aside
      v-if="modelValue"
      class="git-diff-sidebar"
      :class="{ resizing: isResizing }"
      :style="{ width: sidebarWidth + 'px' }"
    >
      <div class="git-diff-sidebar-resizer" @mousedown.prevent="startResize" />
      <div class="git-diff-sidebar-header">
        <div class="git-diff-sidebar-title-wrap">
          <span class="git-diff-sidebar-title">
            {{ tm('spcodeProjectLoad.diffSidebar.title') }}
          </span>
          <v-tooltip v-if="directoryPath" location="bottom" :open-delay="200">
            <template #activator="{ props: tipProps }">
              <v-icon
                v-bind="tipProps"
                size="14"
                class="git-diff-sidebar-dir-icon"
              >mdi-folder-outline</v-icon>
            </template>
            <span class="git-diff-sidebar-dir">{{ directoryPath }}</span>
          </v-tooltip>
        </div>
        <div class="git-diff-sidebar-actions">
          <v-btn
            icon="mdi-refresh"
            size="small"
            variant="text"
            :loading="isFetching"
            @click="onManualRefresh"
          >
            <v-tooltip activator="parent" location="bottom" :open-delay="200">
              {{ tm('spcodeProjectLoad.diffSidebar.refreshTooltip') }}
            </v-tooltip>
          </v-btn>
          <v-btn
            icon="mdi-close"
            size="small"
            variant="text"
            @click="emit('update:modelValue', false)"
          />
        </div>
      </div>
      <div v-if="isTruncated" class="git-diff-sidebar-warning">
        {{ tm('spcodeProjectLoad.diffSidebar.truncated', { shown: truncatedShown, max: truncatedMax }) }}
      </div>
      <div class="git-diff-sidebar-body">
        <GitDiffBodyContent
          :state="composable.state.value"
          :expanded="expandedSet"
          :is-dark="!!isDark"
          @toggle="toggleFile"
          @retry="onManualRefresh"
        />
      </div>
    </aside>
  </transition>
</template>

<style scoped>
.git-diff-sidebar {
  position: fixed; top: 0; right: 0; bottom: 0;
  background: var(--v-theme-surface);
  border-left: 1px solid rgba(0, 0, 0, 0.12);
  display: flex; flex-direction: column; z-index: 1000;
}
.git-diff-sidebar.resizing { transition: none; user-select: none; }
.git-diff-sidebar-resizer {
  position: absolute; top: 0; left: -3px; width: 6px; height: 100%;
  cursor: col-resize; z-index: 1;
}
.git-diff-sidebar-resizer:hover { background: rgba(0, 0, 0, 0.04); }
.git-diff-sidebar-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 12px 12px 16px; border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}
.git-diff-sidebar-title-wrap { display: flex; align-items: center; gap: 6px; }
.git-diff-sidebar-title { font-weight: 600; font-size: 15px; }
.git-diff-sidebar-dir-icon { color: rgba(0, 0, 0, 0.45); }
.git-diff-sidebar-dir { font-family: monospace; font-size: 12px; }
.git-diff-sidebar-actions { display: flex; gap: 4px; }
.git-diff-sidebar-warning {
  padding: 8px 16px; background: rgba(255, 193, 7, 0.12);
  color: rgb(255, 152, 0); font-size: 12px; border-bottom: 1px solid rgba(255, 193, 7, 0.3);
}
.git-diff-sidebar-body { flex: 1; overflow-y: auto; }
.slide-left-enter-active, .slide-left-leave-active { transition: transform 0.2s; }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(100%); }

@media (max-width: 760px) {
  .git-diff-sidebar {
    position: fixed; inset: 0; width: 100vw !important;
    border-left: 0; z-index: 1300;
  }
  .git-diff-sidebar-resizer { display: none; }
  .git-diff-sidebar-header { padding-top: calc(12px + env(safe-area-inset-top)); }
  .git-diff-sidebar-body { padding-bottom: env(safe-area-inset-bottom); }
}
</style>
