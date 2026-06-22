<!-- Author: elecvoid243, 2026-06-22
     Read-only preview dialog for all file-review comments in the
     current session. Comments are grouped by file, sorted by line
     within each group. Per-comment delete (no confirm). Footer has
     "clear all" (parent handles confirm) + "close". Pure presentational;
     emits all mutations to the parent so the store stays a single source
     of truth (useFileComments). See spec §4.2. -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileComment } from "@/composables/useFileComments";

interface CommentGroup {
  filePath: string;
  comments: FileComment[];
}

const props = defineProps<{
  modelValue: boolean;
  groups: CommentGroup[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "delete-comment", commentId: string): void;
  (e: "request-clear-all"): void;
}>();

const { tm } = useModuleI18n("features/chat");

const totalCount = computed<number>(() =>
  props.groups.reduce((n, g) => n + g.comments.length, 0),
);

function close(): void {
  emit("update:modelValue", false);
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="800"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-comment-text-outline</v-icon>
        {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.title", { count: totalCount }) }}
        <v-spacer />
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.previewDialog.closeButton')"
          @click="close"
        />
      </v-card-title>

      <v-card-text class="comments-preview-body">
        <div v-if="groups.length === 0" class="comments-preview-empty">
          {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.empty") }}
        </div>
        <section
          v-for="group in groups"
          :key="group.filePath"
          class="comments-preview-group"
        >
          <h3 class="comments-preview-file">{{ group.filePath }}</h3>
          <article
            v-for="c in group.comments"
            :key="c.id"
            class="comments-preview-item"
          >
            <header class="comments-preview-item-head">
              <span class="comments-preview-line">
                {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.lineLabel", { line: c.line }) }}
              </span>
              <code class="comments-preview-snippet">{{ c.lineContent }}</code>
              <v-spacer />
              <v-btn
                icon="mdi-close"
                variant="text"
                size="x-small"
                color="error"
                :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.previewDialog.deleteButton')"
                @click="emit('delete-comment', c.id)"
              />
            </header>
            <p class="comments-preview-text">{{ c.text }}</p>
          </article>
        </section>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn
          v-if="groups.length > 0"
          color="error"
          variant="text"
          prepend-icon="mdi-delete-sweep"
          @click="emit('request-clear-all')"
        >
          {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.clearAllButton") }}
        </v-btn>
        <v-btn variant="flat" @click="close">
          {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.closeButton") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.comments-preview-body {
  max-height: 60vh;
  padding-top: 8px;
}
.comments-preview-empty {
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.5);
  padding: 48px 0;
}
.comments-preview-group + .comments-preview-group {
  margin-top: 16px;
}
.comments-preview-file {
  font-size: 12px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.65);
  margin: 0 0 6px;
  font-family: ui-monospace, monospace;
  word-break: break-all;
}
.comments-preview-item {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}
.comments-preview-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.comments-preview-line {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.comments-preview-snippet {
  font-size: 12px;
  font-family: ui-monospace, monospace;
  background: rgba(var(--v-theme-on-surface), 0.06);
  padding: 1px 6px;
  border-radius: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.comments-preview-text {
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
