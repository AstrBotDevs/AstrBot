<script setup lang="ts">
import { computed } from "vue";
import ProviderModelMenu from "@/components/chat/ProviderModelMenu.vue";
import { useChatHeaderStore } from "@/stores/chatHeader";

const chatHeader = useChatHeaderStore();
const title = computed(() => {
  const t = chatHeader.title.trim();
  const s = chatHeader.subtitle.trim();
  if (t && s) return `${s} / ${t}`;
  return t || s;
});
</script>

<template>
  <div class="chat-toolbar-context">
    <ProviderModelMenu variant="header" />
    <span v-if="title" class="chat-toolbar-context-title" :title="title">{{
      title
    }}</span>
  </div>
</template>

<style scoped>
.chat-toolbar-context {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

/* Keep the selector compact enough to stack with the title on narrow screens. */
.chat-toolbar-context :deep(.provider-select-menu) {
  height: 20px;
  display: flex;
}

.chat-toolbar-context :deep(.provider-trigger--header) {
  height: 20px;
}

.chat-toolbar-context :deep(.provider-trigger--header .provider-trigger-title) {
  font-size: 0.8125rem;
  line-height: 20px;
}

.chat-toolbar-context
  :deep(.provider-trigger--header .provider-trigger-chevron) {
  font-size: 16px;
}

.chat-toolbar-context-title {
  max-width: 32vw;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.6875rem;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (min-width: 960px) {
  .chat-toolbar-context {
    max-width: min(
      300px,
      calc((100vw - var(--astrbot-chat-sidebar-width, 0px)) * 0.3 - 32px)
    );
    flex-direction: row;
    align-items: center;
  }

  /* Center over the chat pane, independently of the model and action widths. */
  .chat-toolbar-context-title {
    position: absolute;
    top: 50%;
    left: calc(50% + var(--astrbot-chat-sidebar-width, 0px) / 2);
    width: max(
      0px,
      min(
        calc((100% - var(--astrbot-chat-sidebar-width, 0px)) * 0.4),
        calc(100% - var(--astrbot-chat-sidebar-width, 0px) - 440px)
      )
    );
    max-width: none;
    transform: translate(-50%, -50%);
    font-size: 0.8125rem;
    text-align: center;
  }
}
</style>
