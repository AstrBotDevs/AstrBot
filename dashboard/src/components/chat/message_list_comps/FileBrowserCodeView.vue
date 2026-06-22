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

/** Clear the hovered line when the cursor leaves the entire code-view
 *  (gutter + line numbers + code area). Without this, the add button
 *  would stay visible after the mouse leaves the component. */
function onMouseLeave(): void {
  hoveredLine.value = null;
}
</script>

<template>
  <div
    class="code-view"
    :class="{ dark: isDark }"
    @mousemove="onMouseMove"
    @mouseleave="onMouseLeave"
  >
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
  /* 1.55em matches .code-content line-height * font-size (12.5px).
     The line-height on the cell is required so the cell box itself
     is exactly 1.55em tall — otherwise the flex item's intrinsic
     height uses the default line-height (~1.2) and the cells
     become shorter than the Shiki lines. */
  height: 1.55em;
  display: flex;
  align-items: center;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
.gutter-add-btn {
  /* As soon as the hovered line reveals this button, it must look
     like a real, clickable chip — not a faint glyph that the user
     has to chase. Design intent (matches GitHub PR review gutter):
       • filled tinted background so it pops off the code line in
         both light and dark themes
       • 1.5px solid primary-tinted border for a clear "chip" edge
       • 0.85 baseline opacity: visible the moment it appears, no
         need to "find" it before clicking
       • subtle drop shadow for depth so it reads as a layered
         control, not a glyph painted on the code
     On direct hover/focus the chip becomes a fully-saturated,
     slightly-scaled, glowing target — unmistakable click affordance.
     Previous iteration (opacity 0.35 + transparent bg + thin
     0.4-alpha border) read as a stray text character. */
  opacity: 0.85;
  width: 20px;
  height: 20px;
  background: rgba(var(--v-theme-primary), 0.2);
  border: 1.5px solid rgba(var(--v-theme-primary), 0.7);
  border-radius: 5px;
  cursor: pointer;
  color: rgb(var(--v-theme-primary));
  margin: 0 auto;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  transition:
    opacity 0.12s ease,
    background 0.12s ease,
    border-color 0.12s ease,
    transform 0.12s ease,
    box-shadow 0.12s ease;
}
/* Dark theme: lift the fill a touch and use a deeper shadow.
   Against a dark code background the same rgba(primary, 0.2) tint
   reads weaker than it does in light mode, so we bump the alpha
   and rely on a stronger (darker, larger) shadow for depth. */
.code-view.dark .gutter-add-btn {
  background: rgba(var(--v-theme-primary), 0.28);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
}
.gutter-cell:hover .gutter-add-btn,
.gutter-add-btn:hover,
.gutter-add-btn:focus {
  opacity: 1;
  background: rgba(var(--v-theme-primary), 0.4);
  border-color: rgb(var(--v-theme-primary));
  transform: scale(1.15);
  /* Colored glow on hover mirrors the "primary accent" used
     elsewhere in the sidebar (scope pills, worktree tabs), so
     the affordance language stays consistent. */
  box-shadow: 0 2px 6px rgba(var(--v-theme-primary), 0.45);
}
.gutter-add-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.gutter-comment-indicator {
  width: 18px;
  height: 18px;
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
/* Reset Shiki's default <pre>/<code> styles. Two problems to fix:

   1. The default `<pre>` has `margin: 1em 0` (12.5px top/bottom) which
      pushed code content down relative to the gutter columns — that's
      the "blank line before line 1" symptom.

   2. Shiki emits a literal `\n` between each `<span class="line">`
      (the spans sit on separate source lines). When the `<code>` is
      `display: inline` (UA default) and lives inside a `<pre>`
      (`white-space: pre`), those `\n` text nodes render as line
      breaks, producing the "blank line after every code line" symptom
      and desyncing the line-number column.

   Fix: turn the inner `<code>` into a `flex` column container. Flex
   layout IGNORES the raw text nodes between flex items, so the `\n`
   separators cannot influence box generation at all — independent of
   `white-space` rules. Each `.line` becomes a block-level flex item
   and stacks with zero gap. `white-space: pre` is kept on `.line`
   itself so internal source formatting (multiple spaces in
   `import os`) is preserved.
*/
.code-content :deep(pre) {
  display: block;
  margin: 0;
  padding: 0;
  background: transparent;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
}
.code-content :deep(code) {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  background: transparent;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
}
.code-content :deep(.line) {
  display: block;
  white-space: pre;
  min-height: 1.55em;
  line-height: 1.55;
}
@media (max-width: 760px) {
  .code-view {
    grid-template-columns: 16px auto 1fr;
  }
  .gutter-add-btn,
  .gutter-comment-indicator {
    width: 16px;
    height: 16px;
  }
  .gutter-add-btn {
    font-size: 12px;
  }
}
</style>
