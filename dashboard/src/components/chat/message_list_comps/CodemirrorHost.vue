<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.6
     Thin CodeMirror 6 mount/unmount wrapper. Lazy-imports CM6
     modules so the dashboard's initial bundle stays small. If any
     import throws, emits "error" and the parent falls back to a
     plain <textarea>. -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{
  modelValue: string;
  language?: "markdown";
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  (e: "ready"): void;
  (e: "error", err: Error): void;
}>();

const hostEl = ref<HTMLElement | null>(null);
// `view` is set inside onMounted (after the async CM imports resolve).
// Typed as `any` to keep this file free of CM6 imports for the
// bundle-size-sensitive build path; the actual shape is the
// EditorView instance created below. The few fields we touch
// (destroy / state.doc / dispatch) are all stable across CM6
// minor versions.
let view: any = null;
// Buffer the last value we EMITTED upward so the props.modelValue
// watcher can distinguish a genuine external update (parent passed a
// new doc string) from a self-induced one (we just emitted the same
// string back via update:modelValue). Without this guard every
// keystroke triggers a full doc.replace in CM, which (a) costs O(n)
// on every keypress, (b) resets the editor selection back to the
// start of the document on each replacement, and (c) cascades into
// a docChanged → emit → parent ref → watch → replace → emit ... loop
// that swallows the user's second character outright.
let lastEmittedValue: string | null = null;

onMounted(async () => {
  if (!hostEl.value) return;
  try {
    const [
      { EditorState },
      { EditorView, keymap, lineNumbers, highlightActiveLine },
      { defaultKeymap, history, historyKeymap },
      { markdown },
    ] = await Promise.all([
      import("@codemirror/state"),
      import("@codemirror/view"),
      import("@codemirror/commands"),
      import("@codemirror/lang-markdown"),
    ]);

    const update = EditorView.updateListener.of((u) => {
      if (!u.docChanged) return;
      const next = u.state.doc.toString();
      lastEmittedValue = next;
      emit("update:modelValue", next);
    });

    const state = EditorState.create({
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        markdown(),
        update,
      ],
    });
    view = new EditorView({ state, parent: hostEl.value });
    lastEmittedValue = props.modelValue;
    emit("ready");
  } catch (err) {
    emit("error", err instanceof Error ? err : new Error(String(err)));
  }
});

// Sync the CM doc with an *external* change to modelValue. We
// intentionally skip the case where the new value is exactly what
// we just emitted ourselves — that's the parent reflecting our own
// edit back through v-model, not a new doc to load.
watch(
  () => props.modelValue,
  (v) => {
    if (!view) return;
    if (v === lastEmittedValue) return; // self-induced, no-op
    const current = view.state.doc.toString();
    if (current === v) {
      // Parent caught up to CM (e.g. via a debounced buffer write).
      // Update our echo tracker so the next external change still
      // takes effect.
      lastEmittedValue = v;
      return;
    }
    lastEmittedValue = v;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: v },
    });
  },
);

onBeforeUnmount(() => {
  view?.destroy();
  view = null;
});
</script>

<template>
  <div ref="hostEl" class="codemirror-host" />
</template>

<style scoped>
.codemirror-host {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 4px;
  font-family: monospace;
  font-size: 13px;
  background: var(--v-theme-surface, transparent);
}
</style>
