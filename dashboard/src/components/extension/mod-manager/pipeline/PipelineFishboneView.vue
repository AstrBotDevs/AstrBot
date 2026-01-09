<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import type { PipelineSnapshot, PipelineStageId, PluginEventType, StageParticipant } from './pipelineSnapshotTypes'

const STAGES_ORDER: PipelineStageId[] = [
  'WakingCheckStage',
  'WhitelistCheckStage',
  'SessionStatusCheckStage',
  'RateLimitStage',
  'ContentSafetyCheckStage',
  'PreProcessStage',
  'ProcessStage',
  'ResultDecorateStage',
  'RespondStage'
]

type StageEffectBadge = { total: number; high: number }
type StageEffectBadgeMap = Partial<Record<PipelineStageId, StageEffectBadge>>

const props = withDefaults(
  defineProps<{
    snapshot: PipelineSnapshot | null
    selectedStageId?: PipelineStageId | null
    selectedParticipantId?: string | null
    stageBadges?: StageEffectBadgeMap
    zoom?: number
    showAllStages?: boolean
  }>(),
  { showAllStages: false }
)

const emit = defineEmits<{
  (e: 'select-stage', stageId: PipelineStageId): void
  (e: 'select-participant', participantId: string): void
}>()

const { tm } = useModuleI18n('features/extension')

type HandlerKey = string
type PluginKey = string

type PluginGroup = {
  name: string
  displayName: string
  reserved: boolean
  activated: boolean
  participants: StageParticipant[]
  conflictCount: number
  warnCount: number
  errorCount: number
}

type StageNode = {
  stageId: PipelineStageId
  title: string
  description: string
  participantCount: number
  conflictCount: number
  riskCount: number
  effectBadge?: StageEffectBadge
  plugins: PluginGroup[]
}

const pluginOpen = reactive<Record<PluginKey, boolean>>({})

const zoomValue = computed(() => {
  const z = props.zoom ?? 1
  if (!Number.isFinite(z) || z <= 0) return 1
  return Math.min(2, Math.max(0.5, z))
})

const stagesById = computed(() => {
  const map = new Map<PipelineStageId, PipelineSnapshot['stages'][number] | null>()
  for (const id of STAGES_ORDER) map.set(id, null)
  for (const s of props.snapshot?.stages ?? []) {
    const stageId = s?.stage?.id as PipelineStageId | undefined
    if (!stageId) continue
    map.set(stageId, s)
  }
  return map
})

const conflictIndex = computed(() => {
  const conflictCountByStage = new Map<PipelineStageId, number>()
  const conflictHandlerKeys = new Set<HandlerKey>()
  for (const id of STAGES_ORDER) conflictCountByStage.set(id, 0)
  for (const c of props.snapshot?.conflicts ?? []) {
    for (const inv of c?.involved ?? []) {
      const stageId = inv?.stage as PipelineStageId
      const handlerFullName = inv?.handler?.handler_full_name
      if (!stageId || !handlerFullName) continue
      conflictHandlerKeys.add(`${stageId}:${handlerFullName}`)
      conflictCountByStage.set(stageId, (conflictCountByStage.get(stageId) ?? 0) + 1)
    }
  }
  return { conflictCountByStage, conflictHandlerKeys }
})

const stageRiskCount = (stageId: PipelineStageId) => {
  const participants = stagesById.value.get(stageId)?.participants ?? []
  let count = 0
  for (const p of participants) {
    for (const r of p?.risks ?? []) {
      if (r?.level === 'warn' || r?.level === 'error') count += 1
    }
  }
  return count
}

const stageParticipantCount = (stageId: PipelineStageId) =>
  stagesById.value.get(stageId)?.participants?.length ?? 0

const stageHasConflicts = (stageId: PipelineStageId) =>
  (conflictIndex.value.conflictCountByStage.get(stageId) ?? 0) > 0

const stageConflictBadge = (stageId: PipelineStageId) =>
  conflictIndex.value.conflictCountByStage.get(stageId) ?? 0

const isParticipantConflicting = (stageId: PipelineStageId, participant: StageParticipant) => {
  const handlerFullName = participant?.handler?.handler_full_name
  if (!handlerFullName) return false
  return conflictIndex.value.conflictHandlerKeys.has(`${stageId}:${handlerFullName}`)
}

const riskLevelForParticipant = (participant: StageParticipant): 'none' | 'warn' | 'error' => {
  let hasWarn = false
  for (const r of participant?.risks ?? []) {
    if (r?.level === 'error') return 'error'
    if (r?.level === 'warn') hasWarn = true
  }
  return hasWarn ? 'warn' : 'none'
}

const participantLabel = (participant: StageParticipant) =>
  participant?.handler?.handler_name || participant?.handler?.handler_full_name || '—'

const eventTypeLabel = (eventType: PluginEventType | string) => {
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

const handleSelectStage = (stageId: PipelineStageId) => emit('select-stage', stageId)

const handleSelectParticipant = (id: string) => {
  if (!id) return
  emit('select-participant', id)
}

const stageTitle = (stageId: PipelineStageId) => stagesById.value.get(stageId)?.stage?.title || stageId
const stageDescription = (stageId: PipelineStageId) => stagesById.value.get(stageId)?.stage?.description || ''

const visibleStageIds = computed(() => {
  if (props.showAllStages) return STAGES_ORDER
  return STAGES_ORDER.filter((id) => stageParticipantCount(id) > 0)
})

const pluginKeyOf = (stageId: PipelineStageId, name: string) => `${stageId}::${name}`
const isPluginOpen = (stageId: PipelineStageId, name: string) => Boolean(pluginOpen[pluginKeyOf(stageId, name)])

const togglePlugin = (stageId: PipelineStageId, name: string) => {
  if (!name) return
  const key = pluginKeyOf(stageId, name)
  pluginOpen[key] = !pluginOpen[key]
}

const stageNodes = computed<StageNode[]>(() => {
  const snapshot = props.snapshot
  if (!snapshot) return []
  const nodes: StageNode[] = []
  for (const stageId of visibleStageIds.value) {
    const stage = stagesById.value.get(stageId)
    const participants = (stage?.participants ?? []).slice()
    participants.sort((a, b) => {
      const pa = a?.meta?.priority ?? 0
      const pb = b?.meta?.priority ?? 0
      if (pa !== pb) return pb - pa
      const ha = a?.handler?.handler_full_name ?? ''
      const hb = b?.handler?.handler_full_name ?? ''
      return ha.localeCompare(hb)
    })

    const byPlugin = new Map<string, StageParticipant[]>()
    for (const p of participants) {
      const name = p?.plugin?.name
      if (!name) continue
      if (!byPlugin.has(name)) byPlugin.set(name, [])
      byPlugin.get(name)!.push(p)
    }

    const plugins: PluginGroup[] = []
    for (const [name, list] of byPlugin.entries()) {
      const first = list[0]
      const displayName = first?.plugin?.display_name || name
      const reserved = Boolean(first?.plugin?.reserved)
      const activated = Boolean(first?.plugin?.activated)
      let conflictCount = 0
      let warnCount = 0
      let errorCount = 0
      for (const p of list) {
        if (isParticipantConflicting(stageId, p)) conflictCount += 1
        const rl = riskLevelForParticipant(p)
        if (rl === 'error') errorCount += 1
        else if (rl === 'warn') warnCount += 1
      }
      plugins.push({
        name,
        displayName,
        reserved,
        activated,
        participants: list,
        conflictCount,
        warnCount,
        errorCount
      })
    }

    plugins.sort((a, b) => a.displayName.localeCompare(b.displayName) || a.name.localeCompare(b.name))
    nodes.push({
      stageId,
      title: stageTitle(stageId),
      description: stageDescription(stageId),
      participantCount: stageParticipantCount(stageId),
      conflictCount: stageConflictBadge(stageId),
      riskCount: stageRiskCount(stageId),
      effectBadge: props.stageBadges?.[stageId],
      plugins
    })
  }
  return nodes
})

watch(
  () => props.snapshot?.snapshot_id,
  () => {
    for (const stage of stageNodes.value) {
      for (const p of stage.plugins) {
        const key = pluginKeyOf(stage.stageId, p.name)
        if (pluginOpen[key] == null) pluginOpen[key] = false
      }
    }
  },
  { immediate: true }
)

const openPluginForParticipant = (participantId: string | null | undefined) => {
  if (!participantId) return
  const snapshot = props.snapshot
  if (!snapshot) return

  for (const st of snapshot.stages ?? []) {
    const stageId = st?.stage?.id as PipelineStageId | undefined
    if (!stageId) continue
    for (const p of st.participants ?? []) {
      if (p?.id !== participantId) continue
      const pluginName = p?.plugin?.name
      if (!pluginName) return
      pluginOpen[pluginKeyOf(stageId, pluginName)] = true
      return
    }
  }
}

watch(
  () => props.selectedParticipantId,
  (id) => openPluginForParticipant(id),
  { immediate: true }
)
</script>

<template>
  <div class="pfv">
    <div class="pfv__scroll">
      <div class="pfv__canvas" :style="{ transform: `scale(${zoomValue})` }">
        <div v-if="snapshot" class="pfv__rail">
          <div
            v-for="stage in stageNodes"
            :key="stage.stageId"
            class="pfv__node"
            :class="{ 'pfv__node--selected': selectedStageId === stage.stageId }"
          >
            <button
              type="button"
              class="pfv__stage"
              :class="{
                'pfv__stage--selected': selectedStageId === stage.stageId,
                'pfv__stage--conflict': stageHasConflicts(stage.stageId)
              }"
              @click="handleSelectStage(stage.stageId)"
            >
              <div class="pfv__stage-title">
                <div class="pfv__stage-name">{{ stage.title }}</div>
                <v-tooltip v-if="stage.description" activator="parent" location="top">
                  {{ stage.description }}
                </v-tooltip>
              </div>
              <div class="pfv__stage-badges">
                <v-chip
                  v-if="stage.effectBadge?.total"
                  size="x-small"
                  color="info"
                  variant="tonal"
                  class="pfv__badge"
                >
                  E{{ stage.effectBadge.total }}
                </v-chip>
                <v-chip
                  v-if="stage.effectBadge?.high"
                  size="x-small"
                  color="warning"
                  variant="tonal"
                  class="pfv__badge"
                >
                  H{{ stage.effectBadge.high }}
                </v-chip>

                <v-chip
                  v-if="stage.participantCount > 0"
                  size="x-small"
                  color="secondary"
                  variant="tonal"
                  class="pfv__badge"
                >
                  {{ stage.participantCount }}
                </v-chip>
                <v-chip
                  v-if="stage.conflictCount > 0"
                  size="x-small"
                  color="error"
                  variant="tonal"
                  class="pfv__badge"
                >
                  {{ stage.conflictCount }}
                </v-chip>
                <v-icon v-if="stage.riskCount > 0" size="16" color="warning">mdi-alert-outline</v-icon>
              </div>
            </button>

            <div class="pfv__plugins">
              <div
                v-for="pl in stage.plugins"
                :key="stage.stageId + ':' + pl.name"
                class="pfv__plugin"
                :class="{ 'pfv__plugin--reserved': pl.reserved }"
              >
                <div class="pfv__plugin-head" @click="togglePlugin(stage.stageId, pl.name)">
                  <div class="pfv__plugin-title">
                    <div class="pfv__plugin-name">{{ pl.displayName }}</div>
                    <div class="pfv__plugin-sub text-caption text-medium-emphasis">{{ pl.name }}</div>
                  </div>
                  <div class="pfv__plugin-badges">
                    <v-chip size="x-small" color="secondary" variant="tonal" class="pfv__badge">
                      {{ pl.participants.length }}
                    </v-chip>
                    <v-chip
                      v-if="pl.conflictCount > 0"
                      size="x-small"
                      color="error"
                      variant="tonal"
                      class="pfv__badge"
                    >
                      {{ pl.conflictCount }}
                    </v-chip>
                    <v-icon v-if="pl.warnCount + pl.errorCount > 0" size="16" color="warning">
                      mdi-alert-outline
                    </v-icon>
                    <v-icon size="18" class="pfv__chev">
                      {{ isPluginOpen(stage.stageId, pl.name) ? 'mdi-chevron-up' : 'mdi-chevron-down' }}
                    </v-icon>
                  </div>
                </div>

                <div v-if="isPluginOpen(stage.stageId, pl.name)" class="pfv__methods">
                  <button
                    v-for="p in pl.participants"
                    :key="p.id"
                    type="button"
                    class="pfv__method"
                    :class="{
                      'pfv__method--selected': props.selectedParticipantId === p.id,
                      'pfv__method--conflict': isParticipantConflicting(stage.stageId, p),
                      'pfv__method--warn': riskLevelForParticipant(p) === 'warn',
                      'pfv__method--error': riskLevelForParticipant(p) === 'error'
                    }"
                    @click="handleSelectParticipant(p.id); handleSelectStage(stage.stageId)"
                  >
                    <span class="pfv__method-priority">P{{ p.meta?.priority ?? 0 }}</span>
                    <span class="pfv__method-name">{{ participantLabel(p) }}</span>
                    <span class="pfv__method-event">{{ eventTypeLabel(p.meta?.event_type) }}</span>
                    <span v-if="p.meta?.enabled === false" class="pfv__method-muted">OFF</span>
                  </button>
                </div>
              </div>

              <div v-if="stage.plugins.length === 0" class="pfv__empty text-caption text-medium-emphasis">
                {{ tm('pipeline.fishbone.noParticipants') }}
              </div>
            </div>
          </div>
        </div>

        <div v-else class="pfv__placeholder text-caption text-medium-emphasis">
          {{ tm('pipeline.fishbone.noSnapshot') }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pfv { display:flex; flex-direction:column; min-height:0; width:100%; min-width:0; }
.pfv__scroll { flex:1 1 auto; min-height:0; overflow-x:auto; overflow-y:auto; padding:8px 6px; }
.pfv__canvas { transform-origin:top left; }
.pfv__rail { display:flex; align-items:flex-start; gap:16px; padding-right:24px; }
.pfv__node { position:relative; flex:0 0 310px; max-width:310px; }
.pfv__node:not(:last-child)::after { content:''; position:absolute; top:18px; right:-16px; width:28px; height:2px; background:rgba(var(--v-theme-on-surface),0.18); }
.pfv__node:not(:last-child)::before { content:''; position:absolute; top:14px; right:-18px; width:0; height:0; border-left:6px solid rgba(var(--v-theme-on-surface),0.28); border-top:5px solid transparent; border-bottom:5px solid transparent; }
.pfv__stage { width:100%; border-radius:14px; border:1px solid rgba(var(--v-theme-on-surface),0.12); background:rgba(var(--v-theme-surface),0.9); box-shadow:0 6px 16px rgba(0,0,0,0.06); padding:10px 12px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; cursor:pointer; user-select:none; text-align:left; }
.pfv__stage--selected { border-color:rgba(var(--v-theme-primary),0.55); box-shadow:0 0 0 2px rgba(var(--v-theme-primary),0.12); }
.pfv__stage--conflict { border-color:rgba(var(--v-theme-error),0.55); box-shadow:0 0 0 2px rgba(var(--v-theme-error),0.1); }
.pfv__stage-title { min-width:0; flex:1 1 auto; }
.pfv__stage-name { font-weight:900; font-size:13px; line-height:1.2; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pfv__stage-badges { display:flex; align-items:center; gap:6px; flex:0 0 auto; }
.pfv__plugins { margin-top:10px; display:grid; gap:10px; }
.pfv__plugin { border-radius:14px; overflow:hidden; border:1px solid rgba(var(--v-theme-on-surface),0.12); background:rgba(var(--v-theme-surface),0.85); }
.pfv__plugin--reserved { border-color:rgba(var(--v-theme-on-surface),0.18); }
.pfv__plugin-head { padding:10px 12px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; cursor:pointer; user-select:none; background:rgba(var(--v-theme-surface-variant),0.16); }
.pfv__plugin-title { display:flex; flex-direction:column; flex:1 1 auto; min-width:0; }
.pfv__plugin-name { font-weight:800; font-size:13px; line-height:1.2; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pfv__plugin-badges { display:flex; align-items:center; gap:6px; flex:0 0 auto; }
.pfv__badge { font-weight:900; min-width:26px; justify-content:center; }
.pfv__chev { color:rgba(var(--v-theme-on-surface),0.6); }
.pfv__methods { padding:10px 12px 12px; display:grid; gap:6px; }
.pfv__method { width:100%; border-radius:12px; border:1px solid rgba(var(--v-theme-on-surface),0.14); background:rgba(var(--v-theme-surface),0.95); padding:8px 10px; display:grid; grid-template-columns:auto 1fr auto auto; align-items:center; gap:8px; cursor:pointer; text-align:left; }
.pfv__method:hover { border-color:rgba(var(--v-theme-primary),0.45); background:rgba(var(--v-theme-primary),0.06); }
.pfv__method--selected { border-color:rgba(var(--v-theme-primary),0.75); box-shadow:0 0 0 2px rgba(var(--v-theme-primary),0.12); background:rgba(var(--v-theme-primary),0.06); }
.pfv__method-priority { font-size:11px; font-weight:900; color:rgba(var(--v-theme-on-surface),0.7); }
.pfv__method-name { font-size:12px; font-weight:800; color:rgba(var(--v-theme-on-surface),0.9); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pfv__method-event { font-size:11px; font-weight:800; color:rgba(var(--v-theme-on-surface),0.6); white-space:nowrap; }
.pfv__method-muted { font-size:10px; font-weight:900; color:rgba(var(--v-theme-on-surface),0.55); white-space:nowrap; }
.pfv__method--conflict { border-color:rgba(var(--v-theme-error),0.6); background:rgba(var(--v-theme-error),0.06); }
.pfv__method--warn { border-color:rgba(var(--v-theme-warning),0.55); }
.pfv__method--error { border-color:rgba(var(--v-theme-error),0.7); }
.pfv__empty { padding:6px 2px 0; }
.pfv__placeholder { padding:10px 6px; }
</style>