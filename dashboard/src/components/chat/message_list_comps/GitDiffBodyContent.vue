<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.3 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { GitDiffFetchState } from '@/composables/useSpcodeGitDiff'
import { useModuleI18n } from '@/i18n/composables'
import GitDiffFileItem from '@/components/chat/message_list_comps/GitDiffFileItem.vue'

const { tm } = useModuleI18n('features/chat')

const props = defineProps<{
  state: GitDiffFetchState
  expanded: Set<string>
  isDark: boolean
}>()
const emit = defineEmits<{
  (e: 'toggle', path: string): void
  (e: 'retry'): void
}>()

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
      @toggle="emit('toggle', f.path)"
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
.git-diff-center-text { color: rgba(0, 0, 0, 0.6); font-size: 14px; }
.git-diff-error-title { font-weight: 600; font-size: 15px; }
.git-diff-error-detail { color: rgba(0, 0, 0, 0.6); font-size: 13px; text-align: center; }
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
