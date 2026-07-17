<!-- Author: elecvoid243
     Date: 2026-06-24
     Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §6.4
     Submission dialog for the commit workflow. Mirrors the inline
     <v-dialog persistent> pattern of the existing restore dialog so
     the UX is consistent. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeGitDiff,
  type SpcodeGitDiffRawResponse,
  type SpcodeGitDiffSnapshot,
} from "@/composables/parseSpcodeGitDiff";
import { buildCommitMessagePrompt } from "@/composables/commitMessagePrompt";
import { useSpcodeBtw } from "@/composables/useSpcodeBtw";

const { tm } = useModuleI18n("features/chat");

const props = defineProps<{
  modelValue: boolean;
  stagedFiles: string[];
  isCommitting: boolean;
  /** Last failure reason + stderr; dialog stays open on failure so
   *  the user can edit message and retry (spec §3.3.4). */
  lastError?: { reason: string; stderr: string };
  /** Current session origin; forwarded to the git-diff and btw calls. */
  umo: string | null;
  /** Selected worktree path (null = primary); forwarded to git-diff. */
  worktree: string | null;
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

// Reset message + lastError + generate error every time the dialog opens.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      message.value = "";
      generateErrorKey.value = null;
    }
  },
);

// ── AI commit-message generation (spec 2026-07-17 §4.3) ────────────
const { locale } = useI18n();
const btw = useSpcodeBtw();

// Persisted language for the generated message. Mirrors the sidebar's
// safeGetItem/safeSetItem convention: never throw, invalid values fall
// back to the default (zh when the UI locale is zh-CN, else en).
const COMMIT_MSG_LANG_KEY = "astrbot.spcode.gitDiffSidebar.commitMsgLang";
type MsgLang = "zh" | "en";

function loadMsgLang(): MsgLang {
  try {
    const v = localStorage.getItem(COMMIT_MSG_LANG_KEY);
    if (v === "zh" || v === "en") return v;
  } catch {
    /* localStorage may be unavailable (private mode) — fall through */
  }
  return locale.value === "zh-CN" ? "zh" : "en";
}

const msgLanguage = ref<MsgLang>(loadMsgLang());
watch(msgLanguage, (v) => {
  try {
    localStorage.setItem(COMMIT_MSG_LANG_KEY, v);
  } catch {
    /* no-op */
  }
});

// i18n key suffix of the last generate failure; null = no error.
const generateErrorKey = ref<string | null>(null);

// Set by onCancel so a late git-diff/btw resolution never overwrites a
// closed dialog's state (btw itself is aborted via btw.cancel()).
let generateAborted = false;

const canGenerate = computed(
  () =>
    props.stagedFiles.length > 0 &&
    !!props.umo &&
    !props.isCommitting &&
    !btw.isGenerating.value,
);

async function onGenerate(): Promise<void> {
  if (!canGenerate.value || !props.umo) return;
  generateAborted = false;
  generateErrorKey.value = null;
  // 1. Fetch the fresh staged diff — the btw endpoint mounts no LLM
  //    tools, so the change content must be embedded in the prompt.
  let snapshot: SpcodeGitDiffSnapshot;
  try {
    const resp = await pluginExtensionApi.get<SpcodeGitDiffRawResponse>(
      "spcode/git-diff",
      {
        params: {
          umo: props.umo,
          scope: "staged",
          ...(props.worktree ? { worktree: props.worktree } : {}),
        },
      },
    );
    const data = resp.data?.data;
    if (!data) throw new Error("empty git-diff response");
    snapshot = parseSpcodeGitDiff(data);
  } catch {
    if (!generateAborted) generateErrorKey.value = "diff_fetch_failed";
    return;
  }
  if (generateAborted) return;
  // 2. Build the bilingual prompt and ask btw.
  const prompt = buildCommitMessagePrompt({
    language: msgLanguage.value,
    files: snapshot.files,
    rawDiff: snapshot.rawDiff,
  });
  const result = await btw.ask({ prompt, umo: props.umo });
  if (result.ok) {
    message.value = result.reply;
    return;
  }
  if (result.reason === "aborted") return; // dialog cancelled mid-flight
  generateErrorKey.value =
    result.reason === "no_provider" ||
    result.reason === "empty_response" ||
    result.reason === "llm_error" ||
    result.reason === "network"
      ? result.reason
      : "unknown";
}

onBeforeUnmount(() => {
  btw.dispose();
});

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
  // Abort any in-flight generation; unlike commit-in-flight, generation
  // never blocks closing (btw is side-effect-free).
  generateAborted = true;
  btw.cancel();
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
        <div class="commit-message-label-row">
          <label class="commit-message-label">
            {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.messageLabel") }}
          </label>
          <div class="commit-generate-controls">
            <v-btn-toggle
              v-model="msgLanguage"
              mandatory
              density="compact"
              variant="tonal"
              :aria-label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.langToggleAria')"
            >
              <v-btn value="zh" size="x-small">
                {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.langZh") }}
              </v-btn>
              <v-btn value="en" size="x-small">
                {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.langEn") }}
              </v-btn>
            </v-btn-toggle>
            <v-btn
              variant="text"
              size="small"
              color="primary"
              prepend-icon="mdi-auto-fix"
              :loading="btw.isGenerating.value"
              :disabled="!canGenerate"
              :aria-label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.generateAria')"
              @click="onGenerate"
            >
              {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.generate") }}
            </v-btn>
          </div>
        </div>
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
        <div v-if="generateErrorKey" class="commit-generate-error">
          {{ tm(`spcodeProjectLoad.diffSidebar.gitWorkflow.commit.dialog.generateError.${generateErrorKey}`) }}
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
.commit-message-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.commit-message-label-row .commit-message-label {
  margin-bottom: 0;
}
.commit-generate-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.commit-generate-error {
  margin-top: 4px;
  font-size: 12px;
  color: rgb(var(--v-theme-error));
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
