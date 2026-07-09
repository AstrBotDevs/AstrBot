<!--
  Author: elecvoid243, 2026-07-09
  Spec: docs/superpowers/specs/2026-07-09-chat-input-chips-beautify-design.md §5.1, §5.2

  SpcodeProjectIndicator — status badge for the loaded/unloaded spcode project.

  Visual states (locked by spec §5.2):
    - Not loaded → empty state (empty dot ring + mdi-folder-outline + "未加载项目")
    - Loaded → success dot + mdi-folder-check-outline + "项目已加载" + truncated path

  Event contract (unchanged from prior version):
    - Emits `open-load-dialog` on click
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'

const { status } = useSpcodeProjectStatus()
const { tm } = useModuleI18n('features/chat')

const emit = defineEmits<{
  (e: 'open-load-dialog'): void
}>()

/** Truncate a long path to 48 chars with leading ellipsis. */
function truncatePath(path: string): string {
  if (path.length <= 48) return path
  return `…${path.slice(-47)}`
}

const displayPath = computed(() =>
  status.value.loaded && status.value.directory ? truncatePath(status.value.directory) : '',
)

const loadedAtDisplay = computed(() => {
  if (!status.value.loadedAt) return ''
  const ts = status.value.loadedAt
  const ms = ts > 1e12 ? ts : ts * 1000
  try {
    const d = new Date(ms)
    if (Number.isNaN(d.getTime())) return ''
    return d.toLocaleString()
  } catch {
    return ''
  }
})

const icon = computed(() =>
  status.value.loaded ? 'mdi-folder-check-outline' : 'mdi-folder-outline',
)

const label = computed(() =>
  status.value.loaded
    ? tm('spcodeProjectLoad.indicator.loadedLabel')
    : tm('spcodeProjectLoad.indicator.noProject'),
)

const tooltipText = computed(() => {
  if (status.value.loaded && loadedAtDisplay.value) {
    return `${tm('spcodeProjectLoad.indicator.loadedAtPrefix')}: ${loadedAtDisplay.value}`
  }
  return tm('spcodeProjectLoad.indicator.noProject')
})

function openLoadDialog(): void {
  emit('open-load-dialog')
}
</script>

<template>
  <v-tooltip location="bottom" :open-delay="200">
    <template #activator="{ props: tipProps }">
      <button
        v-bind="tipProps"
        type="button"
        :class="[
          'sp-status-badge',
          { 'sp-status-badge--empty': !status.loaded },
        ]"
        :aria-label="tooltipText"
        @click="openLoadDialog"
      >
        <span
          class="sp-status-badge__dot"
          :class="{
            'sp-status-badge__dot--success': status.loaded,
            'sp-status-badge__dot--neutral': !status.loaded,
          }"
          aria-hidden="true"
        />
        <v-icon size="14" class="sp-status-badge__icon">{{ icon }}</v-icon>
        <span class="sp-status-badge__label">{{ label }}</span>
        <span
          v-if="displayPath"
          class="sp-status-badge__path"
          :title="status.directory ?? ''"
        >{{ displayPath }}</span>
      </button>
    </template>
    <span>{{ tooltipText }}</span>
  </v-tooltip>
</template>

<style scoped>
.sp-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: var(--sp-chip-height);
  padding: 0 10px;
  border: 1px solid var(--sp-chip-border);
  border-radius: 12px;
  background: transparent;
  color: var(--sp-text-primary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 150ms ease;
  max-width: 100%;
  min-width: 0;
}

.sp-status-badge:hover { background: var(--sp-chip-hover-bg); }
.sp-status-badge:active { background: var(--sp-chip-active-bg); }
.sp-status-badge:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}

.sp-status-badge__dot {
  flex: 0 0 6px;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--sp-status-dot-success);
  transition: background-color 200ms ease;
}

.sp-status-badge__dot--neutral { background: var(--sp-status-dot-neutral); }

.sp-status-badge--empty .sp-status-badge__dot {
  background: transparent;
  box-shadow: inset 0 0 0 1.5px var(--sp-status-dot-neutral);
}

.sp-status-badge__icon {
  flex: 0 0 14px;
  color: rgb(var(--v-theme-primary));
}

.sp-status-badge__label { white-space: nowrap; }

.sp-status-badge__path {
  font-family: var(--v-font-mono, monospace);
  font-size: 11px;
  font-weight: 400;
  color: var(--sp-text-path);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>