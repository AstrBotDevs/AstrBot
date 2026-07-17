<!-- Author: elecvoid243
     Date: 2026-06-24
     Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §6.7
     Sticky bottom bar shown only when a project is loaded. Surfaces
     stagedCount, the bulk action trigger (Stage all on unstaged/all
     scopes, Unstage all on the staged scope), and the "Commit" trigger
     (which opens the commit dialog).

     The bulk action swaps label / disabled / event based on
     `selectedScope` so the same button row carries both directions of
     the stage ↔ unstage cycle without taking more vertical space. -->
<script setup lang="ts">
import { computed } from "vue";
import type { GitDiffScope } from "@/composables/useSpcodeGitDiff";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/chat");

const props = defineProps<{
  stagedCount: number;
  unstagedCount: number;
  isStagingAll: boolean;
  isUnstagingAll: boolean;
  isCommitting: boolean;
  /** Drives the bulk action label/handler:
   *    "staged"   → "取消全部暂存" → emit('unstage-all')
   *    "unstaged" | "all" → "全部暂存" → emit('stage-all')
   */
  selectedScope: GitDiffScope;
}>();

const emit = defineEmits<{
  (e: "stage-all"): void;
  (e: "unstage-all"): void;
  (e: "commit"): void;
}>();

// The bulk action flips between stage-all and unstage-all based on
// the scope the user is looking at. Deriving everything (label /
// aria / disabled / loading / event) from a single `isUnstageMode`
// flag keeps the four outputs in lock-step — adding a new branch
// later (e.g. a third mode) only requires flipping this boolean.
const isUnstageMode = computed(() => props.selectedScope === "staged");

const bulkLabel = computed(() =>
  isUnstageMode.value
    ? tm("spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.unstageAll.button")
    : tm("spcodeProjectLoad.diffSidebar.gitWorkflow.stage.stageAll.button"),
);

const bulkAria = computed(() =>
  isUnstageMode.value
    ? tm(
        "spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.unstageAll.buttonAria",
      )
    : tm("spcodeProjectLoad.diffSidebar.gitWorkflow.stage.stageAll.buttonAria"),
);

const bulkDisabled = computed(() => {
  // Disable when there's nothing to act on, when a bulk write is
  // already in flight, or while a commit is pending (mutual
  // exclusion with the commit dialog).
  if (isUnstageMode.value) {
    return (
      props.stagedCount === 0 || props.isUnstagingAll || props.isCommitting
    );
  }
  return props.unstagedCount === 0 || props.isStagingAll || props.isCommitting;
});

const bulkLoading = computed(() =>
  isUnstageMode.value ? props.isUnstagingAll : props.isStagingAll,
);

// 2026-07-17: commit is gated to the "staged" scope. Committing from
// the unstaged/all scopes made it too easy to leave changes out of
// the index (user commits, silently missing files they forgot to
// stage). The button stays visible-but-disabled on other scopes so
// the workflow stays discoverable; the title hint explains how to
// re-enable it.
const isStagedScope = computed(() => props.selectedScope === "staged");

const commitDisabled = computed(
  () => !isStagedScope.value || props.stagedCount === 0 || props.isCommitting,
);

const commitHint = computed(() => {
  if (!isStagedScope.value) {
    return tm(
      "spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.commitScopeHint",
    );
  }
  if (props.stagedCount === 0) {
    return tm(
      "spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.commitDisabledHint",
    );
  }
  return "";
});

const bulkColor = computed(() =>
  // Unstage is reversible but still "moves work out of the index";
  // the warning tint visually flags it as an undo-ish action while
  // staying calmer than `error`. Stage stays `secondary` to match
  // its non-destructive role.
  isUnstageMode.value ? "warning" : "secondary",
);

function onBulkClick(): void {
  if (isUnstageMode.value) emit("unstage-all");
  else emit("stage-all");
}
</script>

<template>
  <div class="git-commit-bar" role="region" aria-label="Git commit controls">
    <span class="git-commit-bar-status">
      <v-icon size="14" class="git-commit-bar-status-icon"
        >mdi-information-outline</v-icon
      >
      <span v-if="stagedCount > 0">
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.stagedCount",
            { count: stagedCount },
          )
        }}
      </span>
      <span v-else class="is-muted">
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.stagedCountZero",
          )
        }}
      </span>
    </span>
    <div class="git-commit-bar-actions">
      <v-btn
        size="small"
        variant="tonal"
        :color="bulkColor"
        :disabled="bulkDisabled"
        :loading="bulkLoading"
        :title="bulkAria"
        @click="onBulkClick"
      >
        {{ bulkLabel }}
      </v-btn>
      <v-btn
        size="small"
        variant="flat"
        color="primary"
        :disabled="commitDisabled"
        :title="commitHint"
        append-icon="mdi-arrow-right"
        @click="emit('commit')"
      >
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.commit") }}
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.git-commit-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  flex-shrink: 0;
}
.git-commit-bar-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.8);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.git-commit-bar-status-icon {
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}
.is-muted {
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.git-commit-bar-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

@media (max-width: 760px) {
  /* Spec §10 风险 #10 + §11.1 移动端可见可用 */
  .git-commit-bar {
    padding: 8px 10px;
  }
  .git-commit-bar-status {
    font-size: 11.5px;
  }
}
</style>
