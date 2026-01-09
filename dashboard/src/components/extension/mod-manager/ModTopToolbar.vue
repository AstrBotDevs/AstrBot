<template>
  <v-toolbar
    class="mod-top-toolbar"
    color="surface"
    density="compact"
    height="52"
    elevation="1"
  >
    <v-spacer />

    <!-- Right: Reserved toggle + Actions -->
    <div class="mod-top-toolbar__right d-flex align-center ga-2">
      <v-switch
        class="mod-top-toolbar__toggle"
        :model-value="props.showReserved"
        density="compact"
        hide-details
        inset
        label="显示系统插件"
        @update:model-value="emit('toggle-show-reserved')"
      />

      <v-btn icon size="small" variant="text" @click="emit('install')">
        <v-icon size="20">mdi-plus</v-icon>
        <v-tooltip activator="parent" location="top">安装插件</v-tooltip>
      </v-btn>

      <v-badge
        :content="props.updatableCount"
        :model-value="props.updatableCount > 0"
        color="warning"
        location="top end"
        offset-x="2"
        offset-y="2"
      >
        <v-btn
          icon
          size="small"
          variant="text"
          :loading="isUpdatingAll"
          :disabled="isUpdatingAll || props.updatableCount <= 0"
          @click="emit('update-all')"
        >
          <v-icon size="20">mdi-download-multiple</v-icon>
          <v-tooltip activator="parent" location="top">
            批量更新
          </v-tooltip>
        </v-btn>
      </v-badge>

      <StyledMenu offset="10" location="bottom end">
        <template #activator="{ props: menuProps }">
          <v-btn v-bind="menuProps" icon size="small" variant="text" aria-label="more">
            <v-icon size="20">mdi-dots-vertical</v-icon>
            <v-tooltip activator="parent" location="top">更多</v-tooltip>
          </v-btn>
        </template>

        <v-list-item class="styled-menu-item" @click="toggleViewMode">
          <template #prepend>
            <v-icon size="18">{{ viewModeIcon }}</v-icon>
          </template>
          <v-list-item-title>{{ viewModeLabel }}</v-list-item-title>
        </v-list-item>

        <v-list-item
          v-if="props.selectedPlugin"
          class="styled-menu-item"
          @click="emit('open-legacy-handlers')"
        >
          <template #prepend>
            <v-icon size="18">mdi-information-outline</v-icon>
          </template>
          <v-list-item-title>查看旧版详情</v-list-item-title>
        </v-list-item>
      </StyledMenu>
    </div>
  </v-toolbar>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StyledMenu from '@/components/shared/StyledMenu.vue'
import type { InstalledViewMode, PluginSummary } from './types'

const props = defineProps<{
  search: string
  showReserved: boolean
  updatableCount: number
  updatingAll?: boolean
  installedViewMode: InstalledViewMode
  selectedPlugin?: PluginSummary | null
}>()

const emit = defineEmits<{
  (e: 'update:search', value: string): void
  (e: 'toggle-show-reserved'): void
  (e: 'install'): void
  (e: 'update-all'): void
  (e: 'set-view-mode', mode: InstalledViewMode): void
  (e: 'open-legacy-handlers'): void
}>()

const searchModel = computed<string>({
  get: () => props.search ?? '',
  set: (val) => emit('update:search', val ?? '')
})

const isUpdatingAll = computed(() => props.updatingAll ?? false)

const nextViewMode = computed<InstalledViewMode>(() =>
  props.installedViewMode === 'mod' ? 'legacy' : 'mod'
)

const viewModeLabel = computed(() =>
  props.installedViewMode === 'mod' ? '切换到旧版视图' : '切换到MOD管理器'
)

const viewModeIcon = computed(() =>
  props.installedViewMode === 'mod' ? 'mdi-backup-restore' : 'mdi-cube-outline'
)

const toggleViewMode = () => emit('set-view-mode', nextViewMode.value)
</script>

<style scoped>
.mod-top-toolbar {
  border-radius: 14px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.mod-top-toolbar__toggle {
  flex: 0 0 auto;
}

.mod-top-toolbar__toggle :deep(.v-label) {
  white-space: nowrap;
}
</style>