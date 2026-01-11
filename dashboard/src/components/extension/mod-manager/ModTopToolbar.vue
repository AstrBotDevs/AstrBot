<template>
  <v-toolbar
    class="mod-top-toolbar"
    color="surface"
    density="compact"
    height="60"
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
        :label="props.showReserved ? tm('buttons.hideSystemPlugins') : tm('buttons.showSystemPlugins')"
        @update:model-value="emit('toggle-show-reserved')"
      />

      <v-btn
        size="small"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-plus"
        @click="emit('install')"
      >
        {{ tm('buttons.install') }}
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
          size="small"
          variant="tonal"
          color="warning"
          prepend-icon="mdi-download-multiple"
          :loading="isUpdatingAll"
          :disabled="isUpdatingAll || props.updatableCount <= 0"
          @click="emit('update-all')"
        >
          {{ tm('buttons.updateAll') }}
        </v-btn>
      </v-badge>

      <!-- Failed plugin load info (extension_data.message) -->
      <v-dialog v-if="hasFailedMessage" max-width="500px">
        <template #activator="{ props: activatorProps }">
          <v-btn
            v-bind="activatorProps"
            data-testid="failed-message-alert"
            aria-label="插件加载失败"
            icon
            size="small"
            color="error"
            variant="tonal"
            class="mod-top-toolbar__alert"
          >
            <v-icon size="20" color="error">mdi-alert-circle</v-icon>
            <v-tooltip activator="parent" location="top">{{ tm('dialogs.error.title') }}</v-tooltip>
          </v-btn>
        </template>

        <template #default="{ isActive }">
          <v-card class="rounded-lg">
            <v-card-title class="headline d-flex align-center">
              <v-icon color="error" class="mr-2">mdi-alert-circle</v-icon>
              {{ tm('dialogs.error.title') }}
            </v-card-title>
            <v-card-text>
              <p class="text-body-1">{{ failedMessageText }}</p>
              <p class="text-caption mt-2">{{ tm('dialogs.error.checkConsole') }}</p>
            </v-card-text>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn color="primary" @click="isActive.value = false">{{ tm('buttons.close') }}</v-btn>
            </v-card-actions>
          </v-card>
        </template>
      </v-dialog>

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
import { useModuleI18n } from '@/i18n/composables'
import StyledMenu from '@/components/shared/StyledMenu.vue'
import type { InstalledViewMode, PluginSummary } from './types'

const { tm } = useModuleI18n('features/extension')

const props = defineProps<{
  search: string
  showReserved: boolean
  updatableCount: number
  updatingAll?: boolean
  installedViewMode: InstalledViewMode
  selectedPlugin?: PluginSummary | null
  failedMessage?: string
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

const failedMessageText = computed(() => (props.failedMessage ?? '').trim())
const hasFailedMessage = computed(() => failedMessageText.value.length > 0)

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
  overflow: visible;
}

.mod-top-toolbar :deep(.v-toolbar__content) {
  overflow: visible;
}

.mod-top-toolbar__toggle {
  flex: 0 0 auto;
}

.mod-top-toolbar__toggle :deep(.v-label) {
  white-space: nowrap;
}

.mod-top-toolbar__alert {
  flex: 0 0 auto;
}
</style>