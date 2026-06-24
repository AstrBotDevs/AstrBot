<!-- Author: elecvoid243, 2026-06-24 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.1 -->
<!-- Renamed chip label/icon from "Git Diff" / mdi-source-pull to "查看工作区" /
     mdi-folder-open to reflect the broader workspace scope (file browser +
     diff + staging + commit + history). -->
<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables'
const { tm } = useModuleI18n('features/chat')
const emit = defineEmits<{ (e: 'open-diff-sidebar'): void }>()
function open(): void { emit('open-diff-sidebar') }
</script>

<template>
  <v-tooltip location="bottom" :open-delay="200">
    <template #activator="{ props: tipProps }">
      <v-chip
        v-bind="tipProps"
        variant="outlined"
        size="small"
        density="comfortable"
        prepend-icon="mdi-folder-open"
        class="git-diff-chip"
        @click="open"
      >
        {{ tm('spcodeProjectLoad.diffSidebar.chip') }}
      </v-chip>
    </template>
    <span>{{ tm('spcodeProjectLoad.diffSidebar.chipTooltip') }}</span>
  </v-tooltip>
</template>

<style scoped>
.git-diff-chip { cursor: pointer; }
</style>
