<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.6
     Edit area with CodeMirror 6 + textarea fallback. Owns the
     edit buffer, dirty tracking, and the action bar (save /
     cancel / copy / delete / rename). Rename is real and uses
     the PATCH /spcode/docs endpoint. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { copyToClipboard } from "@/utils/clipboard";
import CodemirrorHost from "./CodemirrorHost.vue";

const props = defineProps<{
  initialContent: string;
  fileRelative: string;
  isSaving: boolean;
  isDeleting: boolean;
  isRenaming: boolean;
  // Rename failure reason from the parent (set after the PATCH
  // request settles). Used to keep the rename input open so the
  // user can see what went wrong. Cleared when the user opens a
  // new rename dialog or the request succeeds.
  renameErrorMessage: string | null;
  simpleTextarea?: boolean;
}>();
const emit = defineEmits<{
  (e: "save", content: string): void;
  (e: "cancel"): void;
  (e: "delete"): void;
  (e: "rename", newPath: string): void;
  (e: "rename-cancel"): void;
}>();
const { tm } = useModuleI18n("features/chat");

const buffer = ref(props.initialContent);
const showDeleteConfirm = ref(false);
const renameOpen = ref(false);
const renameDraft = ref(props.fileRelative);
const renameError = ref<string | null>(null);
const useTextarea = ref(!!props.simpleTextarea);

const isDirty = computed(() => buffer.value !== props.initialContent);

watch(
  () => props.initialContent,
  (v) => {
    buffer.value = v;
  },
);

function onCancel() {
  if (isDirty.value) {
    const ok = window.confirm(
      tm("spcodeProjectLoad.documentManager.editor.cancelDirty"),
    );
    if (!ok) return;
  }
  emit("cancel");
}

function onSave() {
  if (!isDirty.value || props.isSaving) return;
  emit("save", buffer.value);
}

function onCopyRaw() {
  void copyToClipboard(buffer.value);
}

function onDeleteClick() {
  showDeleteConfirm.value = true;
}
function onDeleteConfirm() {
  showDeleteConfirm.value = false;
  emit("delete");
}

function onRenameOpen() {
  renameDraft.value = props.fileRelative;
  renameError.value = null;
  renameOpen.value = true;
}
function onRenameCancel() {
  renameOpen.value = false;
  renameError.value = null;
}
function onRenameSubmit() {
  const trimmed = renameDraft.value.trim();
  if (!trimmed || trimmed === props.fileRelative) {
    renameOpen.value = false;
    return;
  }
  if (!/^[\w\-./ ]+\.md$/i.test(trimmed)) {
    renameError.value = tm(
      "spcodeProjectLoad.documentManager.editor.filenameInvalid",
    );
    return;
  }
  // Do NOT close the dialog here — the request is async and we
  // want the user to see the failure reason (server error,
  // path_unsafe, file_exists, ...) if it does. The watcher
  // below closes the dialog on the success branch only.
  renameError.value = null;
  emit("rename", trimmed);
}

// Close the rename dialog AFTER the request resolves, but only
// on success. On failure we keep it open so the user sees the
// reason supplied by the parent. `isRenaming` is true while the
// PATCH is in flight; the dialog stays open the whole time so the
// user gets visual feedback (button shows "重命名中" via the
// outer bar's `:disabled="isRenaming"`).
watch(
  [() => props.isRenaming, () => props.renameErrorMessage],
  ([renaming, parentErr]) => {
    if (renaming) return;
    if (!renameOpen.value) return;
    if (parentErr) {
      // Mirror the parent's reason into our local field so the
      // existing error slot below the input can render it.
      renameError.value = parentErr;
      return;
    }
    renameOpen.value = false;
  },
);

function onCodemirrorUpdate(v: string) {
  buffer.value = v;
}
function onCodemirrorError() {
  useTextarea.value = true;
}
</script>

<template>
  <div class="document-editor">
    <CodemirrorHost
      v-if="!useTextarea"
      :model-value="buffer"
      language="markdown"
      @update:model-value="onCodemirrorUpdate"
      @error="onCodemirrorError"
    />
    <textarea
      v-else
      v-model="buffer"
      class="document-editor__textarea"
      spellcheck="false"
    />
    <div class="document-editor__bar">
      <button
        type="button"
        class="document-editor__btn document-editor__btn--primary"
        :disabled="!isDirty || isSaving"
        @click="onSave"
      >
        <v-icon size="14">mdi-content-save-outline</v-icon>
        {{
          isSaving
            ? tm("spcodeProjectLoad.documentManager.editor.saving")
            : tm("spcodeProjectLoad.documentManager.editor.save")
        }}
      </button>
      <button type="button" class="document-editor__btn" @click="onCancel">
        <v-icon size="14">mdi-close</v-icon>
        {{ tm("spcodeProjectLoad.documentManager.editor.cancel") }}
      </button>
      <button
        type="button"
        class="document-editor__btn"
        :title="tm('spcodeProjectLoad.documentManager.editor.rename')"
        :disabled="isRenaming"
        @click="onRenameOpen"
      >
        <v-icon size="14">mdi-rename-outline</v-icon>
        {{ tm("spcodeProjectLoad.documentManager.editor.rename") }}
      </button>
      <button type="button" class="document-editor__btn" @click="onCopyRaw">
        <v-icon size="14">mdi-content-copy</v-icon>
      </button>
      <span class="document-editor__spacer" />
      <button
        v-if="!showDeleteConfirm"
        type="button"
        class="document-editor__btn document-editor__btn--danger"
        :disabled="isDeleting"
        @click="onDeleteClick"
      >
        <v-icon size="14">mdi-delete-outline</v-icon>
        {{ tm("spcodeProjectLoad.documentManager.editor.delete") }}
      </button>
      <span v-else class="document-editor__confirm">
        {{
          tm("spcodeProjectLoad.documentManager.editor.deleteConfirmBody", {
            path: fileRelative,
          })
        }}
        <button
          type="button"
          class="document-editor__btn document-editor__btn--danger"
          @click="onDeleteConfirm"
        >
          {{ tm("spcodeProjectLoad.documentManager.editor.delete") }}
        </button>
        <button
          type="button"
          class="document-editor__btn"
          @click="showDeleteConfirm = false"
        >
          {{ tm("spcodeProjectLoad.documentManager.editor.cancel") }}
        </button>
      </span>
    </div>

    <div v-if="renameOpen" class="document-editor__rename">
      <input
        v-model="renameDraft"
        type="text"
        class="document-editor__rename-input"
        @keydown.enter.prevent="onRenameSubmit"
        @keydown.escape.prevent="renameOpen = false"
      />
      <button
        type="button"
        class="document-editor__btn document-editor__btn--primary"
        @click="onRenameSubmit"
      >
        {{ tm("spcodeProjectLoad.documentManager.editor.rename") }}
      </button>
      <button
        type="button"
        class="document-editor__btn"
        @click="renameOpen = false"
      >
        {{ tm("spcodeProjectLoad.documentManager.editor.cancel") }}
      </button>
      <span v-if="renameError" class="document-editor__rename-error">{{
        renameError
      }}</span>
    </div>
  </div>
</template>

<style scoped>
.document-editor {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  gap: 6px;
  padding: 6px;
}
.document-editor__textarea {
  flex: 1 1 auto;
  min-height: 0;
  resize: none;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.5;
  padding: 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 4px;
  background: var(--v-theme-surface, transparent);
  color: rgb(var(--v-theme-on-surface));
  outline: none;
}
.document-editor__textarea:focus {
  border-color: rgb(var(--v-theme-primary));
}
.document-editor__bar {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding-top: 4px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.document-editor__spacer {
  flex: 1 1 auto;
}
.document-editor__btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  padding: 3px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  background: transparent;
  border-radius: 4px;
  color: rgba(var(--v-theme-on-surface), 0.75);
  cursor: pointer;
}

.document-editor__btn:hover:not(:disabled) {
  border-color: rgba(var(--v-theme-primary), 0.4);
  color: rgb(var(--v-theme-primary));
}
.document-editor__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.document-editor__btn--primary {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.4);
  color: rgb(var(--v-theme-primary));
}
.document-editor__btn--primary:disabled {
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgba(var(--v-theme-on-surface), 0.4);
}
.document-editor__btn--danger {
  color: rgb(var(--v-theme-error));
  border-color: rgba(var(--v-theme-error), 0.4);
}
.document-editor__btn--danger:hover:not(:disabled) {
  background: rgba(var(--v-theme-error), 0.08);
}

.document-editor__confirm {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgb(var(--v-theme-error));
}
.document-editor__rename {
  display: flex;
  align-items: center;
  gap: 4px;
}
.document-editor__rename-input {
  flex: 1 1 auto;
  font-family: monospace;
  font-size: 12px;
  padding: 2px 6px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.3);
  border-radius: 4px;
  background: var(--v-theme-surface, transparent);
  color: rgb(var(--v-theme-on-surface));
  outline: none;
}
.document-editor__rename-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.document-editor__rename-error {
  font-size: 11px;
  color: rgb(var(--v-theme-error));
}
</style>
