<!--
  Author: elecvoid243, 2026-07-09
  Spec: docs/superpowers/specs/2026-07-09-chat-input-chips-beautify-design.md §5.5

  GitDiffChip — ghost button for the "查看工作区" workspace entry point.

  No border, hover-only background. Differentiates from status badges (which
  have 1px border + status dot) to signal "this is an entry, not a status".

  Event contract (unchanged):
    - Emits `open-diff-sidebar` on click
-->
<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/chat");
const emit = defineEmits<{
  (e: "open-diff-sidebar"): void;
}>();

function open(): void {
  emit("open-diff-sidebar");
}
</script>

<template>
  <v-tooltip location="bottom" :open-delay="200">
    <template #activator="{ props: tipProps }">
      <button
        v-bind="tipProps"
        type="button"
        class="sp-ghost-btn"
        :aria-label="tm('spcodeProjectLoad.diffSidebar.chipTooltip')"
        @click="open"
      >
        <v-icon size="14">mdi-folder-open-outline</v-icon>
        <span>{{ tm("spcodeProjectLoad.diffSidebar.chip") }}</span>
      </button>
    </template>
    <span>{{ tm("spcodeProjectLoad.diffSidebar.chipTooltip") }}</span>
  </v-tooltip>
</template>

<style scoped>
.sp-ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: var(--sp-chip-height);
  padding: 0 8px;
  border: 0;
  border-radius: 12px;
  background: var(--sp-chip-bg);
  color: var(--sp-text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.sp-ghost-btn:hover {
  background: var(--sp-chip-hover-bg);
  color: var(--sp-text-primary);
}

.sp-ghost-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}
</style>
