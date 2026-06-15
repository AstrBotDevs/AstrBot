<template>
  <transition name="slide-left">
    <div v-if="isOpen" class="todo-sidebar">
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
        <!-- 有数据 -->
        <TodoListPanel
          v-if="list && stats"
          :list="list"
          :stats="stats"
          :attention-items="attentionItems"
        />

        <!-- 空状态 -->
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
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { TodoList, TodoStats } from "@/composables/useMessages";
import TodoListPanel from "./spcode_tools/TodoListPanel.vue";

/**
 * TodoSidebar — 实时显示当前 todo_list 工具调用最新一份快照的右侧抽屉。
 *
 * 数据由父组件 (Chat.vue) 从 useMessages 的 latestTodoSnapshotBySession 中
 * 取出,经 currentTodoSnapshot computed 隔离当前 session 后传入。
 * 与 RefsSidebar 互斥显示:父组件控制 v-model 即可。
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

/** v-model 受控的开关 getter/setter。 */
const isOpen = computed<boolean>({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

function close() {
  isOpen.value = false;
}

/** 把 list.updated_at ISO 字符串渲染为紧凑时间显示。
 *
 * 形如 "18:14" (当天) 或 "06-08 18:14" (其他日期)。
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
</script>

<style scoped>
.todo-sidebar {
  width: 380px;
  height: 100%;
  background-color: rgb(var(--v-theme-surface));
  border-left: 1px solid rgba(var(--v-border-color), 0.16);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  color: rgb(var(--v-theme-on-surface));
  /* 阻止内部滚动穿透 */
  overscroll-behavior: contain;
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
    width: 100%;
    position: absolute;
    inset: 0;
    z-index: 10;
    border-left: 0;
  }
}
</style>
