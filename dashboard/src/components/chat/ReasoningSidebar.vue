<template>
  <transition name="chat-panel">
    <aside v-if="modelValue" class="reasoning-sidebar chat-side-panel">
      <div class="reasoning-sidebar-header">
        <div class="reasoning-sidebar-title">{{ reasoningTitle }}</div>
        <v-btn icon="mdi-close" size="small" variant="text" @click="close" />
      </div>

      <div
        ref="sidebarBody"
        class="reasoning-sidebar-body"
        tabindex="0"
        @scroll="handleSidebarScroll"
        @wheel.passive="handleSidebarInteraction"
        @touchstart.passive="handleSidebarInteraction"
        @touchmove.passive="handleSidebarInteraction"
        @pointerdown="handleSidebarInteraction"
        @keydown="handleSidebarInteraction"
      >
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
import "@/components/chat/chatPanelTransition.css";
import { computed, nextTick, ref, watch } from "vue";
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

const sidebarBody = ref<HTMLElement | null>(null);
const shouldStickToBottom = ref(true);
let lastSidebarScrollTop = 0;
let touchScrollY = 0;
let scrollIntent = 0;

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

function scrollToLatestActivity() {
  if (!props.modelValue || !shouldStickToBottom.value) return;
  void nextTick(() => {
    const body = sidebarBody.value;
    if (!body || !shouldStickToBottom.value) return;
    body.scrollTop = body.scrollHeight;
    lastSidebarScrollTop = Math.max(0, body.scrollTop);
  });
}

function handleSidebarInteraction(
  event: WheelEvent | TouchEvent | PointerEvent | KeyboardEvent,
) {
  if (event instanceof WheelEvent) {
    if (event.ctrlKey || event.deltaY === 0) return;
    scrollIntent = Math.sign(event.deltaY);
  } else if (event.type === "touchstart" || event.type === "touchmove") {
    const touch = (event as TouchEvent).touches[0];
    if (!touch) return;
    if (event.type === "touchstart") {
      touchScrollY = touch.clientY;
      return;
    }
    scrollIntent = Math.sign(touchScrollY - touch.clientY);
    touchScrollY = touch.clientY;
  } else if (event instanceof KeyboardEvent) {
    const target = event.target as HTMLElement;
    if (
      target.closest("input, textarea, select, [contenteditable], button, a")
    ) {
      return;
    }
    if (
      ["ArrowUp", "PageUp", "Home"].includes(event.key) ||
      (event.key === " " && event.shiftKey)
    ) {
      scrollIntent = -1;
    } else if (["ArrowDown", "PageDown", "End", " "].includes(event.key)) {
      scrollIntent = 1;
    } else {
      return;
    }
  } else {
    if (event.target !== sidebarBody.value) return;
    scrollIntent = 0;
    shouldStickToBottom.value = false;
  }
  if (scrollIntent < 0) shouldStickToBottom.value = false;
}

function handleSidebarScroll() {
  const body = sidebarBody.value;
  if (!body) return;
  const maxScrollTop = Math.max(0, body.scrollHeight - body.clientHeight);
  const scrollTop = Math.max(0, body.scrollTop);
  const previousTop = Math.min(lastSidebarScrollTop, maxScrollTop);
  const isAwayFromBottom = maxScrollTop - scrollTop > 2;
  if (scrollTop < previousTop) {
    shouldStickToBottom.value = false;
  } else if (
    scrollTop > previousTop &&
    !isAwayFromBottom &&
    scrollIntent >= 0
  ) {
    shouldStickToBottom.value = true;
  }
  lastSidebarScrollTop = scrollTop;
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    shouldStickToBottom.value = true;
    scrollIntent = 0;
    lastSidebarScrollTop = 0;
    scrollToLatestActivity();
  },
  { flush: "post", immediate: true },
);

watch(() => [props.reasoning, props.parts], scrollToLatestActivity, {
  deep: true,
  flush: "post",
});
</script>

<style scoped>
.reasoning-sidebar {
  --chat-side-panel-width: 380px;
  width: var(--chat-side-panel-width);
  height: calc(100% - var(--chat-panel-top-offset, 0px));
  margin-top: var(--chat-panel-top-offset, 0px);
  border-left: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.1));
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

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

.reasoning-sidebar-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 14px 12px;
  font-size: 14.5px;
  line-height: 1.62;
}

.reasoning-sidebar-body :deep(.reasoning-text) {
  --ms-text-body: 0.8125rem;
  --ms-leading-body: 1.55;
  font-size: 13px;
  line-height: 1.55;
}

.reasoning-sidebar-empty {
  padding: 12px 2px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 13px;
}

@media (max-width: 760px) {
  .reasoning-sidebar {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw;
    height: 100dvh;
    margin-top: 0;
    border-left: 0;
  }

  .reasoning-sidebar-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid
      var(--chat-border, rgba(var(--v-border-color), 0.12));
  }

  .reasoning-sidebar-body {
    padding: 0 12px calc(12px + env(safe-area-inset-bottom));
  }
}
</style>
