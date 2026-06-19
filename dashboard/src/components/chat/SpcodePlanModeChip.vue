<!--
  SpcodePlanModeChip.vue

  Toggle chip that mirrors the spcode plugin's per-umo plan/build
  state. Sits in the status row of ChatInput alongside
  ``SpcodeProjectIndicator`` and ``GitDiffChip``.

  Interaction model:
    - Click the chip → emit ``toggle`` so the parent (ChatInput) can
      dispatch ``/plan`` or ``/build`` as a chat message. We do NOT
      POST to a separate endpoint — the chip reuses the existing
      chat command path, which is what makes the toggle resilient to
      plugin restarts (the bot's state of record is the truth, and
      a successful chat message guarantees the toggle took effect).
    - The chip's own visual state is driven by ``useSpcodePlanMode``'s
      singleton ref. The parent is expected to call
      ``useSpcodePlanMode().refresh()`` whenever the active session
      changes (see :class:`Chat.vue`'s ``currSessionId`` watcher).

  Why a singleton composable:
    - The same status is read by this chip AND the (eventual) menu
      item / chat-stream parser; a single ref guarantees consistency.
    - Optimistic ``setActive`` flips the chip immediately while the
      ``/plan`` or ``/build`` command is in flight, and the next
      refresh call corrects any drift.

  Author: elecvoid243
  Last-Modified: 2026-06-19
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import { useSpcodePlanMode } from '@/composables/useSpcodePlanMode'

const { tm } = useModuleI18n('features/chat')
const { status } = useSpcodePlanMode()

const emit = defineEmits<{
  /**
   * Emitted on chip click. The parent decides whether to send
   * ``/plan`` (when currently build) or ``/build`` (when currently
   * plan). We emit the intent, not the command text, so the parent
   * can pre-fill the input box vs. send-through semantics can be
   * decided in one place.
   */
  (e: 'toggle'): void
}>()

/** Whether the chip should show "Plan" (active) styling. */
const isPlanActive = computed<boolean>(() => status.value.active === true)

/** Visual color when active (plan) vs. inactive (build). */
const chipColor = computed(() =>
  isPlanActive.value ? 'warning' : 'success',
)

/** Visual variant when active vs. inactive. */
const chipVariant = computed<'tonal' | 'outlined'>(() =>
  isPlanActive.value ? 'tonal' : 'outlined',
)

/** MDI icon: clipboard-list when plan, hammer-wrench when build. */
const chipIcon = computed(() =>
  isPlanActive.value ? 'mdi-clipboard-list-outline' : 'mdi-hammer-wrench',
)

/** Label key for the active (plan) state. */
const activeLabel = computed(() =>
  tm('spcodeProjectLoad.planModeChip.activeLabel'),
)

/** Label key for the inactive (build) state. */
const inactiveLabel = computed(() =>
  tm('spcodeProjectLoad.planModeChip.inactiveLabel'),
)

/**
 * Tooltip body. When more than one session is in plan mode, mention
 * the cross-session count so power users get a hint that the chip
 * is per-umo. Otherwise the tooltip just repeats the chip's label.
 */
const tooltipText = computed<string>(() => {
  if (isPlanActive.value) {
    if (status.value.allActiveCount > 1) {
      return tm('spcodeProjectLoad.planModeChip.activeTooltipMulti', {
        count: status.value.allActiveCount,
      })
    }
    return tm('spcodeProjectLoad.planModeChip.activeTooltip')
  }
  return tm('spcodeProjectLoad.planModeChip.inactiveTooltip')
})

function onClick(): void {
  emit('toggle')
}
</script>

<template>
  <v-tooltip location="bottom" :open-delay="200">
    <template #activator="{ props: tipProps }">
      <v-chip
        v-bind="tipProps"
        :color="chipColor"
        :variant="chipVariant"
        :prepend-icon="chipIcon"
        size="small"
        density="comfortable"
        class="spcode-plan-mode-chip"
        :class="{
          'spcode-plan-mode-chip--plan': isPlanActive,
          'spcode-plan-mode-chip--build': !isPlanActive,
        }"
        @click="onClick"
      >
        <span class="spcode-plan-mode-chip__label">
          {{ isPlanActive ? activeLabel : inactiveLabel }}
        </span>
      </v-chip>
    </template>
    <span>{{ tooltipText }}</span>
  </v-tooltip>
</template>

<style scoped>
.spcode-plan-mode-chip {
  cursor: pointer;
  user-select: none;
}

.spcode-plan-mode-chip__label {
  white-space: nowrap;
}
</style>
