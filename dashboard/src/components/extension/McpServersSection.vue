<template>
  <div class="tools-page">
    <v-container fluid class="pa-0" elevation="0">
      <!-- 页面标题 -->
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
        <div>
          <v-btn color="success" prepend-icon="mdi-plus" class="me-2" variant="tonal"
            @click="showMcpServerDialog = true" >
            {{ tm('mcpServers.buttons.add') }}
          </v-btn>
          <v-btn color="success" prepend-icon="mdi-refresh" variant="tonal" @click="showSyncMcpServerDialog = true"
            >
            {{ tm('mcpServers.buttons.sync') }}
          </v-btn>
        </div>
      </v-row>

      <!-- MCP 服务器部分 -->
      <div v-if="mcpServers.length === 0" class="text-center pa-8">
        <v-icon size="64" color="grey-lighten-1">mdi-server-off</v-icon>
        <p class="text-grey mt-4">{{ tm('mcpServers.empty') }}</p>
      </div>

      <v-row v-else>
        <v-col v-for="(server, index) in mcpServers || []" :key="index" cols="12" md="6" lg="4" xl="3">
          <item-card style="background-color: rgb(var(--v-theme-mcpCardBg));" :item="server" title-field="name"
            enabled-field="active" @toggle-enabled="updateServerStatus" @delete="deleteServer" @edit="editServer">
            <template v-slot:item-details="{ item }">
              <div class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-file-code</v-icon>
                <span class="text-caption text-medium-emphasis text-truncate" :title="getServerConfigSummary(item)">
                  {{ getServerConfigSummary(item) }}
                </span>
              </div>

              <div v-if="item.oauth2_enabled" class="d-flex align-center mb-2">
                <v-icon size="small" :color="item.oauth2_authorized ? 'success' : 'warning'" class="me-2">
                  mdi-shield-key-outline
                </v-icon>
                <span class="text-caption text-medium-emphasis">
                  {{ item.oauth2_grant_type === 'client_credentials'
                    ? tm('mcpServers.status.oauthClientCredentials')
                    : (item.oauth2_authorized
                      ? tm('mcpServers.status.oauthAuthorized')
                      : tm('mcpServers.status.oauthLoginRequired')) }}
                </span>
              </div>

              <div class="d-flex" style="gap: 8px;">
                <div>
                  <div v-if="item.tools && item.tools.length > 0">
                    <div class="d-flex align-center mb-1">
                      <v-icon size="small" color="grey" class="me-2">mdi-tools</v-icon>
                      <v-dialog max-width="600px">
                        <template v-slot:activator="{ props: listToolsProps }">
                          <span class="text-caption text-medium-emphasis cursor-pointer" v-bind="listToolsProps"
                            style="text-decoration: underline;">
                            {{ tm('mcpServers.status.availableTools', { count: item.tools.length }) }} ({{ item.tools.length }})
                          </span>
                        </template>
                        <template v-slot:default="{ isActive }">
                          <v-card style="padding: 16px;">
                            <v-card-title class="d-flex align-center">
                              <span>{{ tm('mcpServers.status.availableTools') }}</span>
                            </v-card-title>
                            <v-card-text>
                              <ul>
                                <li v-for="(tool, idx) in item.tools" :key="idx" style="margin: 8px 0px;">{{ tool }}</li>
                              </ul>
                            </v-card-text>
                            <v-card-actions class="d-flex justify-end">
                              <v-btn variant="text" color="primary" @click="isActive.value = false">
                                Close
                              </v-btn>
                            </v-card-actions>
                          </v-card>
                        </template>
                      </v-dialog>
                    </div>
                  </div>
                  <div v-else class="text-caption text-medium-emphasis">
                    <v-icon size="small" color="warning" class="me-1">mdi-alert-circle</v-icon>
                    {{ tm('mcpServers.status.noTools') }}
                  </div>
                </div>
                <div v-if="mcpServerUpdateLoaders[item.name]" class="text-caption text-medium-emphasis">
                  <v-progress-circular indeterminate color="primary" size="16"></v-progress-circular>
                </div>
              </div>
            </template>
          </item-card>
        </v-col>
      </v-row>
    </v-container>

    <!-- 添加/编辑 MCP 服务器对话框 -->
    <v-dialog v-model="showMcpServerDialog" max-width="750px">
      <v-card>
        <v-card-title class="pa-4 pl-6">
          <v-icon class="me-2">{{ isEditMode ? 'mdi-pencil' : 'mdi-plus' }}</v-icon>
          <span>{{ isEditMode ? tm('dialogs.addServer.editTitle') : tm('dialogs.addServer.title') }}</span>
        </v-card-title>

        <v-card-text class="py-4">
          <v-form @submit.prevent="saveServer" ref="form">
            <v-text-field v-model="currentServer.name" :label="tm('dialogs.addServer.fields.name')" variant="outlined"
              :rules="[v => !!v || tm('dialogs.addServer.fields.nameRequired')]" required class="mb-3"></v-text-field>

            <div class="mb-2 d-flex align-center">
              <span class="text-subtitle-1">{{ tm('dialogs.addServer.fields.config') }}</span>
              <v-spacer></v-spacer>
              <v-btn size="small" color="primary" variant="tonal" @click="setConfigTemplate('stdio')" class="me-1">
                {{ tm('mcpServers.buttons.useTemplateStdio') }}
              </v-btn>
              <v-btn size="small" color="primary" variant="tonal" @click="setConfigTemplate('streamable_http')"
                class="me-1">
                {{ tm('mcpServers.buttons.useTemplateStreamableHttp') }}
              </v-btn>
              <v-btn size="small" color="primary" variant="tonal" @click="setConfigTemplate('sse')" class="me-1">
                {{ tm('mcpServers.buttons.useTemplateSse') }}
              </v-btn>
              <v-btn size="small" color="primary" variant="tonal" @click="setConfigTemplate('streamable_http_oauth')">
                {{ tm('mcpServers.buttons.useTemplateOauth2') }}
              </v-btn>
            </div>

            <small style="color: grey">*{{ tm('dialogs.addServer.tips.timeoutConfig') }}</small>

            <v-alert type="info" variant="tonal" density="compact" class="mt-3">
              {{ tm('dialogs.addServer.tips.transportRecommendation') }}
            </v-alert>

            <div class="monaco-container" style="margin-top: 16px;">
              <VueMonacoEditor v-model:value="serverConfigJson" theme="vs-dark" language="json" :options="{
                minimap: {
                  enabled: false
                },
                scrollBeyondLastLine: false,
                automaticLayout: true,
                lineNumbers: 'on',
                roundedSelection: true,
                tabSize: 2
              }" @change="validateJson" />
            </div>

            <div v-if="jsonError" class="mt-2 text-error">
              <v-icon color="error" size="small" class="me-1">mdi-alert-circle</v-icon>
              <span>{{ jsonError }}</span>
            </div>

            <div v-if="hasAuthorizationCodeOAuthConfig" class="mt-3">
              <div class="d-flex align-center mb-2">
                <v-icon size="small" :color="oauthFlowStatusColor" class="me-2">mdi-shield-key-outline</v-icon>
                <span :class="oauthFlowStatusClass" class="text-caption font-weight-bold">{{ oauthFlowStatusText }}</span>
              </div>
              
              <div v-if="oauthUrl && oauthFlowStatus === 'awaiting_user'" class="mt-2 pa-3 bg-grey-lighten-4 rounded border">
                <div class="text-caption text-grey-darken-1 mb-1">请复制以下链接在浏览器中打开：</div>
                <div class="d-flex align-center">
                  <v-text-field
                    :value="oauthUrl"
                    readonly
                    density="compact"
                    variant="plain"
                    hide-details
                    class="text-body-2"
                  ></v-text-field>
                  <v-btn icon="mdi-content-copy" size="x-small" variant="text" @click="copyOauthUrl"></v-btn>
                </div>
                <v-btn
                  block
                  color="info"
                  variant="tonal"
                  size="small"
                  class="mt-3"
                  prepend-icon="mdi-qrcode-scan"
                  @click="showQrCodeDialog = true"
                >
                  扫描二维码登录
                </v-btn>
              </div>
            </div>

          </v-form>
          <div style="margin-top: 8px;">
            <small>{{ addServerDialogMessage }}</small>
          </div>

        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeServerDialog" :disabled="loading">
            {{ tm('dialogs.addServer.buttons.cancel') }}
          </v-btn>
          <v-btn variant="text" @click="testServerConnection" :disabled="loading">
            {{ tm('dialogs.addServer.buttons.testConnection') }}
          </v-btn>
          <v-btn variant="text" color="secondary" @click="authorizeOauth" :disabled="loading || !hasAuthorizationCodeOAuthConfig">
            {{ tm('dialogs.addServer.buttons.oauthLogin') }}
          </v-btn>
          <v-btn color="primary" @click="saveServer" :loading="loading" :disabled="!isServerFormValid">
            {{ tm('dialogs.addServer.buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 二维码对话框 -->
    <v-dialog v-model="showQrCodeDialog" max-width="320px">
      <v-card>
        <v-card-title class="text-center py-4">扫描二维码登录</v-card-title>
        <v-card-text class="text-center pb-6">
          <QrCodeViewer
            v-if="oauthUrl"
            :value="oauthUrl"
            :size="240"
            class="mx-auto border rounded-lg"
          />
          <div class="mt-4 text-caption text-grey">请使用移动端或浏览器扫描此二维码完成授权</div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" block @click="showQrCodeDialog = false">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 同步 MCP 服务器对话框 -->
    <v-dialog v-model="showSyncMcpServerDialog" max-width="500px" persistent>
      <v-card>
        <v-card-title class="bg-primary text-white py-3">
          <span>同步外部平台 MCP 服务器</span>
        </v-card-title>

        <v-card-text class="py-4">
          <v-select v-model="selectedMcpServerProvider" :items="mcpServerProviderList"
            label="选择平台" variant="outlined" required></v-select>
          <div v-if="selectedMcpServerProvider === 'modelscope'">
            <v-timeline align="start" side="end">
              <v-timeline-item icon="mdi-numeric-1" icon-color="rgb(var(--v-theme-background))">
                <div>
                  <div class="text-h4">发现 MCP 服务器</div>
                  <p class="mt-2">
                    访问 <a href="https://www.modelscope.cn/mcp" target="_blank">ModelScope 平台</a> 浏览需要的 MCP 服务器。
                  </p>
                </div>
              </v-timeline-item>

              <v-timeline-item icon="mdi-numeric-2" icon-color="rgb(var(--v-theme-background))">
                <div>
                  <div class="text-h4">获取访问令牌</div>
                  <p class="mt-2">
                    从<a href="https://modelscope.cn/my/myaccesstoken" target="_blank">账户设置</a>中获取个人访问令牌。
                  </p>
                </div>
              </v-timeline-item>

              <v-timeline-item icon="mdi-numeric-3" icon-color="rgb(var(--v-theme-background))">
                <div>
                  <div class="text-h4">输入您的访问令牌</div>
                  <p class="mt-2">
                    输入您的访问令牌以同步 MCP 服务器。
                  </p>
                  <v-text-field v-model="mcpProviderToken" type="password" variant="outlined"
                    label="访问令牌" class="mt-2" hide-details/>
                </div>
              </v-timeline-item>
            </v-timeline>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showSyncMcpServerDialog = false" :disabled="loading">
            {{ tm('dialogs.addServer.buttons.cancel') }}
          </v-btn>
          <v-btn color="primary" @click="syncMcpServers" :loading="loading" :disabled="loading">
            {{ tm('dialogs.addServer.buttons.sync') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack" location="top">
      {{ save_message }}
    </v-snackbar>
  </div>
</template>

<script>
import axios from 'axios';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import ItemCard from '@/components/shared/ItemCard.vue';
import QrCodeViewer from '@/components/shared/QrCodeViewer.vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog
} from '@/utils/confirmDialog';

export default {
  name: 'McpServersSection',
  components: {
    VueMonacoEditor,
    ItemCard,
    QrCodeViewer
  },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n('features/tooluse');
    const confirmDialog = useConfirmDialog();
    return { t, tm, confirmDialog };
  },
  data() {
    return {
      refreshInterval: null,
      mcpServers: [],
      showMcpServerDialog: false,
      selectedMcpServerProvider: 'modelscope',
      mcpServerProviderList: ['modelscope'],
      mcpProviderToken: '',
      showSyncMcpServerDialog: false,
      addServerDialogMessage: '',
      loading: false,
      loadingGettingServers: false,
      mcpServerUpdateLoaders: {},
      oauthFlowId: '',
      oauthUrl: '',
      showQrCodeDialog: false,
      oauthFlowStatus: '',
      oauthFlowError: '',
      oauthPollTimer: null,
      oauthPollInFlight: false,
      isEditMode: false,
      serverConfigJson: '',
      jsonError: null,
      currentServer: {
        name: '',
        active: true,
        tools: []
      },
      originalServerName: '',
      save_message_snack: false,
      save_message: '',
      save_message_success: 'success'
    };
  },
  computed: {
    isServerFormValid() {
      return !!this.currentServer.name && !this.jsonError;
    },
    parsedServerConfig() {
      try {
        if (!this.serverConfigJson.trim()) {
          return null;
        }
        return JSON.parse(this.serverConfigJson);
      } catch {
        return null;
      }
    },
    currentOauthConfig() {
      if (!this.parsedServerConfig || typeof this.parsedServerConfig !== 'object') {
        return null;
      }
      return this.parsedServerConfig.oauth2 || this.parsedServerConfig.oauth || null;
    },
    hasAuthorizationCodeOAuthConfig() {
      return !!this.currentOauthConfig
        && (this.currentOauthConfig.grant_type || 'authorization_code') === 'authorization_code';
    },
    oauthFlowStatusColor() {
      if (this.oauthFlowStatus === 'completed') {
        return 'success';
      }
      if (this.oauthFlowStatus === 'failed') {
        return 'error';
      }
      return 'warning';
    },
    oauthFlowStatusClass() {
      if (this.oauthFlowStatus === 'completed') {
        return 'text-success';
      }
      if (this.oauthFlowStatus === 'failed') {
        return 'text-error';
      }
      return 'text-medium-emphasis';
    },
    oauthFlowStatusText() {
      if (this.oauthFlowStatus === 'completed') {
        return this.tm('dialogs.addServer.oauth.status.authorized');
      }
      if (this.oauthFlowStatus === 'awaiting_user') {
        return this.tm('dialogs.addServer.oauth.status.awaitingUser');
      }
      if (this.oauthFlowStatus === 'authorizing') {
        return this.tm('dialogs.addServer.oauth.status.authorizing');
      }
      if (this.oauthFlowStatus === 'failed') {
        return this.oauthFlowError || this.tm('dialogs.addServer.oauth.status.failed');
      }
      return this.tm('dialogs.addServer.oauth.status.notAuthorized');
    },
    getServerConfigSummary() {
      return (server) => {
        if (server.command) {
          return `${server.command} ${(server.args || []).join(' ')}`;
        }
        if (server.url) {
          return server.url;
        }
        const configKeys = Object.keys(server).filter(key =>
          !['name', 'active', 'tools', 'oauth2_enabled', 'oauth2_authorized', 'oauth2_grant_type'].includes(key)
        );
        if (configKeys.length > 0) {
          return this.tm('mcpServers.status.configSummary', { keys: configKeys.join(', ') });
        }
        return this.tm('mcpServers.status.noConfig');
      };
    }
  },
  mounted() {
    this.getServers();
    this.refreshInterval = setInterval(() => {
      // 轮询时间延长到30秒，减少服务器压力，同时保持数据相对新鲜
      this.getServers();
    }, 30000);
  },
  unmounted() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
    this.stopOauthPolling();
  },
  methods: {
    openurl(url) {
      window.open(url, '_blank');
    },
    getServers() {
      this.loadingGettingServers = true;
      axios.get('/api/tools/mcp/servers')
        .then(response => {
          if (response.data.status === 'error') {
            this.showError(response.data.message || this.tm('messages.getServersError', { error: 'Unknown error' }));
            return;
          }
          this.mcpServers = response.data.data || [];
          this.mcpServers.forEach(server => {
            if (!this.mcpServerUpdateLoaders[server.name]) {
              this.mcpServerUpdateLoaders[server.name] = false;
            }
          });
        })
        .catch(error => {
          this.showError(this.tm('messages.getServersError', { error: error.message }));
        }).finally(() => {
          this.loadingGettingServers = false;
        });
    },
    validateJson() {
      try {
        if (!this.serverConfigJson.trim()) {
          this.jsonError = this.tm('dialogs.addServer.errors.configEmpty');
          return false;
        }
        JSON.parse(this.serverConfigJson);
        this.jsonError = null;
        return true;
      } catch (e) {
        this.jsonError = this.tm('dialogs.addServer.errors.jsonFormat', { error: e.message });
        return false;
      }
    },
    setConfigTemplate(type = 'stdio') {
      let template = {};
      if (type === 'streamable_http') {
        template = {
          transport: 'streamable_http',
          url: 'your mcp server url',
          headers: {},
          timeout: 5,
          sse_read_timeout: 300
        };
      } else if (type === 'sse') {
        template = {
          transport: 'sse',
          url: 'your mcp server url',
          headers: {},
          timeout: 5,
          sse_read_timeout: 300
        };
      } else if (type === 'streamable_http_oauth') {
        template = {
          transport: 'streamable_http',
          url: 'your mcp server url',
          headers: {},
          timeout: 5,
          sse_read_timeout: 300,
          oauth2: {
            grant_type: 'authorization_code',
            client_name: 'AstrBot MCP Client'
          }
        };
      } else {
        template = {
          command: 'python',
          args: ['-m', 'your_module']
        };
      }
      this.serverConfigJson = JSON.stringify(template, null, 2);
    },
    saveServer() {
      if (!this.validateJson()) {
        return;
      }
      this.loading = true;
      try {
        const configObj = JSON.parse(this.serverConfigJson);
        const serverData = {
          name: this.currentServer.name,
          active: this.currentServer.active,
          ...configObj
        };
        if (this.isEditMode && this.originalServerName) {
          serverData.oldName = this.originalServerName;
        }
        const endpoint = this.isEditMode ? '/api/tools/mcp/update' : '/api/tools/mcp/add';
        axios.post(endpoint, serverData)
          .then(response => {
            this.loading = false;
            if (response.data.status === 'error') {
              this.showError(response.data.message || this.tm('messages.saveError', { error: 'Unknown error' }));
              return;
            }
            this.showMcpServerDialog = false;
            this.addServerDialogMessage = '';
            this.getServers();
            this.showSuccess(response.data.message || this.tm('messages.saveSuccess'));
            this.resetForm();
          })
          .catch(error => {
            this.loading = false;
            this.showError(this.tm('messages.saveError', { error: error.response?.data?.message || error.message }));
          });
      } catch (e) {
        this.loading = false;
        this.showError(this.tm('dialogs.addServer.errors.jsonParse', { error: e.message }));
      }
    },
    async deleteServer(server) {
      const serverName = server.name || server;
      const message = this.tm('dialogs.confirmDelete', { name: serverName });
      if (!(await askForConfirmationDialog(message, this.confirmDialog))) {
        return;
      }

      axios.post('/api/tools/mcp/delete', { name: serverName })
        .then(response => {
          this.getServers();
          this.showSuccess(response.data.message || this.tm('messages.deleteSuccess'));
        })
        .catch(error => {
          this.showError(this.tm('messages.deleteError', { error: error.response?.data?.message || error.message }));
        });
    },
    editServer(server) {
      const configCopy = { ...server };
      delete configCopy.name;
      delete configCopy.active;
      delete configCopy.tools;
      delete configCopy.errlogs;
      delete configCopy.oauth2_enabled;
      delete configCopy.oauth2_authorized;
      delete configCopy.oauth2_grant_type;
      this.currentServer = {
        name: server.name,
        active: server.active,
        tools: server.tools || []
      };
      this.originalServerName = server.name;
      this.oauthFlowStatus = server.oauth2_authorized ? 'completed' : '';
      this.oauthFlowError = '';
      this.serverConfigJson = JSON.stringify(configCopy, null, 2);
      this.isEditMode = true;
      this.showMcpServerDialog = true;
    },
    updateServerStatus(server) {
      this.mcpServerUpdateLoaders[server.name] = true;
      server.active = !server.active;
      axios.post('/api/tools/mcp/update', server)
        .then(response => {
          this.getServers();
          this.showSuccess(response.data.message || this.tm('messages.updateSuccess'));
        })
        .catch(error => {
          this.showError(this.tm('messages.updateError', { error: error.response?.data?.message || error.message }));
          server.active = !server.active;
        })
        .finally(() => {
          this.mcpServerUpdateLoaders[server.name] = false;
        });
    },
    closeServerDialog() {
      this.showMcpServerDialog = false;
      this.addServerDialogMessage = '';
      this.resetForm();
    },
    stopOauthPolling() {
      if (this.oauthPollTimer) {
        clearInterval(this.oauthPollTimer);
        this.oauthPollTimer = null;
      }
      this.oauthPollInFlight = false;
    },
    async pollOauthStatus() {
      if (!this.oauthFlowId || this.oauthPollInFlight) {
        return;
      }
      this.oauthPollInFlight = true;
      const serverName = this.currentServer.name || 'unknown';
      try {
        const response = await axios.get('/api/tools/mcp/oauth/status', {
          params: { 
            flow_id: this.oauthFlowId,
            name: serverName
          }
        });
        if (response.data.status === 'error') {
          this.stopOauthPolling();
          this.oauthFlowStatus = 'failed';
          this.oauthFlowError = response.data.message || this.tm('dialogs.addServer.oauth.status.failed');
          this.showError(this.oauthFlowError);
          return;
        }
        const flow = response.data.data || {};
        this.oauthFlowStatus = flow.status || '';
        this.oauthFlowError = flow.error || '';
        if (this.oauthFlowStatus === 'completed') {
          this.stopOauthPolling();
          this.addServerDialogMessage = this.tm('messages.oauthAuthorized');
          this.showSuccess(this.tm('messages.oauthAuthorized'));
        } else if (this.oauthFlowStatus === 'failed') {
          this.stopOauthPolling();
          const errorMessage = flow.error || this.tm('dialogs.addServer.oauth.status.failed');
          this.addServerDialogMessage = errorMessage;
          this.showError(errorMessage);
        }
      } catch (error) {
        this.stopOauthPolling();
        this.oauthFlowStatus = 'failed';
        this.oauthFlowError = error.response?.data?.message || error.message;
        this.showError(this.oauthFlowError);
      } finally {
        this.oauthPollInFlight = false;
      }
    },
    startOauthPolling() {
      this.stopOauthPolling();
      this.pollOauthStatus();
      this.oauthPollTimer = setInterval(() => {
        this.pollOauthStatus();
      }, 1500);
    },
    copyOauthUrl() {
      if (!this.oauthUrl) return;
      navigator.clipboard.writeText(this.oauthUrl).then(() => {
        this.showSuccess('链接已复制到剪贴板');
      }).catch(err => {
        this.showError('复制失败: ' + err);
      });
    },
    async authorizeOauth() {
      if (!this.validateJson()) {
        return;
      }
      const configObj = this.parsedServerConfig;
      if (!configObj) {
        this.showError(this.tm('dialogs.addServer.errors.configEmpty'));
        return;
      }

      this.loading = true;
      this.oauthFlowError = '';
      this.oauthUrl = '';
      const serverName = this.currentServer.name || 'unknown';

      try {
        const response = await axios.post('/api/tools/mcp/oauth/start', {
          mcp_server_config: configObj,
          callback_base_url: window.location.origin,
          force: true
        }, {
          params: { name: serverName }
        });

        if (response.data.status === 'error') {
          this.showError(response.data.message || this.tm('messages.oauthStartError', { error: 'Unknown error' }));
          return;
        }

        const flow = response.data.data || {};
        this.oauthFlowId = flow.flow_id || '';
        this.oauthFlowStatus = flow.status || '';
        this.addServerDialogMessage = '';

        if (flow.authorization_url) {
          this.oauthUrl = flow.authorization_url;
          this.startOauthPolling();
        }
      } catch (error) {
        this.showError(error.response?.data?.message || error.message);
      } finally {
        this.loading = false;
      }
    },
    testServerConnection() {
      if (!this.validateJson()) {
        return;
      }
      this.loading = true;
      let configObj;
      try {
        configObj = JSON.parse(this.serverConfigJson);
      } catch (e) {
        this.loading = false;
        this.showError(this.tm('dialogs.addServer.errors.jsonParse', { error: e.message }));
        return;
      }
      axios.post('/api/tools/mcp/test', {
        mcp_server_config: configObj
      })
        .then(response => {
          this.loading = false;
          this.addServerDialogMessage = `${response.data.message} (tools: ${response.data.data})`;
        })
        .catch(error => {
          this.loading = false;
          this.showError(this.tm('messages.testError', { error: error.response?.data?.message || error.message }));
        });
    },
    resetForm() {
      this.stopOauthPolling();
      this.currentServer = {
        name: '',
        active: true,
        tools: []
      };
      this.serverConfigJson = '';
      this.jsonError = null;
      this.oauthFlowId = '';
      this.oauthFlowStatus = '';
      this.oauthFlowError = '';
      this.isEditMode = false;
      this.originalServerName = '';
    },
    showSuccess(message) {
      this.save_message = message;
      this.save_message_success = 'success';
      this.save_message_snack = true;
    },
    showError(message) {
      this.save_message = message;
      this.save_message_success = 'error';
      this.save_message_snack = true;
    },
    async syncMcpServers() {
      if (!this.selectedMcpServerProvider) {
        this.showError(this.tm('syncProvider.status.selectProvider'));
        return;
      }
      this.loading = true;
      try {
        const requestData = {
          name: this.selectedMcpServerProvider
        };
        if (this.selectedMcpServerProvider === 'modelscope') {
          if (!this.mcpProviderToken.trim()) {
            this.showError(this.tm('syncProvider.status.enterToken'));
            this.loading = false;
            return;
          }
          requestData.access_token = this.mcpProviderToken.trim();
        }
        const response = await axios.post('/api/tools/mcp/sync-provider', requestData);
        if (response.data.status === 'ok') {
          this.showSuccess(response.data.message || this.tm('syncProvider.messages.syncSuccess'));
          this.showSyncMcpServerDialog = false;
          this.mcpProviderToken = '';
          this.getServers();
        } else {
          this.showError(response.data.message || this.tm('syncProvider.messages.syncError', { error: 'Unknown error' }));
        }
      } catch (error) {
        this.showError(this.tm('syncProvider.messages.syncError', {
          error: error.response?.data?.message || error.message || '网络连接或访问令牌问题'
        }));
      } finally {
        this.loading = false;
      }
    }
  }
};
</script>

<style scoped>
.tools-page {
  padding: 0px;
  padding-top: 8px;
}

.monaco-container {
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  height: 300px;
  margin-top: 4px;
  overflow: hidden;
}
</style>
