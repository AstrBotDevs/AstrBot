<!-- Author: elecvoid243, 2026-06-22
     Spec: docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md §4, §6.1-§6.2
     Refactored: outer row <button> -> <div role="button" tabindex=0> to allow
     nesting a real <button> for the restore action (HTML5 forbids
     button-in-button nesting; see spec §2 decision #4). -->
<script setup lang="ts">
import { computed } from 'vue'
import type { SpcodeGitDiffFile, FileStatus } from '@/composables/parseSpcodeGitDiff'
import { useModuleI18n } from '@/i18n/composables'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import DiffPreview from '@/components/chat/message_list_comps/DiffPreview.vue'

const { tm } = useModuleI18n('features/chat')

const props = defineProps<{
  file: SpcodeGitDiffFile
  expanded: boolean
  isDark: boolean
  /** When provided, renders the restore button and emits 'restore' on click. */
  onRestore?: (path: string) => void
  /** True while a restore request is in flight for THIS row. */
  isRestoring?: boolean
  // Spec §6.2.4 (P1-1): child is scope-agnostic. Parent pre-computes
  // showStage / showUnstage from selectedScope + project status and
  // passes booleans down. Default false keeps the file item
  // backward-compatible with callers that don't yet supply these.
  showStage?: boolean
  showUnstage?: boolean
  onStage?: (path: string) => void
  onUnstage?: (path: string) => void
  isStaging?: boolean
  isUnstaging?: boolean
}>()
const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'restore', path: string): void
  (e: 'stage', path: string): void
  (e: 'unstage', path: string): void
}>()

const ICON_MAP: Record<FileStatus, { icon: string; color: string }> = {
  M: { icon: 'mdi-pencil', color: 'primary' },
  A: { icon: 'mdi-plus-circle', color: 'success' },
  D: { icon: 'mdi-minus-circle', color: 'error' },
  R: { icon: 'mdi-rename-box', color: 'warning' },
  C: { icon: 'mdi-content-copy', color: 'info' },
  T: { icon: 'mdi-swap-horizontal', color: 'info' },
  unknown: { icon: 'mdi-file-document-edit-outline', color: 'grey' },
}
const iconInfo = computed(() => ICON_MAP[props.file.status])

const spcodeStatus = useSpcodeProjectStatus()
/** Spec §6.2: button visible only when project is loaded + umo present. */
const showRestoreButton = computed(() => {
  return Boolean(
    props.onRestore &&
      spcodeStatus.status.value.loaded &&
      spcodeStatus.status.value.umo,
  )
})

function onRowKeydown(e: KeyboardEvent): void {
  // Spec §6.5: Enter / Space toggles the row.
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    emit('toggle')
  }
}

function onRestoreClick(e: MouseEvent): void {
  // Spec §6.1: @click.stop prevents the click from bubbling to the row's
  // toggle handler.
  e.stopPropagation()
  if (props.isRestoring) return
  emit('restore', props.file.path)
}

function onStageClick(e: MouseEvent): void {
  e.stopPropagation()
  if (props.isStaging) return
  emit('stage', props.file.path)
}

function onUnstageClick(e: MouseEvent): void {
  e.stopPropagation()
  if (props.isUnstaging) return
  emit('unstage', props.file.path)
}
</script>

<template>
  <div class="git-diff-file-item" :class="{ expanded: expanded }">
    <div
      class="git-diff-file-row"
      role="button"
      tabindex="0"
      :aria-expanded="expanded"
      @click="emit('toggle')"
      @keydown="onRowKeydown"
    >
      <v-icon :size="16" :color="iconInfo.color">{{ iconInfo.icon }}</v-icon>
      <span class="git-diff-file-path">{{ file.path }}</span>
      <span class="git-diff-file-stats">
        <span class="git-diff-add">+{{ file.additions }}</span>
        <span class="git-diff-del">−{{ file.deletions }}</span>
      </span>
      <!-- Spec §6.2: 行内暂存 / 取消暂存按钮。
           子组件不感知 scope(由父级 GitDiffBodyContent 派生 showStage / showUnstage),
           在 scope='all' 时两个 prop 均为 false,按钮不渲染(决策 #6)。
           hover 行时才显全 opacity,与 restore 按钮一致(风险 #6 缓解)。 -->
      <button
        v-if="showUnstage"
        type="button"
        class="git-diff-file-stage is-unstage"
        :class="{ 'is-loading': isUnstaging }"
        :disabled="isUnstaging"
        :aria-label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.buttonAria', { path: file.path })"
        :aria-busy="isUnstaging ? 'true' : 'false'"
        :title="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.buttonAria', { path: file.path })"
        @click="onUnstageClick"
      >
        <v-progress-circular
          v-if="isUnstaging"
          indeterminate
          :size="14"
          :width="2"
        />
        <v-icon v-else :size="16">mdi-arrow-down-bold-circle-outline</v-icon>
      </button>
      <button
        v-if="showStage"
        type="button"
        class="git-diff-file-stage is-stage"
        :class="{ 'is-loading': isStaging }"
        :disabled="isStaging"
        :aria-label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.stage.buttonAria', { path: file.path })"
        :aria-busy="isStaging ? 'true' : 'false'"
        :title="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.stage.buttonAria', { path: file.path })"
        @click="onStageClick"
      >
        <v-progress-circular
          v-if="isStaging"
          indeterminate
          :size="14"
          :width="2"
        />
        <v-icon v-else :size="16">mdi-arrow-up-bold-circle-outline</v-icon>
      </button>
      <button
        v-if="showRestoreButton"
        type="button"
        class="git-diff-file-restore"
        :class="{ 'is-loading': isRestoring }"
        :disabled="isRestoring"
        :aria-label="tm('spcodeProjectLoad.diffSidebar.restore.buttonAria', { path: file.path })"
        :aria-busy="isRestoring ? 'true' : 'false'"
        :title="tm('spcodeProjectLoad.diffSidebar.restore.buttonAria', { path: file.path })"
        @click="onRestoreClick"
      >
        <v-progress-circular
          v-if="isRestoring"
          indeterminate
          :size="14"
          :width="2"
        />
        <v-icon v-else :size="16">mdi-restore</v-icon>
      </button>
      <v-icon
        :size="16"
        class="git-diff-file-chevron"
        :class="{ expanded: expanded }"
      >mdi-chevron-down</v-icon>
    </div>
    <div v-if="expanded" class="git-diff-file-body">
      <v-alert
        v-if="file.isBinary"
        type="info"
        density="compact"
        variant="tonal"
        class="git-diff-binary-alert"
      >
        {{ tm('spcodeProjectLoad.diffSidebar.binaryFile') }}
      </v-alert>
      <DiffPreview
        v-else-if="file.slice"
        :content="file.slice"
        :file-path="file.path"
        :collapsible="false"
        :is-dark="isDark"
      />
      <div v-else class="git-diff-file-no-content">
        {{ tm('spcodeProjectLoad.diffSidebar.noContent') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.git-diff-file-item {
  /* Dark mode flips to a translucent white so the divider remains
     visible against the dark surface. Tied to the `isDark` prop that
     Chat.vue already passes down. */
  border-bottom: 1px solid v-bind('isDark ? "rgba(255, 255, 255, 0.18)" : "rgba(0, 0, 0, 0.08)"');
}
.git-diff-file-row {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 12px;
  background: transparent; border: none; cursor: pointer; text-align: left;
}
.git-diff-file-row:hover { background: rgba(0, 0, 0, 0.04); }
.git-diff-file-row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.git-diff-file-path {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: monospace; font-size: 13px;
}
.git-diff-file-stats { display: flex; gap: 6px; font-family: monospace; font-size: 12px; }
.git-diff-add { color: rgb(46, 160, 67); }
.git-diff-del { color: rgb(248, 81, 73); }
.git-diff-file-restore {
  /* Spec §6.1: muted by default, full opacity on row hover. Real <button>
     so it can be focused, disabled, and announced by screen readers. */
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  opacity: 0.5;
  transition: opacity 0.12s ease, background 0.12s ease, border-color 0.12s ease;
  flex-shrink: 0;
}
.git-diff-file-row:hover .git-diff-file-restore { opacity: 1; }
.git-diff-file-restore:hover { background: rgba(var(--v-theme-primary), 0.1); }
.git-diff-file-restore:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  opacity: 1;
}
.git-diff-file-restore:disabled { cursor: not-allowed; opacity: 0.3; }
.git-diff-file-restore.is-loading { opacity: 1; }

/* Spec §6.2: 行内 stage / unstage 按钮;与 restore 共享 opacity 0.5/1 模式。 */
.git-diff-file-stage {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  opacity: 0.5;
  transition: opacity 0.12s ease, background 0.12s ease, border-color 0.12s ease;
  flex-shrink: 0;
}
.git-diff-file-row:hover .git-diff-file-stage { opacity: 1; }
.git-diff-file-stage:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  opacity: 1;
}
.git-diff-file-stage:disabled { cursor: not-allowed; opacity: 0.3; }
.git-diff-file-stage.is-loading { opacity: 1; }
.git-diff-file-stage.is-stage {
  color: rgb(var(--v-theme-secondary));
}
.git-diff-file-stage.is-stage:hover { background: rgba(var(--v-theme-secondary), 0.1); }
.git-diff-file-stage.is-unstage {
  color: rgb(255, 152, 0);
}
.git-diff-file-stage.is-unstage:hover { background: rgba(255, 152, 0, 0.1); }

@media (max-width: 760px) {
  /* Spec §10 风险 #10: 移动端按钮缩窄 */
  .git-diff-file-stage,
  .git-diff-file-restore {
    width: 22px; height: 22px;
  }
}
.git-diff-file-chevron { transition: transform 0.15s; }
.git-diff-file-chevron.expanded { transform: rotate(180deg); }
.git-diff-file-body { padding: 0 12px 12px; }
.git-diff-file-no-content {
  /* Themed muted text — stays readable in both light and dark modes. */
  padding: 12px; text-align: center; color: rgba(var(--v-theme-on-surface), 0.45); font-size: 12px;
}
.git-diff-binary-alert { font-size: 13px; }
</style>