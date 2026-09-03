<template>
  <button class="thread-node" type="button" @click="open">
    {{ thread?.selected_text || threadId }}
  </button>
</template>

<script setup lang="ts">
import { computed, inject, useSlots } from "vue";
import type { ChatThread } from "@/composables/useMessages";

const props = defineProps<{
  node?: {
    content?: string;
  } | null;
}>();

const slots = useSlots();
const threadMap = inject("chatThreadMap", () => ({} as Record<string, ChatThread>));
const openThread = inject("openChatThread", (_thread: ChatThread) => {});

const threadId = computed(() => {
  const nodeContent = props.node?.content?.trim();
  if (nodeContent) return nodeContent;
  return slotText(slots.default?.()).trim();
});

const thread = computed(() => {
  const map = typeof threadMap === "function" ? threadMap() : threadMap;
  return map[threadId.value] || null;
});

function open() {
  if (thread.value) {
    openThread(thread.value);
  }
}

function slotText(nodes: unknown[] = []): string {
  return nodes
    .map((node: any) => {
      if (typeof node.children === "string") return node.children;
      if (Array.isArray(node.children)) return slotText(node.children);
      return "";
    })
    .join("");
}
</script>

<style scoped>
.thread-node {
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  line-height: inherit;
  text-decoration-line: underline;
  text-decoration-style: dotted;
  text-decoration-thickness: 2px;
  text-underline-offset: 3px;
  cursor: pointer;
}
</style>
