import type { AxiosRequestConfig, AxiosResponse } from 'axios';

import * as openApiV1 from './generated/openapi-v1';
import {
  type BackupChunkUploadRequest,
  client as openApiV1Client,
  type BackupExportRequest,
  type BackupRenameRequest,
  type BackupUploadInitRequest,
  type BackupUploadRequest,
  type BackupUploadSessionRequest,
  type BotConfigRequest,
  type BotRegistrationRequest,
  type ChatMessagePatchRequest,
  type ChatMessageRegenerateRequest,
  type ChatProjectRequest,
  type ChatRequest,
  type ChatSessionBatchDeleteRequest,
  type ChatSessionPatchRequest,
  type ChatThreadCreateRequest,
  type ChatThreadMessageRequest,
  type CommandPatchRequest,
  type ConfigRouteUpsertRequest,
  type ConfigRoutesReplaceRequest,
  type ConversationBatchDeleteRequest,
  type ConversationExportRequest,
  type ConversationMessagesReplaceRequest,
  type ConversationPatchRequest,
  type CreateApiKeyRequest,
  type CronJobPatchRequest,
  type CronJobRequest,
  type DynamicConfig,
  type EnabledPatch,
  type GhproxyTestRequest,
  type KnowledgeBaseCreateRequest,
  type KnowledgeBaseRequest,
  type LoginRequest,
  type ListConversationsData,
  type McpServerConfig,
  type ModelScopeSyncRequest,
  type PipInstallRequest,
  type PluginVersionSupportRequest,
  type PluginValidateRepoRequest,
  type PluginConfigFileDeleteRequest,
  type ProviderConfigRequest,
  type BatchSessionProviderRequest,
  type BatchSessionServiceRequest,
  type SetupAuthRequest,
  type SessionGroupRequest,
  type SessionRuleRequest,
  type UmoListRequest,
  type SuccessEnvelope,
  type T2iTemplateRequest,
  type TotpSetupRequest,
  type TraceSettingsRequest,
  type UpdateAccountRequest,
  type UpdateRequest,
} from './generated/openapi-v1';
import { apiV1Client, httpClient } from './http';

openApiV1Client.setConfig({
  axios: httpClient,
  throwOnError: true,
});

export interface ApiEnvelope<T> {
  status: 'ok' | 'error';
  message?: string | null;
  data: T;
}

export const UPGRADE_RECOVERY_EVENT = 'astrbot-upgrade-recovery';
export const UPGRADE_RECOVERY_TOKEN_KEY = 'astrbot-upgrade-recovery-token';

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

type StartTimeData = {
  start_time?: number | string | null;
};

export interface CommandListData {
  items?: any[];
  wake_prefix?: string[];
  summary?: {
    disabled?: number;
    conflicts?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface BotListParams {
  enabled?: boolean;
  type?: string;
}

export interface ProviderListParams {
  capability?: 'chat' | 'agent' | 'stt' | 'tts' | 'embedding' | 'rerank';
  source_id?: string;
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

type ProviderCapability = NonNullable<ProviderListParams['capability']>;

const PROVIDER_TYPE_TO_CAPABILITY: Record<string, ProviderCapability> = {
  chat_completion: 'chat',
  agent_runner: 'agent',
  speech_to_text: 'stt',
  text_to_speech: 'tts',
  embedding: 'embedding',
  rerank: 'rerank',
};

type V1Response<T> = Promise<
  AxiosResponse<ApiEnvelope<T>> & { legacyFallback?: boolean }
>;
type ListConversationsQuery = NonNullable<ListConversationsData['query']>;

function typed<T>(response: Promise<unknown>): V1Response<T> {
  return response as unknown as V1Response<T>;
}

export function isLegacyFallbackError(error: unknown): boolean {
  const axiosError = error as {
    response?: { status?: number; data?: { message?: string } | string };
    message?: string;
  };
  if (axiosError.response?.status === 404) {
    return true;
  }

  const data = axiosError.response?.data;
  const message =
    typeof data === 'string' ? data : data?.message || axiosError.message || '';
  return message.toLowerCase().includes('missing api key');
}

function withLegacyFallback<T>(
  primary: Promise<unknown>,
  legacy: () => Promise<AxiosResponse<ApiEnvelope<T>>>,
): V1Response<T> {
  const legacyRequest = () =>
    legacy().then((response) => {
      const legacyResponse = response as AxiosResponse<ApiEnvelope<T>> & {
        legacyFallback?: boolean;
      };
      legacyResponse.legacyFallback = true;
      return legacyResponse;
    });

  return typed<T>(primary).then((response) => {
    const message = response.data?.message || '';
    if (
      response.data?.status === 'error' &&
      message.toLowerCase().includes('missing api key')
    ) {
      return legacyRequest();
    }
    return response;
  }).catch((error) => {
    if (isLegacyFallbackError(error)) {
      return legacyRequest();
    }
    throw error;
  });
}

function firstSuccessfulResponse<T>(
  requests: Array<Promise<AxiosResponse<ApiEnvelope<T>>>>,
): V1Response<T> {
  return new Promise<AxiosResponse<ApiEnvelope<T>>>((resolve, reject) => {
    let pending = requests.length;
    let firstError: unknown;
    requests.forEach((request) => {
      request.then(resolve).catch((error) => {
        if (firstError === undefined) {
          firstError = error;
        }
        pending -= 1;
        if (pending === 0) {
          reject(firstError);
        }
      });
    });
  });
}

function generatedOptions(
  options: Record<string, unknown>,
  requestConfig?: AxiosRequestConfig,
) {
  return { ...options, ...(requestConfig || {}) } as any;
}

function generatedQuery<T extends object>(
  params?: T,
): (T & Record<string, unknown>) | undefined {
  return params as (T & Record<string, unknown>) | undefined;
}

function generatedFormData(formData: FormData | Record<string, unknown>) {
  if (typeof FormData !== 'undefined' && formData instanceof FormData) {
    const body: Record<string, unknown> = {};
    formData.forEach((value, key) => {
      const existing = body[key];
      if (existing === undefined) {
        body[key] = value;
      } else if (Array.isArray(existing)) {
        existing.push(value);
      } else {
        body[key] = [existing, value];
      }
    });
    return body as any;
  }
  return formData as any;
}

function botConfig(config: OpenConfig): BotConfigRequest {
  return {
    id: typeof config.id === 'string' ? config.id : undefined,
    type: typeof config.type === 'string' ? config.type : '',
    enabled:
      typeof config.enable === 'boolean'
        ? config.enable
        : typeof config.enabled === 'boolean'
          ? config.enabled
          : undefined,
    config,
  };
}

function providerConfig(config: OpenConfig): ProviderConfigRequest {
  return { config } as ProviderConfigRequest;
}

function providerTypeToCapabilities(providerType: string): ProviderCapability[] {
  return providerType
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => PROVIDER_TYPE_TO_CAPABILITY[item] || (item as ProviderCapability));
}

function pluginExtensionPath(pluginPath: string): string {
  return pluginPath
    .replace(/^\/+/, '')
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

export const configProfileApi = {
  schema() {
    return typed<OpenConfig>(openApiV1.getConfigProfileSchema());
  },
  list() {
    return typed<{ info_list: OpenConfig[] }>(openApiV1.listConfigProfiles());
  },
  create(payload: { name?: string | null; config?: OpenConfig | null }) {
    return typed<{ conf_id: string }>(
      openApiV1.createConfigProfile({
        body: {
          name: payload.name ?? undefined,
          config: payload.config ?? undefined,
        },
      }),
    );
  },
  get(configId: string) {
    return typed<OpenConfig>(
      openApiV1.getConfigProfile({ path: { config_id: configId } }),
    );
  },
  update(
    configId: string,
    config: OpenConfig,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<OpenConfig>(
      openApiV1.updateConfigProfileContent(
        generatedOptions(
          {
            path: { config_id: configId },
            body: config,
          },
          requestConfig,
        ),
      ),
    );
  },
  rename(configId: string, name: string | null) {
    return typed<OpenConfig>(
      openApiV1.renameConfigProfile({
        path: { config_id: configId },
        body: { name: name ?? '' },
      }),
    );
  },
  delete(configId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteConfigProfile({ path: { config_id: configId } }),
    );
  },
};

export const systemConfigApi = {
  schema() {
    return typed<OpenConfig>(openApiV1.getSystemConfigSchema());
  },
  get() {
    return typed<OpenConfig>(openApiV1.getSystemConfig());
  },
  runtime() {
    return typed<OpenConfig>(openApiV1.getSystemConfigRuntime());
  },
  update(config: OpenConfig, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.updateSystemConfig(
        generatedOptions({ body: config }, requestConfig),
      ),
    );
  },
};

export const configRouteApi = {
  list() {
    return typed<{ routing?: Record<string, string> }>(openApiV1.listConfigRoutes());
  },
  replace(payload: ConfigRoutesReplaceRequest) {
    return typed<OpenConfig>(openApiV1.replaceConfigRoutes({ body: payload }));
  },
  upsert(umo: string, payload: ConfigRouteUpsertRequest) {
    return typed<OpenConfig>(
      openApiV1.upsertConfigRoute({ path: { umo }, body: payload }),
    );
  },
  delete(umo: string) {
    return typed<OpenConfig>(
      openApiV1.deleteConfigRoute({ path: { umo } }),
    );
  },
};

export const botApi = {
  types() {
    return typed<{ bot_types: OpenConfig[] }>(openApiV1.listBotTypes());
  },
  list(params?: BotListParams) {
    return typed<{ bots: OpenConfig[] }>(
      openApiV1.listBots({ query: generatedQuery(params) }),
    );
  },
  stats() {
    return typed<{ platforms: OpenConfig[] }>(openApiV1.listBotStats());
  },
  registration(botType: string, payload: BotRegistrationRequest) {
    return typed<any>(
      openApiV1.registerBotType({
        path: { bot_type: botType },
        body: payload,
      }),
    );
  },
  create(config: OpenConfig) {
    return typed<OpenConfig>(openApiV1.createBot({ body: botConfig(config) }));
  },
  get(botId: string) {
    return typed<{ bot: OpenConfig }>(
      openApiV1.getBotById({ query: { bot_id: botId } }),
    );
  },
  update(botId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updateBotById({
        body: { bot_id: botId, config },
      }),
    );
  },
  setEnabled(botId: string, payload: EnabledPatch) {
    return typed<OpenConfig>(
      openApiV1.setBotEnabledById({
        body: { bot_id: botId, enabled: payload.enabled },
      }),
    );
  },
  delete(botId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteBotById({ query: { bot_id: botId } }),
    );
  },
};

export const providerApi = {
  schema() {
    return typed<ProviderSchemaData>(openApiV1.getProviderSchema());
  },
  sources() {
    return typed<{ provider_sources: OpenConfig[] }>(
      openApiV1.listProviderSources(),
    );
  },
  upsertSource(sourceId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.upsertProviderSourceById({
        body: { source_id: sourceId, config },
      }),
    );
  },
  deleteSource(sourceId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteProviderSourceById({ query: { source_id: sourceId } }),
    );
  },
  sourceModels(sourceId: string) {
    return typed<ProviderSourceModelsData>(
      openApiV1.listProviderSourceModelsById({
        query: { source_id: sourceId },
      }),
    );
  },
  list(params?: ProviderListParams) {
    return typed<ProviderListData>(
      openApiV1.listProviders({ query: generatedQuery(params) }),
    );
  },
  async listByProviderType(
    providerType: string,
  ): Promise<AxiosResponse<ProviderByTypeEnvelope>> {
    const capabilities = providerTypeToCapabilities(providerType);
    if (capabilities.length === 0) {
      const response = await providerApi.list();
      return {
        ...response,
        data: {
          ...response.data,
          data: response.data.data.providers || [],
          model_metadata: response.data.data.model_metadata || {},
        },
      };
    }

    const responses = await Promise.all(
      capabilities.map((capability) => providerApi.list({ capability })),
    );
    const first = responses[0];
    const modelMetadata = responses.reduce<Record<string, unknown>>(
      (acc, response) => ({
        ...acc,
        ...(response.data.data.model_metadata || {}),
      }),
      {},
    );
    return {
      ...first,
      data: {
        ...first.data,
        data: responses.flatMap(
          (response) => response.data.data.providers || [],
        ),
        model_metadata: modelMetadata,
      },
    };
  },
  create(config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createProvider({ body: providerConfig(config) }),
    );
  },
  listBySource(sourceId: string, params?: Pick<ProviderListParams, 'capability'>) {
    return typed<{ providers: OpenConfig[] }>(
      openApiV1.listProvidersBySourceId({
        query: { source_id: sourceId, ...params },
      }),
    );
  },
  createInSource(sourceId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createProviderInSourceById({
        body: { source_id: sourceId, config },
      }),
    );
  },
  get(providerId: string, merged = false) {
    return typed<ProviderByIdData>(
      openApiV1.getProviderById({
        query: { provider_id: providerId, merged },
      }),
    );
  },
  update(providerId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updateProviderById({
        body: { provider_id: providerId, config },
      }),
    );
  },
  setEnabled(providerId: string, payload: EnabledPatch) {
    return typed<OpenConfig>(
      openApiV1.setProviderEnabledById({
        body: { provider_id: providerId, enabled: payload.enabled },
      }),
    );
  },
  delete(providerId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteProviderById({ query: { provider_id: providerId } }),
    );
  },
  test(providerId: string) {
    return typed<ProviderTestData>(
      openApiV1.testProviderById({ body: { provider_id: providerId } }),
    );
  },
  embeddingDimension(providerId: string, providerConfig?: OpenConfig) {
    return typed<ProviderEmbeddingDimensionData>(
      openApiV1.getProviderEmbeddingDimensionById({
        body: {
          provider_id: providerId,
          ...(providerConfig ? { provider_config: providerConfig } : {}),
        },
      }),
    );
  },
};

export const authApi = {
  login(payload: LoginRequest) {
    return withLegacyFallback<any>(openApiV1.login({ body: payload }), () =>
      httpClient.post<ApiEnvelope<any>>('/api/auth/login', payload),
    );
  },
  logout() {
    return withLegacyFallback<OpenConfig>(openApiV1.logout(), () =>
      httpClient.post<ApiEnvelope<OpenConfig>>('/api/auth/logout'),
    );
  },
  setupStatus() {
    return withLegacyFallback<any>(openApiV1.getAuthSetupStatus(), () =>
      httpClient.get<ApiEnvelope<any>>('/api/auth/setup-status'),
    );
  },
  setup(payload: SetupAuthRequest) {
    return withLegacyFallback<OpenConfig>(openApiV1.setupAuth({ body: payload }), () =>
      httpClient.post<ApiEnvelope<OpenConfig>>('/api/auth/setup', payload),
    );
  },
  setupTotp(payload?: TotpSetupRequest) {
    return withLegacyFallback<any>(openApiV1.setupTotp({ body: payload }), () =>
      httpClient.post<ApiEnvelope<any>>('/api/auth/totp/setup', payload),
    );
  },
  recoverTotp() {
    return withLegacyFallback<any>(openApiV1.recoverTotp(), () =>
      httpClient.post<ApiEnvelope<any>>('/api/auth/totp/recovery'),
    );
  },
  updateAccount(payload: UpdateAccountRequest) {
    return withLegacyFallback<OpenConfig>(
      openApiV1.updateAuthAccount({ body: payload }),
      () => httpClient.post<ApiEnvelope<OpenConfig>>('/api/auth/account/edit', payload),
    );
  },
};

export const apiKeyApi = {
  list() {
    return typed<OpenConfig[]>(openApiV1.listApiKeys());
  },
  create(payload: CreateApiKeyRequest) {
    return typed<{ api_key?: string }>(openApiV1.createApiKey({ body: payload }));
  },
  revoke(keyId: string) {
    return typed<OpenConfig>(
      openApiV1.revokeApiKey({ path: { key_id: keyId } }),
    );
  },
  delete(keyId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteApiKey({ path: { key_id: keyId } }),
    );
  },
};

export const traceApi = {
  getSettings() {
    return typed<OpenConfig>(openApiV1.getTraceSettings());
  },
  updateSettings(settings: TraceSettingsRequest) {
    return typed<OpenConfig>(
      openApiV1.updateTraceSettings({ body: settings }),
    );
  },
};

export const updatesApi = {
  check() {
    return withLegacyFallback<any>(openApiV1.checkUpdate(), () =>
      httpClient.get<ApiEnvelope<any>>('/api/update/check'),
    );
  },
  releases(type?: 'core' | 'dashboard') {
    return withLegacyFallback<any[]>(
      openApiV1.listReleases({
        query: type ? { type } : undefined,
      }),
      () =>
        httpClient.get<ApiEnvelope<any[]>>('/api/update/releases', {
          params: type ? { type } : undefined,
        }),
    );
  },
  core(payload?: UpdateRequest) {
    return withLegacyFallback<OpenConfig>(openApiV1.updateCore({ body: payload }), () =>
      httpClient.post<ApiEnvelope<OpenConfig>>('/api/update/do', payload),
    );
  },
  dashboard(payload?: UpdateRequest) {
    return withLegacyFallback<OpenConfig>(
      openApiV1.updateDashboard({ body: payload }),
      () => httpClient.post<ApiEnvelope<OpenConfig>>('/api/update/dashboard', payload),
    );
  },
  progress(taskId: string) {
    return withLegacyFallback<any>(
      openApiV1.getUpdateProgress({ path: { task_id: taskId } }),
      () =>
        httpClient.get<ApiEnvelope<any>>('/api/update/progress', {
          params: { id: taskId },
        }),
    );
  },
  installPip(payload: PipInstallRequest) {
    return withLegacyFallback<OpenConfig>(
      openApiV1.installPipPackage({ body: payload }),
      () => httpClient.post<ApiEnvelope<OpenConfig>>('/api/update/pip-install', payload),
    );
  },
};

export const backupApi = {
  list(params?: BackupListParams) {
    return typed<any>(openApiV1.listBackups({ query: generatedQuery(params) }));
  },
  create(payload?: BackupExportRequest) {
    return typed<any>(openApiV1.createBackup({ body: payload }));
  },
  progress(taskId: string) {
    return typed<any>(
      openApiV1.getBackupProgress({ path: { task_id: taskId } }),
    );
  },
  upload(formData: FormData | BackupUploadRequest) {
    return typed<any>(
      openApiV1.uploadBackup({ body: generatedFormData(formData) }),
    );
  },
  initUpload(payload: BackupUploadInitRequest) {
    return typed<any>(openApiV1.initBackupUpload({ body: payload }));
  },
  uploadChunk(formData: FormData | BackupChunkUploadRequest) {
    return typed<any>(
      openApiV1.uploadBackupChunk({ body: generatedFormData(formData) }),
    );
  },
  completeUpload(payload: BackupUploadSessionRequest) {
    return typed<any>(openApiV1.completeBackupUpload({ body: payload }));
  },
  abortUpload(payload: BackupUploadSessionRequest) {
    return typed<OpenConfig>(openApiV1.abortBackupUpload({ body: payload }));
  },
  check(filename: string) {
    return typed<any>(
      openApiV1.checkBackup({ path: { filename } }),
    );
  },
  import(filename: string, confirmed = true) {
    return typed<any>(
      openApiV1.importBackup({
        path: { filename },
        body: { confirmed } as any,
      }),
    );
  },
  delete(filename: string) {
    return typed<OpenConfig>(
      openApiV1.deleteBackup({ path: { filename } }),
    );
  },
  rename(filename: string, payload: BackupRenameRequest) {
    return typed<any>(
      openApiV1.renameBackup({ path: { filename }, body: payload }),
    );
  },
  downloadUrl(filename: string, token: string) {
    return `/api/v1/backups/${encodeURIComponent(filename)}?token=${encodeURIComponent(token)}`;
  },
};

export const chatApi = {
  send(payload: ChatRequest) {
    return typed<any>(openApiV1.sendChatMessage({ body: payload }));
  },
  sendStreamUrl() {
    return '/api/v1/chat';
  },
  resumeRunStreamUrl(runId: string) {
    return `/api/v1/chat/runs/${encodeURIComponent(runId)}/stream`;
  },
  liveWebSocketUrl(token: string, host = window.location.host) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}/api/v1/live-chat/ws?token=${encodeURIComponent(token)}`;
  },
  unifiedWebSocketUrl(token: string, host = window.location.host) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}/api/v1/unified-chat/ws?token=${encodeURIComponent(token)}`;
  },
  listSessions(params?: ChatSessionListParams) {
    return typed<any>(
      openApiV1.listChatSessions({ query: generatedQuery(params) }),
    );
  },
  createSession(platformId?: string) {
    return typed<any>(
      openApiV1.createChatSession({
        query: platformId ? { platform_id: platformId } : undefined,
      }),
    );
  },
  getSession(sessionId: string) {
    return typed<any>(
      openApiV1.getChatSession({ path: { session_id: sessionId } }),
    );
  },
  updateSession(sessionId: string, payload: ChatSessionPatchRequest) {
    return typed<any>(
      openApiV1.updateChatSession({
        path: { session_id: sessionId },
        body: payload,
      }),
    );
  },
  deleteSession(sessionId: string) {
    return typed<any>(
      openApiV1.deleteChatSession({ path: { session_id: sessionId } }),
    );
  },
  batchDeleteSessions(payload: ChatSessionBatchDeleteRequest) {
    return typed<any>(openApiV1.batchDeleteChatSessions({ body: payload }));
  },
  stopSession(sessionId: string) {
    return typed<any>(
      openApiV1.stopChatSession({ path: { session_id: sessionId } }),
    );
  },
  updateMessage(
    sessionId: string,
    messageId: string | number,
    payload: ChatMessagePatchRequest,
  ) {
    return typed<any>(
      openApiV1.updateChatMessage({
        path: { session_id: sessionId, message_id: String(messageId) },
        body: payload,
      }),
    );
  },
  regenerateMessage(
    sessionId: string,
    messageId: string | number,
    payload?: ChatMessageRegenerateRequest,
  ) {
    return typed<any>(
      openApiV1.regenerateChatMessage({
        path: { session_id: sessionId, message_id: String(messageId) },
        body: payload,
      }) as any,
    );
  },
  regenerateMessageUrl(sessionId: string, messageId: string | number) {
    return `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(String(messageId))}/regenerate`;
  },
  createThread(payload: ChatThreadCreateRequest) {
    return typed<any>(openApiV1.createChatThread({ body: payload }));
  },
  getThread(threadId: string) {
    return typed<any>(
      openApiV1.getChatThread({ path: { thread_id: threadId } }),
    );
  },
  deleteThread(threadId: string) {
    return typed<any>(
      openApiV1.deleteChatThread({ path: { thread_id: threadId } }),
    );
  },
  sendThreadMessage(threadId: string, payload: ChatThreadMessageRequest) {
    return typed<any>(
      openApiV1.sendChatThreadMessage({
        path: { thread_id: threadId },
        body: payload,
      }) as any,
    );
  },
  sendThreadMessageUrl(threadId: string) {
    return `/api/v1/chat/threads/${encodeURIComponent(threadId)}/messages`;
  },
  listProjects() {
    return typed<any>(openApiV1.listChatProjects());
  },
  createProject(payload: ChatProjectRequest) {
    return typed<any>(openApiV1.createChatProject({ body: payload }));
  },
  getProject(projectId: string) {
    return typed<any>(
      openApiV1.getChatProject({ path: { project_id: projectId } }),
    );
  },
  updateProject(projectId: string, payload: ChatProjectRequest) {
    return typed<any>(
      openApiV1.updateChatProject({
        path: { project_id: projectId },
        body: payload,
      }),
    );
  },
  deleteProject(projectId: string) {
    return typed<any>(
      openApiV1.deleteChatProject({ path: { project_id: projectId } }),
    );
  },
  listProjectSessions(projectId: string) {
    return typed<any>(
      openApiV1.listChatProjectSessions({ path: { project_id: projectId } }),
    );
  },
  addProjectSession(projectId: string, sessionId: string) {
    return typed<any>(
      openApiV1.addChatProjectSession({
        path: { project_id: projectId, session_id: sessionId },
      }),
    );
  },
  removeProjectSession(sessionId: string) {
    return typed<any>(
      openApiV1.removeChatProjectSession({ path: { session_id: sessionId } }),
    );
  },
};

export const fileApi = {
  upload(formData: FormData) {
    return typed<any>(
      openApiV1.uploadFile({ body: generatedFormData(formData) }),
    );
  },
  getByName(filename: string) {
    return openApiV1.getFileByName({
      query: { filename },
      responseType: 'blob',
    }) as Promise<AxiosResponse<Blob>>;
  },
  byNameUrl(filename: string) {
    return `/api/v1/files/content?filename=${encodeURIComponent(filename)}`;
  },
  contentUrl(attachmentId: string) {
    return `/api/v1/files/${encodeURIComponent(attachmentId)}/content`;
  },
  tokenUrl(fileToken: string) {
    return `/api/v1/files/tokens/${encodeURIComponent(fileToken)}`;
  },
};

export const sessionApi = {
  list(params?: SessionListParams) {
    return typed<any>(openApiV1.listSessions({ query: generatedQuery(params) }));
  },
  activeUmos() {
    return typed<any>(openApiV1.listActiveUmos());
  },
  listRules(params?: SessionRuleListParams) {
    return typed<any>(
      openApiV1.listSessionRules({ query: generatedQuery(params) }),
    );
  },
  upsertRule(payload: SessionRuleRequest) {
    return typed<any>(openApiV1.upsertSessionRule({ body: payload }));
  },
  deleteRules(payload: UmoListRequest) {
    return typed<any>(openApiV1.deleteSessionRules({ body: payload }));
  },
  batchUpdateProvider(payload: BatchSessionProviderRequest) {
    return typed<any>(
      openApiV1.batchUpdateSessionProvider({ body: payload }),
    );
  },
  batchUpdateService(payload: BatchSessionServiceRequest) {
    return typed<any>(
      openApiV1.batchUpdateSessionService({ body: payload }),
    );
  },
  listGroups() {
    return typed<any>(openApiV1.listSessionGroups());
  },
  createGroup(payload: SessionGroupRequest) {
    return typed<any>(openApiV1.createSessionGroup({ body: payload }));
  },
  updateGroup(groupId: string, payload: SessionGroupRequest) {
    return typed<any>(
      openApiV1.updateSessionGroup({
        path: { group_id: groupId },
        body: payload,
      }),
    );
  },
  deleteGroup(groupId: string) {
    return typed<any>(
      openApiV1.deleteSessionGroup({ path: { group_id: groupId } }),
    );
  },
};

export const cronApi = {
  list(params?: CronJobListParams) {
    return typed<any>(openApiV1.listCronJobs({ query: generatedQuery(params) }));
  },
  create(payload: CronJobRequest) {
    return typed<any>(openApiV1.createCronJob({ body: payload }));
  },
  update(jobId: string, payload: CronJobPatchRequest) {
    return typed<any>(
      openApiV1.updateCronJob({ path: { job_id: jobId }, body: payload }),
    );
  },
  delete(jobId: string) {
    return typed<any>(openApiV1.deleteCronJob({ path: { job_id: jobId } }));
  },
  run(jobId: string) {
    return typed<any>(openApiV1.runCronJob({ path: { job_id: jobId } }));
  },
};

export const subagentApi = {
  getConfig() {
    return typed<OpenConfig>(openApiV1.getSubagentConfig());
  },
  updateConfig(config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updateSubagentConfig({ body: config }),
    );
  },
  availableTools() {
    return typed<any>(openApiV1.listSubagentAvailableTools());
  },
};

export const commandApi = {
  list(configId?: string) {
    return typed<CommandListData>(
      openApiV1.listCommands({
        query: configId ? { config_id: configId } : undefined,
      }),
    );
  },
  conflicts() {
    return typed<OpenConfig>(openApiV1.listCommandConflicts());
  },
  update(commandId: string, patch: CommandPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateCommand({
        path: { command_id: commandId },
        body: patch,
      }),
    );
  },
};

export const toolApi = {
  list(params?: ToolListParams) {
    return typed<any[]>(openApiV1.listTools({ query: generatedQuery(params) }));
  },
  setEnabled(toolId: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setToolEnabled({
        path: { tool_id: toolId },
        body: { enabled },
      }),
    );
  },
  setPermission(toolId: string, permission: 'admin' | 'member') {
    return typed<OpenConfig>(
      openApiV1.setToolPermission({
        path: { tool_id: toolId },
        body: { permission },
      }),
    );
  },
};

export const mcpApi = {
  list() {
    return typed<OpenConfig[]>(openApiV1.listMcpServers());
  },
  create(config: McpServerConfig) {
    return typed<OpenConfig>(openApiV1.createMcpServer({ body: config }));
  },
  update(serverName: string, config: McpServerConfig) {
    return typed<OpenConfig>(
      openApiV1.updateMcpServerByName({
        body: { server_name: serverName, config },
      }),
    );
  },
  delete(serverName: string) {
    return typed<OpenConfig>(
      openApiV1.deleteMcpServerByName({ query: { server_name: serverName } }),
    );
  },
  setEnabled(serverName: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setMcpServerEnabledByName({
        body: { server_name: serverName, enabled },
      }),
    );
  },
  test(serverName: string, config?: DynamicConfig) {
    return typed<OpenConfig>(
      openApiV1.testMcpServerByName({
        body: {
          server_name: serverName,
          ...(config ? { mcp_server_config: config } : {}),
        },
      }),
    );
  },
  syncModelScope(payload?: ModelScopeSyncRequest) {
    return typed<OpenConfig>(
      openApiV1.syncModelScopeMcpServers({ body: payload }),
    );
  },
};

export const t2iApi = {
  listTemplates() {
    return typed<OpenConfig[]>(openApiV1.listT2iTemplates());
  },
  getTemplate(name: string) {
    return typed<{ name: string; content: string }>(
      openApiV1.getT2iTemplate({ path: { name } }),
    );
  },
  createTemplate(payload: T2iTemplateRequest) {
    return typed<OpenConfig>(
      openApiV1.createT2iTemplate({ body: payload }),
    );
  },
  updateTemplate(name: string, content: string) {
    return typed<OpenConfig>(
      openApiV1.updateT2iTemplate({
        path: { name },
        body: { content },
      }),
    );
  },
  deleteTemplate(name: string) {
    return typed<OpenConfig>(
      openApiV1.deleteT2iTemplate({ path: { name } }),
    );
  },
  getActiveTemplate() {
    return typed<{ active_template?: string }>(openApiV1.getActiveT2iTemplate());
  },
  setActiveTemplate(name: string) {
    return typed<OpenConfig>(
      openApiV1.setActiveT2iTemplate({ body: { name } }),
    );
  },
  resetDefaultTemplate() {
    return typed<OpenConfig>(openApiV1.resetDefaultT2iTemplate());
  },
};

export const logApi = {
  history() {
    return typed<{ logs?: OpenConfig[] }>(openApiV1.getLogHistory());
  },
  liveUrl() {
    return '/api/v1/logs/live';
  },
};

export const pluginApi = {
  list(params?: { include_reserved?: boolean; enabled?: boolean }) {
    return typed<any[]>(openApiV1.listPlugins({ query: params }));
  },
  get(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginById({ query: { plugin_id: pluginId } }),
    );
  },
  failed() {
    return typed<Record<string, OpenConfig>>(openApiV1.listFailedPlugins());
  },
  reloadFailed(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.reloadFailedPlugin({ path: { plugin_id: pluginId } }),
    );
  },
  uninstallFailed(
    pluginId: string,
    options?: { delete_config?: boolean; delete_data?: boolean },
  ) {
    return typed<OpenConfig>(
      openApiV1.uninstallFailedPlugin({
        path: { plugin_id: pluginId },
        body: options,
      }),
    );
  },
  uninstall(
    pluginId: string,
    options?: { delete_config?: boolean; delete_data?: boolean },
  ) {
    return typed<OpenConfig>(
      openApiV1.uninstallPluginById({
        query: { plugin_id: pluginId },
        body: options,
      }),
    );
  },
  reload(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.reloadPluginById({ body: { plugin_id: pluginId } }),
    );
  },
  setEnabled(pluginId: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setPluginEnabledById({
        body: { plugin_id: pluginId, enabled },
      }),
    );
  },
  update(pluginId: string, body?: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePlugins({
        body: { plugin_id: pluginId, ...(body || {}) } as any,
      }),
    );
  },
  updateMany(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePlugins({ body: body as any }),
    );
  },
  checkVersionSupport(payload: PluginVersionSupportRequest) {
    return typed<any>(
      openApiV1.checkPluginVersionSupport({ body: payload }),
    );
  },
  config(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginConfigById({ query: { plugin_id: pluginId } }),
    );
  },
  updateConfig(pluginId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePluginConfigById({
        body: { plugin_id: pluginId, config },
      }),
    );
  },
  listConfigFiles(pluginId: string, configKey: string) {
    return typed<any>(
      openApiV1.listPluginConfigFilesById({
        query: { plugin_id: pluginId, config_key: configKey },
      }),
    );
  },
  uploadConfigFiles(pluginId: string, configKey: string, formData: FormData) {
    return typed<any>(
      openApiV1.uploadPluginConfigFilesById({
        query: { plugin_id: pluginId, config_key: configKey },
        body: generatedFormData(formData),
      }),
    );
  },
  deleteConfigFile(pluginId: string, payload: PluginConfigFileDeleteRequest) {
    return typed<OpenConfig>(
      openApiV1.deletePluginConfigFileById({
        query: { plugin_id: pluginId },
        body: payload,
      }),
    );
  },
  readme(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginReadmeById({ query: { plugin_id: pluginId } }),
    );
  },
  changelog(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginChangelogById({ query: { plugin_id: pluginId } }),
    );
  },
  market(params?: {
    page?: number;
    page_size?: number;
    category?: string;
    sort?: 'recommended' | 'downloads' | 'updated' | 'name';
    keyword?: string;
    force_refresh?: boolean;
    custom_registry?: string;
  }) {
    return typed<any>(openApiV1.listPluginMarket({ query: params }));
  },
  sources() {
    return typed<any>(openApiV1.listPluginSources());
  },
  replaceSources(sources: OpenConfig[]) {
    return typed<OpenConfig>(
      openApiV1.replacePluginSources({ body: { sources: sources as any } }),
    );
  },
  installUpload(formData: FormData) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromUpload({
        body: generatedFormData(formData),
      }),
    );
  },
  installGithub(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromGithub({ body: body as any }),
    );
  },
  installUrl(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromUrl({ body: body as any }),
    );
  },
  validateRepo(body: PluginValidateRepoRequest) {
    return typed<OpenConfig>(
      openApiV1.validatePluginRepo({ body }),
    );
  },
  bindSource(pluginId: string, body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.bindPluginSource({
        path: { plugin_id: pluginId },
        body: body as any,
      }),
    );
  },
  page(pluginId: string, pageName: string) {
    return typed<any>(
      openApiV1.getPluginPageById({
        query: { plugin_id: pluginId, page_name: pageName },
      }) as any,
    );
  },
};

export const pluginExtensionApi = {
  get<T = any>(pluginPath: string, config?: AxiosRequestConfig) {
    return apiV1Client.get<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      config,
    );
  },
  post<T = any>(
    pluginPath: string,
    data?: unknown,
    config?: AxiosRequestConfig,
  ) {
    return apiV1Client.post<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      data,
      config,
    );
  },
  put<T = any>(pluginPath: string, data?: unknown, config?: AxiosRequestConfig) {
    return apiV1Client.put<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      data,
      config,
    );
  },
  patch<T = any>(pluginPath: string, data?: unknown, config?: AxiosRequestConfig) {
    return apiV1Client.patch<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      data,
      config,
    );
  },
  delete<T = any>(pluginPath: string, config?: AxiosRequestConfig) {
    return apiV1Client.delete<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      config,
    );
  },
};

export const knowledgeApi = {
  list(params?: { page?: number; page_size?: number; refresh_stats?: boolean }) {
    return typed<any>(openApiV1.listKnowledgeBases({ query: params }));
  },
  get(kbId: string) {
    return typed<OpenConfig>(
      openApiV1.getKnowledgeBase({ path: { kb_id: kbId } }),
    );
  },
  create(config: KnowledgeBaseCreateRequest) {
    return typed<OpenConfig>(
      openApiV1.createKnowledgeBase({ body: config }),
    );
  },
  update(kbId: string, config: KnowledgeBaseRequest) {
    return typed<OpenConfig>(
      openApiV1.updateKnowledgeBase({
        path: { kb_id: kbId },
        body: config,
      }),
    );
  },
  delete(kbId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteKnowledgeBase({ path: { kb_id: kbId } }),
    );
  },
  documents(kbId: string, params?: { page?: number; page_size?: number; search?: string }) {
    return typed<any>(
      openApiV1.listKnowledgeDocuments({
        path: { kb_id: kbId },
        query: params,
      }),
    );
  },
  uploadDocument(kbId: string, formData: FormData) {
    return typed<any>(
      openApiV1.uploadKnowledgeDocument({
        path: { kb_id: kbId },
        body: generatedFormData(formData),
      }),
    );
  },
  importDocumentFromUrl(kbId: string, payload: OpenConfig) {
    return typed<any>(
      openApiV1.importKnowledgeDocumentFromUrl({
        path: { kb_id: kbId },
        body: payload as any,
      }),
    );
  },
  task(taskId: string) {
    return typed<any>(
      openApiV1.getKnowledgeTask({ path: { task_id: taskId } }),
    );
  },
  document(kbId: string, documentId: string) {
    return typed<OpenConfig>(
      openApiV1.getKnowledgeDocument({
        path: { kb_id: kbId, document_id: documentId },
      }),
    );
  },
  deleteDocument(kbId: string, documentId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteKnowledgeDocument({
        path: { kb_id: kbId, document_id: documentId },
      }),
    );
  },
  chunks(
    kbId: string,
    params?: { document_id?: string; page?: number; page_size?: number },
  ) {
    return typed<any>(
      openApiV1.listKnowledgeChunks({
        path: { kb_id: kbId },
        query: params,
      }),
    );
  },
  deleteChunk(kbId: string, chunkId: string, documentId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteKnowledgeChunk({
        path: { kb_id: kbId, chunk_id: chunkId },
        query: { document_id: documentId },
      }),
    );
  },
  retrieve(kbId: string, payload: OpenConfig) {
    return typed<any>(
      openApiV1.retrieveKnowledgeBase({
        path: { kb_id: kbId },
        body: payload as any,
      }),
    );
  },
};

export const skillApi = {
  list(params?: { enabled?: boolean; source?: string }) {
    return typed<any>(openApiV1.listSkills({ query: params }));
  },
  uploadBatch(files: File[]) {
    return typed<any>(
      openApiV1.uploadSkillsBatch({ body: { files } }),
    );
  },
  setEnabled(skillName: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.updateSkillByName({
        body: { skill_name: skillName, enabled },
      }),
    );
  },
  delete(skillName: string) {
    return typed<OpenConfig>(
      openApiV1.deleteSkillByName({ query: { skill_name: skillName } }),
    );
  },
  download(skillName: string) {
    return openApiV1.downloadSkillByName({
      query: { skill_name: skillName },
      responseType: 'blob',
    });
  },
  listFiles(skillName: string, path = '') {
    return typed<any>(
      openApiV1.listSkillFilesByName({
        query: { skill_name: skillName, ...(path ? { path } : {}) },
      }),
    );
  },
  getFile(skillName: string, path: string) {
    return typed<any>(
      openApiV1.getSkillFileByName({
        query: { skill_name: skillName, path },
      }),
    );
  },
  updateFile(skillName: string, path: string, content: string) {
    return typed<OpenConfig>(
      openApiV1.updateSkillFileByName({
        body: { skill_name: skillName, path, content },
      }),
    );
  },
  neoCandidates(params?: { skill_key?: string; status?: string }) {
    return typed<any>(openApiV1.listNeoSkillCandidates({ query: params }));
  },
  neoReleases(params?: { skill_key?: string; stage?: string }) {
    return typed<any>(openApiV1.listNeoSkillReleases({ query: params }));
  },
  neoPayload(payloadRef: string) {
    return typed<any>(
      openApiV1.getNeoSkillPayload({ query: { payload_ref: payloadRef } }),
    );
  },
  evaluateNeoCandidate(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.evaluateNeoSkillCandidate({ body: body as any }),
    );
  },
  promoteNeoCandidate(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.promoteNeoSkillCandidate({ body: body as any }),
    );
  },
  rollbackNeoRelease(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.rollbackNeoSkillRelease({ body: body as any }),
    );
  },
  syncNeoRelease(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.syncNeoSkillRelease({ body: body as any }),
    );
  },
  deleteNeoCandidate(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.deleteNeoSkillCandidate({ body: body as any }),
    );
  },
  deleteNeoRelease(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.deleteNeoSkillRelease({ body: body as any }),
    );
  },
};

export const personaApi = {
  tree() {
    return typed<any>(openApiV1.getPersonaTree());
  },
  folders(parentId?: string | null) {
    return typed<any[]>(
      openApiV1.listPersonaFolders({
        query:
          parentId === undefined ? undefined : { parent_id: parentId ?? '' },
      }),
    );
  },
  createFolder(folder: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createPersonaFolder({ body: folder as any }),
    );
  },
  updateFolder(folderId: string, folder: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePersonaFolder({
        path: { folder_id: folderId },
        body: folder as any,
      }),
    );
  },
  deleteFolder(folderId: string) {
    return typed<OpenConfig>(
      openApiV1.deletePersonaFolder({ path: { folder_id: folderId } }),
    );
  },
  list(folderId?: string | null) {
    return typed<any[]>(
      openApiV1.listPersonas({
        query:
          folderId === undefined ? undefined : { folder_id: folderId ?? '' },
      }),
    );
  },
  get(personaId: string) {
    return typed<OpenConfig>(
      openApiV1.getPersonaById({ query: { persona_id: personaId } }),
    );
  },
  create(persona: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createPersona({ body: persona as any }),
    );
  },
  update(personaId: string, persona: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePersonaById({
        body: { persona_id: personaId, ...persona } as any,
      }),
    );
  },
  delete(personaId: string) {
    return typed<OpenConfig>(
      openApiV1.deletePersonaById({ query: { persona_id: personaId } }),
    );
  },
  move(personaId: string, folderId: string | null) {
    return typed<OpenConfig>(
      openApiV1.movePersonaItem({
        body: { persona_id: personaId, folder_id: folderId } as any,
      }),
    );
  },
  reorder(items: any[]) {
    return typed<OpenConfig>(
      openApiV1.reorderPersonaItems({ body: { items } as any }),
    );
  },
};

export const conversationApi = {
  list(params?: ListConversationsQuery, requestConfig?: AxiosRequestConfig) {
    return typed<any>(
      openApiV1.listConversations(
        generatedOptions(
          { query: generatedQuery(params) },
          requestConfig,
        ),
      ),
    );
  },
  get(userId: string, cid: string) {
    return typed<any>(
      openApiV1.getConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
      }),
    );
  },
  update(userId: string, cid: string, payload: ConversationPatchRequest) {
    return typed<any>(
      openApiV1.updateConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
        body: payload,
      }),
    );
  },
  replaceMessages(
    userId: string,
    cid: string,
    payload: ConversationMessagesReplaceRequest,
  ) {
    return typed<any>(
      openApiV1.replaceConversationMessages({
        path: { conversation_id: cid },
        query: { user_id: userId },
        body: payload,
      }),
    );
  },
  delete(userId: string, cid: string) {
    return typed<any>(
      openApiV1.deleteConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
      }),
    );
  },
  batchDelete(payload: ConversationBatchDeleteRequest) {
    return typed<any>(openApiV1.batchDeleteConversations({ body: payload }));
  },
  export(payload: ConversationExportRequest) {
    return openApiV1.exportConversations({
      body: payload,
      responseType: 'blob',
    }) as Promise<AxiosResponse<Blob>>;
  },
};

export const statsApi = {
  get(offsetSec?: number) {
    return typed<any>(
      openApiV1.getStats({
        query: offsetSec === undefined ? undefined : { offset_sec: offsetSec },
      }),
    );
  },
  providerTokens(days?: number) {
    return typed<any>(
      openApiV1.getProviderTokenStats({
        query: days === undefined ? undefined : { days },
      }),
    );
  },
  version() {
    return withLegacyFallback<VersionData>(openApiV1.getVersion(), () =>
      httpClient.get<ApiEnvelope<VersionData>>('/api/stat/version'),
    );
  },
  firstNotice(locale?: string) {
    return typed<{ content?: string | null }>(
      openApiV1.getFirstNotice({
        query: locale ? { locale } : undefined,
      }),
    );
  },
  testGhproxy(payload: GhproxyTestRequest) {
    return withLegacyFallback<{ latency?: number }>(
      openApiV1.testGhproxyConnection({ body: payload }),
      () =>
        httpClient.post<ApiEnvelope<{ latency?: number }>>(
          '/api/stat/test-ghproxy-connection',
          payload,
        ),
    );
  },
  startTime() {
    const v1Request = typed<StartTimeData>(openApiV1.getStartTime());
    const legacyRequest = httpClient.get<ApiEnvelope<StartTimeData>>(
      '/api/stat/start-time',
    );

    // Restart polling must also work after downgrading to backends without v1 stats routes.
    return firstSuccessfulResponse<StartTimeData>([v1Request, legacyRequest]);
  },
  restart() {
    return withLegacyFallback<OpenConfig>(openApiV1.restartCore(), () =>
      httpClient.post<ApiEnvelope<OpenConfig>>('/api/stat/restart-core'),
    );
  },
  storage() {
    return typed<OpenConfig>(openApiV1.getStorageStatus());
  },
  cleanupStorage(target?: string) {
    return typed<OpenConfig>(
      openApiV1.cleanupStorage({
        body: target ? { target } : undefined,
      }),
    );
  },
};

export const publicApi = {
  versions() {
    return withLegacyFallback<PublicVersionData>(
      openApiV1.getPublicVersions(),
      () => httpClient.get<ApiEnvelope<PublicVersionData>>('/api/stat/versions'),
    );
  },
};

export const changelogApi = {
  listVersions() {
    return typed<{ versions?: string[] }>(openApiV1.listChangelogVersions());
  },
  get(version: string) {
    return typed<{ content?: string }>(
      openApiV1.getChangelog({ path: { version } }),
    );
  },
};
