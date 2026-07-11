<!--
  Author: elecvoid243, 2026-07-09
  Spec: docs/superpowers/specs/2026-07-09-chat-input-chips-beautify-design.md §5.3

  SpSegmentedControl — generic 2+ segment toggle with v-model.

  Contract (locked by SpSegmentedControl.spec.ts):
    - Props: segments (>=2), modelValue (string), disabled (boolean, default false)
    - Emits: update:modelValue, change (both fire with the new value)
    - Clicking the already-active segment is a no-op (no events)
    - ArrowLeft/Right/Up/Down move focus and emit
    - Home/End jump to first/last
-->
<script setup lang="ts">
import { ref } from "vue";

export interface Segment {
  value: string;
  label: string;
  icon?: string;
}

interface Props {
  segments: Segment[];
  modelValue: string;
  disabled?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [value: string];
}>();

const buttonRefs = ref<HTMLButtonElement[]>([]);

function focusSegment(index: number): void {
  const len = props.segments.length;
  const wrapped = ((index % len) + len) % len;
  const target = buttonRefs.value[wrapped];
  if (target) target.focus();
}

function onClick(value: string): void {
  if (props.disabled) return;
  if (value === props.modelValue) return; // No-op on already-active segment
  emit("update:modelValue", value);
  emit("change", value);
}

function onKeydown(e: KeyboardEvent, currentIndex: number): void {
  if (props.disabled) return;
  const len = props.segments.length;
  if (e.key === "ArrowRight" || e.key === "ArrowDown") {
    e.preventDefault();
    const next = (currentIndex + 1) % len;
    onClick(props.segments[next].value);
    focusSegment(next);
  } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
    e.preventDefault();
    const prev = (currentIndex - 1 + len) % len;
    onClick(props.segments[prev].value);
    focusSegment(prev);
  } else if (e.key === "Home") {
    e.preventDefault();
    onClick(props.segments[0].value);
    focusSegment(0);
  } else if (e.key === "End") {
    e.preventDefault();
    onClick(props.segments[len - 1].value);
    focusSegment(len - 1);
  }
}
</script>

<template>
  <div
    :class="['sp-segmented', { 'sp-segmented--disabled': disabled }]"
    role="tablist"
  >
    <button
      v-for="(seg, i) in segments"
      :key="seg.value"
      :ref="
        (el) => {
          if (el) buttonRefs[i] = el as HTMLButtonElement;
        }
      "
      type="button"
      role="tab"
      :aria-selected="seg.value === modelValue"
      :disabled="disabled"
      :tabindex="seg.value === modelValue ? 0 : -1"
      :class="[
        'sp-segmented__seg',
        { 'sp-segmented__seg--active': seg.value === modelValue },
      ]"
      @click="onClick(seg.value)"
      @keydown="onKeydown($event, i)"
    >
      <v-icon v-if="seg.icon" size="14">{{ seg.icon }}</v-icon>
      <span>{{ seg.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.sp-segmented {
  display: inline-flex;
  border: 1px solid var(--sp-chip-border-strong);
  border-radius: 14px;
  background: var(--sp-chip-bg);
  overflow: hidden;
  height: var(--sp-segmented-height);
}

.sp-segmented__seg {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: calc(var(--sp-segmented-height) - 2px);
  padding: 0 12px;
  border: 0;
  background: transparent;
  color: var(--sp-text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition:
    background-color 200ms ease,
    color 200ms ease;
}

.sp-segmented__seg + .sp-segmented__seg {
  border-left: 1px solid var(--sp-chip-divider);
}

.sp-segmented__seg--active {
  background: var(--sp-segmented-active-bg);
  color: rgb(var(--v-theme-primary));
}

.sp-segmented__seg:hover:not(.sp-segmented__seg--active) {
  background: var(--sp-chip-hover-bg);
  color: var(--sp-text-primary);
}

.sp-segmented__seg:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.sp-segmented__seg:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
