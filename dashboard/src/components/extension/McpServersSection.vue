<template>
  <div class="tools-page">
    <v-container fluid class="pa-0" elevation="0">
      <!-- MCP 服务器部分 -->
      <div v-if="mcpServers.length === 0" class="text-center pa-8">
        <v-icon size="64" color="grey-lighten-1">mdi-server-off</v-icon>
        <p class="text-grey mt-4">{{ tm('mcpServers.empty') }}</p>
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
              <v-dialog max-width="600px">
                <template v-slot:activator="{ props: listToolsProps }">
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
                <template v-slot:default="{ isActive }">
                  <v-card style="padding: 16px;">
                    <v-card-title class="d-flex align-center">
                      <span>{{ tm('mcpServers.status.availableTools') }}</span>
                    </v-card-title>
                    <v-card-text>
                      <ul>
                        <li
                          v-for="(tool, idx) in server.tools"
                          :key="idx"
                          style="margin: 8px 0px;"
                        >
                          {{ tool }}
                        </li>
                      </ul>
                    </v-card-text>
                    <v-card-actions class="d-flex justify-end">
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

          <template #actions>
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

    <div class="mcp-fab-stack">
      <v-tooltip :text="tm('mcpServers.buttons.sync')" location="left">
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            color="darkprimary"
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
            color="darkprimary"
            icon="mdi-plus"
            size="x-large"
            variant="elevated"
            class="mcp-fab"
            @click="showMcpServerDialog = true"
          />
        </template>
      </v-tooltip>
    </div>

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
          <v-btn color="primary" @click="saveServer" :loading="loading" :disabled="!isServerFormValid">
            {{ tm('dialogs.addServer.buttons.save') }}
          </v-btn>
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
import { useI18n, useModuleI18n } from '@/i18n/composables';
import OutlinedActionListItem from '@/components/shared/OutlinedActionListItem.vue';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog
} from '@/utils/confirmDialog';

export default {
  name: 'McpServersSection',
  components: {
    VueMonacoEditor,
    OutlinedActionListItem
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
    getServerConfigSummary() {
      return (server) => {
        if (server.transport) {
          return String(server.transport).trim();
        }
        if (server.command) {
          return `${server.command} ${(server.args || []).join(' ')}`;
        }
        const configKeys = Object.keys(server).filter(key =>
          !['name', 'active', 'tools'].includes(key)
        );
        if (configKeys.length > 0) {
          return this.tm('mcpServers.status.configSummary', { keys: configKeys.join(', ') });
        }
        return this.tm('mcpServers.status.noConfig');
      };
    },
    getServerConfigIcon() {
      return (server) => {
        const transport = String(server.transport || '').toLowerCase();
        if (transport === 'streamable_http') {
          return 'mdi-web';
        }
        if (transport === 'sse') {
          return 'mdi-broadcast';
        }
        if (server.command) {
          return 'mdi-console-line';
        }
        return 'mdi-file-code-outline';
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
      this.currentServer = {
        name: server.name,
        active: server.active,
        tools: server.tools || []
      };
      this.originalServerName = server.name;
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
      this.currentServer = {
        name: '',
        active: true,
        tools: []
      };
      this.serverConfigJson = '';
      this.jsonError = null;
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
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.list-action-icon-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}

.mcp-fab-stack {
  align-items: center;
  bottom: 52px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: fixed;
  right: 52px;
  z-index: 10000;
}

.mcp-fab {
  border-radius: 16px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.mcp-fab:hover {
  box-shadow: 0 12px 20px rgba(var(--v-theme-primary), 0.4);
  transform: translateY(-4px) scale(1.05);
}

.monaco-container {
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  height: 300px;
  margin-top: 4px;
  overflow: hidden;
}

</style>
