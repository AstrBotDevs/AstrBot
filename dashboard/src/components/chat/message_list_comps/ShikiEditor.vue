<!-- Author: elecvoid243
     Date: 2026-07-17
     Shiki overlay code editor: a transparent <textarea> stacked on top
     of a Shiki-highlighted layer. The textarea owns input / caret /
     selection; the layer underneath renders colors through the SAME
     highlighter pipeline as the read-only preview (renderShikiCode +
     "auto" dual theme), so edit mode looks identical to browse mode.

     Key mechanics:
     - Re-highlight is debounced (~200 ms) on input so a fast typist
       does not trigger a full highlight pass per keystroke.
     - Scroll is synced textarea → highlight layer.
     - Both layers share identical font metrics (ui-monospace 12.5px /
       line-height 1.55, matching FileBrowserCodeView).
     - Files larger than MAX_HIGHLIGHT_CHARS skip highlighting (plain
       escaped fallback) to keep typing latency flat; editing and
       saving still work.
     - A trailing "\n" gets a zero-width-space sentinel so the
       highlight layer's height matches the textarea's last line. -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  detectLanguage,
  ensureShikiLanguages,
  escapeHtml,
  renderShikiCode,
} from "@/utils/shiki";

const props = defineProps<{
  modelValue: string;
  /** Only the extension is used (language detection for the
   *  highlight pass); absolute or relative both work. */
  filePath: string;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
}>();

/** Beyond this many chars the per-keystroke re-highlight cost stops
 *  being invisible; fall back to plain (escaped) rendering. */
const MAX_HIGHLIGHT_CHARS = 500_000;
const HIGHLIGHT_DEBOUNCE_MS = 200;

const textareaRef = ref<HTMLTextAreaElement | null>(null);
const highlightRef = ref<HTMLElement | null>(null);

const shikiHighlighter = ref<any>(null);
onMounted(async () => {
  try {
    shikiHighlighter.value = await ensureShikiLanguages();
  } catch (err) {
    console.error("Shiki init failed (editor):", err);
  }
});

function render(code: string): string {
  // Zero-width-space sentinel: when the buffer ends with "\n" the
  // textarea shows one more (empty) line than Shiki's line spans
  // cover; the sentinel gives that last line height without a
  // visible glyph.
  const display = code.endsWith("\n") ? code + "\u200B" : code;
  if (display.length > MAX_HIGHLIGHT_CHARS || !shikiHighlighter.value) {
    return `<pre><code>${escapeHtml(display)}</code></pre>`;
  }
  try {
    return renderShikiCode(
      shikiHighlighter.value,
      display,
      detectLanguage(props.filePath),
      "auto",
    );
  } catch (err) {
    console.error("Shiki render failed (editor):", err);
    return `<pre><code>${escapeHtml(display)}</code></pre>`;
  }
}

const highlightedHtml = ref<string>(render(props.modelValue));
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => props.modelValue,
  (v) => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      highlightedHtml.value = render(v);
      debounceTimer = null;
    }, HIGHLIGHT_DEBOUNCE_MS);
  },
);
// Re-render once the async highlighter becomes available.
watch(shikiHighlighter, () => {
  highlightedHtml.value = render(props.modelValue);
});
onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer);
});

function onInput(e: Event): void {
  emit("update:modelValue", (e.target as HTMLTextAreaElement).value);
}

function onScroll(): void {
  const ta = textareaRef.value;
  const hl = highlightRef.value;
  if (!ta || !hl) return;
  hl.scrollTop = ta.scrollTop;
  hl.scrollLeft = ta.scrollLeft;
}

function onKeydown(e: KeyboardEvent): void {
  // Insert two spaces instead of moving focus on Tab.
  if (e.key !== "Tab") return;
  e.preventDefault();
  const ta = e.target as HTMLTextAreaElement;
  const { selectionStart: s, selectionEnd: end, value } = ta;
  emit("update:modelValue", value.slice(0, s) + "  " + value.slice(end));
  // Restore the caret after Vue re-renders the textarea value.
  requestAnimationFrame(() => {
    ta.selectionStart = ta.selectionEnd = s + 2;
  });
}

function focus(): void {
  textareaRef.value?.focus();
}
defineExpose({ focus });
</script>

<template>
  <div class="shiki-editor">
    <div
      ref="highlightRef"
      class="shiki-editor-highlight"
      aria-hidden="true"
      v-html="highlightedHtml"
    ></div>
    <textarea
      ref="textareaRef"
      class="shiki-editor-input"
      :value="modelValue"
      spellcheck="false"
      autocapitalize="off"
      autocomplete="off"
      autocorrect="off"
      wrap="off"
      @input="onInput"
      @scroll="onScroll"
      @keydown="onKeydown"
    ></textarea>
  </div>
</template>

<style scoped>
.shiki-editor {
  position: relative;
  height: 100%;
  overflow: hidden;
  /* Font metrics MUST match FileBrowserCodeView exactly so the two
     layers (and the read-only preview) align glyph-for-glyph. */
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
.shiki-editor-highlight,
.shiki-editor-input {
  position: absolute;
  inset: 0;
  margin: 0;
  padding: 8px 14px;
  border: 0;
  font: inherit;
  line-height: inherit;
  letter-spacing: inherit;
  white-space: pre;
  overflow: auto;
  tab-size: 2;
}
.shiki-editor-highlight {
  pointer-events: none;
  user-select: none;
  background: rgb(var(--v-theme-surface));
}
/* Reset Shiki's default <pre>/<code> styles (mirrors
   FileBrowserCodeView): kill the default margin, force transparent
   background, inherit the shared font metrics. */
.shiki-editor-highlight :deep(pre.shiki) {
  margin: 0;
  padding: 0;
  background: transparent !important;
  font: inherit;
  line-height: inherit;
}
.shiki-editor-highlight :deep(code) {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  background: transparent;
  font: inherit;
  line-height: inherit;
}
.shiki-editor-highlight :deep(.line) {
  display: block;
  white-space: pre;
  min-height: 1.55em;
  line-height: 1.55;
}
.shiki-editor-highlight :deep(pre:not(.shiki)) {
  margin: 0;
  font: inherit;
}
.shiki-editor-input {
  resize: none;
  outline: none;
  color: transparent;
  background: transparent;
  caret-color: rgb(var(--v-theme-on-surface));
}
.shiki-editor-input::selection {
  background: rgba(var(--v-theme-primary), 0.28);
}
</style>
