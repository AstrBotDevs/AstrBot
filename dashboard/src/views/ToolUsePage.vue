<template>
  <div class="tools-page">
    <v-container fluid class="pa-0" elevation="0">
      <!-- 页面标题 -->
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
        <div>
          <h1 class="text-h1 font-weight-bold mb-2">
            <v-icon color="black" class="me-2">mdi-function-variant</v-icon>{{ tm('title') }}
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4 d-flex align-center">
            {{ tm('subtitle') }}
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" size="small" color="primary" class="ms-1 cursor-pointer"
                  @click="openurl('https://astrbot.app/use/function-calling.html')">
                  mdi-information
                </v-icon>
              </template>
              <span>{{ tm('tooltip.info') }}</span>
            </v-tooltip>
          </p>
        </div>
        <div>
          <v-btn color="primary" prepend-icon="mdi-tools" class="me-2" variant="tonal" @click="showToolsDialog = true"
            rounded="xl" size="x-large">
            {{ tm('functionTools.buttons.view') }}({{ tools.length }})
          </v-btn>
          <v-btn color="success" prepend-icon="mdi-plus" class="me-2" variant="tonal"
            @click="showMcpServerDialog = true" rounded="xl" size="x-large">
            {{ tm('mcpServers.buttons.add') }}
          </v-btn>
          <v-btn color="success" prepend-icon="mdi-refresh" variant="tonal" @click="showSyncMcpServerDialog = true"
            rounded="xl" size="x-large">
            {{ tm('mcpServers.buttons.sync') }}
          </v-btn>
        </div>
      </v-row>

      <!-- 本地服务器列表 -->

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


              <div class="d-flex" style="gap: 8px;">
                <div>
                  <div v-if="item.tools && item.tools.length > 0">
                    <div class="d-flex align-center mb-1">
                      <v-icon size="small" color="grey" class="me-2">mdi-tools</v-icon>
                      <v-dialog max-width="600px">
                        <template v-slot:activator="{ props: listToolsProps }">
                          <span class="text-caption text-medium-emphasis cursor-pointer" v-bind="listToolsProps"
                            style="text-decoration: underline;">
                            {{ tm('mcpServers.status.availableTools', { count: item.tools.length }) }} ({{
                              item.tools.length }})
                          </span>
                        </template>
                        <template v-slot:default="{ isActive }">
                          <v-card style="padding: 16px;">
                            <v-card-title class="d-flex align-center">
                              <span>{{ tm('mcpServers.status.availableTools') }}</span>
                            </v-card-title>
                            <v-card-text>
                              <ul>
                                <li v-for="(tool, idx) in item.tools" :key="idx" style="margin: 8px 0px;">{{
                                  tool
                                  }}
                                </li>
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
    <v-dialog v-model="showMcpServerDialog" max-width="750px" persistent>
      <v-card>
        <v-card-title class="bg-primary text-white py-3">
          <v-icon color="white" class="me-2">{{ isEditMode ? 'mdi-pencil' : 'mdi-plus' }}</v-icon>
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


    <!-- 添加/编辑 MCP 服务器对话框 -->
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

    <!-- 函数工具对话框 -->
    <v-dialog v-model="showToolsDialog" max-width="800px">
      <v-card elevation="0" class="mt-4">
        <v-card-title class="d-flex align-center py-3 px-4">
          {{ tm('functionTools.title') }}
          <v-chip color="info" size="small" class="ml-2">{{ tools.length }}</v-chip>
        </v-card-title>
        <v-expand-transition>
          <v-card-text class="pa-0" v-if="showTools">
            <div class="pa-4">
              <div v-if="tools.length === 0" class="text-center pa-8">
                <v-icon size="64" color="grey-lighten-1">mdi-api-off</v-icon>
                <p class="text-grey mt-4">{{ tm('functionTools.empty') }}</p>
              </div>

              <div v-else>
                <v-text-field v-model="toolSearch" prepend-inner-icon="mdi-magnify" :label="tm('functionTools.search')"
                  variant="outlined" density="compact" class="mb-4" hide-details clearable></v-text-field>

                <small>复选框代表该工具是否被启用。</small>

                <v-expansion-panels v-model="openedPanel" multiple style="max-height: 500px; overflow-y: auto;">
                  <v-expansion-panel v-for="(tool, index) in filteredTools" :key="index" :value="index"
                    class="mb-2 tool-panel" rounded="lg">
                    <v-expansion-panel-title>
                      <v-row no-gutters align="center">
                        <v-col cols="1">
                          <v-checkbox v-model="tool.active" color="primary" hide-details density="compact" @click.stop
                            @change="toggleToolStatus(tool)"></v-checkbox>
                        </v-col>
                        <v-col cols="3">
                          <div class="d-flex align-center">
                            <v-icon color="primary" class="me-2" size="small">
                              {{ tool.name.includes(':') ? 'mdi-server-network' : 'mdi-function-variant' }}
                            </v-icon>
                            <span class="text-body-1 text-high-emphasis font-weight-medium text-truncate"
                              :title="tool.name">
                              {{ formatToolName(tool.name) }}
                            </span>
                          </div>
                        </v-col>
                        <v-col cols="8" class="text-grey">
                          {{ tool.description }}
                        </v-col>
                      </v-row>
                    </v-expansion-panel-title>

                    <v-expansion-panel-text>
                      <v-card flat>
                        <v-card-text>
                          <p class="text-body-1 font-weight-medium mb-3">
                            <v-icon color="primary" size="small" class="me-1">mdi-information</v-icon>
                            {{ tm('functionTools.description') }}
                          </p>
                          <p class="text-body-2 ml-6 mb-4">{{ tool.description }}</p>

                          <template v-if="tool.parameters && tool.parameters.properties">
                            <p class="text-body-1 font-weight-medium mb-3">
                              <v-icon color="primary" size="small" class="me-1">mdi-code-json</v-icon>
                              {{ tm('functionTools.parameters') }}
                            </p>

                            <v-table density="compact" class="params-table mt-1">
                              <thead>
                                <tr>
                                  <th>{{ tm('functionTools.table.paramName') }}</th>
                                  <th>{{ tm('functionTools.table.type') }}</th>
                                  <th>{{ tm('functionTools.table.description') }}</th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr v-for="(param, paramName) in tool.parameters.properties" :key="paramName">
                                  <td class="font-weight-medium">{{ paramName }}</td>
                                  <td>
                                    <v-chip size="x-small" color="primary" text class="text-caption">
                                      {{ param.type }}
                                    </v-chip>
                                  </td>
                                  <td>{{ param.description }}</td>
                                </tr>
                              </tbody>
                            </v-table>
                          </template>
                          <div v-else class="text-center pa-4 text-medium-emphasis">
                            <v-icon size="large" color="grey-lighten-1">mdi-code-brackets</v-icon>
                            <p>{{ tm('functionTools.noParameters') }}</p>
                          </div>
                        </v-card-text>
                      </v-card>
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </div>
            </div>
          </v-card-text>
        </v-expand-transition>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showToolsDialog = false">
            {{ tm('dialogs.serverDetail.buttons.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack"
      location="top">
      {{ save_message }}
    </v-snackbar>
  </div>
</template>

<script>
import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import ItemCard from '@/components/shared/ItemCard.vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';

export default {
  name: 'ToolUsePage',
  components: {
    AstrBotConfig,
    VueMonacoEditor,
    ItemCard
  },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n('features/tooluse');
    return { t, tm };
  },
  data() {
    return {
      refreshInterval: null,
      mcpServers: [],
      tools: [],
      showMcpServerDialog: false,

      selectedMcpServerProvider: "modelscope",
      mcpServerProviderList: ["modelscope"],
      mcpProviderToken: '',
      
      showSyncMcpServerDialog: false,
      addServerDialogMessage: "",
      showToolsDialog: false,
      showTools: true,
      loading: false,
      loadingGettingServers: false,
      mcpServerUpdateLoaders: {}, // record loading state for each server update
      isEditMode: false,
      serverConfigJson: '',
      jsonError: null,
      currentServer: {
        name: '',
        active: true,
        tools: []
      },
      save_message_snack: false,
      save_message: "",
      save_message_success: "success",
      toolSearch: '',
      openedPanel: [], // 存储打开的面板索引
    }
  },

  computed: {
    filteredTools() {
      if (!this.toolSearch) return this.tools;

      const searchTerm = this.toolSearch.toLowerCase();
      return this.tools.filter(tool =>
        tool.name.toLowerCase().includes(searchTerm) ||
        tool.description.toLowerCase().includes(searchTerm)
      );
    },

    isServerFormValid() {
      return !!this.currentServer.name && !this.jsonError;
    },

    // 显示服务器配置的文本摘要
    getServerConfigSummary() {
      return (server) => {
        if (server.command) {
          return `${server.command} ${(server.args || []).join(' ')}`;
        }

        // 如果没有command字段，尝试显示其他有意义的配置信息
        const configKeys = Object.keys(server).filter(key =>
          !['name', 'active', 'tools'].includes(key)
        );

        if (configKeys.length > 0) {
          return this.tm('mcpServers.status.configSummary', { keys: configKeys.join(', ') });
        }

        return this.tm('mcpServers.status.noConfig');
      }
    },
  },

  mounted() {
    this.getServers();
    this.getTools();

    this.refreshInterval = setInterval(() => {
      this.getServers();
      this.getTools();
    }, 5000);
  },

  unmounted() {
    // 清除定时器 if it exists
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  },

  methods: {
    openurl(url) {
      window.open(url, '_blank');
    },

    formatToolName(name) {
      if (name.includes(':')) {
        // MCP 工具通常命名为 mcp:server:tool
        const parts = name.split(':');
        return parts[parts.length - 1]; // 返回最后一部分
      }
      return name;
    },

    getServers() {
      this.loadingGettingServers = true;
      axios.get('/api/tools/mcp/servers')
        .then(response => {
          this.mcpServers = response.data.data || [];
          this.mcpServers.forEach(server => {
            // Ensure each server has a loader state
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

    getTools() {
      axios.get('/api/tools/list')
        .then(response => {
          this.tools = response.data.data || [];
        })
        .catch(error => {
          this.showError(this.tm('messages.getToolsError', { error: error.message }));
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
          transport: "streamable_http",
          url: "your mcp server url",
          headers: {},
          timeout: 30,
        };
      } else if (type === 'sse') {
        template = {
          transport: "sse",
          url: "your mcp server url",
          headers: {},
          timeout: 30,
        };
      } else {
        template = {
          command: "python",
          args: ["-m", "your_module"],
        };
      }
      this.serverConfigJson = JSON.stringify(template, null, 2);
    },

    saveServer() {
      if (!this.validateJson()) {
        return;
      }

      this.loading = true;

      // 解析JSON配置并与基本信息合并
      try {
        const configObj = JSON.parse(this.serverConfigJson);

        // 创建要发送的完整配置对象
        const serverData = {
          name: this.currentServer.name,
          active: this.currentServer.active,
          ...configObj
        };

        const endpoint = this.isEditMode ? '/api/tools/mcp/update' : '/api/tools/mcp/add';

        axios.post(endpoint, serverData)
          .then(response => {
            this.loading = false;
            this.showMcpServerDialog = false;
            this.addServerDialogMessage = "";
            this.getServers();
            this.getTools();
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

    deleteServer(server) {
      let serverName = server.name || server;
      if (confirm(this.tm('dialogs.confirmDelete', { name: serverName }))) {
        axios.post('/api/tools/mcp/delete', { name: serverName })
          .then(response => {
            this.getServers();
            this.getTools();
            this.showSuccess(response.data.message || this.tm('messages.deleteSuccess'));
          })
          .catch(error => {
            this.showError(this.tm('messages.deleteError', { error: error.response?.data?.message || error.message }));
          });
      }
    },

    editServer(server) {
      // 创建一个不包含基本字段的配置对象副本
      const configCopy = { ...server };

      // 移除基本字段，只保留配置相关字段
      try {
        delete configCopy.name;
        delete configCopy.active;
        delete configCopy.tools;
        delete configCopy.errlogs;
      } catch (e) {
        console.error("Error removing basic fields: ", e);
      }

      // 设置当前服务器的基本信息
      this.currentServer = {
        name: server.name,
        active: server.active,
        tools: server.tools || []
      };

      // 将剩余配置转换为JSON字符串
      this.serverConfigJson = JSON.stringify(configCopy, null, 2);

      this.isEditMode = true;
      this.showMcpServerDialog = true;
    },

    updateServerStatus(server) {
      // 切换服务器状态
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
        "mcp_server_config": configObj,
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
    },

    showSuccess(message) {
      this.save_message = message;
      this.save_message_success = "success";
      this.save_message_snack = true;
    },

    showError(message) {
      this.save_message = message;
      this.save_message_success = "error";
      this.save_message_snack = true;
    },

    // MCP 市场相关方法已移除

    // 切换工具状态
    async toggleToolStatus(tool) {
      try {
        const response = await axios.post('/api/tools/toggle-tool', {
          name: tool.name,
          activate: tool.active
        });

        if (response.data.status === 'ok') {
          this.showSuccess(response.data.message || this.tm('messages.toggleToolSuccess'));
        } else {
          // 如果失败，恢复原状态
          tool.active = !tool.active;
          this.showError(response.data.message || this.tm('messages.toggleToolError'));
        }
      } catch (error) {
        // 如果失败，恢复原状态
        tool.active = !tool.active;
        this.showError(this.tm('messages.toggleToolError', { error: error.response?.data?.message || error.message }));
      }
    },

    // 同步 MCP 服务器
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

        // 根据不同平台添加相应的参数
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
          // 刷新服务器列表
          this.getServers();
          this.getTools();
        } else {
          this.showError(response.data.message || this.tm('syncProvider.messages.syncError', { error: 'Unknown error' }));
        }
      } catch (error) {
        console.error('同步 MCP 服务器失败:', error);
        this.showError(this.tm('syncProvider.messages.syncError', { 
          error: error.response?.data?.message || error.message || '网络连接或访问令牌问题' 
        }));
      } finally {
        this.loading = false;
      }
    }
  }
}
</script>

<style scoped>
.tools-page {
  padding: 20px;
  padding-top: 8px;
}

.tool-chips {
  max-height: 60px;
  overflow-y: auto;
}

.tool-panel {
  border: 1px solid rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
}

.tool-panel:hover {
  border-color: rgba(0, 0, 0, 0.1);
}

.params-table {
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
}

.params-table th {
  background-color: rgba(0, 0, 0, 0.02);
}

.monaco-container {
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  height: 300px;
  margin-top: 4px;
  overflow: hidden;
}
</style>