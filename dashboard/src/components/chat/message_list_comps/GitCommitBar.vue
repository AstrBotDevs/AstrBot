<!-- Author: elecvoid243
     Date: 2026-06-24
     Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §6.7
     Sticky bottom bar shown only when a project is loaded. Surfaces
     stagedFiles.size, the "Stage all" trigger (which opens the
     confirm dialog owned by the sidebar), and the "Commit" trigger
     (which opens the commit dialog). -->
<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/chat");

defineProps<{
  stagedCount: number;
  unstagedCount: number;
  isStagingAll: boolean;
  isCommitting: boolean;
}>();

const emit = defineEmits<{
  (e: "stage-all"): void;
  (e: "commit"): void;
}>();
</script>

<template>
  <div class="git-commit-bar" role="region" aria-label="Git commit controls">
    <span class="git-commit-bar-status">
      <v-icon size="14" class="git-commit-bar-status-icon">mdi-information-outline</v-icon>
      <span v-if="stagedCount > 0">
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.stagedCount",
            { count: stagedCount },
          )
        }}
      </span>
      <span v-else class="is-muted">
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.stagedCountZero") }}
      </span>
    </span>
    <div class="git-commit-bar-actions">
      <v-btn
        size="small"
        variant="tonal"
        color="secondary"
        :disabled="unstagedCount === 0 || isStagingAll || isCommitting"
        :loading="isStagingAll"
        :title="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.stageAllAria')"
        @click="emit('stage-all')"
      >
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.stageAll") }}
      </v-btn>
      <v-btn
        size="small"
        variant="flat"
        color="primary"
        :disabled="stagedCount === 0 || isCommitting"
        :title="stagedCount === 0 ? tm('spcodeProjectLoad.diffSidebar.gitWorkflow.commit.bar.commitDisabledHint') : ''"
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
