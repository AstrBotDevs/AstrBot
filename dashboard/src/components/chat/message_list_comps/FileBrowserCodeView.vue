<!-- Author: elecvoid243, 2026-06-21
     Spec: docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md §4.2 -->
<script setup lang="ts">
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileComment } from "@/composables/useFileComments";

const props = defineProps<{
  highlightedHtml: string;
  filePath: string;
  comments: FileComment[];
  activeEditLine: number | null;
  activeEditCommentId: string | null;
  isDark: boolean;
}>();

const emit = defineEmits<{
  (e: "request-add", line: number): void;
  (e: "request-edit", commentId: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

/** Total line count derived from the Shiki output by counting
 *  `<span class="line">` wrappers. Single point that knows the
 *  Shiki DOM convention (see spec §6 risk #1). Returns a number
 *  (not an array) so the template can use `v-for="line in count"`. */
const lineCount = computed<number>(() => {
  const m = props.highlightedHtml.match(/<span class="line">/g);
  return m ? m.length : 0;
});

const codeContentRef = ref<HTMLElement | null>(null);
const hoveredLine = ref<number | null>(null);

function hasComment(line: number): boolean {
  return props.comments.some((c) => c.line === line);
}
function commentText(line: number): string {
  return props.comments.find((c) => c.line === line)?.text ?? "";
}
function commentIdFor(line: number): string | null {
  return props.comments.find((c) => c.line === line)?.id ?? null;
}

function onMouseMove(e: MouseEvent): void {
  if (!codeContentRef.value) return;
  const lineEls = codeContentRef.value.querySelectorAll<HTMLElement>(".line");
  for (let i = 0; i < lineEls.length; i++) {
    const rect = lineEls[i].getBoundingClientRect();
    if (rect.bottom > e.clientY) {
      hoveredLine.value = i + 1;
      return;
    }
  }
  hoveredLine.value = lineEls.length || null;
}
</script>

<template>
  <div class="code-view" :class="{ dark: isDark }">
    <div class="code-gutter">
      <div
        v-for="line in lineCount"
        :key="line"
        class="gutter-cell"
      >
        <button
          v-if="line === hoveredLine && !hasComment(line)"
          class="gutter-add-btn"
          :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.addButtonAria', { line })"
          @click="emit('request-add', line)"
        >+</button>
        <button
          v-else-if="hasComment(line)"
          class="gutter-comment-indicator"
          :title="commentText(line)"
          :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.indicatorAria', { line, preview: commentText(line) })"
          @click="emit('request-edit', commentIdFor(line) ?? '')"
        >
          <v-icon size="12">mdi-comment-text-outline</v-icon>
        </button>
      </div>
    </div>
    <div class="line-numbers">
      <div
        v-for="line in lineCount"
        :key="line"
        class="line-number-cell"
      >{{ line }}</div>
    </div>
    <pre
      ref="codeContentRef"
      class="code-content"
      v-html="highlightedHtml"
      @mousemove="onMouseMove"
    />
  </div>
</template>

<style scoped>
.code-view {
  flex: 1;
  display: grid;
  grid-template-columns: 24px auto 1fr;
  min-height: 0;
  overflow: auto;
  background: transparent;
}
.code-gutter,
.line-numbers {
  display: flex;
  flex-direction: column;
}
.gutter-cell,
.line-number-cell {
  min-height: 1.55em;       /* matches .code-content font-size 12.5px * 1.55 */
  display: flex;
  align-items: center;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
.gutter-add-btn {
  opacity: 0;
  width: 20px;
  height: 20px;
  background: transparent;
  border: 1px solid rgba(var(--v-theme-primary), 0.4);
  border-radius: 4px;
  cursor: pointer;
  color: rgb(var(--v-theme-primary));
  margin: 0 auto;
  font-size: 12px;
  line-height: 1;
}
.gutter-cell:hover .gutter-add-btn,
.gutter-add-btn:focus {
  opacity: 1;
}
.gutter-comment-indicator {
  width: 20px;
  height: 20px;
  background: rgba(var(--v-theme-warning), 0.15);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: rgb(var(--v-theme-warning));
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
}
.line-number-cell {
  padding-right: 8px;
  justify-content: flex-end;
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-variant-numeric: tabular-nums;
  user-select: none;
}
.code-content {
  margin: 0;
  padding: 0 14px;
  background: transparent !important;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
.code-content :deep(.line) {
  display: block;
  min-height: 1.55em;
}
@media (max-width: 760px) {
  .code-view {
    grid-template-columns: 16px auto 1fr;
  }
  .gutter-add-btn,
  .gutter-comment-indicator {
    opacity: 1 !important;  /* always visible on mobile (no hover) */
    width: 14px;
    height: 14px;
  }
}
</style>
