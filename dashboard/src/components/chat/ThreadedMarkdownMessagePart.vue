<template>
  <MarkdownRender
    custom-id="chat-message"
    :content="threadedContent"
    :is-dark="isDark"
    :custom-html-tags="threadedCustomHtmlTags"
    :typewriter="false"
    :max-live-nodes="0"
  />
</template>

<script setup lang="ts">
import { computed, provide } from "vue";
import { MarkdownRender } from "markstream-vue";
import type { ChatThread } from "@/composables/useMessages";

const props = defineProps<{
  text: string;
  threads: ChatThread[];
  refs: { used?: Array<Record<string, unknown>> } | null;
  isDark: boolean;
  customHtmlTags: string[];
}>();

const emit = defineEmits<{
  openThread: [thread: ChatThread];
}>();

const isDarkRef = computed(() => props.isDark);
const refsByIndex = computed(() => {
  const refs = props.refs && Array.isArray(props.refs.used) ? props.refs.used : [];
  return refs.reduce<Record<string, Record<string, unknown>>>((acc, item) => {
    if (item.index != null) {
      acc[String(item.index)] = item;
    }
    return acc;
  }, {});
});
const threadMap = computed(() =>
  props.threads.reduce<Record<string, ChatThread>>((acc, thread) => {
    acc[thread.thread_id] = thread;
    return acc;
  }, {}),
);
const threadedCustomHtmlTags = computed(() =>
  Array.from(new Set([...props.customHtmlTags, "thread"])),
);

const threadedContent = computed(() => {
  const source = props.text || "";
  const ranges = props.threads
    .map((thread) => {
      const selected = thread.selected_text || "";
      const start = selected ? source.indexOf(selected) : -1;
      return {
        start,
        end: start + selected.length,
        thread,
      };
    })
    .filter((range) => range.start >= 0 && range.end > range.start)
    .sort((a, b) => a.start - b.start);

  if (!ranges.length) return source;

  let cursor = 0;
  let result = "";
  for (const range of ranges) {
    if (range.start < cursor) continue;
    result += source.slice(cursor, range.start);
    result += `<thread>${escapeHtml(range.thread.thread_id)}</thread>`;
    cursor = range.end;
  }
  result += source.slice(cursor);
  return result;
});

provide("isDark", isDarkRef);
provide("webSearchResults", () => refsByIndex.value);
provide("chatThreadMap", () => threadMap.value);
provide("openChatThread", (thread: ChatThread) => emit("openThread", thread));

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
</script>
