import type { DynamicConfig } from '../generated/openapi-v1';
import type { AgentStats, ChatContent } from '@/domain/chat';
import type { CommandItem } from '@/domain/commands';

export interface ApiEnvelope<T> {
  status: 'ok' | 'warning' | 'error';
  message?: string | null;
  data: T;
}

export type OpenConfig = DynamicConfig;

export interface ProviderSchemaData {
  config_schema?: OpenConfig;
  providers?: OpenConfig[];
  provider_sources?: OpenConfig[];
  model_metadata?: Record<string, unknown>;
}

export interface ProviderListData {
  providers?: OpenConfig[];
  model_metadata?: Record<string, unknown>;
}

export interface ProviderByTypeEnvelope extends ApiEnvelope<OpenConfig[]> {
  model_metadata?: Record<string, unknown>;
}

export interface ProviderByIdData {
  provider?: OpenConfig;
  model_metadata?: Record<string, unknown>;
}

export interface ProviderSourceModelsData {
  models?: string[];
  model_metadata?: Record<string, unknown>;
}

export interface ProviderTestData {
  id?: string;
  model?: string | null;
  type?: string | null;
  name?: string;
  status?: string;
  error?: string | null;
}

export interface ProviderEmbeddingDimensionData {
  embedding_dimensions?: number;
  [key: string]: unknown;
}

export interface VersionData {
  version?: string;
  dashboard_version?: string;
  change_pwd_hint?: boolean;
  md5_pwd_hint?: boolean;
  password_upgrade_required?: boolean;
  [key: string]: unknown;
}

export interface PublicVersionData {
  webui_version?: string | null;
  astrbot_version?: string | null;
  astrbot_code_version?: string | null;
  [key: string]: unknown;
}

export interface T2iRuntimeStatsData {
  render_in_progress: number;
  active_pages: number;
  peak_active_pages: number;
  successful_renders: number;
  failed_renders: number;
  cancelled_renders: number;
  total_render_duration_ms: number;
  last_render_duration_ms: number;
  average_render_duration_ms: number;
  max_render_duration_ms: number;
  output_bytes: number;
  browser_starts: number;
  browser_restarts: number;
  browser_connected: boolean;
  context_count: number;
}

export interface AuthLoginData {
  username?: string;
  token?: string;
  password_upgrade_required?: boolean;
  md5_pwd_hint?: boolean;
  change_pwd_hint?: boolean;
  [key: string]: unknown;
}

export interface AuthSetupStatusData {
  setup_required?: boolean;
  skip_default_password_auth?: boolean;
  totp_required?: boolean;
  [key: string]: unknown;
}

export interface TotpSetupData {
  secret?: string | null;
  recovery_code?: string | null;
  recovery_code_hash?: string | null;
  [key: string]: unknown;
}

export interface UpdateCheckData {
  has_new_version: boolean;
  [key: string]: unknown;
}

export interface UploadedFileData {
  attachment_id: string;
  filename: string;
  type: string;
  [key: string]: unknown;
}

export interface BotRegistrationData {
  status?: string;
  registration_code?: string;
  interval?: number;
  verification_uri_complete?: string;
  qrcode_img_content?: string;
  qrcode?: string;
  task_id?: string;
  bind_key?: string;
  app_id?: string;
  app_secret?: string;
  appid?: string;
  secret?: string;
  domain?: string;
  weixin_oc_token?: string;
  weixin_oc_account_id?: string;
  weixin_oc_base_url?: string;
  client_id?: string;
  client_secret?: string;
  [key: string]: unknown;
}

export interface CommandListData {
  items?: CommandItem[];
  wake_prefix?: string[];
  summary?: {
    disabled?: number;
    conflicts?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface PagedItemsData<T> {
  items?: T[];
  total?: number;
  page?: number;
  page_size?: number;
  [key: string]: unknown;
}

export interface ChatSessionSummary {
  session_id: string;
  display_name: string | null;
  updated_at: string;
  platform_id: string;
  creator: string;
  is_group: number;
  created_at: string;
  [key: string]: unknown;
}

export interface AppearanceWallpaper {
  id: string;
  content_type: 'image/jpeg' | 'image/png' | 'image/webp' | 'image/gif';
  width: number;
  height: number;
  image_url: string;
  thumbnail_url: string;
}

export interface AppearanceWallpaperListData {
  items: AppearanceWallpaper[];
}

export interface ChatThreadData {
  thread_id: string;
  parent_session_id: string;
  parent_message_id: number;
  base_checkpoint_id: string;
  selected_text: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ChatSessionProjectData {
  project_id: string;
  title: string;
  emoji?: string;
  [key: string]: unknown;
}

export interface ChatSessionDetailData {
  session_id?: string;
  display_name?: string | null;
  platform_id?: string;
  history?: HistoryRecordData[];
  threads?: ChatThreadData[];
  project?: ProjectData | null;
  [key: string]: unknown;
}

export interface ChatMessageMutationData {
  message?: OpenConfig;
  truncated_after_message?: boolean;
  needs_regenerate?: boolean;
  [key: string]: unknown;
}

export interface ChatBatchDeleteData {
  deleted_count?: number;
  failed_count?: number;
  failed_items?: OpenConfig[];
  [key: string]: unknown;
}

export interface SessionRuleListData {
  rules?: OpenConfig[];
  total?: number;
  available_personas?: OpenConfig[];
  available_chat_providers?: OpenConfig[];
  available_stt_providers?: OpenConfig[];
  available_tts_providers?: OpenConfig[];
  available_plugins?: OpenConfig[];
  available_kbs?: OpenConfig[];
  [key: string]: unknown;
}

export interface UmoInfoData {
  umo: string;
  platform?: string;
  message_type?: string;
  session_id?: string;
  auto_name?: string;
  user_alias?: string;
  display_name?: string;
  [key: string]: unknown;
}

export interface ActiveUmosData {
  umos?: string[];
  umo_infos?: UmoInfoData[];
  [key: string]: unknown;
}

export interface SkillItemData {
  name?: string;
  description?: string;
  path?: string;
  active?: boolean;
  source_type?: string;
  source_label?: string;
  plugin_name?: string;
  plugin_active?: boolean;
  plugin_display_name?: string;
  readonly?: boolean;
  [key: string]: unknown;
}

export type SkillListData =
  | SkillItemData[]
  | {
      skills?: SkillItemData[];
      runtime?: string;
      sandbox_cache?: OpenConfig;
      [key: string]: unknown;
    };

export interface PersonaFolderData {
  folder_id: string;
  name: string;
  parent_id: string | null;
  description: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
  children: PersonaFolderData[];
  [key: string]: unknown;
}

export interface PersonaData {
  persona_id: string;
  system_prompt: string;
  custom_error_message: string | null;
  begin_dialogs: string[];
  tools: string[] | null;
  skills: string[] | null;
  folder_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
}

export interface PersonaFolderMutationData {
  folder?: PersonaFolderData;
  [key: string]: unknown;
}

export interface PersonaFolderInput {
  name?: string;
  parent_id?: string | null;
  description?: string | null;
  [key: string]: unknown;
}

export interface PersonaInput {
  persona_id: string;
  system_prompt: string;
  begin_dialogs?: string[];
  tools?: string[] | null;
  skills?: string[] | null;
  folder_id?: string | null;
  custom_error_message?: string | null;
  [key: string]: unknown;
}

export interface ConversationPaginationData {
  page?: number;
  page_size?: number;
  total?: number;
  total_pages?: number;
  [key: string]: unknown;
}

export interface ConversationRecordData {
  cid?: string;
  user_id?: string;
  title?: string;
  history?: string;
  [key: string]: unknown;
}

export interface ConversationListResponseData {
  conversations?: ConversationRecordData[];
  pagination?: ConversationPaginationData;
  [key: string]: unknown;
}

export interface ConversationBatchDeleteData {
  deleted_count?: number;
  failed_count?: number;
  [key: string]: unknown;
}

export interface KnowledgeBaseData {
  kb_id: string;
  kb_name: string;
  description?: string | null;
  emoji?: string | null;
  init_error?: string | null;
  doc_count?: number;
  chunk_count?: number;
  embedding_provider_id?: string | null;
  rerank_provider_id?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface KnowledgeDocumentData {
  document_id?: string;
  doc_id?: string;
  doc_name: string;
  file_type?: string;
  file_size?: number;
  chunk_count?: number;
  created_at?: string;
  [key: string]: unknown;
}

export interface KnowledgeChunkData {
  chunk_id: string;
  chunk_index: number;
  content: string;
  char_count: number;
  [key: string]: unknown;
}

export interface KnowledgeRetrieveResultData {
  chunk_id: string;
  chunk_index: number;
  doc_name: string;
  char_count: number;
  score: number;
  content: string;
  [key: string]: unknown;
}

export interface KnowledgeRetrieveData {
  results?: KnowledgeRetrieveResultData[];
  visualization?: string | null;
  [key: string]: unknown;
}

export interface MemoryFactData {
  id: number;
  person_id: string;
  chat_id: string;
  scope_id: string;
  fact_text: string;
  fact_type: string;
  source_message_id?: string;
  evidence_message_ids?: string[];
  confidence: number;
  status: 'active' | 'deleted' | string;
  ttl_at?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface MemoryProfileData {
  id: number;
  person_id: string;
  chat_scope: string;
  profile_text: string;
  source_version: number;
  is_override: boolean;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface MemoryOperationData {
  id: number;
  operation_id: string;
  operator: string;
  target_type: string;
  target_id: string;
  action: string;
  reason?: string | null;
  payload?: OpenConfig;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface MemoryFactDetailData {
  fact?: MemoryFactData;
  operation_logs?: MemoryOperationData[];
  [key: string]: unknown;
}

export interface MemoryStatsData {
  facts?: number;
  deleted_facts?: number;
  profiles?: number;
  episodes?: number;
  operations?: number;
  worker?: {
    running?: boolean;
    queue_size?: number;
    queue_max_size?: number;
    recent_profile_tasks?: unknown[];
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface PluginData {
  name?: string;
  activated?: boolean;
  reserved?: boolean;
  origin?: string;
  origin_name?: string;
  readme?: string;
  readme_content?: string;
  content?: string;
  [key: string]: unknown;
}

export interface ProjectData {
  project_id: string;
  title: string;
  emoji?: string;
  description?: string;
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
}

export interface DownloadStageData {
  status: 'pending' | 'running' | 'done' | 'error';
  downloaded: number;
  total: number;
  percent: number;
  speed: number;
  [key: string]: unknown;
}

export interface UpdateProgressData {
  id: string;
  status: 'idle' | 'running' | 'success' | 'error';
  stage: string;
  version: string;
  message: string;
  overall_percent: number;
  stages: Record<string, DownloadStageData>;
  [key: string]: unknown;
}

export interface PluginConfigFilesData {
  files?: string[];
  [key: string]: unknown;
}

export interface PluginConfigUploadData {
  uploaded?: string[];
  errors?: OpenConfig[];
  [key: string]: unknown;
}

export interface ReleaseItemData {
  tag_name: string;
  published_at: string;
  body: string;
  [key: string]: unknown;
}

export interface HistoryRecordData {
  content?: ChatContent & {
    agent_stats?: AgentStats | null;
  };
  sender_id?: string;
  [key: string]: unknown;
}

export interface ChatThreadDetailData extends ChatThreadData {
  history?: HistoryRecordData[];
}

export interface BaseStatsData {
  message_count: number;
  platform_count: number;
  platform: Array<{
    name: string;
    count: number;
    timestamp: number;
  }>;
  message_time_series: Array<[number, number]>;
  memory: {
    process: number;
    system: number;
  };
  cpu_percent: number;
  running: {
    hours: number;
    minutes: number;
    seconds: number;
  };
  thread_count: number;
  start_time: number;
}

export interface ProviderTrendItemData {
  name: string;
  data: Array<[number, number]>;
  total_tokens: number;
}

export interface ProviderRankingItemData {
  provider_id: string;
  tokens: number;
}

export interface UmoRankingItemData {
  umo: string;
  tokens: number;
}

export interface ProviderTokenStatsData {
  days: 1 | 3 | 7;
  trend: {
    series: ProviderTrendItemData[];
    total_series: Array<[number, number]>;
  };
  range_total_tokens: number;
  range_total_calls: number;
  range_avg_ttft_ms: number;
  range_avg_duration_ms: number;
  range_avg_tpm: number;
  range_success_rate: number;
  range_by_provider: ProviderRankingItemData[];
  range_by_umo: UmoRankingItemData[];
  today_total_tokens: number;
  today_total_calls: number;
  today_by_provider: ProviderRankingItemData[];
}

export interface BotListParams {
  enabled?: boolean;
  type?: string;
}

export interface ProviderListParams {
  provider_type?:
    | 'chat_completion'
    | 'agent_runner'
    | 'speech_to_text'
    | 'text_to_speech'
    | 'embedding'
    | 'rerank'
    | string;
  provider_source_id?: string;
  enabled?: boolean;
}

export interface ToolListParams {
  origin?: 'builtin' | 'plugin' | 'mcp';
  enabled?: boolean;
}

export interface BackupListParams {
  page?: number;
  page_size?: number;
}

export interface SessionListParams {
  page?: number;
  page_size?: number;
  search?: string;
  platform?: string;
  message_type?: 'all' | 'group' | 'private';
}

export interface SessionRuleListParams {
  page?: number;
  page_size?: number;
  search?: string;
}

export interface ChatSessionListParams {
  page?: number;
  page_size?: number;
  username?: string;
}

export interface CronJobListParams {
  type?: string;
}
