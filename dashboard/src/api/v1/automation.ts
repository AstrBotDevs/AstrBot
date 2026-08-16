import { generatedOptions, generatedQuery, openApiV1, typed } from './shared';
import type {
  CommandPatchRequest,
  CronJobPatchRequest,
  CronJobRequest,
  DynamicConfig,
  McpServerConfig,
  ModelScopeSyncRequest,
  T2iTemplateRequest,
} from './shared';
import type { AxiosRequestConfig } from './shared';
import type {
  CommandListData,
  CronJobListParams,
  OpenConfig,
  ToolListParams,
} from './types';
import type { ToolItem } from '@/domain/tools';

export const cronApi = {
  list(params?: CronJobListParams) {
    return typed<OpenConfig[]>(
      openApiV1.listCronJobs({ query: generatedQuery(params) }),
    );
  },
  create(payload: CronJobRequest) {
    return typed<OpenConfig>(openApiV1.createCronJob({ body: payload }));
  },
  update(jobId: string, payload: CronJobPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateCronJob({ path: { job_id: jobId }, body: payload }),
    );
  },
  delete(jobId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteCronJob({ path: { job_id: jobId } }),
    );
  },
  run(jobId: string) {
    return typed<OpenConfig>(openApiV1.runCronJob({ path: { job_id: jobId } }));
  },
};

export const subagentApi = {
  getConfig() {
    return typed<OpenConfig>(openApiV1.getSubagentConfig());
  },
  updateConfig(config: OpenConfig) {
    return typed<OpenConfig>(openApiV1.updateSubagentConfig({ body: config }));
  },
  availableTools() {
    return typed<OpenConfig>(openApiV1.listSubagentAvailableTools());
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
    return typed<ToolItem[]>(
      openApiV1.listTools({ query: generatedQuery(params) }),
    );
  },
  setEnabled(toolId: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setToolEnabled({
        path: { tool_id: toolId },
        body: { enabled },
      }),
    );
  },
  setParallelEnabled(enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setParallelEnabled({ body: { enabled } }),
    );
  },
  setParallel(toolId: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setToolParallel({
        path: { tool_id: toolId },
        body: { enabled },
      }),
    );
  },
};

export const mcpApi = {
  list() {
    return typed<OpenConfig[]>(openApiV1.listMcpServers());
  },
  create(config: McpServerConfig, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.createMcpServer(
        generatedOptions({ body: config }, requestConfig),
      ),
    );
  },
  update(
    serverName: string,
    config: McpServerConfig,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<OpenConfig>(
      openApiV1.updateMcpServer(
        generatedOptions(
          {
            path: { server_name: serverName },
            body: config,
          },
          requestConfig,
        ),
      ),
    );
  },
  delete(serverName: string, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.deleteMcpServer(
        generatedOptions({ path: { server_name: serverName } }, requestConfig),
      ),
    );
  },
  setEnabled(
    serverName: string,
    enabled: boolean,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<OpenConfig>(
      openApiV1.setMcpServerEnabled(
        generatedOptions(
          {
            path: { server_name: serverName },
            body: { enabled },
          },
          requestConfig,
        ),
      ),
    );
  },
  test(serverName: string, config?: DynamicConfig) {
    return typed<OpenConfig>(
      openApiV1.testMcpServer({
        path: { server_name: serverName },
        body: config ? { name: serverName, ...config } : undefined,
      }),
    );
  },
  catalog(serverName: string) {
    return typed<OpenConfig>(
      openApiV1.getMcpCatalog({ path: { server_name: serverName } }),
    );
  },
  resources(serverName: string) {
    return typed<OpenConfig>(
      openApiV1.listMcpResources({ path: { server_name: serverName } }),
    );
  },
  resourceTemplates(serverName: string) {
    return typed<OpenConfig>(
      openApiV1.listMcpResourceTemplates({
        path: { server_name: serverName },
      }),
    );
  },
  readResource(serverName: string, uri: string) {
    return typed<OpenConfig>(
      openApiV1.readMcpResource({
        path: { server_name: serverName },
        body: { uri },
      }),
    );
  },
  prompts(serverName: string) {
    return typed<OpenConfig>(
      openApiV1.listMcpPrompts({ path: { server_name: serverName } }),
    );
  },
  getPrompt(
    serverName: string,
    promptName: string,
    promptArguments?: Record<string, string>,
  ) {
    return typed<OpenConfig>(
      openApiV1.getMcpPrompt({
        path: { server_name: serverName, prompt_name: promptName },
        body: promptArguments ? { arguments: promptArguments } : undefined,
      }),
    );
  },
  complete(
    serverName: string,
    reference: DynamicConfig,
    argument: Record<string, string>,
    contextArguments?: Record<string, string>,
  ) {
    return typed<OpenConfig>(
      openApiV1.completeMcp({
        path: { server_name: serverName },
        body: {
          reference,
          argument,
          context_arguments: contextArguments,
        },
      }),
    );
  },
  oauthStatus(serverName: string) {
    return typed<OpenConfig>(
      openApiV1.getMcpOAuthStatus({ path: { server_name: serverName } }),
    );
  },
  startOAuth(serverName: string, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.startMcpOAuth(
        generatedOptions({ path: { server_name: serverName } }, requestConfig),
      ),
    );
  },
  revokeOAuth(serverName: string, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.revokeMcpOAuth(
        generatedOptions({ path: { server_name: serverName } }, requestConfig),
      ),
    );
  },
  syncModelScope(
    payload?: ModelScopeSyncRequest,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<OpenConfig>(
      openApiV1.syncModelScopeMcpServers(
        generatedOptions({ body: payload }, requestConfig),
      ),
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
    return typed<OpenConfig>(openApiV1.createT2iTemplate({ body: payload }));
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
    return typed<OpenConfig>(openApiV1.deleteT2iTemplate({ path: { name } }));
  },
  getActiveTemplate() {
    return typed<{ active_template?: string }>(
      openApiV1.getActiveT2iTemplate(),
    );
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
  history(filters?: { category?: string[]; privacy?: string[] }) {
    return typed<{ logs?: OpenConfig[] }>(
      openApiV1.getLogHistory({ query: filters }),
    );
  },
  liveUrl(filters?: { category?: string[]; privacy?: string[] }) {
    const params = new URLSearchParams();
    for (const category of filters?.category || []) {
      params.append('category', category);
    }
    for (const privacy of filters?.privacy || []) {
      params.append('privacy', privacy);
    }
    const query = params.toString();
    return `/api/v1/logs/live${query ? `?${query}` : ''}`;
  },
};
