export type SnapshotScopeMode = 'global' | 'session'

export interface SnapshotScope {
  mode: SnapshotScopeMode
  umo?: string | null
}

export type PipelineStageId =
  | 'WakingCheckStage'
  | 'WhitelistCheckStage'
  | 'SessionStatusCheckStage'
  | 'RateLimitStage'
  | 'ContentSafetyCheckStage'
  | 'PreProcessStage'
  | 'ProcessStage'
  | 'ResultDecorateStage'
  | 'RespondStage'

export interface PipelineStageMeta {
  id: PipelineStageId
  title: string
  description: string
  kind: 'gate' | 'processing'
}

export type PluginEventType =
  | 'AdapterMessageEvent'
  | 'OnLLMRequestEvent'
  | 'OnLLMResponseEvent'
  | 'OnDecoratingResultEvent'
  | 'OnCallingFuncToolEvent'
  | 'OnAfterMessageSentEvent'

export type HandlerTriggerType =
  | 'command'
  | 'command_group'
  | 'sub_command'
  | 'regex'
  | 'event_listener'
  | 'auto'
  | 'tool'

export interface HandlerTrigger {
  type: HandlerTriggerType
  signature: string
  extra?: Record<string, any>
}

export interface PluginRef {
  name: string
  display_name?: string | null
  reserved: boolean
  activated: boolean
  version?: string | null
  repo?: string | null
}

export interface HandlerRef {
  handler_full_name: string
  handler_name: string
  handler_module_path: string
}

export interface HandlerExecutionMeta {
  event_type: PluginEventType
  priority: number
  enabled: boolean
  trigger?: HandlerTrigger
  description?: string
  permission?: 'everyone' | 'member' | 'admin'
}

export type StaticRiskType =
  | 'may_stop_event'
  | 'may_send_directly'
  | 'may_set_result'
  | 'may_request_llm'
  | 'may_mutate_prompt'
  | 'may_mutate_system_prompt'
  | 'may_modify_persona_prompt'
  | 'may_call_tools'
  | 'duplicate_send_risk'
  | 'stop_blocks_pipeline_risk'
  | 'unknown_source'

export type ConfidenceLevel = 'high' | 'medium' | 'low'

export interface StaticRiskFlag {
  type: StaticRiskType
  level: 'info' | 'warn' | 'error'
  summary: string
  details?: string

  // backward compatible: optional metadata returned by newer backend
  confidence?: ConfidenceLevel
  confidence_reason?: string
}

type EffectTargetKnown =
  | 'provider_request.prompt'
  | 'provider_request.system_prompt'
  | 'provider_request.persona_prompt'
  | 'provider_request.contexts'
  | 'provider_request.extra_user_content_parts'
  | 'provider_request.func_tool'
  | 'llm_response.completion_text'
  | 'llm_response.result_chain'
  | 'llm_response.tools_call_name'
  | 'llm_response.tools_call_args'
  | 'result.chain'
  | 'event.message_str'
  | 'send'
  | 'stop'

export type EffectTarget = EffectTargetKnown | (string & {})

export type EffectOp = 'append' | 'overwrite' | 'clear' | 'mutate_list' | 'call' | (string & {})

export type EffectConfidence = 'high' | 'medium' | 'low' | 'unknown'

export interface Effect {
  target: EffectTarget
  op: EffectOp
  confidence: EffectConfidence
  evidence?: string
  lineno?: number | null
  col?: number | null
}

export interface StageParticipant {
  id: string
  plugin: PluginRef
  handler: HandlerRef
  meta: HandlerExecutionMeta
  risks: StaticRiskFlag[]
  effects?: Effect[]
}

export interface PipelineStageSnapshot {
  stage: PipelineStageMeta
  participants: StageParticipant[]
  notes?: Array<{ level: 'info' | 'warn' | 'error'; text: string }>
}

export type ConflictType =
  | 'command_name_conflict'
  | 'command_alias_conflict'
  | 'priority_tie_conflict'
  | 'prompt_overwrite_conflict'
  | 'system_prompt_overwrite_conflict'
  | 'stop_interception_conflict'
  | 'duplicate_send_conflict'
  | 'tool_name_conflict'
  | 'unknown'

export interface ConflictItem {
  id: string
  type: ConflictType
  severity: 'info' | 'warn' | 'error'
  title: string
  description: string
  involved: Array<{
    plugin: PluginRef
    handler: HandlerRef
    stage: PipelineStageId
    event_type: PluginEventType
    priority: number
    enabled: boolean
  }>
  suggestion?: string
  references?: Array<{ kind: 'stage' | 'handler' | 'plugin'; id: string }>

  // backward compatible: optional metadata returned by newer backend
  confidence?: ConfidenceLevel
  confidence_reason?: string
  note?: string
  impact?: {
    same_stage_following_handlers?: string[]
    downstream_stages?: string[]
  }
}

export interface SystemPromptSegmentSource {
  plugin: string
  handler: string
  priority: number
  field: string
  mutation: string
  status: string
}

export interface SystemPromptSegment {
  text: string
  source: SystemPromptSegmentSource | null
  // Optional: when a segment is derived from persona prompt but affected by multiple plugins,
  // backend may attach all sources here. UI can still rely on `source` for primary color.
  sources?: SystemPromptSegmentSource[] | null
}

export interface LlmPromptPreview {
  prompt: string
  system_prompt: string
  contexts: {
    present: boolean
    source?: 'conversation_history' | 'external_contexts' | 'unknown'
    count?: number
    note?: string
  }
  injected_by: Array<{
    plugin: PluginRef
    handler: HandlerRef
    priority: number
    mutation: 'append' | 'overwrite' | 'replace' | 'unknown'
    field: 'prompt' | 'system_prompt' | 'persona_prompt'
    source_type?: 'llm_request' | 'persona'
  }>

  // Newer backend optional fields (backward compatible)
  rendered_prompt?: string
  rendered_system_prompt?: string
  rendered_system_prompt_segments?: SystemPromptSegment[]
  rendered_extra_user_content_segments?: SystemPromptSegment[]
  render_warnings?: string[]
  render_executed_handlers?: Array<{
    plugin: PluginRef
    handler: HandlerRef
    priority: number
    status: 'executed' | 'blocked' | 'errored' | 'skipped'
    blocked?: Array<{ action: string; reason: string }>
    error?: string | null
    stop_event?: boolean
    diff?: {
      prompt?: { changed?: boolean; before_len?: number; after_len?: number }
      system_prompt?: { changed?: boolean; before_len?: number; after_len?: number }
    }
  }>
}

export interface PipelineSnapshotStats {
  pluginCount: number
  handlerCount: number
  conflictCount: number
  riskCount: number
  byConflictType: Record<string, number>
}

export interface PipelineSnapshot {
  snapshot_id: string
  generated_at: string
  scope: SnapshotScope
  plugins: PluginRef[]
  stages: PipelineStageSnapshot[]
  conflicts: ConflictItem[]
  llm_prompt_preview?: LlmPromptPreview
  stats: PipelineSnapshotStats
}