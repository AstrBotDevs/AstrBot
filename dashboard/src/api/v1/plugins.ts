import {
  generatedFormData,
  generatedOptions,
  httpClient,
  openApiV1,
  typed,
} from './shared';
import { fetchWithAuth } from '../http';
import type {
  ApiEnvelope,
  AxiosRequestConfig,
  AxiosResponse,
  PluginBatchUpdateRequest,
  PluginConfigFileDeleteRequest,
  PluginDashboardAction,
  PluginDashboardCatalog,
  PluginDashboardFileTicket,
  PluginDashboardPage,
  PluginDashboardSession,
  PluginGithubInstallRequest,
  PluginSourceBindRequest,
  PluginSourceRequest,
  PluginUpdateRequest,
  PluginUrlInstallRequest,
} from './shared';
import { notifyPluginDashboardLifecycle } from './lifecycle';
import type {
  OpenConfig,
  PluginConfigFilesData,
  PluginConfigUploadData,
  PluginData,
} from './types';

const nativeFetch =
  typeof window === 'undefined' ? fetch : window.fetch.bind(window);

export const pluginApi = {
  list(params?: { include_reserved?: boolean; enabled?: boolean }) {
    return typed<PluginData[]>(openApiV1.listPlugins({ query: params }));
  },
  get(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPlugin({ path: { plugin_id: pluginId } }),
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
    const response = typed<OpenConfig>(
      openApiV1.uninstallPlugin({
        path: { plugin_id: pluginId },
        body: options,
      }),
    );
    void response.then((result) => {
      if (result.data.status === 'ok') {
        notifyPluginDashboardLifecycle({
          reason: 'plugin_changed',
          plugin_name: pluginId,
        });
      }
    });
    return response;
  },
  reload(pluginId: string) {
    const response = typed<OpenConfig>(
      openApiV1.reloadPlugin({ path: { plugin_id: pluginId } }),
    );
    void response.then((result) => {
      if (result.data.status === 'ok') {
        notifyPluginDashboardLifecycle({
          reason: 'plugin_changed',
          plugin_name: pluginId,
        });
      }
    });
    return response;
  },
  setEnabled(pluginId: string, enabled: boolean) {
    const response = typed<OpenConfig>(
      openApiV1.setPluginEnabled({
        path: { plugin_id: pluginId },
        body: { enabled },
      }),
    );
    if (!enabled) {
      void response.then((result) => {
        if (result.data.status === 'ok') {
          notifyPluginDashboardLifecycle({
            reason: 'plugin_changed',
            plugin_name: pluginId,
          });
        }
      });
    }
    return response;
  },
  update(pluginId: string, body?: PluginUpdateRequest, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.updatePlugin({
        path: { plugin_id: pluginId },
        body,
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  updateMany(body: PluginBatchUpdateRequest, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.updatePlugins({
        body,
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  config(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginConfig({ path: { plugin_id: pluginId } }),
    );
  },
  updateConfig(pluginId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePluginConfig({
        path: { plugin_id: pluginId },
        body: { config },
      }),
    );
  },
  updateLogLevel(
    pluginId: string,
    level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | null,
  ) {
    return typed<OpenConfig>(
      openApiV1.updatePluginLogLevel({
        path: { plugin_id: pluginId },
        body: { level },
      }),
    );
  },
  listConfigFiles(pluginId: string, configKey: string) {
    return typed<PluginConfigFilesData>(
      openApiV1.listPluginConfigFiles({
        path: { plugin_id: pluginId, config_key: configKey },
      }),
    );
  },
  uploadConfigFiles(pluginId: string, configKey: string, formData: FormData) {
    return typed<PluginConfigUploadData>(
      openApiV1.uploadPluginConfigFiles({
        path: { plugin_id: pluginId, config_key: configKey },
        body: generatedFormData(formData) as Record<string, unknown>,
      }),
    );
  },
  deleteConfigFile(pluginId: string, payload: PluginConfigFileDeleteRequest) {
    return typed<OpenConfig>(
      openApiV1.deletePluginConfigFile({
        path: { plugin_id: pluginId },
        body: payload,
      }),
    );
  },
  readme(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginReadme({ path: { plugin_id: pluginId } }),
    );
  },
  changelog(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginChangelog({ path: { plugin_id: pluginId } }),
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
    return typed<OpenConfig>(openApiV1.listPluginMarket({ query: params }));
  },
  sources() {
    return typed<PluginSourceRequest[]>(openApiV1.listPluginSources());
  },
  replaceSources(sources: PluginSourceRequest[]) {
    return typed<OpenConfig>(
      openApiV1.replacePluginSources({ body: { sources } }),
    );
  },
  async installUpload(formData: FormData, stepUp?: string) {
    const response = await fetchWithAuth('/api/v1/plugins/install/upload', {
      method: 'POST',
      body: formData,
      headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(
        data?.message || `Plugin upload failed (${response.status})`,
      );
    }
    return { data } as AxiosResponse<ApiEnvelope<OpenConfig>>;
  },
  installGithub(body: PluginGithubInstallRequest, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromGithub({
        body,
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  installUrl(body: PluginUrlInstallRequest, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromUrl({
        body,
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  bindSource(pluginId: string, body: PluginSourceBindRequest) {
    return typed<OpenConfig>(
      openApiV1.bindPluginSource({
        path: { plugin_id: pluginId },
        body,
      }),
    );
  },
};

export const pluginDashboardApi = {
  catalog(extensionId: string, requestConfig?: AxiosRequestConfig) {
    return typed<PluginDashboardCatalog>(
      openApiV1.getPluginDashboardCatalog(
        generatedOptions(
          { path: { extension_id: extensionId } },
          requestConfig,
        ),
      ),
    );
  },
  createSession(
    extensionId: string,
    pageId: string,
    expectedGeneration: string,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<PluginDashboardSession>(
      openApiV1.createPluginDashboardPageSession(
        generatedOptions(
          {
            path: { extension_id: extensionId, page_id: pageId },
            body: {
              protocol_version: 1,
              expected_generation: expectedGeneration,
            },
          },
          requestConfig,
        ),
      ),
    );
  },
  invoke(
    extensionId: string,
    actionId: string,
    instanceId: string,
    expectedGeneration: string,
    payload: unknown,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<unknown>(
      openApiV1.invokePluginDashboardAction(
        generatedOptions(
          {
            path: { extension_id: extensionId, action_id: actionId },
            body: {
              protocol_version: 1,
              instance_id: instanceId,
              expected_generation: expectedGeneration,
              payload,
            },
          },
          requestConfig,
        ),
      ),
    );
  },
  upload(
    extensionId: string,
    actionId: string,
    instanceId: string,
    expectedGeneration: string,
    file: File,
    fields: unknown,
    requestConfig?: AxiosRequestConfig,
  ) {
    const formData = new FormData();
    formData.append(
      'metadata',
      new File(
        [
          JSON.stringify({
            protocol_version: 1,
            instance_id: instanceId,
            expected_generation: expectedGeneration,
            fields,
          }),
        ],
        'metadata.json',
        { type: 'application/json' },
      ),
    );
    formData.append('file', file);
    return typed<unknown>(
      httpClient.post(
        `/api/v1/plugins/${encodeURIComponent(extensionId)}/dashboard/uploads/${encodeURIComponent(actionId)}`,
        formData,
        requestConfig,
      ),
    );
  },
  createFileTicket(
    extensionId: string,
    actionId: string,
    instanceId: string,
    expectedGeneration: string,
    expectedDisposition: 'inline' | 'attachment',
    payload: unknown,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<PluginDashboardFileTicket>(
      openApiV1.invokePluginDashboardFile(
        generatedOptions(
          {
            path: { extension_id: extensionId, action_id: actionId },
            body: {
              protocol_version: 1,
              instance_id: instanceId,
              expected_generation: expectedGeneration,
              expected_disposition: expectedDisposition,
              payload,
            },
          },
          requestConfig,
        ),
      ),
    );
  },
  async readInlineTicket(
    ticket: PluginDashboardFileTicket,
    signal?: AbortSignal,
  ) {
    const ticketUrl = new URL(ticket.ticket_url, window.location.origin);
    if (
      ticketUrl.origin !== window.location.origin ||
      !ticketUrl.pathname.startsWith('/api/plugin-files/v1/') ||
      ticketUrl.search ||
      ticketUrl.hash
    ) {
      throw new Error('Invalid plugin file ticket');
    }
    const response = await nativeFetch(ticketUrl, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      redirect: 'error',
      signal,
    });
    if (!response.ok) throw new Error('Plugin file read failed');
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength !== ticket.size) {
      throw new Error('Plugin file size mismatch');
    }
    return bytes;
  },
};

export type {
  PluginDashboardAction,
  PluginDashboardCatalog,
  PluginDashboardFileTicket,
  PluginDashboardPage,
  PluginDashboardSession,
};
