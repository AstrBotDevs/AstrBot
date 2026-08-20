<template>
  <div class="tools-page">
    <v-container fluid class="pa-0">
      <!-- MCP 服务器部分 -->
      <div v-if="mcpServers.length === 0" class="text-center pa-8">
        <v-icon size="64" color="on-surface-variant">mdi-server-off</v-icon>
        <p class="text-medium-emphasis mt-4">{{ tm('mcpServers.empty') }}</p>
      </div>

      <div v-else class="mcp-server-list">
        <OutlinedActionListItem
          v-for="server in mcpServers || []"
          :key="server.name"
          :title="server.name"
          clickable
          @click="editServer(server)"
        >
          <div
            class="mcp-server-config text-body-2 text-medium-emphasis"
            :title="getServerConfigSummary(server)"
          >
            <v-icon
              :icon="getServerConfigIcon(server)"
              size="small"
              class="me-1"
            />
            <span>{{ getServerConfigSummary(server) }}</span>
          </div>

          <div class="mcp-server-tools text-caption text-medium-emphasis">
            <template v-if="server.tools && server.tools.length > 0">
              <v-dialog max-width="600px" scrollable>
                <template #activator="{ props: listToolsProps }">
                  <button
                    v-bind="listToolsProps"
                    class="mcp-server-tools__button"
                    type="button"
                    @click.stop
                  >
                    <v-icon size="small" class="me-1">mdi-tools</v-icon>
                    {{
                      tm('mcpServers.status.availableTools', {
                        count: server.tools.length,
                      })
                    }}
                    ({{ server.tools.length }})
                  </button>
                </template>
                <template #default="{ isActive }">
                  <v-card class="app-dialog mcp-dialog__card mcp-tools-dialog">
                    <v-card-title class="d-flex align-center">
                      <span>{{ tm('mcpServers.status.availableTools') }}</span>
                    </v-card-title>
                    <v-card-text class="mcp-dialog__content">
                      <ul>
                        <li
                          v-for="(tool, idx) in server.tools"
                          :key="idx"
                          class="mcp-tools-dialog__item"
                        >
                          {{ tool }}
                        </li>
                      </ul>
                    </v-card-text>
                    <v-card-actions
                      class="d-flex justify-end mcp-dialog__actions"
                    >
                      <v-btn
                        variant="text"
                        color="primary"
                        @click="isActive.value = false"
                      >
                        Close
                      </v-btn>
                    </v-card-actions>
                  </v-card>
                </template>
              </v-dialog>
            </template>
            <template v-else>
              <v-icon size="small" color="warning" class="me-1">
                mdi-alert-circle
              </v-icon>
              {{ tm('mcpServers.status.noTools') }}
            </template>
          </div>

          <div
            v-if="server.connection_status"
            class="text-caption text-medium-emphasis"
          >
            {{
              tm('mcpServers.status.runtime', {
                status: server.connection_status,
                resources: server.resource_count || 0,
                prompts: server.prompt_count || 0,
              })
            }}
          </div>

          <template #actions>
            <v-tooltip :text="tm('mcpServers.buttons.catalog')" location="top">
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  icon="mdi-database-search-outline"
                  variant="text"
                  size="small"
                  class="list-action-icon-btn"
                  @click.stop="openCatalog(server)"
                />
              </template>
            </v-tooltip>
            <v-tooltip
              v-if="server.auth_ref"
              :text="tm('mcpServers.buttons.authorize')"
              location="top"
            >
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  icon="mdi-shield-key-outline"
                  variant="text"
                  size="small"
                  class="list-action-icon-btn"
                  @click.stop="startAuthorization(server)"
                />
              </template>
            </v-tooltip>
            <v-tooltip :text="t('core.common.itemCard.delete')" location="top">
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  icon="mdi-delete-outline"
                  variant="text"
                  size="small"
                  class="list-action-icon-btn"
                  @click.stop="deleteServer(server)"
                />
              </template>
            </v-tooltip>
          </template>

          <template #control>
            <v-progress-circular
              v-if="mcpServerUpdateLoaders[server.name]"
              indeterminate
              color="primary"
              size="18"
            />

            <v-tooltip location="top">
              <template #activator="{ props }">
                <v-switch
                  v-bind="props"
                  color="primary"
                  density="compact"
                  hide-details
                  inset
                  :model-value="server.active"
                  :loading="mcpServerUpdateLoaders[server.name] || false"
                  :disabled="mcpServerUpdateLoaders[server.name] || false"
                  @click.stop
                  @update:model-value="updateServerStatus(server)"
                />
              </template>
              <span>{{
                server.active
                  ? t('core.common.itemCard.enabled')
                  : t('core.common.itemCard.disabled')
              }}</span>
            </v-tooltip>
          </template>
        </OutlinedActionListItem>
      </div>
    </v-container>

    <FloatingActionStack :label="tm('mcpServers.buttons.add')">
      <v-tooltip :text="tm('mcpServers.buttons.sync')" location="left">
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            color="primary"
            icon="mdi-sync"
            size="x-large"
            variant="elevated"
            class="mcp-fab"
            @click="showSyncMcpServerDialog = true"
          />
        </template>
      </v-tooltip>
      <v-tooltip :text="tm('mcpServers.buttons.add')" location="left">
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            color="primary"
            icon="mdi-plus"
            size="x-large"
            variant="elevated"
            class="mcp-fab"
            @click="showMcpServerDialog = true"
          />
        </template>
      </v-tooltip>
    </FloatingActionStack>

    <!-- 添加/编辑 MCP 服务器对话框 -->
    <v-dialog v-model="showMcpServerDialog" max-width="750px" scrollable>
      <v-card class="app-dialog mcp-dialog__card">
        <v-card-title class="pa-4 pl-6">
          <v-icon class="me-2">{{
            isEditMode ? 'mdi-pencil' : 'mdi-plus'
          }}</v-icon>
          <span>{{
            isEditMode
              ? tm('dialogs.addServer.editTitle')
              : tm('dialogs.addServer.title')
          }}</span>
        </v-card-title>

        <v-card-text class="py-4 mcp-dialog__content">
          <v-form ref="form" @submit.prevent="saveServer">
            <v-text-field
              v-model="currentServer.name"
              :label="tm('dialogs.addServer.fields.name')"
              variant="outlined"
              :rules="[
                (v) => !!v || tm('dialogs.addServer.fields.nameRequired'),
              ]"
              required
              class="mb-3"
            ></v-text-field>

            <div class="mb-2 d-flex align-center">
              <span class="text-subtitle-1">{{
                tm('dialogs.addServer.fields.config')
              }}</span>
              <v-spacer></v-spacer>
              <v-btn
                size="small"
                color="primary"
                variant="tonal"
                class="me-1"
                @click="setConfigTemplate('stdio')"
              >
                {{ tm('mcpServers.buttons.useTemplateStdio') }}
              </v-btn>
              <v-btn
                size="small"
                color="primary"
                variant="tonal"
                class="me-1"
                @click="setConfigTemplate('streamable_http')"
              >
                {{ tm('mcpServers.buttons.useTemplateStreamableHttp') }}
              </v-btn>
            </div>

            <small class="text-medium-emphasis"
              >*{{ tm('dialogs.addServer.tips.timeoutConfig') }}</small
            >

            <v-alert type="info" variant="tonal" density="compact" class="mt-3">
              {{ tm('dialogs.addServer.tips.transportRecommendation') }}
            </v-alert>

            <div class="monaco-container mcp-monaco-container">
              <VueMonacoEditor
                v-model:value="serverConfigJson"
                theme="vs-dark"
                language="json"
                :options="{
                  minimap: {
                    enabled: false,
                  },
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  lineNumbers: 'on',
                  roundedSelection: true,
                  tabSize: 2,
                }"
                @change="validateJson"
              />
            </div>

            <div v-if="jsonError" class="mt-2 text-error">
              <v-icon color="error" size="small" class="me-1"
                >mdi-alert-circle</v-icon
              >
              <span>{{ jsonError }}</span>
            </div>
          </v-form>
          <div class="mt-2">
            <small>{{ addServerDialogMessage }}</small>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 mcp-dialog__actions">
          <v-spacer></v-spacer>
          <v-btn variant="text" :disabled="loading" @click="closeServerDialog">
            {{ tm('dialogs.addServer.buttons.cancel') }}
          </v-btn>
          <v-btn
            variant="text"
            :disabled="loading"
            @click="testServerConnection"
          >
            {{ tm('dialogs.addServer.buttons.testConnection') }}
          </v-btn>
          <v-btn
            color="primary"
            :loading="loading"
            :disabled="!isServerFormValid"
            @click="saveServer"
          >
            {{ tm('dialogs.addServer.buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="showMcpCatalogDialog" max-width="760px" scrollable>
      <v-card class="app-dialog mcp-dialog__card">
        <v-card-title>{{
          tm('mcpServers.catalog.title', { name: catalogServerName })
        }}</v-card-title>
        <v-card-text class="mcp-dialog__content">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            {{ tm('mcpServers.catalog.untrusted') }}
          </v-alert>
          <div class="text-subtitle-2">
            {{ tm('mcpServers.catalog.resources') }}
          </div>
          <v-list density="compact">
            <v-list-item
              v-for="resource in catalogResources"
              :key="String(resource.uri)"
              :title="String(resource.name || resource.uri)"
              :subtitle="String(resource.uri)"
              @click="readCatalogResource(String(resource.uri))"
            />
          </v-list>
          <div class="text-subtitle-2">
            {{ tm('mcpServers.catalog.prompts') }}
          </div>
          <v-list density="compact">
            <v-list-item
              v-for="prompt in catalogPrompts"
              :key="String(prompt.name)"
              :title="String(prompt.title || prompt.name)"
              @click="getCatalogPrompt(String(prompt.name))"
            />
          </v-list>
          <pre v-if="catalogResult" class="mt-3 text-body-2">{{
            catalogResult
          }}</pre>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 同步 MCP 服务器对话框 -->
    <v-dialog
      v-model="showSyncMcpServerDialog"
      max-width="500px"
      persistent
      scrollable
    >
      <v-card class="app-dialog mcp-dialog__card">
        <v-card-title class="bg-primary text-white py-3">
          <span>同步外部平台 MCP 服务器</span>
        </v-card-title>

        <v-card-text class="py-4 mcp-dialog__content">
          <v-select
            v-model="selectedMcpServerProvider"
            :items="mcpServerProviderList"
            label="选择平台"
            variant="outlined"
            required
          ></v-select>
          <div v-if="selectedMcpServerProvider === 'modelscope'">
            <v-timeline align="start" side="end">
              <v-timeline-item icon="mdi-numeric-1" icon-color="on-primary">
                <div>
                  <div class="text-h4">发现 MCP 服务器</div>
                  <p class="mt-2">
                    访问
                    <a href="https://www.modelscope.cn/mcp" target="_blank"
                      >ModelScope 平台</a
                    >
                    浏览需要的 MCP 服务器。
                  </p>
                </div>
              </v-timeline-item>

              <v-timeline-item icon="mdi-numeric-2" icon-color="on-primary">
                <div>
                  <div class="text-h4">获取访问令牌</div>
                  <p class="mt-2">
                    从<a
                      href="https://modelscope.cn/my/myaccesstoken"
                      target="_blank"
                      >账户设置</a
                    >中获取个人访问令牌。
                  </p>
                </div>
              </v-timeline-item>

              <v-timeline-item icon="mdi-numeric-3" icon-color="on-primary">
                <div>
                  <div class="text-h4">输入您的访问令牌</div>
                  <p class="mt-2">输入您的访问令牌以同步 MCP 服务器。</p>
                  <v-text-field
                    v-model="mcpProviderToken"
                    type="password"
                    variant="outlined"
                    label="访问令牌"
                    class="mt-2"
                    hide-details
                  />
                </div>
              </v-timeline-item>
            </v-timeline>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 mcp-dialog__actions">
          <v-spacer></v-spacer>
          <v-btn
            variant="text"
            :disabled="loading"
            @click="showSyncMcpServerDialog = false"
          >
            {{ tm('dialogs.addServer.buttons.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            :loading="loading"
            :disabled="loading"
            @click="syncMcpServers"
          >
            {{ tm('dialogs.addServer.buttons.sync') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar
      :timeout="3000"
      elevation="4"
      :color="save_message_success"
      v-model="save_message_snack"
      location="top"
    >
      {{ save_message }}
    </v-snackbar>
    <DashboardStepUpDialog
      v-model="stepUpDialogOpen"
      :loading="stepUpLoading"
      :error-message="stepUpErrorMessage"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />
  </div>
</template>

<script setup lang="ts">
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import '@/utils/monacoLoader';
import { mcpApi } from '@/api/v1';
import type {
  DynamicConfig,
  McpServerConfig,
} from '@/api/generated/openapi-v1';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import OutlinedActionListItem from '@/components/shared/OutlinedActionListItem.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import FloatingActionStack from '@/components/ui/FloatingActionStack.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { stepUpHeaders } from '@/utils/stepUp';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import { resolveErrorMessage } from '@/utils/errorUtils';

type McpServerProvider = 'modelscope';
type SnackbarColor = 'success' | 'error';

interface McpServerItem extends McpServerConfig {
  name: string;
  active: boolean;
  tools: string[];
  connection_status?: string;
  protocol_version?: string;
  resource_count?: number;
  prompt_count?: number;
  auth_status?: string;
}

interface McpServerDraft {
  name: string;
  active: boolean;
}

const { t } = useI18n();
const { tm } = useModuleI18n('features/tooluse');
const confirmDialog = useConfirmDialog();
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const mcpServers = ref<McpServerItem[]>([]);
const showMcpServerDialog = ref(false);
const showMcpCatalogDialog = ref(false);
const catalogServerName = ref('');
const catalogResources = ref<Record<string, unknown>[]>([]);
const catalogPrompts = ref<Record<string, unknown>[]>([]);
const catalogResult = ref('');
const selectedMcpServerProvider = ref<McpServerProvider>('modelscope');
const mcpServerProviderList: McpServerProvider[] = ['modelscope'];
const mcpProviderToken = ref('');
const showSyncMcpServerDialog = ref(false);
const addServerDialogMessage = ref('');
const loading = ref(false);
const mcpServerUpdateLoaders = reactive<Record<string, boolean>>({});
const isEditMode = ref(false);
const serverConfigJson = ref('');
const jsonError = ref<string | null>(null);
const currentServer = ref<McpServerDraft>(createEmptyServerDraft());
const originalServerName = ref('');
const save_message_snack = ref(false);
const save_message = ref('');
const save_message_success = ref<SnackbarColor>('success');

const isServerFormValid = computed(
  () => Boolean(currentServer.value.name.trim()) && !jsonError.value,
);

const requestMcpStepUp = (resourceId: string) =>
  requestStepUp({
    action: 'tool.mcp_write',
    resourceType: 'dashboard-api',
    resourceId,
  });

let refreshInterval: ReturnType<typeof window.setInterval> | null = null;

function createEmptyServerDraft(): McpServerDraft {
  return {
    name: '',
    active: true,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((entry): entry is string => typeof entry === 'string');
}

function normalizeMcpServer(value: unknown): McpServerItem | null {
  if (!isRecord(value)) {
    return null;
  }

  const name = typeof value.name === 'string' ? value.name.trim() : '';
  if (!name) {
    return null;
  }

  return {
    ...value,
    name,
    active: typeof value.active === 'boolean' ? value.active : true,
    tools: normalizeStringArray(value.tools),
  };
}

function parseServerConfigJson(): DynamicConfig | null {
  const rawConfig = serverConfigJson.value.trim();
  if (!rawConfig) {
    jsonError.value = tm('dialogs.addServer.errors.configEmpty');
    return null;
  }

  try {
    const parsed = JSON.parse(rawConfig);
    if (!isRecord(parsed)) {
      jsonError.value = tm('dialogs.addServer.errors.jsonFormat', {
        error: 'Config must be a JSON object',
      });
      return null;
    }

    jsonError.value = null;
    return parsed;
  } catch (error) {
    jsonError.value = tm('dialogs.addServer.errors.jsonFormat', {
      error: resolveErrorMessage(error, 'Invalid JSON'),
    });
    return null;
  }
}

function validateJson() {
  return parseServerConfigJson() !== null;
}

function setConfigTemplate(
  type: NonNullable<McpServerConfig['transport']> = 'stdio',
) {
  let template: DynamicConfig;
  if (type === 'streamable_http') {
    template = {
      transport: 'streamable_http',
      url: 'your mcp server url',
      allow_private_network: false,
      headers: {},
      connect_timeout_seconds: 15,
      read_timeout_seconds: 60,
    };
  } else {
    template = {
      command: 'python',
      args: ['-m', 'your_module'],
    };
  }

  serverConfigJson.value = JSON.stringify(template, null, 2);
  jsonError.value = null;
}

function showMessage(message: string, color: SnackbarColor) {
  save_message.value = message;
  save_message_success.value = color;
  save_message_snack.value = true;
}

function showSuccess(message: string) {
  showMessage(message, 'success');
}

function showError(message: string) {
  showMessage(message, 'error');
}

async function openCatalog(server: McpServerItem) {
  try {
    const response = await mcpApi.catalog(server.name);
    const data = response.data.data;
    if (!isRecord(data)) {
      throw new Error('Invalid MCP catalog response');
    }
    catalogServerName.value = server.name;
    catalogResources.value = Array.isArray(data.resources)
      ? data.resources.filter(isRecord)
      : [];
    catalogPrompts.value = Array.isArray(data.prompts)
      ? data.prompts.filter(isRecord)
      : [];
    catalogResult.value = '';
    showMcpCatalogDialog.value = true;
  } catch (error) {
    showError(
      tm('messages.catalogError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  }
}

async function readCatalogResource(uri: string) {
  try {
    const response = await mcpApi.readResource(catalogServerName.value, uri);
    catalogResult.value = JSON.stringify(response.data.data, null, 2);
  } catch (error) {
    showError(
      tm('messages.catalogError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  }
}

async function getCatalogPrompt(name: string) {
  try {
    const response = await mcpApi.getPrompt(catalogServerName.value, name);
    catalogResult.value = JSON.stringify(response.data.data, null, 2);
  } catch (error) {
    showError(
      tm('messages.catalogError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  }
}

async function startAuthorization(server: McpServerItem) {
  try {
    const stepUp = await requestMcpStepUp('post-mcp');
    if (!stepUp) return;
    const response = await mcpApi.startOAuth(server.name, {
      headers: stepUpHeaders(stepUp),
    });
    const data = response.data.data;
    if (isRecord(data) && typeof data.authorization_url === 'string') {
      window.open(data.authorization_url, '_blank', 'noopener,noreferrer');
      return;
    }
    showMessage(tm('mcpServers.auth.pending'), 'success');
  } catch (error) {
    showError(
      tm('messages.catalogError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  }
}

async function getServers() {
  try {
    const response = await mcpApi.list();
    if (response.data.status === 'error') {
      showError(
        response.data.message ||
          tm('messages.getServersError', { error: 'Unknown error' }),
      );
      return;
    }

    mcpServers.value = Array.isArray(response.data.data)
      ? response.data.data
          .map((server) => normalizeMcpServer(server))
          .filter((server): server is McpServerItem => server !== null)
      : [];

    for (const server of mcpServers.value) {
      if (!(server.name in mcpServerUpdateLoaders)) {
        mcpServerUpdateLoaders[server.name] = false;
      }
    }
  } catch (error) {
    showError(
      tm('messages.getServersError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  }
}

function getServerConfigSummary(server: McpServerItem) {
  if (server.transport) {
    return String(server.transport).trim();
  }

  if (server.command) {
    const args = normalizeStringArray(server.args);
    return `${server.command} ${args.join(' ')}`.trim();
  }

  const configKeys = Object.keys(server).filter(
    (key) =>
      ![
        'name',
        'active',
        'tools',
        'connection_status',
        'protocol_version',
        'resource_count',
        'prompt_count',
        'auth_status',
        'headers_configured',
      ].includes(key),
  );
  if (configKeys.length > 0) {
    return tm('mcpServers.status.configSummary', {
      keys: configKeys.join(', '),
    });
  }

  return tm('mcpServers.status.noConfig');
}

function getServerConfigIcon(server: McpServerItem) {
  const transport = String(server.transport || '').toLowerCase();
  if (transport === 'streamable_http') {
    return 'mdi-web';
  }
  if (server.command) {
    return 'mdi-console-line';
  }
  return 'mdi-file-code-outline';
}

async function saveServer() {
  const configObj = parseServerConfigJson();
  if (!configObj) {
    return;
  }

  loading.value = true;
  try {
    const serverData: McpServerConfig = {
      name: currentServer.value.name.trim(),
      active: currentServer.value.active,
      ...configObj,
    };
    const stepUp = await requestMcpStepUp(
      isEditMode.value ? 'put-mcp' : 'post-mcp',
    );
    if (!stepUp) return;
    const requestConfig = { headers: stepUpHeaders(stepUp) };
    const response = isEditMode.value
      ? await mcpApi.update(
          originalServerName.value || serverData.name,
          serverData,
          requestConfig,
        )
      : await mcpApi.create(serverData, requestConfig);

    if (response.data.status === 'error') {
      showError(
        response.data.message ||
          tm('messages.saveError', { error: 'Unknown error' }),
      );
      return;
    }

    showMcpServerDialog.value = false;
    addServerDialogMessage.value = '';
    await getServers();
    showSuccess(response.data.message || tm('messages.saveSuccess'));
    resetForm();
  } catch (error) {
    showError(
      tm('messages.saveError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  } finally {
    loading.value = false;
  }
}

async function deleteServer(server: McpServerItem | string) {
  const serverName = typeof server === 'string' ? server : server.name;
  const message = tm('dialogs.confirmDelete', { name: serverName });
  if (!(await askForConfirmationDialog(message, confirmDialog))) {
    return;
  }

  try {
    const stepUp = await requestMcpStepUp('delete-mcp');
    if (!stepUp) return;
    const response = await mcpApi.delete(serverName, {
      headers: stepUpHeaders(stepUp),
    });
    await getServers();
    showSuccess(response.data.message || tm('messages.deleteSuccess'));
  } catch (error) {
    showError(
      tm('messages.deleteError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  }
}

function editServer(server: McpServerItem) {
  const {
    name,
    active,
    tools: _tools,
    errlogs: _errlogs,
    connection_status: _connectionStatus,
    protocol_version: _protocolVersion,
    resource_count: _resourceCount,
    resource_template_count: _resourceTemplateCount,
    prompt_count: _promptCount,
    capabilities: _capabilities,
    tool_count: _toolCount,
    headers_configured: _headersConfigured,
    auth_status: _authStatus,
    ...configCopy
  } = server as McpServerItem & {
    errlogs?: unknown;
    capabilities?: unknown;
    resource_template_count?: unknown;
    tool_count?: unknown;
    headers_configured?: unknown;
  };
  currentServer.value = {
    name,
    active,
  };
  originalServerName.value = name;
  serverConfigJson.value = JSON.stringify(configCopy, null, 2);
  isEditMode.value = true;
  showMcpServerDialog.value = true;
}

async function updateServerStatus(server: McpServerItem) {
  const previousActive = server.active;
  mcpServerUpdateLoaders[server.name] = true;
  server.active = !previousActive;

  try {
    const stepUp = await requestMcpStepUp('patch-mcp');
    if (!stepUp) {
      server.active = previousActive;
      return;
    }
    const response = await mcpApi.setEnabled(server.name, server.active, {
      headers: stepUpHeaders(stepUp),
    });
    await getServers();
    showSuccess(response.data.message || tm('messages.updateSuccess'));
  } catch (error) {
    server.active = previousActive;
    showError(
      tm('messages.updateError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  } finally {
    mcpServerUpdateLoaders[server.name] = false;
  }
}

function resetForm() {
  currentServer.value = createEmptyServerDraft();
  serverConfigJson.value = '';
  jsonError.value = null;
  isEditMode.value = false;
  originalServerName.value = '';
}

function closeServerDialog() {
  showMcpServerDialog.value = false;
  addServerDialogMessage.value = '';
  resetForm();
}

async function testServerConnection() {
  const configObj = parseServerConfigJson();
  if (!configObj) {
    return;
  }

  loading.value = true;
  try {
    const response = await mcpApi.test(
      currentServer.value.name.trim() || 'draft',
      configObj,
    );
    const toolSummary = Array.isArray(response.data.data)
      ? response.data.data.join(', ')
      : String(response.data.data ?? '');
    addServerDialogMessage.value = toolSummary
      ? `${response.data.message} (tools: ${toolSummary})`
      : String(response.data.message || '');
  } catch (error) {
    showError(
      tm('messages.testError', {
        error: resolveErrorMessage(error, 'Unknown error'),
      }),
    );
  } finally {
    loading.value = false;
  }
}

async function syncMcpServers() {
  const accessToken = mcpProviderToken.value.trim();
  if (!accessToken) {
    showError(tm('syncProvider.status.enterToken'));
    return;
  }

  loading.value = true;
  try {
    const stepUp = await requestMcpStepUp('post-mcp');
    if (!stepUp) return;
    const response = await mcpApi.syncModelScope(
      { access_token: accessToken },
      { headers: stepUpHeaders(stepUp) },
    );
    if (response.data.status !== 'ok') {
      showError(
        response.data.message ||
          tm('syncProvider.messages.syncError', {
            error: 'Unknown error',
          }),
      );
      return;
    }

    showSuccess(
      response.data.message || tm('syncProvider.messages.syncSuccess'),
    );
    showSyncMcpServerDialog.value = false;
    mcpProviderToken.value = '';
    await getServers();
  } catch (error) {
    showError(
      tm('syncProvider.messages.syncError', {
        error: resolveErrorMessage(error, '网络连接或访问令牌问题'),
      }),
    );
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void getServers();
  refreshInterval = window.setInterval(() => {
    void getServers();
  }, 30000);
});

onUnmounted(() => {
  if (refreshInterval !== null) {
    clearInterval(refreshInterval);
  }
});
</script>

<style scoped>
.tools-page {
  padding: 0px;
  padding-top: 8px;
}

.mcp-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 960px);
}

.mcp-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.mcp-dialog__actions {
  flex-shrink: 0;
}

.mcp-tools-dialog {
  padding: var(--astrbot-space-4);
}

.mcp-tools-dialog__item {
  margin: var(--astrbot-space-2) 0;
}

.mcp-server-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mcp-server-config {
  align-items: center;
  display: flex;
  overflow: hidden;
  word-break: break-all;
}

.mcp-server-config span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mcp-server-tools {
  align-items: center;
  display: flex;
  margin-top: 6px;
}

.mcp-server-tools__button {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.62);
  display: inline-flex;
  text-decoration: underline;
}

.mcp-server-tools__button:hover {
  color: rgb(var(--v-theme-primary));
}

.list-action-icon-btn {
  color: rgb(var(--v-theme-on-surface-variant));
}

.list-action-icon-btn:hover {
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface));
}

.monaco-container {
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 8px;
  height: 300px;
  margin-top: var(--astrbot-space-1);
  overflow: hidden;
}

.mcp-monaco-container {
  margin-top: var(--astrbot-space-4);
}
</style>
