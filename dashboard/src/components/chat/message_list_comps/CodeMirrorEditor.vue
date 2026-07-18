<!-- Author: elecvoid243
     Date: 2026-07-18
     Spec: docs/superpowers/specs/2026-07-18-codemirror-file-editor-design.md
     CodeMirror 6 file editor — drop-in replacement for the former
     ShikiEditor overlay (identical props/emits/expose contract).

     Why CM6: the Shiki overlay painted text through a debounced
     highlight layer (transparent textarea on top), which forced a
     200ms+ echo delay on every keystroke and re-tokenized the whole
     document per pause. CM6 renders text directly with incremental
     parsing + a virtual viewport, so typing echo is immediate even
     on large files.

     Contract notes (callers rely on these):
     - The per-keystroke buffer lives INSIDE this component; parents
       never listen to update:modelValue (GitIgnoreEditor /
       FileBrowserFilePreview only use dirty-change + getValue()).
     - dirty-change fires ONLY on clean<->dirty transitions.
     - modelValue is the authoritative baseline: external replacements
       are adopted; own echoes (=== lastEmitted) are ignored.
     - If the CM core modules fail to load, the component silently
       degrades to a plain textarea implementing the same contract. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useTheme } from "vuetify";
import { languageKeyForPath, loadLanguage } from "@/utils/codemirrorLanguages";

const props = defineProps<{
  /** Authoritative loaded content (the dirty baseline). Set once per
   *  editing session; external replacements are adopted, own echoes
   *  are ignored. */
  modelValue: string;
  /** Only the extension is used (CM language detection). */
  filePath: string;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  /** Fires ONLY on clean<->dirty transitions (buffer vs modelValue). */
  (e: "dirty-change", dirty: boolean): void;
}>();

// Dark-mode detection via Vuetify (reactive, hot-swapped through a CM
// Compartment). Falls back to light when no Vuetify app is injected
// (unit tests mount the component bare).
let isDark = ref(false);
try {
  const theme = useTheme();
  isDark = computed(() => theme.current.value.dark);
} catch {
  // No Vuetify in context — stay on the light theme.
}

const hostEl = ref<HTMLElement | null>(null);
const textareaRef = ref<HTMLTextAreaElement | null>(null);
/** True when the CM core modules failed to load -> plain textarea. */
const cmFailed = ref(false);

// CM view instance. Typed as any to keep this file free of CM type
// imports; the few fields touched (destroy / state.doc / dispatch /
// focus) are stable across CM6 minor versions.
let view: any = null;
/** Last content WE emitted upward; a modelValue update equal to this
 *  is our own echo and must not reset the buffer. */
let lastEmitted: string | null = null;
let lastDirty = false;
let destroyed = false;

// Buffer for the textarea fallback path (the CM path keeps its buffer
// inside the EditorView document).
const buffer = ref(props.modelValue);

function checkDirty(doc: string): void {
  const d = doc !== props.modelValue;
  if (d !== lastDirty) {
    lastDirty = d;
    emit("dirty-change", d);
  }
}

onMounted(async () => {
  if (!hostEl.value) return;
  try {
    const [
      { EditorState, Compartment },
      { EditorView, keymap, lineNumbers, highlightActiveLine },
      { defaultKeymap, history, historyKeymap, indentWithTab },
      { indentUnit, syntaxHighlighting, defaultHighlightStyle },
      { oneDark },
    ] = await Promise.all([
      import("@codemirror/state"),
      import("@codemirror/view"),
      import("@codemirror/commands"),
      import("@codemirror/language"),
      import("@codemirror/theme-one-dark"),
    ]);
    if (destroyed || !hostEl.value) return;

    const themeComp = new Compartment();
    const langComp = new Compartment();
    const themeExt = (dark: boolean) =>
      dark
        ? oneDark
        : syntaxHighlighting(defaultHighlightStyle, { fallback: true });

    // Font metrics + sizing mirror the former ShikiEditor / the
    // read-only FileBrowserCodeView so edit <-> preview stays visually
    // continuous. Colors come from oneDark / defaultHighlightStyle.
    const baseTheme = EditorView.theme({
      "&": { height: "100%", fontSize: "12.5px" },
      ".cm-scroller": {
        fontFamily: "ui-monospace, monospace",
        lineHeight: "1.55",
      },
      ".cm-gutters": { backgroundColor: "transparent", border: "none" },
    });

    const state = EditorState.create({
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        history(),
        indentUnit.of("  "),
        keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
        baseTheme,
        themeComp.of(themeExt(isDark.value)),
        langComp.of([]),
        EditorView.updateListener.of((u: any) => {
          if (!u.docChanged) return;
          const doc = u.state.doc.toString();
          lastEmitted = doc;
          emit("update:modelValue", doc);
          checkDirty(doc);
        }),
      ],
    });
    view = new EditorView({ state, parent: hostEl.value });
    lastEmitted = props.modelValue;

    // Hot-swap the theme when the Vuetify dark flag flips.
    watch(isDark, (dark) => {
      if (!view) return;
      view.dispatch({ effects: themeComp.reconfigure(themeExt(dark)) });
    });

    // Lazy-load the language pack; failure degrades to plain text.
    const key = languageKeyForPath(props.filePath);
    if (key) {
      try {
        const support = await loadLanguage(key);
        if (!destroyed && view) {
          view.dispatch({ effects: langComp.reconfigure(support) });
        }
      } catch (err) {
        console.warn(
          `CodeMirror language "${key}" failed to load; editing as plain text:`,
          err,
        );
      }
    }
  } catch (err) {
    console.error(
      "CodeMirror init failed; falling back to plain textarea:",
      err,
    );
    cmFailed.value = true;
  }
});

// Adopt EXTERNAL modelValue replacements (e.g. the parent reloaded the
// file). Own echoes are ignored — they carry nothing new and would risk
// clobbering keystrokes that arrived between emit and parent re-render.
watch(
  () => props.modelValue,
  (v) => {
    if (v === lastEmitted) return;
    lastEmitted = null;
    if (view) {
      const cur = view.state.doc.toString();
      if (cur !== v) {
        // The dispatch runs the update listener, which re-emits
        // update:modelValue (harmless echo to the parent) and flips
        // dirty back to clean via checkDirty.
        view.dispatch({ changes: { from: 0, to: cur.length, insert: v } });
      } else {
        checkDirty(v);
      }
    } else {
      buffer.value = v;
      checkDirty(v);
    }
  },
);

// ── Textarea fallback path (only when cmFailed) ─────────────────────

function onInput(e: Event): void {
  const v = (e.target as HTMLTextAreaElement).value;
  buffer.value = v;
  lastEmitted = v;
  emit("update:modelValue", v);
  checkDirty(v);
}

function onKeydown(e: KeyboardEvent): void {
  // Insert two spaces instead of moving focus on Tab (mirrors the CM
  // indentWithTab behavior in the fallback path).
  if (e.key !== "Tab") return;
  e.preventDefault();
  const ta = e.target as HTMLTextAreaElement;
  const { selectionStart: s, selectionEnd: end, value } = ta;
  const next = value.slice(0, s) + "  " + value.slice(end);
  buffer.value = next;
  lastEmitted = next;
  emit("update:modelValue", next);
  checkDirty(next);
  requestAnimationFrame(() => {
    ta.selectionStart = ta.selectionEnd = s + 2;
  });
}

function getValue(): string {
  if (view) return view.state.doc.toString();
  return buffer.value;
}

function focus(): void {
  if (view) view.focus();
  else textareaRef.value?.focus();
}
defineExpose({ focus, getValue });

onBeforeUnmount(() => {
  destroyed = true;
  view?.destroy();
  view = null;
});
</script>

<template>
  <div class="cm-file-editor">
    <!-- v-show (not v-if): the mount element must exist before the
         async CM modules resolve; it simply stays empty + hidden on
         the fallback path. -->
    <div v-show="!cmFailed" ref="hostEl" class="cm-file-editor-mount"></div>
    <textarea
      v-if="cmFailed"
      ref="textareaRef"
      :value="buffer"
      class="cm-file-editor-fallback"
      spellcheck="false"
      autocapitalize="off"
      autocomplete="off"
      autocorrect="off"
      wrap="off"
      @input="onInput"
      @keydown="onKeydown"
    ></textarea>
  </div>
</template>

<style scoped>
.cm-file-editor {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.cm-file-editor-mount {
  flex: 1;
  min-height: 0;
}
.cm-file-editor-mount :deep(.cm-editor) {
  height: 100%;
}
.cm-file-editor-fallback {
  flex: 1;
  width: 100%;
  resize: none;
  border: 0;
  outline: none;
  padding: 8px 14px;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
  tab-size: 2;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
}
</style>
