<!-- Author: elecvoid243, 2026-06-21
     Spec: docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md §4.3
     2026-07-17 selection-comment: range mode — when `endLine` is
     set and > `line`, the header swaps the single-line ±1 context
     preview for the frozen `selectionContent` (verbatim) and a
     `L{start}-L{end}` label. The save payload now also carries
     `endLine` / `selection` so the parent can route to
     `addSelectionComment` vs `addComment` based on the same shape. -->
<script setup lang="ts">
import { computed, ref, watch, nextTick } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  line: number | null;
  commentId: string | null;
  initialText: string;
  lineContent: string | null;
  contextBefore: string | null;
  contextAfter: string | null;
  filePath: string;
  /** 2026-07-17 selection-comment: 1-based end line for range
   *  comments. Undefined/null or <= `line` means single-line. */
  endLine?: number | null;
  /** 2026-07-17 selection-comment: frozen selected text (range mode).
   *  Renders verbatim in a scrollable <pre> when endLine > line. */
  selectionContent?: string | null;
}>();

interface SavePayload {
  text: string;
  commentId: string | null;
  line: number;
  endLine: number | null;
  selection: string | null;
}

const emit = defineEmits<{
  (e: "save", payload: SavePayload): void;
  (e: "cancel"): void;
  (e: "delete", commentId: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

const text = ref<string>("");
const textareaRef = ref<HTMLTextAreaElement | null>(null);

const isRange = computed<boolean>(
  () => props.endLine != null && props.line != null && props.endLine > props.line,
);

const rangeLabel = computed<string>(() => {
  if (!isRange.value || props.line == null || props.endLine == null) return "";
  return tm("spcodeProjectLoad.fileBrowser.comment.rangeLabel", {
    start: props.line,
    end: props.endLine,
  });
});

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
      emit("save", {
        text: text.value.trim(),
        commentId: props.commentId,
        line: props.line,
        endLine: isRange.value ? props.endLine ?? null : null,
        selection: isRange.value ? props.selectionContent ?? null : null,
      });
    }
  }
}

function onSave(): void {
  if (props.line === null) return;
  emit("save", {
    text: text.value.trim(),
    commentId: props.commentId,
    line: props.line,
    endLine: isRange.value ? props.endLine ?? null : null,
    selection: isRange.value ? props.selectionContent ?? null : null,
  });
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
        {{
          commentId
            ? tm("spcodeProjectLoad.fileBrowser.comment.editTitle", { line })
            : tm("spcodeProjectLoad.fileBrowser.comment.newTitle", { line })
        }}
      </span>
      <!-- 2026-07-17 selection-comment: range header. Sits next to
           the title; the title itself stays the single-line
           anchor (the start line) so existing aria/label flows
           don't have to know about ranges. -->
      <span v-if="isRange" class="editor-range-label" :title="rangeLabel">
        {{ rangeLabel }}
      </span>
      <span v-if="!isRange" class="editor-context">
        <code v-if="contextBefore">{{ contextBefore }}</code>
        <code v-if="lineContent" class="commented-line">{{ lineContent }}</code>
        <code v-if="contextAfter">{{ contextAfter }}</code>
      </span>
    </div>
    <!-- Range mode replaces the ±1 context preview with the frozen
         selection. Verbatim, no syntax highlighting: this is what
         the user dragged, not the rest of the file. -->
    <pre v-if="isRange" class="comment-editor-selection">{{ selectionContent }}</pre>
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
        @click="onSave"
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
.editor-range-label {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
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
.comment-editor-selection {
  max-height: 140px;
  overflow: auto;
  margin: 0 0 8px 0;
  padding: 6px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 4px;
  background: rgba(var(--v-theme-primary), 0.04);
  font-family: ui-monospace, monospace;
  font-size: 11.5px;
  white-space: pre;
  color: rgba(var(--v-theme-on-surface), 0.85);
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
</style>
