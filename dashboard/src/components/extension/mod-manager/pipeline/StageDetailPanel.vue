<script setup lang="ts">
import { computed, nextTick, watch } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import type { ConflictItem, PipelineSnapshot, PipelineStageId, StageParticipant } from './pipelineSnapshotTypes'

const { tm } = useModuleI18n('features/extension')

const props = defineProps<{
  snapshot: PipelineSnapshot | null
  stageId: PipelineStageId | null
  selectedParticipantId?: string | null
}>()

const emit = defineEmits<{
  (e: 'select-participant', participantId: string): void
  (e: 'select-plugin', pluginName: string): void
  (e: 'view-impact-chain', payload: { participantId: string; stageId: PipelineStageId | null }): void
}>()

type HandlerKey = string

const participantElById = new Map<string, HTMLElement>()

const resolveRefToElement = (refValue: Element | ComponentPublicInstance | null): HTMLElement | null => {
  if (!refValue) return null
  if (refValue instanceof HTMLElement) return refValue
  const maybeEl = (refValue as any).$el
  return maybeEl instanceof HTMLElement ? maybeEl : null
}

const setParticipantEl = (id: string) => (refValue: Element | ComponentPublicInstance | null) => {
  if (!id) return
  const el = resolveRefToElement(refValue)
  if (el) participantElById.set(id, el)
  else participantElById.delete(id)
}

const stageSnapshot = computed(() => {
  if (!props.snapshot || !props.stageId) return null
  return (props.snapshot.stages ?? []).find((s) => s?.stage?.id === props.stageId) ?? null
})

const participants = computed<StageParticipant[]>(() => {
  return (stageSnapshot.value?.participants ?? []).filter(Boolean)
})

const participantsSorted = computed(() => {
  const list = [...participants.value]
  list.sort((a, b) => {
    const pa = a?.meta?.priority ?? 0
    const pb = b?.meta?.priority ?? 0
    if (pa !== pb) return pb - pa
    const ha = a?.handler?.handler_full_name ?? ''
    const hb = b?.handler?.handler_full_name ?? ''
    return ha.localeCompare(hb)
  })
  return list
})

const focusedParticipant = computed(() => {
  const id = props.selectedParticipantId
  if (!id) return null
  return participantsSorted.value.find((p) => p?.id === id) ?? null
})

const focusedPluginName = computed(() => {
  const p = focusedParticipant.value
  return p?.plugin?.name || null
})

const focusedPluginDisplay = computed(() => {
  const p = focusedParticipant.value
  if (!p) return ''
  return p.plugin?.display_name || p.plugin?.name || '—'
})

const visibleParticipantsSorted = computed(() => {
  const pluginName = focusedPluginName.value
  if (!pluginName) return participantsSorted.value
  return participantsSorted.value.filter((p) => p?.plugin?.name === pluginName)
})

const conflictsForStage = computed<ConflictItem[]>(() => {
  if (!props.snapshot || !props.stageId) return []
  return (props.snapshot.conflicts ?? []).filter((c) => (c?.involved ?? []).some((i) => i?.stage === props.stageId))
})

const conflictHandlerKeys = computed(() => {
  const set = new Set<HandlerKey>()
  if (!props.snapshot || !props.stageId) return set
  for (const c of props.snapshot.conflicts ?? []) {
    for (const inv of c?.involved ?? []) {
      if (inv?.stage !== props.stageId) continue
      const full = inv?.handler?.handler_full_name
      if (!full) continue
      set.add(`${props.stageId}:${full}`)
    }
  }
  return set
})

const participantRiskLevel = (p: StageParticipant): 'none' | 'warn' | 'error' => {
  let hasWarn = false
  for (const r of p?.risks ?? []) {
    if (r?.level === 'error') return 'error'
    if (r?.level === 'warn') hasWarn = true
  }
  return hasWarn ? 'warn' : 'none'
}

const participantHasConflict = (p: StageParticipant) => {
  if (!props.stageId) return false
  const full = p?.handler?.handler_full_name
  if (!full) return false
  return conflictHandlerKeys.value.has(`${props.stageId}:${full}`)
}

const eventTypeLabel = (eventType: string) => {
  const map: Record<string, string> = {
    AdapterMessageEvent: '平台消息下发时',
    OnLLMRequestEvent: 'LLM请求前',
    OnLLMResponseEvent: 'LLM响应后',
    OnCallingFuncToolEvent: '函数工具调用',
    OnDecoratingResultEvent: '回复消息前',
    OnAfterMessageSentEvent: '发送消息后'
  }
  return map[eventType] || eventType || '未知事件'
}

const triggerText = (p: StageParticipant) => {
  const t = p?.meta?.trigger
  if (!t) return '—'
  const sig = t.signature || '—'
  return `${t.type}: ${sig}`
}

const openPlugin = (name: string) => {
  if (!name) return
  emit('select-plugin', name)
}

const selectParticipant = (id: string) => {
  if (!id) return
  emit('select-participant', id)
}

const clearFocus = () => {
  emit('select-participant', '')
}

const viewImpactChain = () => {
  const participantId = props.selectedParticipantId
  if (!participantId) return
  emit('view-impact-chain', { participantId, stageId: props.stageId })
}

watch(
  [() => props.stageId, () => props.selectedParticipantId],
  async () => {
    const id = props.selectedParticipantId
    if (!id) return
    await nextTick()
    const el = participantElById.get(id)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'start', inline: 'nearest' })
  },
  { flush: 'post' }
)

const stageTitle = computed(() => {
  if (!stageSnapshot.value) return ''
  return stageSnapshot.value.stage?.title || stageSnapshot.value.stage?.id || ''
})

const stageDescription = computed(() => {
  if (!stageSnapshot.value) return ''
  return stageSnapshot.value.stage?.description || ''
})

const stageTitleDisplay = computed(() => stageTitle.value || props.stageId || '—')
</script>

<template>
  <v-card class="sdp h-100 d-flex flex-column" rounded="lg" variant="flat">
    <div class="px-4 py-3 d-flex align-start ga-3">
      <div class="d-flex flex-column" style="min-width: 0">
        <v-tooltip location="top">
          <template #activator="{ props: tooltipProps }">
            <div v-bind="tooltipProps" class="text-subtitle-1 font-weight-bold sdp__title">
              {{ stageTitleDisplay }}
            </div>
          </template>
          <span class="sdp__tooltip-text">{{ stageTitleDisplay }}</span>
        </v-tooltip>

        <v-tooltip v-if="stageDescription" location="top">
          <template #activator="{ props: tooltipProps }">
            <div v-bind="tooltipProps" class="text-caption text-medium-emphasis sdp__desc-line">
              {{ stageDescription }}
            </div>
          </template>
          <span class="sdp__tooltip-text">{{ stageDescription }}</span>
        </v-tooltip>
      </div>

      <v-spacer />

      <v-btn
        v-if="focusedParticipant"
        size="small"
        color="secondary"
        variant="tonal"
        class="font-weight-medium"
        @click="viewImpactChain"
      >
        <v-icon start>mdi-map-marker-path</v-icon>
        {{ tm('pipeline.detail.viewImpactChain') }}
      </v-btn>

      <v-btn
        v-if="focusedPluginName"
        size="small"
        color="primary"
        variant="tonal"
        class="font-weight-medium"
        @click="clearFocus"
      >
        显示全部
      </v-btn>

      <v-tooltip v-if="focusedPluginName" location="top">
        <template #activator="{ props: tooltipProps }">
          <v-chip
            v-bind="tooltipProps"
            size="small"
            color="info"
            variant="tonal"
            class="font-weight-medium text-truncate"
            style="max-width: 220px"
          >
            仅显示：{{ focusedPluginDisplay }}
          </v-chip>
        </template>
        <span class="sdp__tooltip-text">仅显示：{{ focusedPluginDisplay }}</span>
      </v-tooltip>

      <v-chip size="small" color="secondary" variant="tonal" class="font-weight-medium">
        {{ participants.length }}{{ tm('pipeline.detail.participants') }}
      </v-chip>

      <v-chip
        v-if="conflictsForStage.length"
        size="small"
        color="error"
        variant="tonal"
        class="font-weight-medium"
      >
        {{ conflictsForStage.length }}{{ tm('pipeline.detail.conflicts') }}
      </v-chip>
    </div>

    <v-divider />

    <div class="sdp__scroll pa-3">
      <div v-if="!snapshot" class="h-100 d-flex align-center justify-center pa-8">
        <div class="text-body-2 text-medium-emphasis">{{ tm('pipeline.detail.noSnapshot') }}</div>
      </div>

      <div v-else-if="!stageId" class="h-100 d-flex flex-column align-center justify-center pa-8">
        <v-icon size="56" color="info" class="mb-2">mdi-timeline-clock-outline</v-icon>
        <div class="text-h6 mb-1">{{ tm('pipeline.detail.noStageSelected') }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ tm('pipeline.detail.noStageSelectedHint') }}</div>
      </div>

      <div v-else-if="participantsSorted.length === 0" class="h-100 d-flex flex-column align-center justify-center pa-8">
        <v-icon size="56" color="success" class="mb-2">mdi-check-circle-outline</v-icon>
        <div class="text-h6 mb-1">{{ tm('pipeline.detail.noParticipants') }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ tm('pipeline.detail.noParticipantsHint') }}</div>
      </div>

      <template v-else>
        <v-list density="compact" lines="two" class="sdp__list pa-0">
          <v-list-item
            v-for="p in visibleParticipantsSorted"
            :key="p.id"
            class="sdp__item"
            :class="{
              'sdp__item--selected': selectedParticipantId === p.id,
              'sdp__item--conflict': participantHasConflict(p)
            }"
            @click="selectParticipant(p.id)"
          >
            <div class="py-2" :ref="setParticipantEl(p.id)">
              <div class="d-flex align-center flex-wrap ga-2" style="min-width: 0">
                <v-chip size="x-small" color="info" variant="tonal" class="font-weight-bold">
                  P{{ p.meta?.priority ?? 0 }}
                </v-chip>

                <v-chip
                  size="x-small"
                  color="secondary"
                  variant="tonal"
                  class="font-weight-medium"
                >
                  {{ eventTypeLabel(p.meta?.event_type || 'UnknownEvent') }}
                </v-chip>

                <v-chip
                  v-if="p.meta?.enabled === false"
                  size="x-small"
                  color="grey"
                  variant="tonal"
                  class="font-weight-bold"
                >
                  OFF
                </v-chip>

                <v-icon v-if="participantRiskLevel(p) === 'warn'" size="18" color="warning">mdi-alert-outline</v-icon>
                <v-icon v-else-if="participantRiskLevel(p) === 'error'" size="18" color="error">mdi-alert-circle-outline</v-icon>

                <v-icon v-if="participantHasConflict(p)" size="18" color="error">mdi-close-octagon-outline</v-icon>

                <v-tooltip location="top">
                  <template #activator="{ props: tooltipProps }">
                    <span v-bind="tooltipProps" class="sdp__mono sdp__wrap">
                      {{ p.handler?.handler_full_name || '—' }}
                    </span>
                  </template>
                  <span class="sdp__tooltip-text">{{ p.handler?.handler_full_name || '—' }}</span>
                </v-tooltip>
              </div>

              <div class="mt-1 text-caption text-medium-emphasis d-flex align-center flex-wrap ga-2">
                <span>{{ tm('pipeline.detail.plugin') }}：</span>
                <span
                  class="sdp__plugin-link sdp__wrap"
                  role="button"
                  tabindex="0"
                  @click.stop="openPlugin(p.plugin?.name)"
                  @keydown.enter.stop="openPlugin(p.plugin?.name)"
                >
                  {{ p.plugin?.display_name || p.plugin?.name || '—' }}
                </span>
                <span class="sdp__sep">·</span>
                <span>{{ tm('pipeline.detail.trigger') }}：</span>
                <v-tooltip location="top">
                  <template #activator="{ props: tooltipProps }">
                    <span v-bind="tooltipProps" class="sdp__mono sdp__wrap">
                      {{ triggerText(p) }}
                    </span>
                  </template>
                  <span class="sdp__tooltip-text">{{ triggerText(p) }}</span>
                </v-tooltip>
              </div>

              <div v-if="p.meta?.description" class="mt-1 text-caption sdp__desc">
                {{ p.meta.description }}
              </div>

              <div v-if="(p.risks?.length ?? 0) > 0" class="mt-2 sdp__risks">
                <v-chip
                  v-for="(r, idx) in p.risks"
                  :key="p.id + ':risk:' + idx"
                  size="x-small"
                  :color="r.level === 'error' ? 'error' : r.level === 'warn' ? 'warning' : 'info'"
                  variant="tonal"
                  class="font-weight-medium"
                >
                  {{ r.summary }}
                </v-chip>
              </div>
            </div>
          </v-list-item>
        </v-list>
      </template>
    </div>
  </v-card>
</template>

<style scoped>
.sdp {
  min-height: 0;
}

.sdp__scroll {
  min-height: 0;
  overflow-y: auto;
}

.sdp__list {
  background: transparent;
}

.sdp__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.sdp__wrap {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
}

.sdp__title {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.sdp__desc-line {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.sdp__tooltip-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.sdp__sep {
  opacity: 0.6;
}

.sdp__plugin-link {
  cursor: pointer;
  text-decoration: underline;
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  overflow-wrap: anywhere;
  word-break: break-word;
  max-width: 100%;
}

.sdp__plugin-link:hover {
  color: rgb(var(--v-theme-info));
}

.sdp__item {
  border-radius: 12px;
}

.sdp__item--selected {
  background: rgba(var(--v-theme-primary), 0.06);
}

.sdp__item--conflict {
  outline: 1px solid rgba(var(--v-theme-error), 0.35);
}

.sdp__desc {
  max-width: 820px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  overflow-wrap: anywhere;
  word-break: break-word;
}

.sdp__risks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>