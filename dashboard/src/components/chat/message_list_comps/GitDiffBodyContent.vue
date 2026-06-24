<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.3
     Updated 2026-06-22 — thread 'restore' event for file-restore button -->
<script setup lang="ts">
import { computed, type Ref } from 'vue'
import type { GitDiffFetchState, GitDiffScope } from '@/composables/useSpcodeGitDiff'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import { useModuleI18n } from '@/i18n/composables'
import GitDiffFileItem from '@/components/chat/message_list_comps/GitDiffFileItem.vue'

const { tm } = useModuleI18n('features/chat')

const props = defineProps<{
  state: GitDiffFetchState
  expanded: Set<string>
  isDark: boolean
  onRestore?: (path: string) => void
  // Spec §6.2.3 + §6.2.4: parent (GitDiffSidebar) supplies the
  // scope + reactive Set<string> from useSpcodeGitStage / Unstage.
  // We pre-compute showStage / showUnstage booleans so the file item
  // stays scope-agnostic.
  selectedScope?: GitDiffScope
  onStage?: (path: string) => void
  onUnstage?: (path: string) => void
  isStaging?: Ref<Set<string>>
  isUnstaging?: Ref<Set<string>>
}>()
const emit = defineEmits<{
  (e: 'toggle', path: string): void
  (e: 'retry'): void
  (e: 'restore', path: string): void
  (e: 'stage', path: string): void
  (e: 'unstage', path: string): void
}>()

const spcodeStatus = useSpcodeProjectStatus()
// Spec §6.2.3: scope 派生按钮显隐(项目必须已加载 + scope=unstaged 显示 ↑)
const showStageButton = computed(() => {
  if (!props.onStage) return false
  if (!spcodeStatus.status.value.loaded) return false
  if (!spcodeStatus.status.value.umo) return false
  return props.selectedScope === 'unstaged'
})
const showUnstageButton = computed(() => {
  if (!props.onUnstage) return false
  if (!spcodeStatus.status.value.loaded) return false
  if (!spcodeStatus.status.value.umo) return false
  return props.selectedScope === 'staged'
})

// Spec §3.2 (P1-4): 行级 in-flight 状态从父级 Set 派生。Set 本身在
// Vue 3 里非响应式,所以 useSpcodeGitStage / useSpcodeGitUnstage 在 add
// / delete 时**重新赋值** `isStaging.value = new Set(...)`,而不是 in-
// place `.add()`。这里读 `props.isStaging?.value` 就能让模板的函数
// 调用注册依赖,行级 spinner 会在 in-flight 窗口出现。
function isStagingForPath(path: string): boolean {
  return props.isStaging?.value?.has(path) ?? false
}
function isUnstagingForPath(path: string): boolean {
  return props.isUnstaging?.value?.has(path) ?? false
}

const REASON_I18N_KEYS: Record<string, string> = {
  feature_disabled: 'spcodeProjectLoad.diffSidebar.error.reason.feature_disabled',
  no_project_loaded: 'spcodeProjectLoad.diffSidebar.error.reason.no_project_loaded',
  directory_missing: 'spcodeProjectLoad.diffSidebar.error.reason.directory_missing',
  not_a_git_repo: 'spcodeProjectLoad.diffSidebar.error.reason.not_a_git_repo',
  git_unavailable: 'spcodeProjectLoad.diffSidebar.error.reason.git_unavailable',
  git_error: 'spcodeProjectLoad.diffSidebar.error.reason.git_error',
}

function localizedReason(reason: string): string {
  const key = REASON_I18N_KEYS[reason]
  if (key) return tm(key)
  if (reason === 'network') return tm('spcodeProjectLoad.diffSidebar.error.networkTitle')
  return tm('spcodeProjectLoad.diffSidebar.error.reason.generic', { reason })
}

const errorInfo = computed(() => {
  if (props.state.kind !== 'error') return null
  return { reason: props.state.reason, hasPrevious: !!props.state.previousSnapshot }
})

const files = computed(() => {
  if (props.state.kind === 'ok') return props.state.snapshot.files
  if (props.state.kind === 'error' && props.state.previousSnapshot) {
    return props.state.previousSnapshot.files
  }
  return []
})
</script>

<template>
  <!-- Branch 1: loading -->
  <div v-if="state.kind === 'loading'" class="git-diff-center">
    <v-progress-circular indeterminate :size="32" />
    <span class="git-diff-center-text">{{ tm('spcodeProjectLoad.diffSidebar.loading') }}</span>
  </div>

  <!-- Branch 2: error with no previous -->
  <div
    v-else-if="state.kind === 'error' && !state.previousSnapshot && errorInfo"
    class="git-diff-center"
  >
    <v-icon size="36" color="error">mdi-alert-circle-outline</v-icon>
    <div class="git-diff-error-title">{{ tm('spcodeProjectLoad.diffSidebar.error.loadFailedTitle') }}</div>
    <div class="git-diff-error-detail">{{ localizedReason(errorInfo.reason) }}</div>
    <v-btn size="small" color="primary" @click="emit('retry')">
      {{ tm('spcodeProjectLoad.diffSidebar.error.retry') }}
    </v-btn>
  </div>

  <!-- Branch 3 & 4: success (or success with stale error) -->
  <template v-else-if="state.kind === 'ok' || (state.kind === 'error' && state.previousSnapshot)">
    <div v-if="files.length === 0" class="git-diff-center">
      <v-icon size="36" color="grey">mdi-check-circle-outline</v-icon>
      <span class="git-diff-center-text">{{ tm('spcodeProjectLoad.diffSidebar.empty') }}</span>
    </div>
    <GitDiffFileItem
      v-for="f in files"
      :key="f.path + ':' + f.status"
      :file="f"
      :expanded="expanded.has(f.path)"
      :is-dark="isDark"
      :on-restore="onRestore"
      :show-stage="showStageButton"
      :show-unstage="showUnstageButton"
      :on-stage="onStage"
      :on-unstage="onUnstage"
      :is-staging="isStagingForPath(f.path)"
      :is-unstaging="isUnstagingForPath(f.path)"
      @toggle="emit('toggle', f.path)"
      @restore="emit('restore', $event)"
      @stage="emit('stage', $event)"
      @unstage="emit('unstage', $event)"
    />
    <div v-if="state.kind === 'error' && errorInfo" class="git-diff-banner-error">
      <span>{{ localizedReason(errorInfo.reason) }}</span>
      <button class="git-diff-banner-retry" @click="emit('retry')">
        {{ tm('spcodeProjectLoad.diffSidebar.error.retry') }}
      </button>
    </div>
  </template>

  <!-- Branch 5: idle (initial state, no fetch yet) -->
  <div v-else class="git-diff-center">
    <span class="git-diff-center-text">{{ tm('spcodeProjectLoad.diffSidebar.loading') }}</span>
  </div>
</template>

<style scoped>
.git-diff-center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 12px; padding: 32px 16px; min-height: 200px;
}
/* Use themed muted text so empty/loading/error states stay readable
   in both light and dark modes. */
.git-diff-center-text { color: rgba(var(--v-theme-on-surface), 0.6); font-size: 14px; }
.git-diff-error-title { font-weight: 600; font-size: 15px; }
.git-diff-error-detail { color: rgba(var(--v-theme-on-surface), 0.6); font-size: 13px; text-align: center; }
.git-diff-banner-error {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 8px 12px; margin: 8px 12px;
  background: rgba(248, 81, 73, 0.1); border-radius: 4px;
  font-size: 12px; color: rgb(248, 81, 73);
}
.git-diff-banner-retry {
  background: transparent; border: 1px solid currentColor;
  border-radius: 4px; padding: 2px 8px; cursor: pointer; color: inherit;
}
</style>
