<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { PipelineSnapshot, PipelineStageId, Effect, EffectTarget } from './pipelineSnapshotTypes'
import type { RootGroup, TraceRow } from './traceGrouping'
import { applyTraceFilter, buildTraceRows, groupTraceRowsByTarget, impactRank } from './traceGrouping'

const props = withDefaults(
  defineProps<{
    snapshot: PipelineSnapshot | null
    selectedTarget?: '__all__' | EffectTarget
    focusGroupKey?: string | null
  }>(),
  {
    selectedTarget: '__all__',
    focusGroupKey: null
  }
)

const emit = defineEmits<{
  (e: 'select-stage', stageId: PipelineStageId): void
  (e: 'select-participant', participantId: string): void
  (e: 'navigate-pipeline', payload: { stageId: PipelineStageId; participantId: string }): void
  (e: 'update:selected-target', target: '__all__' | EffectTarget): void
}>()

const selectedTarget = computed<'__all__' | EffectTarget>({
  get: () => props.selectedTarget,
  set: (v) => emit('update:selected-target', v)
})

const listScrollEl = ref<HTMLElement | null>(null)

const cssEscape = (value: string) => {
  const cssAny = CSS as any
  if (cssAny?.escape) return cssAny.escape(value)
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

const scrollToGroupKey = async (key: string) => {
  await nextTick()
  const root = listScrollEl.value
  if (!root) return
  const selector = `[data-trace-group-key="${cssEscape(String(key))}"]`
  const dom = root.querySelector(selector) as HTMLElement | null
  if (!dom) return
  dom.scrollIntoView({ block: 'start' })
}

watch(
  () => props.focusGroupKey,
  (key) => {
    if (!key) return
    void scrollToGroupKey(String(key))
  }
)

const impactLabel = (e: Effect) => {
  const target = String(e?.target || '')
  const op = String(e?.op || '')
  if (target === 'stop') return 'STOP'
  if (target === 'send') return 'SEND'
  if (op === 'clear') return 'CLEAR'
  if (op === 'overwrite') return 'OVERWRITE'
  if (op === 'mutate_list') return 'MUTATE'
  if (op === 'append') return 'APPEND'
  if (op === 'call') return 'CALL'
  return op || '—'
}

const impactColor = (e: Effect) => {
  const rank = impactRank(e)
  if (rank === 2) return 'error'
  if (rank === 1) return 'warning'
  return 'secondary'
}

const confidenceLabel = (confidenceRaw: unknown) => {
  const c = String(confidenceRaw || '')
  if (c === 'high') return '高'
  if (c === 'medium') return '中'
  if (c === 'low') return '低'
  if (c === 'unknown') return '未知'
  return '—'
}

const confidenceColor = (confidenceRaw: unknown) => {
  const c = String(confidenceRaw || '')
  if (c === 'high') return 'success'
  if (c === 'medium') return 'warning'
  if (c === 'low') return 'grey'
  return 'secondary'
}

const tooltipTextForEffect = (e: Effect) => {
  const evidence = typeof e?.evidence === 'string' ? e.evidence : ''
  const lineno = e?.lineno
  const col = e?.col
  const locParts: string[] = []
  if (typeof lineno === 'number') locParts.push(`line=${lineno}`)
  if (typeof col === 'number') locParts.push(`col=${col}`)
  const loc = locParts.length ? `（${locParts.join(', ')}）` : ''
  if (evidence) return `evidence: ${evidence}${loc}`
  if (loc) return `位置: ${loc}`
  return '—'
}

const rows = computed<TraceRow[]>(() => buildTraceRows(props.snapshot))

const filteredRows = computed(() =>
  applyTraceFilter(rows.value, {
    selectedTarget: selectedTarget.value,
    onlyHighImpact: false
  })
)

const hasAnyEffects = computed(() => rows.value.length > 0)

const rootGroups = computed<RootGroup[]>(() => groupTraceRowsByTarget(props.snapshot, filteredRows.value))

const selectedRow = ref<TraceRow | null>(null)

watch(
  filteredRows,
  (list) => {
    if (list.length === 0) {
      selectedRow.value = null
      return
    }

    if (!selectedRow.value) {
      selectedRow.value = list[0] ?? null
      return
    }

    const key = selectedRow.value.key
    const stillExists = list.some((r) => r.key === key)
    if (!stillExists) selectedRow.value = list[0] ?? null
  },
  { immediate: true }
)

const selectRow = (r: TraceRow) => {
  selectedRow.value = r
}

const jumpToPipelineForRow = (r: TraceRow) => {
  const stageId = r.stageId
  const participantId = r.participantId
  if (!stageId || !participantId) return
  emit('select-stage', stageId)
  emit('select-participant', participantId)
  emit('navigate-pipeline', { stageId, participantId })
}

const filterByTarget = (target: string) => {
  const t = String(target || '')
  if (!t) return
  selectedTarget.value = t as EffectTarget
}
</script>

<template>
  <v-card class="tp h-100 d-flex flex-column" rounded="lg" variant="flat">
    <div class="tp__body d-flex flex-grow-1" style="min-height: 0">
      <div ref="listScrollEl" class="tp__list-col pa-3">
        <div v-if="!snapshot" class="h-100 d-flex align-center justify-center pa-8">
          <div class="text-body-2 text-medium-emphasis">暂无快照数据</div>
        </div>

        <div v-else-if="!hasAnyEffects" class="h-100 d-flex flex-column align-center justify-center pa-8">
          <v-icon size="56" color="info" class="mb-2">mdi-map-marker-path</v-icon>
          <div class="text-h6 mb-1">暂无可追踪影响（effects）</div>
          <div class="text-body-2 text-medium-emphasis">后端未返回 effects，或当前参与者未产生可识别影响。</div>
        </div>

        <div v-else-if="filteredRows.length === 0" class="h-100 d-flex flex-column align-center justify-center pa-8">
          <v-icon size="56" color="warning" class="mb-2">mdi-filter-variant</v-icon>
          <div class="text-h6 mb-1">无匹配条目</div>
          <div class="text-body-2 text-medium-emphasis">请调整目标对象筛选。</div>
        </div>

        <template v-else>
          <v-expansion-panels :key="String(selectedTarget)" variant="accordion" multiple density="comfortable">
            <v-expansion-panel
              v-for="rg in rootGroups"
              :key="rg.key"
              class="tp__group"
              :data-trace-group-key="String(rg.key)"
            >
              <v-expansion-panel-title>
                <div class="d-flex align-center flex-wrap ga-2" style="min-width: 0">
                  <v-icon size="18" color="primary">mdi-map-marker-path</v-icon>

                  <v-tooltip location="top">
                    <template #activator="{ props: tooltipProps }">
                      <span v-bind="tooltipProps" class="tp__title text-truncate" style="max-width: 720px">
                        {{ rg.title }}
                      </span>
                    </template>
                    <span class="tp__tooltip-text">{{ rg.title }}</span>
                  </v-tooltip>

                  <v-chip size="x-small" color="secondary" variant="tonal" class="font-weight-bold">
                    {{ rg.groups.reduce((acc, g) => acc + g.rows.length, 0) }}
                  </v-chip>

                  <v-spacer />

                  <v-chip v-if="rg.subtitle" size="x-small" color="secondary" variant="tonal" class="font-weight-bold">
                    {{ rg.subtitle }}
                  </v-chip>
                </div>
              </v-expansion-panel-title>

              <v-expansion-panel-text>
                <v-expansion-panels :key="String(rg.key)" variant="accordion" multiple density="compact">
                  <v-expansion-panel v-for="g in rg.groups" :key="g.key" :data-trace-group-key="String(g.key)">
                    <v-expansion-panel-title>
                      <div class="d-flex align-center flex-wrap ga-2" style="min-width: 0">
                        <v-tooltip location="top">
                          <template #activator="{ props: tooltipProps }">
                            <span v-bind="tooltipProps" class="tp__sub-title text-truncate" style="max-width: 680px">
                              {{ g.title }}
                            </span>
                          </template>
                          <span class="tp__tooltip-text">{{ g.title }}</span>
                        </v-tooltip>

                        <v-chip size="x-small" color="secondary" variant="tonal" class="font-weight-bold">
                          {{ g.rows.length }}
                        </v-chip>

                        <v-spacer />

                        <v-chip v-if="g.subtitle" size="x-small" color="secondary" variant="tonal" class="font-weight-bold">
                          {{ g.subtitle }}
                        </v-chip>
                      </div>
                    </v-expansion-panel-title>

                    <v-expansion-panel-text>
                      <v-list density="compact" lines="two" class="tp__list pa-0">
                        <v-list-item
                          v-for="r in g.rows"
                          :key="r.key"
                          class="tp__item"
                          :class="{ 'tp__item--selected': selectedRow?.key === r.key }"
                          role="button"
                          tabindex="0"
                          @click="selectRow(r)"
                          @keydown.enter="selectRow(r)"
                        >
                          <div class="py-2">
                            <div class="d-flex align-center flex-wrap ga-2" style="min-width: 0">
                              <v-tooltip location="top">
                                <template #activator="{ props: tooltipProps }">
                                  <span v-bind="tooltipProps" class="tp__plugin tp__wrap">
                                    {{ r.participant?.plugin?.display_name || r.participant?.plugin?.name || '—' }}
                                  </span>
                                </template>
                                <span class="tp__tooltip-text">
                                  {{ r.participant?.plugin?.display_name || r.participant?.plugin?.name || '—' }}
                                </span>
                              </v-tooltip>

                              <span class="tp__sep">·</span>

                              <v-tooltip location="top">
                                <template #activator="{ props: tooltipProps }">
                                  <span v-bind="tooltipProps" class="tp__mono tp__handler tp__wrap">
                                    {{ r.participant?.handler?.handler_name || r.participant?.handler?.handler_full_name || '—' }}
                                  </span>
                                </template>
                                <span class="tp__tooltip-text">
                                  {{ r.participant?.handler?.handler_full_name || r.participant?.handler?.handler_name || '—' }}
                                </span>
                              </v-tooltip>

                              <v-spacer />

                              <v-tooltip location="top">
                                <template #activator="{ props: tooltipProps }">
                                  <v-chip
                                    v-bind="tooltipProps"
                                    size="x-small"
                                    :color="impactColor(r.effect)"
                                    variant="tonal"
                                    class="font-weight-bold"
                                  >
                                    {{ impactLabel(r.effect) }}
                                  </v-chip>
                                </template>
                                <span class="tp__tooltip-text">{{ tooltipTextForEffect(r.effect) }}</span>
                              </v-tooltip>

                              <v-chip
                                size="x-small"
                                :color="confidenceColor(r.effect.confidence)"
                                variant="tonal"
                                class="font-weight-bold"
                              >
                                置信度 {{ confidenceLabel(r.effect.confidence) }}
                              </v-chip>

                              <v-tooltip location="top">
                                <template #activator="{ props: tooltipProps }">
                                  <v-btn
                                    v-bind="tooltipProps"
                                    icon
                                    variant="text"
                                    size="x-small"
                                    class="tp__jump"
                                    @click.stop="jumpToPipelineForRow(r)"
                                  >
                                    <v-icon size="18">mdi-open-in-new</v-icon>
                                  </v-btn>
                                </template>
                                <span class="tp__tooltip-text">跳转到 pipeline</span>
                              </v-tooltip>
                            </div>

                            <div class="mt-1 text-caption text-medium-emphasis d-flex align-center flex-wrap ga-2">
                              <v-chip size="x-small" color="secondary" variant="tonal" class="font-weight-medium">
                                {{ r.stageTitle }}
                              </v-chip>

                              <v-chip
                                size="x-small"
                                color="info"
                                variant="tonal"
                                class="font-weight-medium tp__chip-clickable"
                                @click.stop="filterByTarget(String(r.effect.target || ''))"
                              >
                                target: {{ String(r.effect.target || '—') }}
                              </v-chip>

                              <v-chip size="x-small" color="secondary" variant="tonal" class="font-weight-medium">
                                op: {{ String(r.effect.op || '—') }}
                              </v-chip>
                            </div>
                          </div>
                        </v-list-item>
                      </v-list>
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </template>
      </div>
    </div>
  </v-card>
</template>

<style scoped>
.tp {
  min-height: 0;
}

.tp__body {
  min-height: 0;
  overflow: hidden;
}

.tp__list-col {
  flex: 1 1 0;
  width: 100%;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
}

.tp__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.tp__wrap {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
}

.tp__tooltip-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.tp__title {
  font-weight: 800;
}

.tp__sub-title {
  font-weight: 700;
}

.tp__list {
  background: transparent;
}

.tp__item {
  border-radius: 12px;
  cursor: pointer;
}

.tp__item:hover {
  background: rgba(var(--v-theme-primary), 0.04);
}

.tp__item--selected {
  background: rgba(var(--v-theme-primary), 0.06);
}

.tp__plugin {
  font-weight: 800;
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.tp__handler {
  text-decoration: underline;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.tp__handler:hover {
  color: rgb(var(--v-theme-primary));
}

.tp__sep {
  opacity: 0.6;
}

.tp__chip-clickable {
  cursor: pointer;
}

.tp__jump {
  opacity: 0.9;
}

.tp__jump:hover {
  opacity: 1;
}
</style>