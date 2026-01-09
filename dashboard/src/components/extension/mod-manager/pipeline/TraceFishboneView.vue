<script setup lang="ts">
import type { EffectTarget, PipelineStageId } from './pipelineSnapshotTypes'
import type { LeafGroup, RootGroup } from './traceGrouping'
import { isHighImpact } from './traceGrouping'

const props = withDefaults(
  defineProps<{
    groups: RootGroup[]
    activeStageId?: PipelineStageId | null
    activeTarget?: EffectTarget | null
    showHighOnly?: boolean
  }>(),
  {
    activeStageId: null,
    activeTarget: null,
    showHighOnly: false
  }
)

const emit = defineEmits<{
  (e: 'select-stage', stageId: PipelineStageId): void
  (e: 'select-target', target: EffectTarget): void
  (e: 'focus-group', groupKey: string): void
}>()

const rootCount = (g: RootGroup) => g.groups.reduce((acc, gg) => acc + gg.rows.length, 0)
const rootHighCount = (g: RootGroup) => g.groups.reduce((acc, gg) => acc + leafHighCount(gg), 0)

const leafHighCount = (g: LeafGroup) => g.rows.reduce((acc, r) => acc + (isHighImpact(r.effect) ? 1 : 0), 0)

const stageIdFromLeaf = (g: LeafGroup): PipelineStageId | null => {
  const raw = g.subtitle
  if (!raw) return null
  return raw as PipelineStageId
}

const targetFromRoot = (g: RootGroup): EffectTarget => g.key as EffectTarget

const isRootActive = (g: RootGroup) => {
  const t = targetFromRoot(g)
  return Boolean(props.activeTarget && String(props.activeTarget) === String(t))
}

const isLeafActive = (root: RootGroup, leaf: LeafGroup) => {
  const t = targetFromRoot(root)
  const stageId = stageIdFromLeaf(leaf)
  return Boolean(props.activeTarget && String(props.activeTarget) === String(t) && stageId && props.activeStageId === stageId)
}

const handleClickRoot = (g: RootGroup) => {
  const target = targetFromRoot(g)
  emit('select-target', target)
  emit('focus-group', String(g.key))
}

const handleClickLeaf = (root: RootGroup, leaf: LeafGroup) => {
  const target = targetFromRoot(root)
  const stageId = stageIdFromLeaf(leaf)
  if (stageId) emit('select-stage', stageId)
  emit('select-target', target)
  emit('focus-group', String(leaf.key))
}
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
              <div class="tfv__name">
                {{ g.title }}
              </div>
              <div v-if="g.subtitle" class="tfv__sub">
                {{ g.subtitle }}
              </div>
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
            <button
              v-for="leaf in g.groups"
              :key="leaf.key"
              type="button"
              class="tfv__child"
              :class="{ 'tfv__child--active': isLeafActive(g, leaf) }"
              @click="handleClickLeaf(g, leaf)"
            >
              <span class="tfv__child-title">{{ leaf.title }}</span>

              <span class="tfv__child-badges">
                <v-chip size="x-small" color="secondary" variant="tonal" class="tfv__badge">
                  {{ leaf.rows.length }}
                </v-chip>
                <v-chip v-if="leafHighCount(leaf) > 0" size="x-small" color="warning" variant="tonal" class="tfv__badge">
                  {{ leafHighCount(leaf) }}
                </v-chip>
                <v-chip v-if="leaf.subtitle" size="x-small" color="secondary" variant="tonal" class="tfv__badge">
                  {{ leaf.subtitle }}
                </v-chip>
              </span>
            </button>

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
.tfv__node { position:relative; flex:0 0 330px; max-width:330px; }
.tfv__node:not(:last-child)::after { content:''; position:absolute; top:18px; right:-16px; width:28px; height:2px; background:rgba(var(--v-theme-on-surface),0.18); }
.tfv__node:not(:last-child)::before { content:''; position:absolute; top:14px; right:-18px; width:0; height:0; border-left:6px solid rgba(var(--v-theme-on-surface),0.28); border-top:5px solid transparent; border-bottom:5px solid transparent; }
.tfv__head { width:100%; border-radius:14px; border:1px solid rgba(var(--v-theme-on-surface),0.12); background:rgba(var(--v-theme-surface),0.9); box-shadow:0 6px 16px rgba(0,0,0,0.06); padding:10px 12px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; cursor:pointer; user-select:none; text-align:left; }
.tfv__head--active { border-color:rgba(var(--v-theme-primary),0.65); box-shadow:0 0 0 2px rgba(var(--v-theme-primary),0.12); }
.tfv__title { min-width:0; flex:1 1 auto; }
.tfv__name { font-weight:900; font-size:13px; line-height:1.2; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tfv__sub { margin-top:2px; font-size:11px; font-weight:800; color: rgba(var(--v-theme-on-surface), 0.6); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tfv__badges { display:flex; align-items:center; gap:6px; flex:0 0 auto; }
.tfv__badge { font-weight:900; min-width:26px; justify-content:center; }
.tfv__children { margin-top:10px; display:grid; gap:8px; }
.tfv__child { width:100%; border-radius:12px; border:1px solid rgba(var(--v-theme-on-surface),0.14); background:rgba(var(--v-theme-surface),0.95); padding:8px 10px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; cursor:pointer; text-align:left; }
.tfv__child:hover { border-color:rgba(var(--v-theme-primary),0.45); background:rgba(var(--v-theme-primary),0.06); }
.tfv__child--active { border-color:rgba(var(--v-theme-primary),0.75); box-shadow:0 0 0 2px rgba(var(--v-theme-primary),0.12); background:rgba(var(--v-theme-primary),0.06); }
.tfv__child-title { font-size:12px; font-weight:800; color:rgba(var(--v-theme-on-surface),0.9); min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tfv__child-badges { display:flex; align-items:center; gap:6px; flex-wrap:wrap; justify-content:flex-end; }
.tfv__empty { padding:6px 2px 0; }
.tfv__placeholder { padding:10px 6px; }
</style>