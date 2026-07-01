<template>
  <div class="markdown-content">
    <MarkdownRender
      custom-id="chat-message"
      :content="content"
      :custom-html-tags="customHtmlTags"
      :is-dark="isDark"
      :final="!isStreaming"
      :smooth-streaming="isStreaming ? 'auto' : false"
      :fade="false"
      :typewriter="false"
      :max-live-nodes="MARKDOWN_RENDER_MAX_LIVE_NODES"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, provide } from "vue";
import { MarkdownRender } from "markstream-vue";
import { MARKDOWN_RENDER_MAX_LIVE_NODES } from "@/components/chat/markdownRenderConfig";

const props = defineProps<{
  content: string;
  refs: { used?: Array<Record<string, unknown>> } | null;
  isDark: boolean;
  customHtmlTags: string[];
  isStreaming?: boolean;
}>();

const isDarkRef = computed(() => props.isDark);
const refsByIndex = computed(() => {
  const messageRefs = props.refs;
  const refs =
    messageRefs && Array.isArray(messageRefs.used) ? messageRefs.used : [];
  return refs.reduce<Record<string, Record<string, unknown>>>((acc, item) => {
    if (item.index != null) {
      acc[String(item.index)] = item;
    }
    return acc;
  }, {});
});

provide("isDark", isDarkRef);
provide("webSearchResults", () => refsByIndex.value);
</script>
