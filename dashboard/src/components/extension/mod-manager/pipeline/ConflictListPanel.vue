<script setup lang="ts">
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import type { ConflictItem, ConfidenceLevel, PipelineSnapshot, PipelineStageId } from './pipelineSnapshotTypes'

type Severity = 'info' | 'warn' | 'error'
type InvolvedItem = ConflictItem['involved'][number]

type ConflictGroup = {
  key: string
  type: ConflictItem['type']
  severity: Severity
  title: string
  description: string
  suggestion?: string
  involved: InvolvedItem[]
  pluginGroups: Array<{
    key: string
    pluginName: string
    pluginDisplay: string
    involved: InvolvedItem[]
  }>
  relationPairs: Array<{ left: InvolvedItem; right: InvolvedItem }>

  confidence?: ConfidenceLevel
  confidenceReason?: string
  note?: string
}

const { tm } = useModuleI18n('features/extension')

const props = defineProps<{
  snapshot: PipelineSnapshot | null
}>()

const emit = defineEmits<{
  (e: 'select-stage', stageId: PipelineStageId): void
  (e: 'select-participant', participantId: string): void
  (e: 'select-plugin', pluginName: string): void
}>()

const conflicts = computed<ConflictItem[]>(() => (props.snapshot?.conflicts ?? []).filter(Boolean))

const stageTitleById = computed(() => {
  const map = new Map<PipelineStageId, string>()
  for (const s of props.snapshot?.stages ?? []) {
    const id = s?.stage?.id as PipelineStageId | undefined
    if (!id) continue
    map.set(id, s.stage?.title || id)
  }
  return map
})

const stageLabel = (stageId: PipelineStageId) => stageTitleById.value.get(stageId) || stageId

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

const severityOrder: Severity[] = ['error', 'warn', 'info']

const severityColor = (sev: Severity) => {
  if (sev === 'error') return 'error'
  if (sev === 'warn') return 'warning'
  return 'info'
}

const severityIcon = (sev: Severity) => {
  if (sev === 'error') return 'mdi-alert-octagon-outline'
  if (sev === 'warn') return 'mdi-alert-outline'
  return 'mdi-information-outline'
}

const confidenceRank = (level?: ConfidenceLevel) => {
  if (level === 'high') return 2
  if (level === 'medium') return 1
  if (level === 'low') return 0
  return -1
}

const confidenceLabel = (level?: ConfidenceLevel) => {
  if (level === 'high') return '高'
  if (level === 'medium') return '中'
  if (level === 'low') return '低'
  return '—'
}

const confidenceColor = (level?: ConfidenceLevel) => {
  if (level === 'high') return 'success'
  if (level === 'medium') return 'warning'
  if (level === 'low') return 'grey'
  return 'secondary'
}

const confidenceIcon = (level?: ConfidenceLevel) => {
  if (level === 'high') return 'mdi-check-decagram-outline'
  if (level === 'medium') return 'mdi-alert-circle-outline'
  if (level === 'low') return 'mdi-help-circle-outline'
  return 'mdi-information-outline'
}

const pluginDisplayName = (inv: InvolvedItem) => inv?.plugin?.display_name || inv?.plugin?.name || '—'

const handlerLabel = (inv: InvolvedItem) => inv?.handler?.handler_name || inv?.handler?.handler_full_name || '—'

const groupKeyForConflict = (c: ConflictItem) => `${c.type}:${c.title}`

const conflictGroups = computed<ConflictGroup[]>(() => {
  const byKey = new Map<string, ConflictItem[]>()
  for (const c of conflicts.value) {
    const key = groupKeyForConflict(c)
    const list = byKey.get(key) ?? []
    list.push(c)
    byKey.set(key, list)
  }

  const groups: ConflictGroup[] = []
  for (const [key, items] of byKey.entries()) {
    const first = items[0]
    if (!first) continue

    const involved: InvolvedItem[] = []
    for (const c of items) involved.push(...((c.involved ?? []).filter(Boolean) as InvolvedItem[]))

    involved.sort((a, b) => {
      const pa = pluginDisplayName(a)
      const pb = pluginDisplayName(b)
      const p = pa.localeCompare(pb)
      if (p !== 0) return p
      const ha = handlerLabel(a)
      const hb = handlerLabel(b)
      const h = ha.localeCompare(hb)
      if (h !== 0) return h
      const fa = a?.handler?.handler_full_name || ''
      const fb = b?.handler?.handler_full_name || ''
      return fa.localeCompare(fb)
    })

    const pluginMap = new Map<string, { pluginName: string; pluginDisplay: string; involved: InvolvedItem[] }>()
    for (const inv of involved) {
      const pluginName = inv?.plugin?.name || 'unknown'
      const entry = pluginMap.get(pluginName) ?? {
        pluginName,
        pluginDisplay: pluginDisplayName(inv),
        involved: []
      }
      entry.involved.push(inv)
      pluginMap.set(pluginName, entry)
    }

    const pluginGroups = [...pluginMap.values()].sort((a, b) => a.pluginDisplay.localeCompare(b.pluginDisplay))
    for (const pg of pluginGroups) {
      pg.involved.sort((a, b) => {
        const sa = String(a?.stage || '')
        const sb = String(b?.stage || '')
        const s = sa.localeCompare(sb)
        if (s !== 0) return s
        const pa = (a?.priority ?? 0) as number
        const pb = (b?.priority ?? 0) as number
        if (pa !== pb) return pb - pa
        return handlerLabel(a).localeCompare(handlerLabel(b))
      })
    }

    const pivot = involved[0]
    const relationPairs = pivot ? involved.slice(1).map((right) => ({ left: pivot, right })) : []

    let bestConfidence: ConfidenceLevel | undefined = undefined
    let bestConfidenceReason: string | undefined = undefined
    let note: string | undefined = undefined

    for (const c of items) {
      const cLevel = c?.confidence as ConfidenceLevel | undefined
      if (confidenceRank(cLevel) > confidenceRank(bestConfidence)) {
        bestConfidence = cLevel
        bestConfidenceReason = (c?.confidence_reason as string | undefined) || undefined
      }
      if (!note && typeof c?.note === 'string' && c.note) {
        note = c.note
      }
    }

    groups.push({
      key,
      type: first.type,
      severity: (first.severity || 'info') as Severity,
      title: first.title,
      description: first.description,
      suggestion: first.suggestion,
      involved,
      pluginGroups: pluginGroups.map((x) => ({ key: x.pluginName, ...x })),
      relationPairs,
      confidence: bestConfidence,
      confidenceReason: bestConfidenceReason,
      note
    })
  }

  groups.sort((a, b) => {
    const sa = severityOrder.indexOf(a.severity)
    const sb = severityOrder.indexOf(b.severity)
    if (sa !== sb) return sa - sb
    const t = a.title.localeCompare(b.title)
    if (t !== 0) return t
    return a.key.localeCompare(b.key)
  })

  return groups
})

const handleJumpToStage = (stageId: PipelineStageId) => {
  if (!stageId) return
  emit('select-stage', stageId)
}

const handleJumpToParticipant = (stageId: PipelineStageId, handlerFullName: string) => {
  if (!stageId || !handlerFullName) return

  // 关键约定：participant.id 由后端生成；前端无法可靠从 handlerFullName 反推。
  // 这里使用“先跳转 stage，再交给容器用映射表（participantIdByHandlerKey）完成精确定位”：
  // emit('select-participant') 仅在容器有映射时调用；因此这里发出一个合成 id 供容器识别。
  emit('select-stage', stageId)
  emit('select-participant', `${stageId}:${handlerFullName}`)
}

const handleSelectPlugin = (pluginName: string) => {
  if (!pluginName) return
  emit('select-plugin', pluginName)
}
</script>

<template>
  <v-card class="clp h-100 d-flex flex-column" rounded="lg" variant="flat">
    <div class="px-4 py-3 d-flex align-center ga-2">
      <v-icon color="warning" size="20">mdi-alert-circle-outline</v-icon>
      <div class="text-subtitle-1 font-weight-bold">{{ tm('pipeline.conflictList.title') }}</div>
      <v-spacer />
      <v-chip size="small" color="secondary" variant="tonal" class="font-weight-medium">
        {{ tm('pipeline.conflictList.total', { count: conflicts.length }) }}
      </v-chip>
    </div>

    <v-divider />

    <div class="clp__scroll pa-3">
      <div v-if="!snapshot" class="h-100 d-flex align-center justify-center pa-8">
        <div class="text-body-2 text-medium-emphasis">{{ tm('pipeline.detail.noSnapshot') }}</div>
      </div>

      <div v-else-if="conflicts.length === 0" class="h-100 d-flex flex-column align-center justify-center pa-8">
        <v-icon size="64" color="success" class="mb-3">mdi-check-circle-outline</v-icon>
        <div class="text-h6 mb-1">{{ tm('pipeline.conflictList.none') }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ tm('pipeline.conflictList.noneHint') }}</div>
      </div>

      <template v-else>
        <v-expansion-panels variant="accordion" multiple density="comfortable">
          <v-expansion-panel v-for="g in conflictGroups" :key="g.key" class="clp__group">
            <v-expansion-panel-title>
              <div class="d-flex align-center flex-wrap ga-2" style="min-width: 0">
                <v-icon :color="severityColor(g.severity)" size="18">{{ severityIcon(g.severity) }}</v-icon>

                <v-tooltip location="top">
                  <template #activator="{ props: tooltipProps }">
                    <span v-bind="tooltipProps" class="clp__title text-truncate" style="max-width: 720px">
                      {{ g.title }}
                    </span>
                  </template>
                  <span class="clp__tooltip-text">{{ g.title }}</span>
                </v-tooltip>

                <v-chip size="x-small" :color="severityColor(g.severity)" variant="tonal" class="font-weight-bold">
                  {{ g.involved.length }}
                </v-chip>

                <v-spacer />

                <v-tooltip v-if="g.confidence" location="top">
                  <template #activator="{ props: tooltipProps }">
                    <v-chip
                      v-bind="tooltipProps"
                      size="x-small"
                      :color="confidenceColor(g.confidence)"
                      variant="tonal"
                      class="font-weight-bold"
                    >
                      <v-icon start size="14">{{ confidenceIcon(g.confidence) }}</v-icon>
                      置信度 {{ confidenceLabel(g.confidence) }}
                    </v-chip>
                  </template>
                  <div class="clp__tooltip-text">
                    <div>置信度：{{ confidenceLabel(g.confidence) }}（{{ g.confidence }}）</div>
                    <div v-if="g.confidenceReason">原因：{{ g.confidenceReason }}</div>
                    <div v-if="g.note" style="margin-top: 6px">说明：{{ g.note }}</div>
                  </div>
                </v-tooltip>

                <v-chip size="x-small" color="secondary" variant="tonal" class="font-weight-bold">
                  {{ g.type }}
                </v-chip>
              </div>
            </v-expansion-panel-title>

            <v-expansion-panel-text>
              <div class="text-caption text-medium-emphasis clp__desc">
                {{ g.description }}
              </div>

              <div v-if="g.confidence" class="mt-2">
                <v-chip size="small" :color="confidenceColor(g.confidence)" variant="tonal" class="font-weight-bold">
                  <v-icon start size="16">{{ confidenceIcon(g.confidence) }}</v-icon>
                  置信度：{{ confidenceLabel(g.confidence) }}
                </v-chip>
                <span v-if="g.confidenceReason" class="text-caption text-medium-emphasis ml-2">
                  原因：{{ g.confidenceReason }}
                </span>
              </div>

              <div v-if="g.note" class="mt-2 text-caption text-medium-emphasis">
                {{ g.note }}
              </div>

              <div v-if="g.suggestion" class="mt-2 clp__suggestion">
                <v-icon size="16" color="info">mdi-lightbulb-on-outline</v-icon>
                <span class="text-caption text-medium-emphasis">{{ g.suggestion }}</span>
              </div>

              <div v-if="g.relationPairs.length" class="mt-3 clp__relation">
                <div class="text-caption font-weight-bold mb-1">冲突关系</div>

                <div class="clp__relation-list">
                  <div v-for="(pair, idx) in g.relationPairs" :key="g.key + ':rel:' + idx" class="clp__relation-row">
                    <div
                      class="clp__rel-node"
                      role="button"
                      tabindex="0"
                      @click="handleJumpToParticipant(pair.left.stage as PipelineStageId, pair.left.handler?.handler_full_name)"
                      @keydown.enter="handleJumpToParticipant(pair.left.stage as PipelineStageId, pair.left.handler?.handler_full_name)"
                    >
                      <v-tooltip location="top">
                        <template #activator="{ props: tooltipProps }">
                          <div v-bind="tooltipProps" class="clp__rel-plugin clp__wrap">
                            {{ pair.left.plugin?.display_name || pair.left.plugin?.name || '—' }}
                          </div>
                        </template>
                        <span class="clp__tooltip-text">{{ pair.left.plugin?.display_name || pair.left.plugin?.name || '—' }}</span>
                      </v-tooltip>

                      <v-tooltip location="top">
                        <template #activator="{ props: tooltipProps }">
                          <div v-bind="tooltipProps" class="clp__rel-handler clp__mono clp__wrap">
                            {{ pair.left.handler?.handler_name || pair.left.handler?.handler_full_name || '—' }}
                          </div>
                        </template>
                        <span class="clp__tooltip-text">{{ pair.left.handler?.handler_name || pair.left.handler?.handler_full_name || '—' }}</span>
                      </v-tooltip>
                    </div>

                    <div class="clp__rel-arrow">
                      <span class="clp__rel-arrow-text">←冲突→</span>
                    </div>

                    <div
                      class="clp__rel-node"
                      role="button"
                      tabindex="0"
                      @click="handleJumpToParticipant(pair.right.stage as PipelineStageId, pair.right.handler?.handler_full_name)"
                      @keydown.enter="handleJumpToParticipant(pair.right.stage as PipelineStageId, pair.right.handler?.handler_full_name)"
                    >
                      <v-tooltip location="top">
                        <template #activator="{ props: tooltipProps }">
                          <div v-bind="tooltipProps" class="clp__rel-plugin clp__wrap">
                            {{ pair.right.plugin?.display_name || pair.right.plugin?.name || '—' }}
                          </div>
                        </template>
                        <span class="clp__tooltip-text">{{ pair.right.plugin?.display_name || pair.right.plugin?.name || '—' }}</span>
                      </v-tooltip>

                      <v-tooltip location="top">
                        <template #activator="{ props: tooltipProps }">
                          <div v-bind="tooltipProps" class="clp__rel-handler clp__mono clp__wrap">
                            {{ pair.right.handler?.handler_name || pair.right.handler?.handler_full_name || '—' }}
                          </div>
                        </template>
                        <span class="clp__tooltip-text">{{ pair.right.handler?.handler_name || pair.right.handler?.handler_full_name || '—' }}</span>
                      </v-tooltip>
                    </div>
                  </div>
                </div>
              </div>

              <div class="mt-3 clp__plugins">
                <div class="text-caption font-weight-bold mb-1">{{ tm('pipeline.conflictList.involved') }}</div>

                <v-expansion-panels variant="accordion" multiple density="compact">
                  <v-expansion-panel v-for="pg in g.pluginGroups" :key="g.key + ':pg:' + pg.key">
                    <v-expansion-panel-title>
                      <div class="d-flex align-center flex-wrap ga-2" style="min-width: 0">
                        <v-tooltip location="top">
                          <template #activator="{ props: tooltipProps }">
                            <span
                              v-bind="tooltipProps"
                              class="clp__plugin-link text-truncate"
                              role="button"
                              tabindex="0"
                              @click.stop="handleSelectPlugin(pg.pluginName)"
                              @keydown.enter.stop="handleSelectPlugin(pg.pluginName)"
                            >
                              {{ pg.pluginDisplay }}
                            </span>
                          </template>
                          <span class="clp__tooltip-text">{{ pg.pluginDisplay }}</span>
                        </v-tooltip>

                        <v-chip size="x-small" color="secondary" variant="tonal" class="font-weight-bold">
                          {{ pg.involved.length }}
                        </v-chip>
                      </div>
                    </v-expansion-panel-title>

                    <v-expansion-panel-text>
                      <div class="clp__methods">
                        <div v-for="(inv, idx) in pg.involved" :key="g.key + ':m:' + pg.key + ':' + idx" class="clp__method">
                          <div class="d-flex align-center flex-wrap ga-2" style="min-width: 0">
                            <v-chip
                              size="x-small"
                              color="secondary"
                              variant="tonal"
                              class="font-weight-medium"
                              @click="handleJumpToStage(inv.stage as PipelineStageId)"
                            >
                              {{ stageLabel(inv.stage as PipelineStageId) }}
                            </v-chip>

                            <v-chip size="x-small" color="info" variant="tonal" class="font-weight-medium">
                              P{{ inv.priority }}
                            </v-chip>

                            <v-chip
                              v-if="inv.enabled === false"
                              size="x-small"
                              color="grey"
                              variant="tonal"
                              class="font-weight-bold"
                            >
                              OFF
                            </v-chip>

                            <v-tooltip location="top">
                              <template #activator="{ props: tooltipProps }">
                                <span
                                  v-bind="tooltipProps"
                                  class="clp__mono clp__handler clp__wrap"
                                  role="button"
                                  tabindex="0"
                                  @click="handleJumpToParticipant(inv.stage as PipelineStageId, inv.handler?.handler_full_name)"
                                  @keydown.enter="handleJumpToParticipant(inv.stage as PipelineStageId, inv.handler?.handler_full_name)"
                                >
                                  {{ inv.handler?.handler_name || inv.handler?.handler_full_name || '—' }}
                                </span>
                              </template>
                              <span class="clp__tooltip-text">{{ inv.handler?.handler_name || inv.handler?.handler_full_name || '—' }}</span>
                            </v-tooltip>
                          </div>

                          <div class="mt-1 text-caption text-medium-emphasis d-flex align-center flex-wrap ga-2">
                            <span class="clp__mono">{{ eventTypeLabel(inv.event_type as string) }}</span>
                          </div>
                        </div>
                      </div>
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </template>
    </div>
  </v-card>
</template>

<style scoped>
.clp {
  min-height: 0;
}

.clp__scroll {
  min-height: 0;
  overflow-y: auto;
}

.clp__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.clp__title {
  font-weight: 700;
}

.clp__desc {
  max-width: 920px;
}

.clp__suggestion {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(var(--v-theme-surface-variant), 0.16);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.clp__handler {
  cursor: pointer;
  text-decoration: underline;
  color: rgba(var(--v-theme-on-surface), 0.85);
  font-weight: 600;
}

.clp__handler:hover {
  color: rgb(var(--v-theme-primary));
}

.clp__plugin-link {
  cursor: pointer;
  text-decoration: underline;
  color: rgb(var(--v-theme-primary));
  font-weight: 700;
  max-width: 100%;
}

.clp__plugin-link:hover {
  color: rgb(var(--v-theme-info));
}

.clp__relation-list {
  display: grid;
  gap: 10px;
}

.clp__relation-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 10px;
  align-items: stretch;
}

.clp__rel-node {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.7);
  min-width: 0;
}

.clp__rel-node:hover {
  border-color: rgba(var(--v-theme-primary), 0.35);
}

.clp__rel-plugin {
  font-weight: 700;
}

.clp__rel-handler {
  opacity: 0.85;
  margin-top: 4px;
}

.clp__rel-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
}

.clp__rel-arrow-text {
  font-weight: 700;
  color: rgba(var(--v-theme-error), 0.85);
  white-space: nowrap;
}

.clp__methods {
  display: grid;
  gap: 10px;
}

.clp__wrap {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
}

.clp__tooltip-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.clp__method {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.55);
}
</style>