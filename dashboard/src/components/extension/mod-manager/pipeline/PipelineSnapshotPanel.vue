<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'

import { useModuleI18n } from '@/i18n/composables'
import { usePipelineSnapshot } from '@/composables/usePipelineSnapshot'
import type {
  EffectTarget,
  PipelineSnapshot,
  PipelineStageId,
  SnapshotScopeMode,
  StageParticipant
} from './pipelineSnapshotTypes'

import {
  applyTraceFilter,
  buildAvailableTargets,
  buildTraceRows,
  groupTraceRowsByTarget
} from './traceGrouping'
import { inferTraceFocusTarget } from './traceFocus'

import PipelineFishboneView from './PipelineFishboneView.vue'
import TraceFishboneView from './TraceFishboneView.vue'
import StageDetailPanel from './StageDetailPanel.vue'
import ConflictListPanel from './ConflictListPanel.vue'
import TraceImpactDetailPanel from './TraceImpactDetailPanel.vue'
import PromptPreviewDialog from './PromptPreviewDialog.vue'
import ResizableSplitPane from '../ResizableSplitPane.vue'

type SnapshotPanelMode = 'pipeline' | 'trace'
type RightTab = 'detail' | 'conflicts'

const props = withDefaults(
  defineProps<{
    mode?: SnapshotPanelMode
    showReserved?: boolean

    /**
     * 仅用于 trace 模式：父组件触发导航时递增，用于强制触发聚焦逻辑（即使 target 相同）。
     */
    traceNavigationToken?: number
    /**
     * 仅用于 trace 模式：需要聚焦的 target（会映射到左侧鱼骨主干与右侧列表筛选/滚动）。
     */
    traceFocusTarget?: EffectTarget | null
    /**
     * 仅用于 trace 模式：需要同时高亮的 stage（用于 target 下的 leaf 高亮）。
     */
    traceStageId?: PipelineStageId | null
    /**
     * 仅用于 trace 模式：外部导航时携带的参与者 id（用于定位影响链路，不默认选中影响点）。
     */
    traceParticipantId?: string | null
  }>(),
  {
    mode: 'pipeline',
    showReserved: true,
    traceNavigationToken: 0,
    traceFocusTarget: null,
    traceStageId: null,
    traceParticipantId: null
  }
)

const { tm } = useModuleI18n('features/extension')

const display = useDisplay()
const isSmallScreen = computed(() => display.width.value <= 960)

const scopeMode = ref<SnapshotScopeMode>('global')
const sessionUmo = ref<string>('')

const rightTab = ref<RightTab>('detail')
const selectedStageId = ref<PipelineStageId | null>(null)
const selectedParticipantId = ref<string | null>(null)

const showAllStages = ref(false)

const SPLIT_RATIO_KEY = 'psp-split-ratio'

function parseStoredRatio(raw: string | null): number | null {
  if (!raw) return null
  const num = Number(raw)
  if (!Number.isFinite(num)) return null
  if (num <= 0 || num >= 1) return null
  return num
}

const splitRatio = ref(parseStoredRatio(localStorage.getItem(SPLIT_RATIO_KEY)) ?? 0.67)

watch(
  splitRatio,
  (val) => {
    if (!Number.isFinite(val)) return
    localStorage.setItem(SPLIT_RATIO_KEY, String(val))
  },
  { flush: 'post' }
)

const traceSelectedTarget = ref<'__all__' | EffectTarget>('__all__')
const traceSelectedImpactKey = ref<string | null>(null)

const promptDialog = ref(false)

const { snapshot, loading, error, refresh } = usePipelineSnapshot({
  scopeMode,
  umo: computed(() => (sessionUmo.value.trim() ? sessionUmo.value.trim() : null)),
  autoRefresh: true,
  render: false // 首屏只加载静态快照，不触发 dry-run
})

const emit = defineEmits<{
  (e: 'select-plugin', pluginName: string): void
  (e: 'navigate-trace', payload: { participantId: string; stageId: PipelineStageId | null; target: EffectTarget }): void
  (e: 'navigate-pipeline', payload: { stageId: PipelineStageId; participantId: string }): void
}>()

const displaySnapshot = computed<PipelineSnapshot | null>(() => {
  const s = snapshot.value
  if (!s) return null
  if (props.showReserved) return s

  const allowPlugin = (p: any) => !p?.reserved

  const plugins = (s.plugins ?? []).filter(allowPlugin)

  const stages = (s.stages ?? []).map((st) => ({
    ...st,
    participants: (st.participants ?? []).filter((p) => allowPlugin(p?.plugin))
  }))

  const conflicts = (s.conflicts ?? [])
    .map((c) => ({
      ...c,
      involved: (c.involved ?? []).filter((inv) => allowPlugin(inv?.plugin))
    }))
    .filter((c) => (c.involved?.length ?? 0) > 0)

  // Do not filter `llm_prompt_preview.injected_by` by `showReserved`.
  // Prompt preview is primarily a debugging tool; hiding reserved plugins here
  // can make the preview appear empty even when the backend provided data.
  const llm_prompt_preview = s.llm_prompt_preview ? { ...s.llm_prompt_preview } : undefined

  const byType: Record<string, number> = {}
  for (const c of conflicts) {
    const t = (c as any)?.type || 'unknown'
    byType[t] = (byType[t] ?? 0) + 1
  }

  const riskCount = stages.reduce(
    (acc, st) => acc + (st.participants ?? []).reduce((a2, p) => a2 + (p.risks?.length ?? 0), 0),
    0
  )
  const handlerCount = stages.reduce((acc, st) => acc + (st.participants?.length ?? 0), 0)

  return {
    ...s,
    plugins,
    stages,
    conflicts,
    llm_prompt_preview,
    stats: {
      ...s.stats,
      pluginCount: plugins.length,
      handlerCount,
      conflictCount: conflicts.length,
      riskCount,
      byConflictType: byType
    }
  }
})

const hasPromptPreview = computed(() => Boolean(displaySnapshot.value?.llm_prompt_preview))

const traceAllRows = computed(() => buildTraceRows(displaySnapshot.value))
const traceAvailableTargets = computed(() => buildAvailableTargets(traceAllRows.value))
const traceTargetItems = computed(() => [
  { title: 'All', value: '__all__' as const },
  ...traceAvailableTargets.value.map((t) => ({ title: String(t), value: t }))
])

const traceFilteredRows = computed(() =>
  applyTraceFilter(traceAllRows.value, {
    selectedTarget: traceSelectedTarget.value,
    onlyHighImpact: false
  })
)

const traceFilteredCount = computed(() => traceFilteredRows.value.length)

const traceRootGroupsAll = computed(() => groupTraceRowsByTarget(displaySnapshot.value, traceAllRows.value))

const traceActiveTarget = computed<EffectTarget | null>(() =>
  traceSelectedTarget.value === '__all__' ? null : (traceSelectedTarget.value as EffectTarget)
)

const traceSelectedRow = computed(() => {
  const key = traceSelectedImpactKey.value
  if (!key) return null
  return traceAllRows.value.find((r) => r.key === key) ?? null
})

const participantIdByHandlerKey = computed(() => {
  const map = new Map<string, string>()
  for (const s of displaySnapshot.value?.stages ?? []) {
    const stageId = s?.stage?.id as PipelineStageId | undefined
    if (!stageId) continue
    for (const p of s?.participants ?? []) {
      const full = p?.handler?.handler_full_name
      const id = p?.id
      if (!full || !id) continue
      map.set(`${stageId}:${full}`, id)
    }
  }
  return map
})

const findParticipantById = (snap: PipelineSnapshot | null, participantId: string): StageParticipant | null => {
  if (!snap || !participantId) return null
  for (const st of snap.stages ?? []) {
    for (const p of st?.participants ?? []) {
      if (p?.id === participantId) return p
    }
  }
  return null
}

const selectImpactKey = (key: string) => {
  traceSelectedImpactKey.value = key || null
}

const applyExternalTraceFocus = () => {
  if (props.mode !== 'trace') return

  const token = Number(props.traceNavigationToken || 0)
  const hasExternal =
    token > 0 || Boolean(props.traceFocusTarget) || Boolean(props.traceStageId) || Boolean(props.traceParticipantId)
  if (!hasExternal) return

  const target = (props.traceFocusTarget || 'result.chain') as EffectTarget
  const stageId = props.traceStageId ?? null

  selectedStageId.value = stageId
  traceSelectedTarget.value = target

  // 外部跳转时：只定位到 target/stage，不默认展开/选中任何具体影响点
  traceSelectedImpactKey.value = null
}

watch(
  () => [props.mode, props.traceNavigationToken, props.traceFocusTarget, props.traceStageId, props.traceParticipantId] as const,
  () => applyExternalTraceFocus(),
  { flush: 'post', immediate: true }
)

const handleRefresh = async (forceRefresh = false) => {
  const mode = scopeMode.value
  const umo = mode === 'session' ? (sessionUmo.value.trim() || null) : null
  await refresh({
    // 刷新按钮只刷新静态快照，不触发 dry-run
    scopeMode: mode,
    umo,
    forceRefresh,
    render: false
  })
}

const handleSelectStage = (stageId: PipelineStageId) => {
  selectedStageId.value = stageId
}

const handleSelectParticipant = (participantId: string) => {
  // 允许子组件用空串清除选择（例如 StageDetailPanel 的“显示全部”）
  if (!participantId) {
    selectedParticipantId.value = null
    if (props.mode === 'pipeline') {
      rightTab.value = 'detail'
    }
    return
  }

  // 兼容来自 ConflictListPanel 的合成 id：`${stageId}:${handler_full_name}`
  if (participantId.includes(':') && !participantId.startsWith('sha256:')) {
    const [stageIdRaw, ...rest] = participantId.split(':')
    const stageId = stageIdRaw as PipelineStageId
    const handlerFullName = rest.join(':')
    if (stageId) {
      selectedStageId.value = stageId
    }
    const mapped = participantIdByHandlerKey.value.get(`${stageId}:${handlerFullName}`)
    selectedParticipantId.value = mapped ?? null
    if (props.mode === 'pipeline') {
      rightTab.value = 'detail'
    }
    return
  }

  selectedParticipantId.value = participantId
  if (props.mode === 'pipeline') {
    rightTab.value = 'detail'
  }
}

const handleSelectPlugin = (name: string) => {
  if (!name) return
  emit('select-plugin', name)
}

const handleNavigatePipeline = (payload: { stageId: PipelineStageId; participantId: string }) => {
  emit('navigate-pipeline', payload)
}

const handleViewImpactChain = (payload: { participantId: string; stageId: PipelineStageId | null }) => {
  const participant = findParticipantById(displaySnapshot.value, payload.participantId)
  const target = inferTraceFocusTarget({ participant, stageId: payload.stageId })
  emit('navigate-trace', { participantId: payload.participantId, stageId: payload.stageId, target })
}

const openPromptPreview = async () => {
  if (!hasPromptPreview.value) return
  const mode = scopeMode.value
  const umo = mode === 'session' ? (sessionUmo.value.trim() || null) : null

  // 打开预览前先请求渲染数据
  const previewPrompt =
    String(displaySnapshot.value?.llm_prompt_preview?.prompt ?? '').trim() || '（预览）用户输入：<未提供>'
  await refresh({ scopeMode: mode, umo, forceRefresh: false, render: true, previewPrompt })

  // 然后再打开对话框
  promptDialog.value = true
}

const scopeItems = computed(() => [
  { title: tm('pipeline.scope.global'), value: 'global' },
  { title: tm('pipeline.scope.session'), value: 'session' }
])
</script>

<template>
  <v-card class="psp h-100 d-flex flex-column" rounded="lg" variant="flat">
    <div class="psp__toolbar px-4 py-3 d-flex align-center flex-wrap ga-2">
      <v-btn color="primary" variant="tonal" size="small" :loading="loading" @click="handleRefresh(true)">
        <v-icon start>mdi-refresh</v-icon>
        {{ tm('pipeline.toolbar.refresh') }}
      </v-btn>

      <v-select
        v-model="scopeMode"
        :items="scopeItems"
        :label="tm('pipeline.scope.label')"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width: 160px"
      />

      <v-text-field
        v-if="scopeMode === 'session'"
        v-model="sessionUmo"
        :label="tm('pipeline.scope.sessionUmo')"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width: 320px"
        @keydown.enter="handleRefresh(true)"
      />

      <v-spacer />

      <v-switch v-model="showAllStages" density="compact" hide-details inset label="显示全部阶段" />

      <v-tooltip location="bottom">
        <template #activator="{ props: tooltipProps }">
          <v-select
            v-bind="tooltipProps"
            v-model="traceSelectedTarget"
            :items="traceTargetItems"
            :label="tm('pipeline.filters.targetObject')"
            :placeholder="tm('pipeline.filters.targetObjectPlaceholder')"
            density="compact"
            variant="outlined"
            hide-details
            :disabled="props.mode !== 'trace'"
            style="max-width: 320px"
          />
        </template>
        {{ tm('pipeline.filters.targetObjectTooltip') }}
      </v-tooltip>

      <v-chip size="small" color="secondary" variant="tonal" class="font-weight-medium">{{ traceFilteredCount }} 条</v-chip>

      <v-btn color="secondary" variant="tonal" size="small" :disabled="!hasPromptPreview" @click="openPromptPreview">
        <v-icon start>mdi-text-box-search-outline</v-icon>
        {{ tm('pipeline.toolbar.promptPreview') }}
      </v-btn>
    </div>

    <v-divider />

    <v-progress-linear v-if="loading" indeterminate color="primary" />

    <div class="psp__content d-flex flex-grow-1" style="min-height: 0">
      <template v-if="isSmallScreen">
        <div class="psp__left">
          <TraceFishboneView
            v-if="props.mode === 'trace'"
            class="psp__fishbone"
            :groups="traceRootGroupsAll"
            :active-stage-id="selectedStageId"
            :active-target="traceActiveTarget"
            :active-impact-key="traceSelectedImpactKey"
            @select-stage="handleSelectStage"
            @select-target="(t) => (traceSelectedTarget = t)"
            @select-impact="selectImpactKey"
          />
          <PipelineFishboneView
            v-else
            class="psp__fishbone"
            :snapshot="displaySnapshot"
            :selected-stage-id="selectedStageId"
            :selected-participant-id="selectedParticipantId"
            :show-all-stages="showAllStages"
            @select-stage="handleSelectStage"
            @select-participant="handleSelectParticipant"
          />
        </div>

        <div class="psp__right">
          <div v-if="props.mode === 'pipeline'" class="psp__right-tabs">
            <v-btn-toggle v-model="rightTab" mandatory density="compact" class="psp__right-toggle w-100">
              <v-btn value="detail" variant="text" class="psp__right-toggle-btn flex-1">{{ tm('pipeline.rightTabs.detail') }}</v-btn>
              <v-btn value="conflicts" variant="text" class="psp__right-toggle-btn flex-1">{{ tm('pipeline.rightTabs.conflicts') }}</v-btn>
            </v-btn-toggle>

            <v-divider />
          </div>

          <div class="psp__right-body">
            <v-window
              v-if="props.mode === 'pipeline'"
              v-model="rightTab"
              class="psp__window flex-grow-1"
              style="min-height: 0"
            >
              <v-window-item value="detail" class="h-100">
                <StageDetailPanel
                  :snapshot="displaySnapshot"
                  :stage-id="selectedStageId"
                  :selected-participant-id="selectedParticipantId"
                  @select-participant="handleSelectParticipant"
                  @select-plugin="handleSelectPlugin"
                  @view-impact-chain="handleViewImpactChain"
                />
              </v-window-item>

              <v-window-item value="conflicts" class="h-100">
                <ConflictListPanel
                  :snapshot="displaySnapshot"
                  @select-stage="handleSelectStage"
                  @select-participant="handleSelectParticipant"
                  @select-plugin="handleSelectPlugin"
                />
              </v-window-item>
            </v-window>

            <div v-else class="h-100 d-flex flex-column" style="min-height: 0">
              <TraceImpactDetailPanel
                class="flex-grow-1"
                :row="traceSelectedRow"
                @select-plugin="handleSelectPlugin"
                @navigate-pipeline="handleNavigatePipeline"
              />
            </div>

            <div v-if="error" class="psp__error px-4 py-3">
              <v-alert type="error" variant="tonal" density="comfortable">{{ error }}</v-alert>
            </div>
          </div>
        </div>
      </template>

      <ResizableSplitPane v-else v-model="splitRatio" direction="horizontal" class="psp__split">
        <template #first>
          <div class="psp__left">
            <TraceFishboneView
              v-if="props.mode === 'trace'"
              class="psp__fishbone"
              :groups="traceRootGroupsAll"
              :active-stage-id="selectedStageId"
              :active-target="traceActiveTarget"
              :active-impact-key="traceSelectedImpactKey"
              @select-stage="handleSelectStage"
              @select-target="(t) => (traceSelectedTarget = t)"
              @select-impact="selectImpactKey"
            />
            <PipelineFishboneView
              v-else
              class="psp__fishbone"
              :snapshot="displaySnapshot"
              :selected-stage-id="selectedStageId"
              :selected-participant-id="selectedParticipantId"
              :show-all-stages="showAllStages"
              @select-stage="handleSelectStage"
              @select-participant="handleSelectParticipant"
            />
          </div>
        </template>

        <template #second>
          <div class="psp__right">
            <div v-if="props.mode === 'pipeline'" class="psp__right-tabs">
              <v-btn-toggle v-model="rightTab" mandatory density="compact" class="psp__right-toggle w-100">
                <v-btn value="detail" variant="text" class="psp__right-toggle-btn flex-1">{{ tm('pipeline.rightTabs.detail') }}</v-btn>
                <v-btn value="conflicts" variant="text" class="psp__right-toggle-btn flex-1">{{ tm('pipeline.rightTabs.conflicts') }}</v-btn>
              </v-btn-toggle>

              <v-divider />
            </div>

            <div class="psp__right-body">
              <v-window
                v-if="props.mode === 'pipeline'"
                v-model="rightTab"
                class="psp__window flex-grow-1"
                style="min-height: 0"
              >
                <v-window-item value="detail" class="h-100">
                  <StageDetailPanel
                    :snapshot="displaySnapshot"
                    :stage-id="selectedStageId"
                    :selected-participant-id="selectedParticipantId"
                    @select-participant="handleSelectParticipant"
                    @select-plugin="handleSelectPlugin"
                    @view-impact-chain="handleViewImpactChain"
                  />
                </v-window-item>

                <v-window-item value="conflicts" class="h-100">
                  <ConflictListPanel
                    :snapshot="displaySnapshot"
                    @select-stage="handleSelectStage"
                    @select-participant="handleSelectParticipant"
                    @select-plugin="handleSelectPlugin"
                  />
                </v-window-item>
              </v-window>

              <div v-else class="h-100 d-flex flex-column" style="min-height: 0">
                <TraceImpactDetailPanel
                  class="flex-grow-1"
                  :row="traceSelectedRow"
                  @select-plugin="handleSelectPlugin"
                  @navigate-pipeline="handleNavigatePipeline"
                />
              </div>

              <div v-if="error" class="psp__error px-4 py-3">
                <v-alert type="error" variant="tonal" density="comfortable">{{ error }}</v-alert>
              </div>
            </div>
          </div>
        </template>
      </ResizableSplitPane>
    </div>

    <PromptPreviewDialog v-model:show="promptDialog" :preview="displaySnapshot?.llm_prompt_preview ?? null" />
  </v-card>
</template>

<style scoped>
.psp {
  min-height: 0;
}

.psp__toolbar {
  background: rgba(var(--v-theme-surface), 0.6);
}

.psp__content {
  min-height: 0;
  overflow: hidden;
}

.psp__split {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

.psp__left {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  padding: 10px;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  display: flex;
  flex-direction: column;
}

.psp__fishbone {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

.psp__right {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.psp__right-tabs {
  position: sticky;
  top: 0;
  z-index: 3;
  background: rgba(var(--v-theme-surface), 0.92);
}

.psp__right-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 右侧切换项在窄宽下也始终可见（均分宽度，不依赖 slide-group 测量/溢出逻辑） */
.psp__right-toggle {
  display: flex;
}

.psp__right-toggle-btn {
  min-width: 0;
  padding-inline: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.psp__window {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.psp__window :deep(.v-window__container) {
  min-height: 0;
  height: 100% !important;
  flex: 1 1 auto;
}

.psp__window :deep(.v-window__container > .v-window-item) {
  min-height: 0;
  height: 100% !important;
}

.psp__window :deep(.v-window__container > .v-window-item.v-window-item--active) {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.psp__window :deep(.v-window__container > .v-window-item.v-window-item--active > *) {
  min-height: 0;
}

.psp__error {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.psp__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
}

@media (max-width: 960px) {
  .psp__content {
    flex-direction: column;
  }

  .psp__left {
    border-right: 0;
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  }

  .psp__right {
    width: 100%;
    max-width: 100%;
    min-width: 0;
  }
}
</style>
