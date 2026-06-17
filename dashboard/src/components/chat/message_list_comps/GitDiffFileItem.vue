<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.4 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { SpcodeGitDiffFile, FileStatus } from '@/composables/parseSpcodeGitDiff'
import { useModuleI18n } from '@/i18n/composables'
import DiffPreview from '@/components/chat/message_list_comps/DiffPreview.vue'

const { tm } = useModuleI18n('features/chat')

const props = defineProps<{
  file: SpcodeGitDiffFile
  expanded: boolean
  isDark: boolean
}>()
const emit = defineEmits<{ (e: 'toggle'): void }>()

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
</script>

<template>
  <div class="git-diff-file-item" :class="{ expanded: expanded }">
    <button type="button" class="git-diff-file-row" @click="emit('toggle')">
      <v-icon :size="16" :color="iconInfo.color">{{ iconInfo.icon }}</v-icon>
      <span class="git-diff-file-path">{{ file.path }}</span>
      <span class="git-diff-file-stats">
        <span class="git-diff-add">+{{ file.additions }}</span>
        <span class="git-diff-del">−{{ file.deletions }}</span>
      </span>
      <v-icon
        :size="16"
        class="git-diff-file-chevron"
        :class="{ expanded: expanded }"
      >mdi-chevron-down</v-icon>
    </button>
    <div v-if="expanded" class="git-diff-file-body">
      <v-alert v-if="file.isBinary" type="info" density="compact" variant="tonal">
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
.git-diff-file-item { border-bottom: 1px solid rgba(0, 0, 0, 0.08); }
.git-diff-file-row {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 12px;
  background: transparent; border: none; cursor: pointer; text-align: left;
}
.git-diff-file-row:hover { background: rgba(0, 0, 0, 0.04); }
.git-diff-file-path {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: monospace; font-size: 13px;
}
.git-diff-file-stats { display: flex; gap: 6px; font-family: monospace; font-size: 12px; }
.git-diff-add { color: rgb(46, 160, 67); }
.git-diff-del { color: rgb(248, 81, 73); }
.git-diff-file-chevron { transition: transform 0.15s; }
.git-diff-file-chevron.expanded { transform: rotate(180deg); }
.git-diff-file-body { padding: 0 12px 12px; }
.git-diff-file-no-content {
  padding: 12px; text-align: center; color: rgba(0, 0, 0, 0.45); font-size: 12px;
}
</style>
