<script setup lang="ts">
import { ref } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import type { CommandConflictGroup, PluginSummary } from './types'

import type { EffectTarget, PipelineStageId } from './pipeline/pipelineSnapshotTypes'
import PipelineSnapshotPanel from './pipeline/PipelineSnapshotPanel.vue'

type GlobalPanelTab = 'pipeline' | 'trace'

const props = withDefaults(
  defineProps<{
    plugins: PluginSummary[]
    conflicts: CommandConflictGroup[]
    loading?: boolean
    showReserved?: boolean
  }>(),
  {
    showReserved: true
  }
)

const emit = defineEmits<{
  (e: 'select-plugin', name: string): void
}>()

const { tm } = useModuleI18n('features/extension')
const $t = tm

const activeTab = ref<GlobalPanelTab>('pipeline')

const traceNavigationToken = ref(0)
const traceFocusTarget = ref<EffectTarget | null>(null)
const traceStageId = ref<PipelineStageId | null>(null)
const traceParticipantId = ref<string | null>(null)

const handleSelectPlugin = (name: string) => {
  if (!name) return
  emit('select-plugin', name)
}

const handleNavigateTrace = (payload: { participantId: string; stageId: PipelineStageId | null; target: EffectTarget }) => {
  traceParticipantId.value = payload.participantId || null
  traceFocusTarget.value = payload.target
  traceStageId.value = payload.stageId
  traceNavigationToken.value += 1
  activeTab.value = 'trace'
}

const handleNavigatePipeline = () => {
  activeTab.value = 'pipeline'
}
</script>

<template>
  <v-card class="h-100 d-flex flex-column global-panel" rounded="lg" variant="flat">
    <div class="global-panel__header">
      <v-tabs v-model="activeTab" color="primary" density="comfortable">
        <v-tab value="pipeline">
          <span class="d-inline-flex align-center">
            {{ $t('pipeline.tabs.pipeline') }}
            <v-tooltip location="bottom">
              <template #activator="{ props: tooltipProps }">
                <v-icon v-bind="tooltipProps" size="small" class="ml-1">mdi-information-outline</v-icon>
              </template>
              {{ $t('pipeline.tabs.pipelineTooltip') }}
            </v-tooltip>
          </span>
        </v-tab>

        <v-tab value="trace">
          <span class="d-inline-flex align-center">
            {{ $t('pipeline.tabs.trace') }}
            <v-tooltip location="bottom">
              <template #activator="{ props: tooltipProps }">
                <v-icon v-bind="tooltipProps" size="small" class="ml-1">mdi-information-outline</v-icon>
              </template>
              {{ $t('pipeline.tabs.traceTooltip') }}
            </v-tooltip>
          </span>
        </v-tab>
      </v-tabs>
      <v-divider />
    </div>

    <div class="global-panel__body">
      <PipelineSnapshotPanel
        class="h-100"
        :mode="activeTab"
        :show-reserved="props.showReserved"
        :trace-navigation-token="traceNavigationToken"
        :trace-focus-target="traceFocusTarget"
        :trace-stage-id="traceStageId"
        :trace-participant-id="traceParticipantId"
        @select-plugin="handleSelectPlugin"
        @navigate-trace="handleNavigateTrace"
        @navigate-pipeline="handleNavigatePipeline"
      />
    </div>
  </v-card>
</template>

<style scoped>
.global-panel {
  min-height: 0;
  overflow: hidden;
}

.global-panel__header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(var(--v-theme-surface), 0.92);
}

.global-panel__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.global-panel__scroll {
  min-height: 0;
  overflow-y: auto;
}

.global-panel__nested-panels {
  background: transparent;
}

.global-panel__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.global-panel__plugin-link {
  cursor: pointer;
  text-decoration: underline;
  color: rgb(var(--v-theme-primary));
  font-weight: 500;
}

.global-panel__plugin-link:hover {
  color: rgb(var(--v-theme-info));
}

.global-panel__plugin-link--danger {
  color: rgb(var(--v-theme-error));
}

.global-panel__plugin-link--danger:hover {
  color: rgb(var(--v-theme-warning));
}

.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-panel__desc {
  max-width: 720px;
}
</style>