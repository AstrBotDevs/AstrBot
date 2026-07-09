<!--
  Author: elecvoid243, 2026-07-09
  Spec: docs/superpowers/specs/2026-07-09-chat-input-chips-beautify-design.md §5.4

  SpcodePlanModeChip — wraps SpSegmentedControl for the plan/build mode toggle.

  Clicking the active segment is a no-op (delegated to SpSegmentedControl);
  clicking the inactive segment emits `toggle`, and the parent ChatInput
  handles the optimistic state flip + /plan or /build command dispatch.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import { useSpcodePlanMode } from '@/composables/useSpcodePlanMode'
import SpSegmentedControl, { type Segment } from './SpSegmentedControl.vue'

const { tm } = useModuleI18n('features/chat')
const { status } = useSpcodePlanMode()

const emit = defineEmits<{
  (e: 'toggle'): void
}>()

const isPlanActive = computed<boolean>(() => status.value.active === true)
const modeValue = computed<string>(() => (isPlanActive.value ? 'plan' : 'build'))

const segments = computed<Segment[]>(() => [
  {
    value: 'plan',
    label: tm('spcodeProjectLoad.planModeChip.activeLabel'),
    icon: 'mdi-clipboard-list-outline',
  },
  {
    value: 'build',
    label: tm('spcodeProjectLoad.planModeChip.inactiveLabel'),
    icon: 'mdi-hammer-wrench',
  },
])

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

function onChange(_next: string): void {
  // SpSegmentedControl already short-circuits active-segment clicks,
  // so any change event is a genuine toggle request.
  emit('toggle')
}
</script>

<template>
  <v-tooltip location="bottom" :open-delay="200">
    <template #activator="{ props: tipProps }">
      <span v-bind="tipProps" class="sp-plan-mode-wrapper" :title="tooltipText">
        <SpSegmentedControl
          :segments="segments"
          :model-value="modeValue"
          @change="onChange"
        />
      </span>
    </template>
    <span>{{ tooltipText }}</span>
  </v-tooltip>
</template>

<style scoped>
.sp-plan-mode-wrapper {
  display: inline-flex;
}
</style>
