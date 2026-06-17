<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.1 -->
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
        prepend-icon="mdi-source-pull"
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
