<!--
  MarkdownView — thin wrapper around markstream-vue's <MarkdownRender>.

  2026-07-13 refactor: this used to ship its own renderer
  (createMarkdownRenderer in MarkdownPipeline.ts) plus ~370 lines of
  hand-written markdown CSS. That was a full re-implementation of
  what markstream-vue already does, and it was the reason the
  DocumentManager render looked noticeably uglier than ChatUI's
  chat-message render — they were two completely independent code
  paths with the DocumentManager one missing major features
  (KaTeX, Mermaid, theme tokens, etc.).

  Now this component delegates to the same <MarkdownRender> that
  ChatUI's MarkdownMessagePart uses. The visual output is identical
  to the chat message view: same heading scale, same inline-code
  pill, same table borders, same blockquote treatment, same Shiki
  highlighter, same dark-mode behavior. The previous custom CSS
  block has been deleted; the only style that remains is a thin
  container rule so the rendered HTML has a stable box.

  Consumers (DocumentManager, ReadmeDialog) keep their existing
  prop shape (:source, :is-dark, :container-class) so no caller
  had to change.
-->
<script setup lang="ts">
import { computed } from "vue";
import { useTheme } from "vuetify";
import { MarkdownRender } from "markstream-vue";
import { MARKDOWN_RENDER_MAX_LIVE_NODES } from "@/components/chat/markdownRenderConfig";

const props = defineProps<{
  /** Raw markdown source. The component re-renders on change. */
  source: string;
  /**
   * Force dark mode. When omitted we follow the current Vuetify
   * theme — same behaviour as MarkdownMessagePart in the chat list.
   */
  isDark?: boolean;
  /** Extra class on the root wrapper, e.g. "historical" to mark
   *  historical-revision renders in DocumentManager. */
  containerClass?: string;
}>();

const theme = useTheme();
const isDarkRef = computed(
  () => props.isDark ?? theme.global.current.value.dark,
);
</script>

<template>
  <div class="markdown-body" :class="props.containerClass">
    <MarkdownRender
      custom-id="document-view"
      :content="source"
      :is-dark="isDarkRef"
      :custom-html-tags="[]"
      :final="true"
      :fade="false"
      :typewriter="false"
      :max-live-nodes="MARKDOWN_RENDER_MAX_LIVE_NODES"
    />
  </div>
</template>

<style scoped>
.markdown-body {
  /* Width + word-wrap rules. Visual styling (typography, colors,
     tables, code blocks, blockquotes, headings) is owned by
     markstream-vue's bundled CSS — same CSS that ChatUI uses. */
  width: 100%;
  box-sizing: border-box;
  word-wrap: break-word;
  overflow-wrap: anywhere;
}
</style>
