<!-- Author: elecvoid243, 2026-06-21
     Spec: docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md §4.3 -->
<script setup lang="ts">
import { ref, watch, nextTick } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  line: number | null;
  commentId: string | null;
  initialText: string;
  lineContent: string | null;
  contextBefore: string | null;
  contextAfter: string | null;
  filePath: string;
}>();

const emit = defineEmits<{
  (e: "save", payload: { text: string; commentId: string | null; line: number }): void;
  (e: "cancel"): void;
  (e: "delete", commentId: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

const text = ref<string>("");
const textareaRef = ref<HTMLTextAreaElement | null>(null);

watch(
  () => [props.line, props.initialText] as const,
  ([newLine, newText]) => {
    text.value = newText;
    if (newLine !== null) {
      nextTick(() => textareaRef.value?.focus());
    }
  },
  { immediate: true },
);

function handleKeyDown(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    e.preventDefault();
    emit("cancel");
  } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    if (text.value.trim() && props.line !== null) {
      emit("save", { text: text.value.trim(), commentId: props.commentId, line: props.line });
    }
  }
}
</script>

<template>
  <div
    v-if="line !== null"
    class="comment-editor"
    @keydown="handleKeyDown"
  >
    <div class="comment-editor-header">
      <v-icon size="14">mdi-comment-text-outline</v-icon>
      <span class="editor-title">
        {{ commentId
          ? tm("spcodeProjectLoad.fileBrowser.comment.editTitle", { line })
          : tm("spcodeProjectLoad.fileBrowser.comment.newTitle", { line }) }}
      </span>
      <span class="editor-context">
        <code v-if="contextBefore">{{ contextBefore }}</code>
        <code v-if="lineContent" class="commented-line">{{ lineContent }}</code>
        <code v-if="contextAfter">{{ contextAfter }}</code>
      </span>
    </div>
    <textarea
      ref="textareaRef"
      v-model="text"
      class="comment-editor-input"
      rows="3"
      :placeholder="tm('spcodeProjectLoad.fileBrowser.comment.placeholder')"
    />
    <div class="comment-editor-actions">
      <v-btn
        v-if="commentId"
        size="small"
        color="error"
        variant="text"
        @click="emit('delete', commentId)"
      >
        {{ tm("spcodeProjectLoad.fileBrowser.comment.delete") }}
      </v-btn>
      <v-spacer />
      <v-btn size="small" variant="text" @click="emit('cancel')">
        {{ tm("spcodeProjectLoad.fileBrowser.comment.cancel") }}
      </v-btn>
      <v-btn
        size="small"
        color="primary"
        variant="flat"
        :disabled="!text.trim()"
        @click="emit('save', { text: text.trim(), commentId, line })"
      >
        {{ tm("spcodeProjectLoad.fileBrowser.comment.save") }}
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.comment-editor {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  padding: 10px 14px;
  background: rgba(var(--v-theme-surface), 0.6);
  flex-shrink: 0;
}
.comment-editor-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}
.editor-title {
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.editor-context {
  display: flex;
  gap: 6px;
  font-family: ui-monospace, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.commented-line {
  color: rgba(var(--v-theme-on-surface), 0.85);
  background: rgba(var(--v-theme-warning), 0.1);
  padding: 0 4px;
  border-radius: 2px;
}
.comment-editor-input {
  width: 100%;
  resize: vertical;
  font-family: inherit;
  font-size: 13px;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  box-sizing: border-box;
}
.comment-editor-input:focus {
  outline: none;
  border-color: rgb(var(--v-theme-primary));
}
.comment-editor-actions {
  display: flex;
  align-items: center;
  margin-top: 8px;
  gap: 4px;
}
.file-browser-preview.is-mobile :deep(.comment-editor) {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgb(var(--v-theme-surface));
  display: flex;
  flex-direction: column;
}
.file-browser-preview.is-mobile :deep(.comment-editor-input) {
  flex: 1;
  resize: none;
}
</style>
