<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.4
     Three-segment control: raw / rendered / diff-vs-current.
     "diff" is disabled when no historical revision is selected. -->
<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  modelValue: "raw" | "rendered" | "diff";
  hasRevision: boolean;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: "raw" | "rendered" | "diff"): void;
}>();
const { tm } = useModuleI18n("features/chat");

const OPTIONS: ReadonlyArray<{
  value: "raw" | "rendered" | "diff";
  labelKey: string;
}> = [
  { value: "raw", labelKey: "spcodeProjectLoad.documentManager.viewMode.raw" },
  {
    value: "rendered",
    labelKey: "spcodeProjectLoad.documentManager.viewMode.rendered",
  },
  { value: "diff", labelKey: "spcodeProjectLoad.documentManager.viewMode.diff" },
];

function setValue(v: "raw" | "rendered" | "diff") {
  if (v === "diff" && !props.hasRevision) return;
  emit("update:modelValue", v);
}
</script>

<template>
  <div class="document-view-mode-tab" role="tablist">
    <button
      v-for="opt in OPTIONS"
      :key="opt.value"
      type="button"
      role="tab"
      :aria-selected="modelValue === opt.value"
      :disabled="opt.value === 'diff' && !hasRevision"
      :class="['document-view-mode-tab__pill', { active: modelValue === opt.value }]"
      @click="setValue(opt.value)"
    >
      {{ tm(opt.labelKey) }}
    </button>
  </div>
</template>

<style scoped>
.document-view-mode-tab {
  display: inline-flex;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 6px;
  padding: 2px;
  gap: 2px;
}
.document-view-mode-tab__pill {
  font-size: 11.5px;
  padding: 3px 10px;
  border: none;
  background: transparent;
  border-radius: 4px;
  color: rgba(var(--v-theme-on-surface), 0.65);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.document-view-mode-tab__pill:hover:not(:disabled) {
  color: rgb(var(--v-theme-on-surface));
}
.document-view-mode-tab__pill.active {
  background: var(--v-theme-surface, rgb(255, 255, 255));
  color: rgb(var(--v-theme-primary));
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}
.document-view-mode-tab__pill:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
