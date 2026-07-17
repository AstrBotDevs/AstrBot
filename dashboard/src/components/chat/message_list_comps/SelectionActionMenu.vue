<!-- Author: elecvoid243, 2026-07-17
     Spec: docs/superpowers/specs/2026-07-17-selection-comment-design.md §4.1
     Pure-presentational fixed-position popup. The parent owns the
     selection snapshot and is responsible for writing to the
     clipboard on `copy`; the menu shows an optimistic "copied"
     feedback and auto-closes after 1.5s. The comment item is
     hidden on rendering views (showComment=false). -->
<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  /** Viewport X for the menu's left edge (clamped to viewport). */
  x: number;
  /** Viewport Y for the menu's top edge (clamped to viewport). */
  y: number;
  /** Whether to render the "comment" item. False on rendering views. */
  showComment: boolean;
}>();

const emit = defineEmits<{
  (e: "copy"): void;
  (e: "comment"): void;
  (e: "close"): void;
}>();

const { tm } = useModuleI18n("features/chat");
const copied = ref(false);
let closeTimer: ReturnType<typeof setTimeout> | null = null;

function clampToViewport(x: number, y: number): { left: number; top: number } {
  // Approximate menu size (140×40) — leave a 6px margin so the menu
  // never touches the edge. Works for both item counts (1 or 2).
  if (typeof window === "undefined") return { left: x, top: y };
  const maxLeft = Math.max(6, window.innerWidth - 140);
  const maxTop = Math.max(6, window.innerHeight - 40);
  return {
    left: Math.min(Math.max(6, x), maxLeft),
    top: Math.min(Math.max(6, y), maxTop),
  };
}

const pos = clampToViewport(props.x, props.y);

function onCopy(): void {
  copied.value = true;
  emit("copy");
  if (closeTimer) clearTimeout(closeTimer);
  closeTimer = setTimeout(() => emit("close"), 1500);
}

function onComment(): void {
  emit("comment");
}

onBeforeUnmount(() => {
  if (closeTimer) clearTimeout(closeTimer);
});
</script>

<template>
  <div
    class="selection-action-menu"
    role="menu"
    :style="{ left: pos.left + 'px', top: pos.top + 'px' }"
    @mousedown.stop
  >
    <button
      type="button"
      class="selection-action-menu__item"
      role="menuitem"
      @click="onCopy"
    >
      <v-icon size="12">mdi-content-copy</v-icon>
      {{
        copied
          ? tm("copy.copied")
          : tm("copy.copy")
      }}
    </button>
    <button
      v-if="showComment"
      type="button"
      class="selection-action-menu__item"
      role="menuitem"
      @click="onComment"
    >
      <v-icon size="12">mdi-comment-text-outline</v-icon>
      {{ tm("spcodeProjectLoad.fileBrowser.comment.addButton") }}
    </button>
  </div>
</template>

<style scoped>
.selection-action-menu {
  position: fixed;
  z-index: 1100;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  background: var(--v-theme-surface, rgb(255, 255, 255));
  color: rgb(var(--v-theme-on-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
  border-radius: 6px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.14);
  font-size: 11.5px;
  user-select: none;
}
.selection-action-menu__item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.82);
}
.selection-action-menu__item:hover {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}
</style>
