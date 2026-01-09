import type { Effect, EffectTarget, PipelineStageId, PluginEventType, StageParticipant } from './pipelineSnapshotTypes'

type InferInput = {
  participant: StageParticipant | null
  stageId: PipelineStageId | null
}

const PROVIDER_REQUEST_PRIORITY: string[] = [
  'provider_request.system_prompt',
  'provider_request.prompt',
  'provider_request.persona_prompt',
  'persona_prompt',
  'provider_request.contexts',
  'provider_request.extra_user_content_parts',
  'provider_request.func_tool'
]

const LLM_RESPONSE_PRIORITY: string[] = [
  'llm_response.result_chain',
  'llm_response.completion_text',
  'llm_response.tools_call_name',
  'llm_response.tools_call_args'
]

const RESULT_PRIORITY: string[] = ['result.chain', 'stop', 'send']

const toTargetSet = (effects: Effect[] | undefined) => {
  const set = new Set<string>()
  for (const e of effects ?? []) {
    const t = String(e?.target || '')
    if (t) set.add(t)
  }
  return set
}

const pickFirst = (set: Set<string>, candidates: string[]): EffectTarget | null => {
  for (const c of candidates) {
    if (set.has(c)) return c as EffectTarget
  }
  return null
}

type ParticipantCategory = 'llm_request' | 'llm_response' | 'decorate_send' | 'unknown'

const categoryFromMeta = (eventType: PluginEventType | null | undefined, stageId: PipelineStageId | null): ParticipantCategory => {
  if (eventType === 'OnLLMRequestEvent' || eventType === 'OnCallingFuncToolEvent') return 'llm_request'
  if (eventType === 'OnLLMResponseEvent') return 'llm_response'
  if (eventType === 'OnDecoratingResultEvent' || eventType === 'OnAfterMessageSentEvent') return 'decorate_send'
  if (stageId === 'RespondStage' || stageId === 'ResultDecorateStage') return 'decorate_send'
  return 'unknown'
}

const normalizePersonaTarget = (set: Set<string>, picked: EffectTarget): EffectTarget => {
  if (String(picked) === 'persona_prompt' && set.has('provider_request.persona_prompt')) {
    return 'provider_request.persona_prompt'
  }
  return picked
}

const inferFromEffects = (participant: StageParticipant | null, category: ParticipantCategory): EffectTarget | null => {
  const effects = participant?.effects
  if (!effects || effects.length === 0) return null

  const set = toTargetSet(effects)

  if (category === 'llm_request') {
    const provider = pickFirst(set, PROVIDER_REQUEST_PRIORITY)
    if (provider) return normalizePersonaTarget(set, provider)

    const result = pickFirst(set, RESULT_PRIORITY)
    if (result) return result

    const response = pickFirst(set, LLM_RESPONSE_PRIORITY)
    if (response) return response

    return null
  }

  if (category === 'decorate_send') {
    const result = pickFirst(set, RESULT_PRIORITY)
    if (result) return result

    const provider = pickFirst(set, PROVIDER_REQUEST_PRIORITY)
    if (provider) return normalizePersonaTarget(set, provider)

    const response = pickFirst(set, LLM_RESPONSE_PRIORITY)
    if (response) return response

    return null
  }

  if (category === 'llm_response') {
    const response = pickFirst(set, LLM_RESPONSE_PRIORITY)
    if (response) return response

    const result = pickFirst(set, RESULT_PRIORITY)
    if (result) return result

    const provider = pickFirst(set, PROVIDER_REQUEST_PRIORITY)
    if (provider) return normalizePersonaTarget(set, provider)

    return null
  }

  const provider = pickFirst(set, PROVIDER_REQUEST_PRIORITY)
  if (provider) return normalizePersonaTarget(set, provider)

  const response = pickFirst(set, LLM_RESPONSE_PRIORITY)
  if (response) return response

  const result = pickFirst(set, RESULT_PRIORITY)
  if (result) return result

  return null
}

const inferFromMeta = (eventType: PluginEventType | null | undefined, stageId: PipelineStageId | null): EffectTarget => {
  if (eventType === 'OnLLMRequestEvent') return 'provider_request.system_prompt'
  if (eventType === 'OnCallingFuncToolEvent') return 'provider_request.func_tool'
  if (eventType === 'OnLLMResponseEvent') return 'llm_response.result_chain'
  if (eventType === 'OnDecoratingResultEvent' || eventType === 'OnAfterMessageSentEvent') return 'result.chain'
  if (stageId === 'RespondStage' || stageId === 'ResultDecorateStage') return 'result.chain'
  return 'result.chain'
}

export const inferTraceFocusTarget = (input: InferInput): EffectTarget => {
  const eventType = input.participant?.meta?.event_type ?? null
  const category = categoryFromMeta(eventType, input.stageId)

  const byEffects = inferFromEffects(input.participant, category)
  if (byEffects) return byEffects

  return inferFromMeta(eventType, input.stageId)
}

export const buildTraceFocusGroupKey = (target: EffectTarget, stageId: PipelineStageId | null): string => {
  if (stageId) return `${String(target)}:${String(stageId)}`
  return String(target)
}