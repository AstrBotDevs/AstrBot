<!-- Author: elecvoid243, 2026-07-02
     Read-only preview dialog for all file-review comments in the
     current session. Comments are grouped by file, sorted by line
     within each group. Each comment has a collapsible code-context
     block:
       - File-browser comments: ±CONTEXT_LINES rows pulled from
         the shared content cache (must match the LLM-facing
         formatForLLM output).
       - Diff comments: the full hunk with the commented line
         marked with `>`.
     Per-comment delete (no confirm). Footer has "clear all" (parent
     handles confirm) + "close". Pure presentational; emits all
     mutations to the parent so the store stays a single source of
     truth (useFileComments). See spec §4.2. -->
<script setup lang="ts">
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  useFileComments,
  type FileComment,
} from "@/composables/useFileComments";

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
const fileComments = useFileComments();

// Per-comment expand state. Keyed by FileComment.id. Independent
// of the dialog's open/close so choices persist across re-opens
// within the same session. Stored in a Set wrapped in ref so the
// template's isExpanded() check tracks the reactive update.
const expandedIds = ref<Set<string>>(new Set());

function isExpanded(id: string): boolean {
  return expandedIds.value.has(id);
}

function toggleExpand(id: string): void {
  // Replace the Set so Vue picks up the change (mutating in place
  // would not trigger the re-render we need for the chevron swap).
  const next = new Set(expandedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedIds.value = next;
}

// Mirrors useFileComments' CONTEXT_LINES. Both render the same
// "±3" window so what the user sees here matches what the LLM
// actually receives via formatForLLM. If you change one, change
// the other.
const CONTEXT_LINES = 3;

interface PreviewRow {
  lineNo: string;
  prefix: string;
  content: string;
}

/**
 * Build the rows shown when a comment is expanded. Mirrors
 * formatForLLM's two code paths (hunk vs window) so the user
 * sees exactly what the LLM will receive for this comment.
 */
function previewRows(c: FileComment): PreviewRow[] {
  if (c.diffHunk) {
    // Diff hunk: render every line in the hunk with its unified-diff
    // prefix; mark the commented new-side line with `>`.
    return c.diffHunk.lines.map((line) => {
      const isMarked = line.newNo === c.diffHunk!.newLine;
      const prefix = isMarked
        ? ">"
        : line.type === "add"
        ? "+"
        : line.type === "del"
        ? "-"
        : " ";
      const lineNo =
        line.newNo !== null
          ? String(line.newNo)
          : line.oldNo !== null
          ? String(line.oldNo)
          : "    ";
      return {
        lineNo: lineNo.padStart(4),
        prefix,
        content: line.content,
      };
    });
  }
  // File-browser window: ±CONTEXT_LINES from contentCache, marked
  // line gets `>`. Same source-of-truth order as formatForLLM's
  // renderWindow (cache first, then ±1 comment-snapshot fallback).
  const fileContent = fileComments.getFileContent(c.filePath);
  const fileLines = fileContent?.split("\n") ?? [];
  const totalLines = fileLines.length;
  const ctxStart = Math.max(1, c.line - CONTEXT_LINES);
  const ctxEnd =
    totalLines > 0
      ? Math.min(totalLines, c.line + CONTEXT_LINES)
      : c.line + CONTEXT_LINES;
  const rows: PreviewRow[] = [];
  for (let line = ctxStart; line <= ctxEnd; line++) {
    rows.push({
      lineNo: String(line).padStart(4),
      prefix: line === c.line ? ">" : " ",
      content: line - 1 < fileLines.length ? fileLines[line - 1] : "",
    });
  }
  return rows;
}

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
        {{
          tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.title", {
            count: totalCount,
          })
        }}
        <v-spacer />
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          :aria-label="
            tm(
              'spcodeProjectLoad.fileBrowser.comment.previewDialog.closeButton',
            )
          "
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
                {{
                  tm(
                    "spcodeProjectLoad.fileBrowser.comment.previewDialog.lineLabel",
                    { line: c.line },
                  )
                }}
              </span>
              <code class="comments-preview-snippet">{{ c.lineContent }}</code>
              <v-spacer />
              <v-btn
                :icon="isExpanded(c.id) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                variant="text"
                size="x-small"
                :aria-label="
                  isExpanded(c.id)
                    ? tm(
                        'spcodeProjectLoad.fileBrowser.comment.previewDialog.collapseContext',
                      )
                    : tm(
                        'spcodeProjectLoad.fileBrowser.comment.previewDialog.expandContext',
                      )
                "
                @click="toggleExpand(c.id)"
              />
              <v-btn
                icon="mdi-close"
                variant="text"
                size="x-small"
                color="error"
                :aria-label="
                  tm(
                    'spcodeProjectLoad.fileBrowser.comment.previewDialog.deleteButton',
                  )
                "
                @click="emit('delete-comment', c.id)"
              />
            </header>
            <p class="comments-preview-text">{{ c.text }}</p>
            <div v-if="isExpanded(c.id)" class="comments-preview-context">
              <div class="comments-preview-pre">
                <div
                  v-for="(row, idx) in previewRows(c)"
                  :key="idx"
                  class="comments-preview-row"
                  :class="{
                    'comments-preview-row--marked': row.prefix === '>',
                  }"
                >
                  {{
                    "  " + row.prefix + " " + row.lineNo + " │ " + row.content
                  }}
                </div>
              </div>
            </div>
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
          {{
            tm(
              "spcodeProjectLoad.fileBrowser.comment.previewDialog.clearAllButton",
            )
          }}
        </v-btn>
        <v-btn variant="flat" @click="close">
          {{
            tm(
              "spcodeProjectLoad.fileBrowser.comment.previewDialog.closeButton",
            )
          }}
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

/* Collapsible code-context block. Mirrors the LLM-facing
   formatForLLM output line-by-line (padded line number, marker,
   `│` separator, content) so the user can spot-check exactly
   what will be sent. */
.comments-preview-context {
  margin-top: 6px;
}
.comments-preview-pre {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  line-height: 1.45;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 4px;
  padding: 4px 8px;
  max-height: 280px;
  overflow: auto;
}
.comments-preview-row {
  white-space: pre;
  padding: 0 4px;
  border-radius: 2px;
  min-height: 1.45em;
}
.comments-preview-row--marked {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgba(var(--v-theme-on-surface), 0.95);
}
</style>
