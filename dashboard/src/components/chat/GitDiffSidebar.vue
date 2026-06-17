<!-- Author: elecvoid243, 2026-06-18 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.2 -->
<!-- Layout mirrors ReasoningSidebar.vue so resizing the sidebar takes
     space from .chat-main (flex sibling) instead of overlaying it. -->
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
    // Re-check modelValue after await: user may have closed the sidebar
    // during the refresh, in which case a sibling watcher already called
    // stopPolling() — calling startPolling() here would re-arm the timer
    // and leak polling after close.
    if (props.modelValue) composable.startPolling(10_000)
  } else {
    composable.stopPolling()
  }
}, { immediate: true })

watch(() => spcodeStatus.status.value.loaded, (loaded) => {
  if (!loaded) emit('update:modelValue', false)
})

onBeforeUnmount(() => {
  onMouseUp()
  composable.dispose()
})

function toggleFile(path: string): void {
  const next = new Set(expandedSet.value)
  if (next.has(path)) next.delete(path); else next.add(path)
  expandedSet.value = next
}

// ── Drag resize ────────────────────────────────────────────────────

const MIN_WIDTH = 320
const MAX_WIDTH = 1200
const DEFAULT_WIDTH = 420

const sidebarWidth = ref(DEFAULT_WIDTH)
const sidebarRef = ref<HTMLElement | null>(null)
let isResizing = false

function startResize(e: MouseEvent): void {
  e.preventDefault()
  isResizing = true
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e: MouseEvent): void {
  if (!isResizing || !sidebarRef.value) return
  // Sidebar sits on the right side of the flex parent (.chat-ui).
  // Distance from the parent's right edge to the cursor equals the
  // new width. Dragging the cursor left therefore grows the sidebar
  // and squeezes the chat panel — same model as ReasoningSidebar.
  const parent = sidebarRef.value.parentElement
  if (!parent) return
  const newWidth = parent.getBoundingClientRect().right - e.clientX
  sidebarWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, newWidth))
}

function onMouseUp(): void {
  if (!isResizing) return
  isResizing = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
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
      ref="sidebarRef"
      class="git-diff-sidebar"
      :class="{ resizing: isResizing }"
      :style="{ width: sidebarWidth + 'px' }"
    >
      <div class="git-diff-sidebar-resizer" @mousedown="startResize" />
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
  width: 420px;
  height: 100%;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: relative;
}

/* ── Drag handle ──────────────────────────────────────────────── */

.git-diff-sidebar-resizer {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
  z-index: 10;
  transition: background 0.15s ease;
}

.git-diff-sidebar-resizer:hover,
.git-diff-sidebar-resizer:active {
  background: rgba(var(--v-theme-primary), 0.2);
}

/* ── Transition ───────────────────────────────────────────────── */

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.2s ease;
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* ── Header ───────────────────────────────────────────────────── */

.git-diff-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 8px;
}

.git-diff-sidebar-title-wrap { display: flex; align-items: center; gap: 6px; }
.git-diff-sidebar-title { font-size: 16px; font-weight: 600; line-height: 1.4; }
.git-diff-sidebar-dir-icon {
  color: rgba(var(--v-theme-on-surface), 0.54);
}
.git-diff-sidebar-dir { font-family: monospace; font-size: 12px; }
.git-diff-sidebar-actions { display: flex; gap: 4px; }

/* ── Truncation warning ──────────────────────────────────────── */

.git-diff-sidebar-warning {
  padding: 8px 16px;
  background: rgba(255, 193, 7, 0.12);
  color: rgb(255, 152, 0);
  font-size: 12px;
  border-bottom: 1px solid rgba(255, 193, 7, 0.3);
}

/* ── Body ─────────────────────────────────────────────────────── */

.git-diff-sidebar-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 14px 12px;
}

/* ── Mobile ───────────────────────────────────────────────────── */

@media (max-width: 760px) {
  .git-diff-sidebar {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw !important;
    height: 100dvh;
    border-left: 0;
  }
  .git-diff-sidebar-resizer { display: none; }
  .git-diff-sidebar-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  }
  .git-diff-sidebar-body {
    padding: 0 12px calc(12px + env(safe-area-inset-bottom));
  }
}
</style>
