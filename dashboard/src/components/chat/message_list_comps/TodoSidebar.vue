<template>
  <transition name="slide-left">
    <div
      v-if="isOpen"
      ref="sidebarRef"
      class="todo-sidebar"
      :style="{ width: sidebarWidth + 'px' }"
    >
      <!-- Left-edge 6px drag handle. Mirrors the ReasoningSidebar /
           GitDiffSidebar pattern: bind mousedown here, listen for
           mousemove/mouseup on document, and unbind on mouseup. -->
      <div class="todo-sidebar-resizer" @mousedown="startResize" />

      <div class="sidebar-header">
        <h3 class="sidebar-title">
          <v-icon size="18" class="title-icon">mdi-format-list-checks</v-icon>
          <span>{{ tm("todo.sidebarTitle") }}</span>
        </h3>
        <v-btn
          icon="mdi-close"
          size="small"
          variant="text"
          :aria-label="tm('todo.close')"
          @click="close"
        ></v-btn>
      </div>

      <div class="sidebar-body">
        <!-- Non-empty state -->
        <TodoListPanel
          v-if="list && stats"
          :list="list"
          :stats="stats"
          :attention-items="attentionItems"
        />

        <!-- Empty state -->
        <div v-else class="empty-state">
          <v-icon size="36" class="empty-icon">mdi-clipboard-text-outline</v-icon>
          <div class="empty-text">{{ tm("todo.empty") }}</div>
        </div>
      </div>

      <div v-if="list?.updated_at" class="sidebar-footer">
        {{ tm("todo.updatedAt", { time: formatUpdatedAt(list.updated_at) }) }}
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { TodoList, TodoStats } from "@/composables/useMessages";
import TodoListPanel from "./spcode_tools/TodoListPanel.vue";

/**
 * TodoSidebar - right-side drawer that renders the latest snapshot of
 * the current session's todo_list tool call in real time.
 *
 * Data is fed by the parent (Chat.vue) from useMessages'
 * latestTodoSnapshotBySession via the currentTodoSnapshot computed
 * that isolates the active session. Mutually exclusive with
 * RefsSidebar: the parent controls the v-model.
 */
const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    list: TodoList | null;
    stats: TodoStats | null;
    attentionItems: number[];
  }>(),
  {
    modelValue: false,
    list: null,
    stats: null,
    attentionItems: () => [],
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const { tm } = useModuleI18n("features/chat");

/** v-model controlled open/close getter/setter. */
const isOpen = computed<boolean>({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

function close() {
  isOpen.value = false;
}

/** Render list.updated_at ISO string as a compact time label.
 *
 *  Format: "HH:MM" (same day) or "MM-DD HH:MM" (other days).
 */
function formatUpdatedAt(value: string | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const hm = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  if (sameDay) return hm;
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${hm}`;
}

// Drag resize ----------------------------------------------------

const MIN_WIDTH = 280;
const MAX_WIDTH = 1800;
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
  // Use the sidebar's own right edge (not the parent's) as the
  // reference point. The flex layout places any siblings shown to
  // the right beyond selfRect.right, so the computed width is
  // automatically reduced by their combined width - same model
  // as ReasoningSidebar.
  const selfRect = sidebarRef.value.getBoundingClientRect();
  const newWidth = selfRect.right - e.clientX;
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
.todo-sidebar {
  /* Width is controlled by the inline :style binding (DEFAULT_WIDTH
     = 380px). On desktop the user can drag between MIN_WIDTH and
     MAX_WIDTH. */
  /* Reserve top space for the absolute v-app-bar (50px), matching
     ReasoningSidebar / RefsSidebar / ThreadPanel / GitDiffSidebar.
     --chat-panel-top-offset is defined by the parent .chat-ui. */
  height: calc(100% - var(--chat-panel-top-offset, 0px));
  margin-top: var(--chat-panel-top-offset, 0px);
  background-color: rgb(var(--v-theme-surface));
  border-left: 1px solid rgba(var(--v-border-color), 0.16);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  color: rgb(var(--v-theme-on-surface));
  position: relative;
  /* Block scroll bleed-through from inside the panel. */
  overscroll-behavior: contain;
}

/* Drag handle */

.todo-sidebar-resizer {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
  z-index: 10;
  transition: background 0.15s ease;
}

.todo-sidebar-resizer:hover,
.todo-sidebar-resizer:active {
  background: rgba(var(--v-theme-primary), 0.2);
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.3s ease;
}

.slide-left-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.slide-left-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px 10px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.08);
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
  line-height: 1.4;
  margin: 0;
}

.title-icon {
  color: rgba(var(--v-theme-on-surface), 0.65);
}

.sidebar-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 16px;
}

.sidebar-footer {
  flex-shrink: 0;
  padding: 8px 16px 12px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-style: italic;
  border-top: 1px solid rgba(var(--v-border-color), 0.08);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 100%;
  padding: 40px 12px;
  text-align: center;
}

.empty-icon {
  color: rgba(var(--v-theme-on-surface), 0.25);
}

.empty-text {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  line-height: 1.5;
}

@media (max-width: 760px) {
  .todo-sidebar {
    /* !important overrides the inline :style width so the mobile
       drawer always fills the screen. position:absolute + inset:0
       makes margin-top / height irrelevant here. */
    width: 100% !important;
    position: absolute;
    inset: 0;
    z-index: 10;
    border-left: 0;
  }

  .todo-sidebar-resizer {
    display: none;
  }
}
</style>
