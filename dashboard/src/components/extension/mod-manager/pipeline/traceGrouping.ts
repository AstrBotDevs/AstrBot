import type { Effect, EffectTarget, PipelineSnapshot, PipelineStageId, StageParticipant } from './pipelineSnapshotTypes'

export type AggregateMode = 'byStage' | 'byTarget'

export type TraceRow = {
  key: string
  stageId: PipelineStageId
  stageTitle: string
  participantId: string
  participant: StageParticipant
  effect: Effect
}

export type LeafGroup = {
  key: string
  title: string
  subtitle?: string
  rows: TraceRow[]
}

export type RootGroup = {
  key: string
  title: string
  subtitle?: string
  groups: LeafGroup[]
}

export const KNOWN_TARGETS: EffectTarget[] = [
  'provider_request.prompt',
  'provider_request.system_prompt',
  'provider_request.persona_prompt',
  'provider_request.contexts',
  'provider_request.extra_user_content_parts',
  'provider_request.func_tool',
  'llm_response.completion_text',
  'llm_response.result_chain',
  'llm_response.tools_call_name',
  'llm_response.tools_call_args',
  'result.chain',
  'event.message_str',
  'send',
  'stop'
]

export const impactRank = (e: Effect): 0 | 1 | 2 => {
  const target = String(e?.target || '')
  const op = String(e?.op || '')
  if (target === 'stop' || target === 'send') return 2
  if (op === 'clear' || op === 'overwrite') return 2
  if (op === 'mutate_list') return 1
  return 0
}

export const isHighImpact = (e: Effect) => impactRank(e) >= 1

export type TraceFilter = {
  selectedTarget: '__all__' | EffectTarget
  onlyHighImpact: boolean
}

export const buildTraceRows = (snapshot: PipelineSnapshot | null): TraceRow[] => {
  const s = snapshot
  if (!s) return []

  const out: TraceRow[] = []
  const stages = s.stages ?? []
  for (const st of stages) {
    const stageId = st?.stage?.id as PipelineStageId | undefined
    if (!stageId) continue
    const stageTitle = st.stage?.title || stageId
    for (const p of st.participants ?? []) {
      const participantId = p?.id
      if (!participantId) continue
      const effects = (p.effects ?? []).filter(Boolean)
      for (const eff of effects) {
        const target = (eff as any)?.target
        const op = (eff as any)?.op
        const confidence = (eff as any)?.confidence
        if (!target || !op) continue
        const effect: Effect = {
          target,
          op,
          confidence: confidence || 'unknown',
          evidence: (eff as any)?.evidence,
          lineno: (eff as any)?.lineno,
          col: (eff as any)?.col
        }
        out.push({
          key: `${stageId}:${participantId}:${String(effect.target)}:${String(effect.op)}:${String(effect.evidence || '')}:${String(
            effect.lineno ?? ''
          )}:${String(effect.col ?? '')}`,
          stageId,
          stageTitle,
          participantId,
          participant: p,
          effect
        })
      }
    }
  }

  out.sort((a, b) => {
    if (a.stageId !== b.stageId) return String(a.stageId).localeCompare(String(b.stageId))
    const ta = String(a.effect.target || '')
    const tb = String(b.effect.target || '')
    const t = ta.localeCompare(tb)
    if (t !== 0) return t
    const pa = a.participant?.meta?.priority ?? 0
    const pb = b.participant?.meta?.priority ?? 0
    if (pa !== pb) return pb - pa
    const ha = a.participant?.handler?.handler_full_name ?? ''
    const hb = b.participant?.handler?.handler_full_name ?? ''
    return ha.localeCompare(hb)
  })

  return out
}

export const buildAvailableTargets = (rows: TraceRow[]): EffectTarget[] => {
  const set = new Set<string>()
  for (const t of KNOWN_TARGETS) set.add(String(t))

  for (const r of rows) {
    const target = String(r.effect?.target || '')
    if (target) set.add(target)
  }

  const list = [...set.values()]
  list.sort((a, b) => {
    const ia = KNOWN_TARGETS.indexOf(a as any)
    const ib = KNOWN_TARGETS.indexOf(b as any)
    if (ia !== -1 || ib !== -1) {
      if (ia === -1) return 1
      if (ib === -1) return -1
      return ia - ib
    }
    return a.localeCompare(b)
  })
  return list as EffectTarget[]
}

export const applyTraceFilter = (rows: TraceRow[], filter: TraceFilter): TraceRow[] => {
  let list = rows

  if (filter.selectedTarget !== '__all__') {
    const selected = String(filter.selectedTarget)
    list = list.filter((r) => String(r.effect?.target || '') === selected)
  }

  if (filter.onlyHighImpact) {
    list = list.filter((r) => isHighImpact(r.effect))
  }

  return list
}

const sortTargets = (targets: string[]) => {
  targets.sort((a, b) => {
    const ia = KNOWN_TARGETS.indexOf(a as any)
    const ib = KNOWN_TARGETS.indexOf(b as any)
    if (ia !== -1 || ib !== -1) {
      if (ia === -1) return 1
      if (ib === -1) return -1
      return ia - ib
    }
    return a.localeCompare(b)
  })
}

export const groupTraceRowsByStage = (snapshot: PipelineSnapshot | null, rows: TraceRow[]): RootGroup[] => {
  const stageOrder = snapshot?.stages?.map((s) => s?.stage?.id as PipelineStageId | undefined).filter(Boolean) ?? []

  const stageMap = new Map<PipelineStageId, { title: string; byTarget: Map<string, TraceRow[]> }>()
  for (const r of rows) {
    const stageId = r.stageId
    const entry = stageMap.get(stageId) ?? { title: r.stageTitle, byTarget: new Map() }
    const target = String(r.effect.target || '')
    const list = entry.byTarget.get(target) ?? []
    list.push(r)
    entry.byTarget.set(target, list)
    stageMap.set(stageId, entry)
  }

  const roots: RootGroup[] = []
  for (const stageId of stageOrder) {
    if (!stageId) continue
    const entry = stageMap.get(stageId)
    if (!entry) continue

    const groups: LeafGroup[] = []
    const targets = [...entry.byTarget.keys()]
    sortTargets(targets)
    for (const t of targets) {
      const list = entry.byTarget.get(t) ?? []
      groups.push({
        key: `${stageId}:${t}`,
        title: t,
        rows: list
      })
    }

    roots.push({
      key: String(stageId),
      title: entry.title || String(stageId),
      subtitle: String(stageId),
      groups
    })
  }

  return roots
}

export const groupTraceRowsByTarget = (snapshot: PipelineSnapshot | null, rows: TraceRow[]): RootGroup[] => {
  const stageTitleById = new Map<PipelineStageId, string>()
  const stageOrder =
    snapshot?.stages
      ?.map((s) => s?.stage?.id as PipelineStageId | undefined)
      .filter((id): id is PipelineStageId => Boolean(id)) ?? []
  const stageIndex = new Map<PipelineStageId, number>()
  stageOrder.forEach((id, idx) => stageIndex.set(id, idx))

  for (const st of snapshot?.stages ?? []) {
    const stageId = st?.stage?.id as PipelineStageId | undefined
    if (!stageId) continue
    stageTitleById.set(stageId, st.stage?.title || stageId)
  }

  const byTarget = new Map<string, Map<PipelineStageId, TraceRow[]>>()
  for (const r of rows) {
    const target = String(r.effect.target || '')
    const byStage = byTarget.get(target) ?? new Map()
    const list = byStage.get(r.stageId) ?? []
    list.push(r)
    byStage.set(r.stageId, list)
    byTarget.set(target, byStage)
  }

  const targets = [...byTarget.keys()]
  sortTargets(targets)

  const roots: RootGroup[] = []
  for (const t of targets) {
    const byStage = byTarget.get(t)
    if (!byStage) continue

    const stageIds = [...byStage.keys()]
    stageIds.sort((a, b) => {
      const ia = stageIndex.get(a)
      const ib = stageIndex.get(b)
      if (ia !== undefined || ib !== undefined) {
        if (ia === undefined) return 1
        if (ib === undefined) return -1
        return ia - ib
      }
      return String(a).localeCompare(String(b))
    })

    const groups: LeafGroup[] = stageIds.map((sid) => ({
      key: `${t}:${sid}`,
      title: stageTitleById.get(sid) || String(sid),
      subtitle: String(sid),
      rows: byStage.get(sid) ?? []
    }))

    roots.push({
      key: t,
      title: t,
      groups
    })
  }

  return roots
}