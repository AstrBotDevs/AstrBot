<template>
  <div class="markdown-content">
    <MarkdownRender
      custom-id="chat-message"
      :content="content"
      :custom-html-tags="customHtmlTags"
      :is-dark="isDark"
      :typewriter="false"
      :max-live-nodes="0"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, provide } from "vue";
import { MarkdownRender } from "markstream-vue";

const props = defineProps<{
  content: string;
  refs: { used?: Array<Record<string, unknown>> } | null;
  isDark: boolean;
  customHtmlTags: string[];
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
