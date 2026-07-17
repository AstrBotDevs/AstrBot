<!-- Author: elecvoid243
     Date: 2026-07-17
     Shiki overlay code editor: a transparent <textarea> stacked on top
     of a Shiki-highlighted layer. The textarea owns input / caret /
     selection; the layer underneath renders colors through the SAME
     highlighter pipeline as the read-only preview (renderShikiCode +
     "auto" dual theme), so edit mode looks identical to browse mode.

     2026-07-18 latency rework (typing must never wait on Vue):
     - UNCONTROLLED textarea: the buffer lives in `internalValue`,
       owned by this component. `modelValue` is the authoritative
       "loaded" content; prop changes that merely echo our own
       emissions (=== lastEmitted) are ignored so a parent re-render
       can never rewrite the textarea mid-typing. External
       replacements (file reloaded) are still adopted.
     - Re-highlight is debounced (~200 ms) and then scheduled through
       requestIdleCallback (setTimeout(0) fallback), so the full-doc
       Shiki pass only runs when the main thread is idle and never
       blocks input echo / paint.
     - `dirty-change` fires on clean↔dirty TRANSITIONS only, letting
       parents track dirtiness without owning per-keystroke state
       (heavy parents like GitDiffSidebar stay out of the keystroke
       render path entirely).
     - Files larger than MAX_HIGHLIGHT_CHARS skip highlighting (plain
       escaped fallback) to keep typing latency flat; editing and
       saving still work.
     - A trailing "\n" gets a zero-width-space sentinel so the
       highlight layer's height matches the textarea's last line. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  detectLanguage,
  ensureShikiLanguages,
  escapeHtml,
  renderShikiCode,
} from "@/utils/shiki";

const props = defineProps<{
  /** Authoritative loaded content (the dirty baseline). Set once per
   *  editing session; external replacements are adopted, own echoes
   *  are ignored. */
  modelValue: string;
  /** Only the extension is used (language detection for the
   *  highlight pass); absolute or relative both work. */
  filePath: string;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  /** Fires ONLY on clean↔dirty transitions (buffer vs modelValue). */
  (e: "dirty-change", dirty: boolean): void;
}>();

/** Beyond this many chars the per-pause re-highlight cost stops
 *  being invisible even on idle; fall back to plain rendering. */
const MAX_HIGHLIGHT_CHARS = 100_000;
const HIGHLIGHT_DEBOUNCE_MS = 200;

// The buffer is owned HERE (uncontrolled textarea): typing updates
// internalValue directly; Vue never writes the textarea's value back
// with parent-round-tripped (potentially stale) content.
const internalValue = ref(props.modelValue);
/** Last content WE emitted upward; a modelValue update equal to this
 *  is our own echo and must not reset the buffer. */
let lastEmitted: string | null = null;

const isDirty = computed(() => internalValue.value !== props.modelValue);
watch(isDirty, (d) => emit("dirty-change", d));

// Adopt EXTERNAL modelValue replacements (e.g. the parent reloaded
// the file). Own echoes (props.modelValue === lastEmitted) are
// ignored — they carry nothing new and would only risk clobbering
// keystrokes that arrived between emit and parent re-render.
watch(
  () => props.modelValue,
  (v) => {
    if (v === lastEmitted) return;
    lastEmitted = null;
    internalValue.value = v;
  },
);

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
let idleHandle: number | null = null;
// requestIdleCallback is missing on some engines (older Safari):
// fall back to a macrotask so input events queued ahead still run
// first in the common case.
const scheduleIdle: (cb: () => void) => number =
  typeof window !== "undefined" && "requestIdleCallback" in window
    ? (cb) => window.requestIdleCallback(cb, { timeout: 500 })
    : (cb) => window.setTimeout(cb, 0) as unknown as number;
const cancelIdle: (h: number) => void =
  typeof window !== "undefined" && "cancelIdleCallback" in window
    ? (h) => window.cancelIdleCallback(h)
    : (h) => clearTimeout(h);

function scheduleHighlight(): void {
  if (debounceTimer) clearTimeout(debounceTimer);
  if (idleHandle !== null) {
    cancelIdle(idleHandle);
    idleHandle = null;
  }
  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    // The full-doc Shiki pass runs only when the main thread is
    // idle — typing never waits on highlighting.
    idleHandle = scheduleIdle(() => {
      idleHandle = null;
      highlightedHtml.value = render(internalValue.value);
    });
  }, HIGHLIGHT_DEBOUNCE_MS);
}
watch(internalValue, scheduleHighlight);
// Re-render once the async highlighter becomes available.
watch(shikiHighlighter, () => {
  highlightedHtml.value = render(internalValue.value);
});
onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer);
  if (idleHandle !== null) cancelIdle(idleHandle);
});

function onInput(e: Event): void {
  const v = (e.target as HTMLTextAreaElement).value;
  internalValue.value = v;
  lastEmitted = v;
  emit("update:modelValue", v);
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
  const next = value.slice(0, s) + "  " + value.slice(end);
  internalValue.value = next;
  lastEmitted = next;
  emit("update:modelValue", next);
  // Restore the caret after Vue re-renders the textarea value.
  requestAnimationFrame(() => {
    ta.selectionStart = ta.selectionEnd = s + 2;
  });
}

function getValue(): string {
  return internalValue.value;
}

function focus(): void {
  textareaRef.value?.focus();
}
defineExpose({ focus, getValue });
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
      :value="internalValue"
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
