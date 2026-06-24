<!-- Author: elecvoid243
     Date: 2026-06-24
     Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §6.4
     Submission dialog for the commit workflow. Mirrors the inline
     <v-dialog persistent> pattern of the existing restore dialog so
     the UX is consistent. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/chat");

const props = defineProps<{
  modelValue: boolean;
  stagedFiles: string[];
  isCommitting: boolean;
  /** Last failure reason + stderr; dialog stays open on failure so
   *  the user can edit message and retry (spec §3.3.4). */
  lastError?: { reason: string; stderr: string };
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "confirm", payload: { message: string }): void;
  (e: "cancel"): void;
}>();

// Spec §6.4.2: 8192 char cap; 7000 is the warning threshold (P1-6 fix).
const MAX_MESSAGE = 8192;
const WARN_MESSAGE = 7000;

const message = ref<string>("");

// Reset message + lastError every time the dialog opens.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      message.value = "";
    }
  },
);

const trimmedLength = computed(() => message.value.trim().length);
const rawLength = computed(() => message.value.length);
const overWarn = computed(() => rawLength.value > WARN_MESSAGE);
const overMax = computed(() => rawLength.value > MAX_MESSAGE);
const canSubmit = computed(
  () => trimmedLength.value > 0 && !overMax.value && !props.isCommitting,
);

function charCounterClass(): string {
  if (overMax.value) return "commit-char-counter is-error";
  if (overWarn.value) return "commit-char-counter is-warning";
  return "commit-char-counter";
}

function onSubmit(): void {
  if (!canSubmit.value) return;
  emit("confirm", { message: message.value });
}

function onCancel(): void {
  if (props.isCommitting) return;
  emit("cancel");
  emit("update:modelValue", false);
}

function onKeydown(e: KeyboardEvent): void {
  // Spec §6.4.2: Ctrl+Enter 提交
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    onSubmit();
  }
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    persistent
    max-width="560"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <v-card>
      <v-card-title class="text-h6">
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.title") }}
      </v-card-title>
      <v-card-text>
        <label class="commit-message-label">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.messageLabel") }}
        </label>
        <textarea
          v-model="message"
          class="commit-message-textarea"
          rows="5"
          :placeholder="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.messagePlaceholder')"
          :disabled="isCommitting"
          @keydown="onKeydown"
        />
        <div :class="charCounterClass()">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.charCounter", { count: rawLength }) }}
        </div>

        <div class="commit-staged-title">
          {{
            tm(
              "spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.stagedFilesTitle",
              { count: stagedFiles.length },
            )
          }}
        </div>
        <ul v-if="stagedFiles.length > 0" class="commit-staged-list">
          <li v-for="f in stagedFiles" :key="f" class="commit-staged-item">
            <v-icon size="12" class="commit-staged-bullet">mdi-circle-small</v-icon>
            <span class="commit-staged-path">{{ f }}</span>
          </li>
        </ul>
        <div v-else class="commit-staged-empty">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.stagedFilesEmpty") }}
        </div>

        <div v-if="lastError && lastError.stderr" class="commit-stderr">
          <div class="commit-stderr-title">
            {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.stderrTitle") }}
          </div>
          <pre class="commit-stderr-pre">{{ lastError.stderr }}</pre>
        </div>

        <div class="commit-shortcut-hint">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.submitShortcutHint") }}
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="isCommitting" @click="onCancel">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.cancel") }}
        </v-btn>
        <v-btn
          variant="flat"
          color="primary"
          :loading="isCommitting"
          :disabled="!canSubmit"
          @click="onSubmit"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.confirm") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.commit-message-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.8);
  margin-bottom: 4px;
}
.commit-message-textarea {
  width: 100%;
  min-height: 120px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  box-sizing: border-box;
}
.commit-message-textarea:focus {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -1px;
  border-color: transparent;
}
.commit-message-textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.commit-char-counter {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 12px;
  text-align: right;
  margin-top: 4px;
}
.commit-char-counter.is-warning {
  color: rgb(var(--v-theme-warning));
  font-weight: 500;
}
.commit-char-counter.is-error {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}

.commit-staged-title {
  margin-top: 12px;
  font-size: 12px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.commit-staged-list {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  max-height: 120px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.02);
}
.commit-staged-item {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
  font-family: monospace;
  font-size: 12px;
}
.commit-staged-bullet {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.commit-staged-path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.commit-staged-empty {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-style: italic;
  margin-top: 2px;
}

.commit-stderr {
  margin-top: 12px;
  padding: 8px 10px;
  background: rgba(248, 81, 73, 0.08);
  border: 1px solid rgba(248, 81, 73, 0.3);
  border-radius: 4px;
}
.commit-stderr-title {
  font-size: 12px;
  font-weight: 600;
  color: rgb(248, 81, 73);
  margin-bottom: 6px;
}
.commit-stderr-pre {
  margin: 0;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.12);
  color: inherit;
  border-radius: 4px;
  font-size: 11px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.commit-shortcut-hint {
  margin-top: 8px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
</style>
