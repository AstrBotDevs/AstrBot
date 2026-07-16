<!-- Author: elecvoid243, 2026-07-16
     Spec: docs/superpowers/specs/2026-07-16-git-repo-init-prompt-design.md §Component -->
<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  directory: string;
  isSubmitting: boolean;
  lastError: { reason: string; stderr?: string } | null;
}>();
const emit = defineEmits<{
  (e: "confirm"): void;
  (e: "cancel"): void;
}>();
const { tm } = useModuleI18n("features/chat");

const errorKey = (reason: string): string =>
  `spcodeProjectLoad.diffSidebar.repoInit.errors.${reason}`;

function onKeyDown(e: KeyboardEvent): void {
  if (e.key === "Escape" && !props.isSubmitting) emit("cancel");
}
</script>

<template>
  <div
    class="git-repo-init-prompt"
    role="dialog"
    aria-modal="false"
    :aria-label="tm('diffSidebar.repoInit.title')"
    tabindex="-1"
    @keydown="onKeyDown"
  >
    <v-icon size="32" class="git-repo-init-prompt-icon"
      >mdi-information-outline</v-icon
    >
    <h2 class="git-repo-init-prompt-title">
      {{ tm("diffSidebar.repoInit.title") }}
    </h2>
    <p class="git-repo-init-prompt-body">
      {{
        tm("diffSidebar.repoInit.body", {
          directory: props.directory,
        })
      }}
    </p>
    <p class="git-repo-init-prompt-hint">
      {{
        tm("diffSidebar.repoInit.hint", {
          defaultBranch: "main",
        })
      }}
    </p>

    <div
      v-if="props.lastError"
      data-testid="repo-init-error"
      class="git-repo-init-prompt-error"
    >
      <v-icon size="16" color="error">mdi-alert-circle-outline</v-icon>
      <span>
        {{
          props.lastError.stderr
            ? tm("diffSidebar.repoInit.errors.init_failed", {
                stderr: props.lastError.stderr,
              })
            : tm(errorKey(props.lastError.reason))
        }}
      </span>
    </div>

    <div class="git-repo-init-prompt-actions">
      <button
        type="button"
        data-testid="repo-init-cancel"
        class="git-repo-init-prompt-btn git-repo-init-prompt-btn--secondary"
        :disabled="props.isSubmitting"
        @click="emit('cancel')"
      >
        {{ tm("diffSidebar.repoInit.cancel") }}
      </button>
      <button
        type="button"
        data-testid="repo-init-confirm"
        class="git-repo-init-prompt-btn git-repo-init-prompt-btn--primary"
        :disabled="props.isSubmitting"
        @click="emit('confirm')"
      >
        <v-progress-circular
          v-if="props.isSubmitting"
          indeterminate
          :size="14"
          :width="2"
          class="git-repo-init-prompt-spinner"
        />
        {{
          props.isSubmitting
            ? tm("diffSidebar.repoInit.submitting")
            : tm("diffSidebar.repoInit.confirm")
        }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.git-repo-init-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 32px 24px;
  text-align: center;
}
.git-repo-init-prompt-icon {
  color: rgb(var(--v-theme-primary));
}
.git-repo-init-prompt-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.git-repo-init-prompt-body,
.git-repo-init-prompt-hint {
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
  color: rgba(var(--v-theme-on-surface), 0.8);
  max-width: 480px;
}
.git-repo-init-prompt-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(var(--v-theme-error), 0.08);
  border-radius: 4px;
  font-size: 12px;
  text-align: left;
  max-width: 480px;
  width: 100%;
  box-sizing: border-box;
}
.git-repo-init-prompt-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.git-repo-init-prompt-btn {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.git-repo-init-prompt-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.git-repo-init-prompt-btn--secondary {
  background: transparent;
  border-color: rgba(var(--v-theme-on-surface), 0.24);
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.git-repo-init-prompt-btn--primary {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
</style>
