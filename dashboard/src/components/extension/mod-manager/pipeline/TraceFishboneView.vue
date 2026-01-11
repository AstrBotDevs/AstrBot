<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { EffectTarget, PipelineStageId } from './pipelineSnapshotTypes'
import type { LeafGroup, RootGroup, TraceRow } from './traceGrouping'
import { impactRank, isHighImpact } from './traceGrouping'

const props = withDefaults(
  defineProps<{
    groups: RootGroup[]
    activeStageId?: PipelineStageId | null
    activeTarget?: EffectTarget | null
    activeImpactKey?: string | null
    showHighOnly?: boolean
  }>(),
  {
    activeStageId: null,
    activeTarget: null,
    activeImpactKey: null,
    showHighOnly: false
  }
)

const emit = defineEmits<{
  (e: 'select-target', target: EffectTarget): void
  (e: 'select-stage', stageId: PipelineStageId): void
  (e: 'select-impact', impactKey: string): void
}>()

type StageOpenMap = Record<string, boolean>

const open = reactive<{
  openImpactsByTarget: Record<string, StageOpenMap>
}>({
  openImpactsByTarget: {}
})

const targetFromRoot = (g: RootGroup): EffectTarget => g.key as EffectTarget

const stageIdFromLeaf = (g: LeafGroup): PipelineStageId | null => {
  const raw = g.subtitle
  if (!raw) return null
  return raw as PipelineStageId
}

const stageKeyFromLeaf = (leaf: LeafGroup) => String(stageIdFromLeaf(leaf) || leaf.key)

const ensureStageMap = (targetKey: string) => {
  if (!open.openImpactsByTarget[targetKey]) open.openImpactsByTarget[targetKey] = {}
  return open.openImpactsByTarget[targetKey]
}

const rootCount = (g: RootGroup) => g.groups.reduce((acc, gg) => acc + gg.rows.length, 0)
const leafHighCount = (g: LeafGroup) => g.rows.reduce((acc, r) => acc + (isHighImpact(r.effect) ? 1 : 0), 0)
const rootHighCount = (g: RootGroup) => g.groups.reduce((acc, gg) => acc + leafHighCount(gg), 0)

const isRootActive = (g: RootGroup) => {
  const t = targetFromRoot(g)
  return Boolean(props.activeTarget && String(props.activeTarget) === String(t))
}

const isStageActive = (root: RootGroup, leaf: LeafGroup) => {
  const t = targetFromRoot(root)
  const stageId = stageIdFromLeaf(leaf)
  return Boolean(props.activeTarget && String(props.activeTarget) === String(t) && stageId && props.activeStageId === stageId)
}

const isImpactActive = (row: TraceRow) => Boolean(props.activeImpactKey && String(props.activeImpactKey) === String(row.key))

const isImpactListOpen = (root: RootGroup, leaf: LeafGroup) => {
  const t = String(targetFromRoot(root))
  const map = ensureStageMap(t)
  const stageKey = stageKeyFromLeaf(leaf)
  return Boolean(map[stageKey])
}

const ensureImpactListOpen = (root: RootGroup, leaf: LeafGroup) => {
  const t = String(targetFromRoot(root))
  const map = ensureStageMap(t)
  map[stageKeyFromLeaf(leaf)] = true
}

const toggleImpactList = (root: RootGroup, leaf: LeafGroup) => {
  const t = String(targetFromRoot(root))
  const map = ensureStageMap(t)
  const stageKey = stageKeyFromLeaf(leaf)
  map[stageKey] = !Boolean(map[stageKey])
}

const impactLabel = (r: TraceRow) => {
  const target = String(r.effect?.target || '')
  const op = String(r.effect?.op || '')
  if (target === 'stop') return 'STOP'
  if (target === 'send') return 'SEND'
  if (op === 'clear') return 'CLEAR'
  if (op === 'overwrite') return 'OVERWRITE'
  if (op === 'mutate_list') return 'MUTATE'
  if (op === 'append') return 'APPEND'
  if (op === 'call') return 'CALL'
  return op || '—'
}

const impactColor = (r: TraceRow) => {
  const rank = impactRank(r.effect)
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

const compactImpactTitle = (r: TraceRow) => {
  const plugin = r.participant?.plugin?.display_name || r.participant?.plugin?.name || '—'
  const handler = r.participant?.handler?.handler_name || r.participant?.handler?.handler_full_name || '—'
  return `${plugin} · ${handler}`
}

const visibleImpactRows = (leaf: LeafGroup) => {
  if (!props.showHighOnly) return leaf.rows
  return leaf.rows.filter((r) => isHighImpact(r.effect))
}

const handleClickRoot = (g: RootGroup) => {
  const target = targetFromRoot(g)
  emit('select-target', target)
}

const handleClickStage = (root: RootGroup, leaf: LeafGroup) => {
  const target = targetFromRoot(root)
  const stageId = stageIdFromLeaf(leaf)
  toggleImpactList(root, leaf)
  emit('select-target', target)
  if (stageId) emit('select-stage', stageId)
}

const handleClickImpact = (root: RootGroup, leaf: LeafGroup, row: TraceRow) => {
  const target = targetFromRoot(root)
  const stageId = stageIdFromLeaf(leaf)
  ensureImpactListOpen(root, leaf)
  emit('select-target', target)
  if (stageId) emit('select-stage', stageId)
  emit('select-impact', row.key)
}

const findLeafByImpactKey = (impactKey: string) => {
  for (const root of props.groups) {
    for (const leaf of root.groups ?? []) {
      if ((leaf.rows ?? []).some((r) => String(r.key) === String(impactKey))) {
        return { root, leaf }
      }
    }
  }
  return null
}

watch(
  () => props.activeImpactKey,
  (impactKey) => {
    if (!impactKey) return
    const found = findLeafByImpactKey(String(impactKey))
    if (!found) return
    ensureImpactListOpen(found.root, found.leaf)
  },
  { immediate: true }
)
</script>

<template>
  <div class="tfv">
    <div class="tfv__toolbar px-2 py-2 d-flex align-center flex-wrap ga-2">
      <v-chip v-if="showHighOnly" size="x-small" color="warning" variant="tonal" class="font-weight-bold">
        仅高影响
      </v-chip>

      <v-spacer />

      <v-chip size="x-small" color="secondary" variant="tonal" class="font-weight-bold">
        {{ groups.reduce((acc, g) => acc + rootCount(g), 0) }} 条
      </v-chip>
    </div>

    <div class="tfv__scroll">
      <div class="tfv__rail">
        <div
          v-for="g in groups"
          :key="g.key"
          class="tfv__node"
          :class="{ 'tfv__node--active': isRootActive(g) }"
        >
          <button type="button" class="tfv__head" :class="{ 'tfv__head--active': isRootActive(g) }" @click="handleClickRoot(g)">
            <div class="tfv__title">
              <div class="tfv__name">{{ g.title }}</div>
              <div v-if="g.subtitle" class="tfv__sub">{{ g.subtitle }}</div>
            </div>

            <div class="tfv__badges">
              <v-chip v-if="rootCount(g) > 0" size="x-small" color="info" variant="tonal" class="tfv__badge">
                E{{ rootCount(g) }}
              </v-chip>
              <v-chip v-if="rootHighCount(g) > 0" size="x-small" color="warning" variant="tonal" class="tfv__badge">
                H{{ rootHighCount(g) }}
              </v-chip>
            </div>
          </button>

          <div class="tfv__children">
            <div v-for="leaf in g.groups" :key="leaf.key" class="tfv__stage-block">
              <button
                type="button"
                class="tfv__child"
                :class="{ 'tfv__child--active': isStageActive(g, leaf) }"
                @click="handleClickStage(g, leaf)"
              >
                <span class="tfv__child-title">{{ leaf.title }}</span>

                <span class="tfv__child-badges">
                  <v-chip size="x-small" color="secondary" variant="tonal" class="tfv__badge">
                    {{ visibleImpactRows(leaf).length }}
                  </v-chip>
                  <v-chip v-if="leafHighCount(leaf) > 0" size="x-small" color="warning" variant="tonal" class="tfv__badge">
                    {{ leafHighCount(leaf) }}
                  </v-chip>
                  <v-chip v-if="leaf.subtitle" size="x-small" color="secondary" variant="tonal" class="tfv__badge">
                    {{ leaf.subtitle }}
                  </v-chip>
                  <v-icon size="18" class="tfv__chev">
                    {{ isImpactListOpen(g, leaf) ? 'mdi-chevron-up' : 'mdi-chevron-down' }}
                  </v-icon>
                </span>
              </button>

              <div v-if="isImpactListOpen(g, leaf)" class="tfv__impacts">
                <button
                  v-for="r in visibleImpactRows(leaf)"
                  :key="r.key"
                  type="button"
                  class="tfv__impact"
                  :class="{ 'tfv__impact--active': isImpactActive(r) }"
                  @click="handleClickImpact(g, leaf, r)"
                >
                  <div class="tfv__impact-main">
                    <div class="tfv__impact-title">{{ compactImpactTitle(r) }}</div>
                    <div class="tfv__impact-sub text-caption text-medium-emphasis">
                      <span class="tfv__mono">target={{ String(r.effect.target || '—') }}</span>
                      <span class="tfv__sep">·</span>
                      <span class="tfv__mono">op={{ String(r.effect.op || '—') }}</span>
                    </div>
                  </div>

                  <div class="tfv__impact-badges">
                    <v-chip size="x-small" :color="impactColor(r)" variant="tonal" class="tfv__badge">
                      {{ impactLabel(r) }}
                    </v-chip>
                    <v-chip size="x-small" color="info" variant="tonal" class="tfv__badge">
                      {{ confidenceLabel(r.effect.confidence) }}
                    </v-chip>
                  </div>
                </button>

                <div v-if="visibleImpactRows(leaf).length === 0" class="tfv__empty text-caption text-medium-emphasis">
                  无影响点
                </div>
              </div>
            </div>

            <div v-if="g.groups.length === 0" class="tfv__empty text-caption text-medium-emphasis">
              无分组
            </div>
          </div>
        </div>

        <div v-if="groups.length === 0" class="tfv__placeholder text-caption text-medium-emphasis">
          暂无可追踪影响（effects）
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tfv { display:flex; flex-direction:column; min-height:0; width:100%; min-width:0; }
.tfv__toolbar { background: rgba(var(--v-theme-surface), 0.6); border-radius: 12px; }
.tfv__scroll { flex:1 1 auto; min-height:0; overflow-x:auto; overflow-y:auto; padding:8px 6px; }
.tfv__rail { display:flex; align-items:flex-start; gap:16px; padding-right:24px; min-height: 100%; }
.tfv__node { position:relative; flex:0 0 380px; max-width:380px; }
.tfv__node:not(:last-child)::after { content:''; position:absolute; top:18px; right:-16px; width:28px; height:2px; background:rgba(var(--v-theme-on-surface),0.18); }
.tfv__node:not(:last-child)::before { content:''; position:absolute; top:14px; right:-18px; width:0; height:0; border-left:6px solid rgba(var(--v-theme-on-surface),0.28); border-top:5px solid transparent; border-bottom:5px solid transparent; }

.tfv__head { width:100%; border-radius:14px; border:1px solid rgba(var(--v-theme-on-surface),0.12); background:rgba(var(--v-theme-surface),0.9); box-shadow:0 6px 16px rgba(0,0,0,0.06); padding:10px 12px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; cursor:pointer; user-select:none; text-align:left; }
.tfv__head--active { border-color:rgba(var(--v-theme-primary),0.65); box-shadow:0 0 0 2px rgba(var(--v-theme-primary),0.12); }
.tfv__title { min-width:0; flex:1 1 auto; }
.tfv__name { font-weight:900; font-size:13px; line-height:1.2; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tfv__sub { margin-top:2px; font-size:11px; font-weight:800; color: rgba(var(--v-theme-on-surface), 0.6); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tfv__badges { display:flex; align-items:center; gap:6px; flex:0 0 auto; }
.tfv__badge { font-weight:900; min-width:26px; justify-content:center; }
.tfv__chev { color:rgba(var(--v-theme-on-surface),0.6); }

.tfv__children { margin-top:10px; display:grid; gap:10px; }
.tfv__stage-block { display:grid; gap:8px; }

.tfv__child { width:100%; border-radius:12px; border:1px solid rgba(var(--v-theme-on-surface),0.14); background:rgba(var(--v-theme-surface),0.95); padding:8px 10px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; cursor:pointer; text-align:left; }
.tfv__child:hover { border-color:rgba(var(--v-theme-primary),0.45); background:rgba(var(--v-theme-primary),0.06); }
.tfv__child--active { border-color:rgba(var(--v-theme-primary),0.75); box-shadow:0 0 0 2px rgba(var(--v-theme-primary),0.12); background:rgba(var(--v-theme-primary),0.06); }
.tfv__child-title { font-size:12px; font-weight:800; color:rgba(var(--v-theme-on-surface),0.9); min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tfv__child-badges { display:flex; align-items:center; gap:6px; flex-wrap:wrap; justify-content:flex-end; }

.tfv__impacts { display:grid; gap:6px; padding-left:10px; border-left:2px solid rgba(var(--v-theme-on-surface), 0.08); margin-left:6px; }
.tfv__impact { width:100%; border-radius:12px; border:1px solid rgba(var(--v-theme-on-surface),0.14); background:rgba(var(--v-theme-surface),0.92); padding:8px 10px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; cursor:pointer; text-align:left; }
.tfv__impact:hover { border-color:rgba(var(--v-theme-primary),0.45); background:rgba(var(--v-theme-primary),0.06); }
.tfv__impact--active { border-color:rgba(var(--v-theme-primary),0.75); box-shadow:0 0 0 2px rgba(var(--v-theme-primary),0.12); background:rgba(var(--v-theme-primary),0.06); }
.tfv__impact-main { min-width:0; flex:1 1 auto; }
.tfv__impact-title { font-size:12px; font-weight:800; color:rgba(var(--v-theme-on-surface),0.9); min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tfv__impact-badges { display:flex; align-items:center; gap:6px; flex:0 0 auto; flex-wrap:wrap; justify-content:flex-end; }
.tfv__impact-sub { margin-top:2px; }
.tfv__mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; }
.tfv__sep { opacity: 0.6; padding: 0 2px; }

.tfv__empty { padding:6px 2px 0; }
.tfv__placeholder { padding:10px 6px; }
</style>