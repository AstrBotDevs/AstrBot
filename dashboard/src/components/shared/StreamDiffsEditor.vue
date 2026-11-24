<template>
  <div ref="host" class="stream-diffs-editor" :style="hostStyle" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import {
  createDiffSurface,
  type DiffSurfaceController,
  type FileContents,
} from 'stream-diffs';

const props = withDefaults(
  defineProps<{
    modelValue: string;
    language?: string;
    themeType?: 'light' | 'dark';
    readonly?: boolean;
    fontSize?: number;
    editStateKey?: string;
  }>(),
  {
    language: 'json',
    themeType: 'light',
    readonly: false,
    fontSize: 13,
    editStateKey: undefined,
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: string];
  change: [value: string];
}>();

// Keep the editor palette identical to the chat code blocks in this app.
const SHIKI_THEMES = { light: 'github-light', dark: 'github-dark' };

// Shiki names a few grammars differently from the language ids the previous
// editors were configured with.
const LANGUAGE_ALIASES: Record<string, string> = {
  plaintext: 'text',
  plain: 'text',
  shell: 'bash',
  sh: 'bash',
  yml: 'yaml',
};

const host = ref<HTMLElement | null>(null);
const hostStyle = computed(() => ({
  '--diffs-font-size': `${props.fontSize}px`,
  '--diffs-line-height': `${Math.round(props.fontSize * 1.5)}px`,
  '--diffs-tab-size': '2',
}));

let controller: DiffSurfaceController | null = null;
let editing = false;
// Last text known to the editor, used to tell our own v-model echo apart from
// an external replacement of the bound value.
let knownText = props.modelValue;
let mountToken = 0;

function resolveLanguage(forcePlainText: boolean): string {
  const language = String(props.language || 'text').toLowerCase();
  return forcePlainText ? 'text' : (LANGUAGE_ALIASES[language] ?? language);
}

function buildFile(contents: string, forcePlainText: boolean): FileContents {
  return {
    name: 'editor',
    contents,
    lang: resolveLanguage(forcePlainText) as FileContents['lang'],
  };
}

function buildOptions(readonly: boolean) {
  return {
    theme: SHIKI_THEMES,
    themeType: props.themeType,
    overflow: 'wrap' as const,
    disableFileHeader: true,
    // 1.7 truncates lines longer than 1000 characters behind a "Show full
    // line" control; editors must show the whole document.
    tokenizeMaxLineLength: 0,
    // Let the edit session reuse the highlighted rows instead of re-running
    // the highlighter on the main thread.
    useTokenTransformer: !readonly,
  };
}

async function startEditing() {
  if (!controller || editing || props.readonly) return;
  editing = true;
  try {
    await controller.startEditing(
      {
        // Monaco never wrapped a selection when a bracket or quote was typed,
        // and upstream's default auto-surround turns a select-all into
        // `{<whole document>}`, which cannot be undone by continuing to type.
        autoSurround: 'never',
        onChange: (event) => {
          const text = event.file.contents;
          if (text === knownText) return;
          knownText = text;
          emit('update:modelValue', text);
          emit('change', text);
        },
      },
      props.editStateKey,
    );
  } catch (error) {
    editing = false;
    console.warn('[StreamDiffsEditor] Failed to start editing session.', error);
  }
}

function stopEditing() {
  if (!controller || !editing) return;
  editing = false;
  controller.stopEditing('complete');
}

async function mountSurface(forcePlainText = false) {
  const element = host.value;
  if (!element) return;
  const token = ++mountToken;
  controller?.dispose();
  controller = null;
  editing = false;
  element.replaceChildren();

  const surface = createDiffSurface({
    kind: 'file',
    file: buildFile(knownText, forcePlainText),
    options: buildOptions(props.readonly),
  });

  try {
    await surface.mount(element);
  } catch (error) {
    if (token !== mountToken) return;
    if (!forcePlainText) {
      // An unknown highlight grammar must not leave the editor blank. The
      // plain-text retry applies to this mount only, so opening a supported
      // file later still gets its grammar.
      surface.dispose();
      await mountSurface(true);
      return;
    }
    console.warn('[StreamDiffsEditor] Failed to mount the code surface.', error);
    return;
  }

  if (token !== mountToken) {
    surface.dispose();
    return;
  }
  controller = surface;
  if (!props.readonly) await startEditing();
}

function replaceAllDocument(text: string) {
  const surface = controller;
  const current = surface?.getEditingText();
  if (!surface || current === undefined) return;
  if (text === current) return;
  const lines = current.split('\n');
  // `applyEdits` reports the change synchronously; mark the text as known
  // first so the resulting change event is not mistaken for a user edit.
  knownText = text;
  try {
    surface.applyEdits([
      {
        range: {
          start: { line: 0, character: 0 },
          end: { line: lines.length - 1, character: lines[lines.length - 1].length },
        },
        newText: text,
      },
    ]);
  } catch (error) {
    knownText = current;
    console.warn('[StreamDiffsEditor] Failed to replace the document.', error);
    return;
  }
  // The surface change callback is suppressed by `knownText` above, so the
  // bound value has to be published here or the applied text never reaches it.
  emit('update:modelValue', text);
}

defineExpose({ replaceAll: replaceAllDocument });

onMounted(mountSurface);

onBeforeUnmount(() => {
  mountToken += 1;
  controller?.dispose();
  controller = null;
  editing = false;
});

watch(
  () => props.modelValue,
  (value) => {
    if (value === knownText) return;
    knownText = value;
    // `update()`/`updateFile()` end an active edit session, so an externally
    // replaced document is re-mounted instead of patched in place.
    void mountSurface();
  },
);

// The grammar is fixed when the surface mounts, so switching to another file
// whose text happens to be identical (an empty file, say) still needs a fresh
// mount to pick up the new language.
watch(
  () => props.language,
  () => {
    // No mounted surface means a mount is already in flight (it cleared the
    // controller before awaiting) or failed; either way there is nothing to
    // re-grammar, and remounting again would only duplicate that work.
    if (!controller) return;
    void mountSurface();
  },
);

watch(
  () => props.readonly,
  (readonly) => {
    if (readonly) stopEditing();
    else void startEditing();
  },
);

watch(
  () => props.themeType,
  () => {
    controller?.setThemeType(props.themeType);
  },
);
</script>

<style scoped>
.stream-diffs-editor {
  height: 100%;
  overflow: auto;
}
</style>
