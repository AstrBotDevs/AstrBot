<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { usePluginConfigCache } from '@/composables/usePluginConfigCache'
import { useModuleI18n } from '@/i18n/composables'
import type { PluginPanelTab, PluginSummary } from './types'

import PluginInfoPanel from './PluginInfoPanel.vue'
import PluginConfigPanel from './PluginConfigPanel.vue'
import PluginOverviewPanel from './PluginOverviewPanel.vue'
import PluginChangelogPanel from './PluginChangelogPanel.vue'
import PluginWelcomePanel from './PluginWelcomePanel.vue'

const props = defineProps<{
  plugin: PluginSummary | null
  activeTab?: PluginPanelTab
}>()

const emit = defineEmits<{
  (e: 'update:activeTab', tab: PluginPanelTab): void
  (e: 'action-update', name: string): void
  (e: 'config-saved', pluginName: string): void
}>()

const cache = usePluginConfigCache()
const { tm } = useModuleI18n('features/extension')

const normalizeTab = (tab: PluginPanelTab | undefined): PluginPanelTab => {
  // 向前兼容：历史版本存在 behavior Tab，现在合并到 info
  if (tab === 'behavior') return 'info'
  return tab ?? 'info'
}

const localActiveTab = ref<PluginPanelTab>(normalizeTab(props.activeTab))

const hasPlugin = computed(() => Boolean(props.plugin))
const pluginName = computed(() => props.plugin?.name || '')
const repoUrl = computed(() => props.plugin?.repo || null)

const isTabActive = (tab: PluginPanelTab) => localActiveTab.value === tab

const setActiveTab = (tab: PluginPanelTab) => {
  const next = normalizeTab(tab)
  if (localActiveTab.value === next) return
  localActiveTab.value = next
  emit('update:activeTab', next)
}

const openRepoInNewTab = (url: string) => {
  if (!url) return
  window.open(url, '_blank')
}

watch(
  () => props.activeTab,
  (val) => {
    if (!val) return
    const next = normalizeTab(val)
    if (next !== localActiveTab.value) {
      localActiveTab.value = next
    }
  }
)

watch(
  () => props.plugin?.name,
  (name, prev) => {
    if (!name) return
    if (name !== prev) {
      // 切换插件时优先展示 Info
      setActiveTab('info')
      // 预加载配置（不阻塞 UI）
      cache.prefetch(name)
    }
  },
  { immediate: true }
)
</script>

<template>
  <v-card class="h-100 d-flex flex-column" rounded="lg" variant="flat">
    <PluginWelcomePanel v-if="!hasPlugin" />

    <template v-else>
      <v-tabs v-model="localActiveTab" color="primary" density="comfortable">
        <v-tab value="info">{{ tm('modManager.panelTabs.info') }}</v-tab>
        <v-tab value="config">{{ tm('modManager.panelTabs.config') }}</v-tab>
        <v-tab value="overview">{{ tm('modManager.panelTabs.overview') }}</v-tab>
        <v-tab value="changelog">{{ tm('modManager.panelTabs.changelog') }}</v-tab>
      </v-tabs>

      <v-divider />

      <v-window v-model="localActiveTab" class="flex-grow-1 plugin-panel__window" style="min-height: 0">
        <v-window-item value="info" class="h-100">
          <div class="plugin-panel__tab plugin-panel__tab--no-scroll pa-3">
            <PluginInfoPanel
              v-if="plugin"
              :plugin="plugin"
              @action-update="emit('action-update', plugin.name)"
              @open-repo="openRepoInNewTab"
            />
          </div>
        </v-window-item>

        <v-window-item value="config" class="h-100">
          <div class="plugin-panel__tab pa-3">
            <PluginConfigPanel
              :pluginName="pluginName"
              :active="isTabActive('config')"
              @saved="(name) => emit('config-saved', name)"
              @error="() => {}"
            />
          </div>
        </v-window-item>

        <v-window-item value="overview" class="h-100">
          <div class="plugin-panel__tab pa-3">
            <PluginOverviewPanel
              :pluginName="pluginName"
              :repoUrl="repoUrl"
              :active="isTabActive('overview')"
            />
          </div>
        </v-window-item>

        <v-window-item value="changelog" class="h-100">
          <div class="plugin-panel__tab pa-3">
            <PluginChangelogPanel :pluginName="pluginName" :active="isTabActive('changelog')" />
          </div>
        </v-window-item>
      </v-window>
    </template>
  </v-card>
</template>

<style scoped>
.plugin-panel__window {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.plugin-panel__window :deep(.v-window__container) {
  min-height: 0;
  height: 100%;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.plugin-panel__window :deep(.v-window-item) {
  min-height: 0;
  height: 100%;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.plugin-panel__tab {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}

.plugin-panel__tab--no-scroll {
  overflow: hidden;
}
</style>