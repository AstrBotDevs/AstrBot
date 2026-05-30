<template>
  <transition name="slide-left">
    <aside
      v-if="modelValue"
      ref="sidebarRef"
      class="reasoning-sidebar"
      :style="{ width: sidebarWidth + 'px' }"
    >
      <!-- Drag handle -->
      <div
        class="reasoning-sidebar-resizer"
        @mousedown="startResize"
      />

      <div class="reasoning-sidebar-header">
        <div class="reasoning-sidebar-title">{{ reasoningTitle }}</div>
        <v-btn icon="mdi-close" size="small" variant="text" @click="close" />
      </div>

      <div class="reasoning-sidebar-body">
        <ReasoningTimeline
          v-if="parts.length || reasoning"
          :parts="parts"
          :reasoning="reasoning"
          :is-dark="isDark"
        />
        <div v-else class="reasoning-sidebar-empty">
          {{ reasoningTitle }}
        </div>
      </div>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, computed } from "vue";
import type { MessagePart } from "@/composables/useMessages";
import {
  reasoningActivityCounts,
  reasoningActivityTitle,
  type MessagePart,
} from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";
import ReasoningTimeline from "@/components/chat/message_list_comps/ReasoningTimeline.vue";

const props = defineProps<{
  modelValue: boolean;
  parts: MessagePart[];
  reasoning?: string;
  isDark?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const { tm } = useModuleI18n("features/chat");

const activityCounts = computed(() =>
  reasoningActivityCounts(props.parts, props.reasoning || ""),
);

const reasoningTitle = computed(() =>
  reasoningActivityTitle(activityCounts.value, tm),
);

function close() {
  emit("update:modelValue", false);
}

// ── Drag resize ────────────────────────────────────────────────────

const MIN_WIDTH = 280;
const MAX_WIDTH = 1200;
const DEFAULT_WIDTH = 380;

const sidebarWidth = ref(DEFAULT_WIDTH);
const sidebarRef = ref<HTMLElement | null>(null);
let isResizing = false;

function startResize(e: MouseEvent) {
  e.preventDefault();
  isResizing = true;
  document.body.style.cursor = "ew-resize";
  document.body.style.userSelect = "none";
  document.addEventListener("mousemove", onMouseMove);
  document.addEventListener("mouseup", onMouseUp);
}

function onMouseMove(e: MouseEvent) {
  if (!isResizing || !sidebarRef.value) return;
  // The sidebar is on the right side of the viewport.
  // `sidebarRef` is positioned inside the parent's flex layout.
  // Calculate width from the right edge of the viewport:
  const rect = sidebarRef.value.parentElement?.getBoundingClientRect();
  if (!rect) return;
  const newWidth = rect.right - e.clientX;
  sidebarWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, newWidth));
}

function onMouseUp() {
  if (!isResizing) return;
  isResizing = false;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  document.removeEventListener("mousemove", onMouseMove);
  document.removeEventListener("mouseup", onMouseUp);
}

onBeforeUnmount(() => {
  onMouseUp();
});
</script>

<style scoped>
.reasoning-sidebar {
  width: 380px;
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

.reasoning-sidebar-resizer {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
  z-index: 10;
  transition: background 0.15s ease;
}

.reasoning-sidebar-resizer:hover,
.reasoning-sidebar-resizer:active {
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

.reasoning-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 8px;
}

.reasoning-sidebar-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface));
}

/* ── Body ─────────────────────────────────────────────────────── */

.reasoning-sidebar-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 14px 12px;
  font-size: 14.5px;
  line-height: 1.62;
}

.reasoning-sidebar-empty {
  padding: 12px 2px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 13px;
}

/* ── Mobile ───────────────────────────────────────────────────── */

@media (max-width: 760px) {
  .reasoning-sidebar {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw !important;
    height: 100dvh;
    border-left: 0;
  }

  .reasoning-sidebar-resizer {
    display: none;
  }

  .reasoning-sidebar-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  }

  .reasoning-sidebar-body {
    padding: 0 12px calc(12px + env(safe-area-inset-bottom));
  }
}
</style>
