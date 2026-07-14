<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.2
     Top-of-page path editor. Click to edit, Enter/blur commits,
     Esc reverts, the ↺ button writes the default. Validation runs
     on commit; failures show inline red and do NOT emit. Storage
     failures are signaled by the parent via the storageOk prop. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  isValidDocsRoot,
  coerceDocsRoot,
} from "@/composables/docsRootStorage";

const props = defineProps<{
  currentPath: string;
  storageOk: boolean;
  defaultPath: string;
}>();

const emit = defineEmits<{
  (e: "path-change", path: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

const editing = ref(false);
const draft = ref(props.currentPath);
const error = ref<string | null>(null);

watch(
  () => props.currentPath,
  (p) => {
    if (!editing.value) draft.value = p;
  },
);

function startEdit() {
  draft.value = props.currentPath;
  error.value = null;
  editing.value = true;
}

function commit() {
  if (!editing.value) return;
  const cleaned = coerceDocsRoot(draft.value);
  if (!isValidDocsRoot(cleaned)) {
    error.value = tm("spcodeProjectLoad.documentManager.pathBar.invalidPath");
    return;
  }
  error.value = null;
  editing.value = false;
  if (cleaned !== props.currentPath) {
    emit("path-change", cleaned);
  }
}

function cancel() {
  draft.value = props.currentPath;
  error.value = null;
  editing.value = false;
}

function reset() {
  error.value = null;
  editing.value = false;
  if (props.defaultPath !== props.currentPath) {
    emit("path-change", props.defaultPath);
  }
}

// "Go up one level" — strip the last path segment and emit the
// result if it is a valid (non-empty) docs root. Hidden when the
// current path has no separator (it would have nowhere to go).
const canGoUp = computed<boolean>(() => {
  return coerceDocsRoot(props.currentPath).includes("/");
});
function goUp() {
  error.value = null;
  editing.value = false;
  const cleaned = coerceDocsRoot(props.currentPath);
  if (!cleaned.includes("/")) return;
  // strip the trailing segment; coerceDocsRoot already trimmed
  // the input so we just slice at the last separator.
  const idx = cleaned.lastIndexOf("/");
  const parent = cleaned.slice(0, idx);
  if (!isValidDocsRoot(parent)) return;
  if (parent !== props.currentPath) {
    emit("path-change", parent);
  }
}
</script>

<template>
  <div class="document-path-bar">
    <span class="document-path-bar__label">
      {{ tm("spcodeProjectLoad.documentManager.pathBar.label") }}
    </span>
    <input
      v-if="editing"
      v-model="draft"
      type="text"
      class="document-path-bar__input"
      :aria-label="tm('spcodeProjectLoad.documentManager.pathBar.label')"
      :class="{ 'document-path-bar__input--error': !!error }"
      @keydown.enter.prevent="commit"
      @keydown.escape.prevent="cancel"
      @blur="commit"
    />
    <button
      v-else
      type="button"
      class="document-path-bar__display"
      :title="tm('spcodeProjectLoad.documentManager.pathBar.editHint')"
      :aria-label="tm('spcodeProjectLoad.documentManager.pathBar.editHint')"
      @click="startEdit"
    >
      {{ currentPath }}
    </button>
    <button
      v-if="canGoUp"
      type="button"
      class="document-path-bar__up"
      :title="tm('spcodeProjectLoad.documentManager.pathBar.goUpTitle')"
      :aria-label="tm('spcodeProjectLoad.documentManager.pathBar.goUpTitle')"
      @click="goUp"
    >
      <v-icon size="14">mdi-arrow-up</v-icon>
    </button>
    <button
      type="button"
      class="document-path-bar__reset"
      :title="tm('spcodeProjectLoad.documentManager.pathBar.resetTitle')"
      :aria-label="tm('spcodeProjectLoad.documentManager.pathBar.resetTitle')"
      @click="reset"
    >
      <v-icon size="14">mdi-restore</v-icon>
    </button>
    <v-icon
      v-if="!storageOk"
      size="14"
      class="document-path-bar__warning"
      :title="tm('spcodeProjectLoad.documentManager.pathBar.storageWarning')"
    >
      mdi-alert-circle-outline
    </v-icon>
    <span v-if="error" class="document-path-bar__error">{{ error }}</span>
  </div>
</template>

<style scoped>
.document-path-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  min-width: 0;
}
.document-path-bar__label {
  flex: 0 0 auto;
  font-weight: 500;
}
.document-path-bar__display {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
  background: transparent;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 4px;
  padding: 2px 6px;
  font-family: monospace;
  font-size: 11.5px;
  color: rgb(var(--v-theme-on-surface));
  cursor: text;
}
.document-path-bar__display:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
}
.document-path-bar__input {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 200px;
  background: var(--v-theme-surface, transparent);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.3);
  border-radius: 4px;
  padding: 2px 6px;
  font-family: monospace;
  font-size: 11.5px;
  color: rgb(var(--v-theme-on-surface));
  outline: none;
}
.document-path-bar__input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.document-path-bar__input--error {
  border-color: rgb(var(--v-theme-error));
  color: rgb(var(--v-theme-error));
}
.document-path-bar__reset,
.document-path-bar__up {
  background: transparent;
  border: none;
  padding: 2px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.55);
  display: flex;
  align-items: center;
}
.document-path-bar__reset:hover,
.document-path-bar__up:hover {
  color: rgb(var(--v-theme-primary));
}
.document-path-bar__warning {
  color: rgb(var(--v-theme-warning));
}
.document-path-bar__error {
  color: rgb(var(--v-theme-error));
  font-size: 11px;
}
</style>
