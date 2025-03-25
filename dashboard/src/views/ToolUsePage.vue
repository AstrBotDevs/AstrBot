<template>
  <div class="tools-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row>
        <v-col cols="12">
          <h1 class="text-h4 font-weight-bold mb-2">
            <v-icon size="x-large" color="primary" class="me-2">mdi-function-variant</v-icon>函数工具管理
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4 d-flex align-center">
            管理 MCP 服务器和查看可用的函数工具 
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-icon 
                  v-bind="props"
                  size="small" 
                  color="primary" 
                  class="ms-1 cursor-pointer"
                  @click="openurl('https://astrbot.app/use/function-calling.html')"
                >
                  mdi-information
                </v-icon>
              </template>
              <span>函数调用和 MCP 是什么？</span>
            </v-tooltip>
          </p>
        </v-col>
      </v-row>

      <!-- MCP 服务器部分 -->
      <v-card class="mb-6" elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-server</v-icon>
          <span class="text-h6">MCP 服务器</span>
          <v-spacer></v-spacer>
          <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="showMcpServerDialog = true">
            新增服务器
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="px-4 py-3">
          <v-row v-if="mcpServers.length === 0">
            <v-col cols="12" class="text-center pa-8">
              <v-icon size="64" color="grey-lighten-1">mdi-server-off</v-icon>
              <p class="text-grey mt-4">暂无 MCP 服务器，点击"新增服务器"添加</p>
            </v-col>
          </v-row>

          <v-row v-else>
            <v-col v-for="(server, index) in mcpServers" :key="index" cols="12" md="6" lg="4" xl="3">
              <v-card class="server-card hover-elevation" :color="server.active ? '' : 'grey-lighten-4'">
                <div class="server-status-indicator" :class="{'active': server.active}"></div>
                <v-card-title class="d-flex justify-space-between align-center pb-1 pt-3">
                  <span class="text-h6 text-truncate" :title="server.name">{{ server.name }}</span>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-switch color="primary" hide-details density="compact" v-model="server.active"
                        v-bind="props" @update:modelValue="updateServerStatus(server)"></v-switch>
                    </template>
                    <span>{{ server.active ? '已启用' : '已禁用' }}</span>
                  </v-tooltip>
                </v-card-title>
                
                <v-card-text>
                  <div class="d-flex align-center mb-2">
                    <v-icon size="small" color="grey" class="me-2">mdi-file-code</v-icon>
                    <span class="text-caption text-medium-emphasis text-truncate" :title="getServerConfigSummary(server)">
                      {{ getServerConfigSummary(server) }}
                    </span>
                  </div>
                  
                  <div v-if="server.tools && server.tools.length > 0">
                    <div class="d-flex align-center mb-1">
                      <v-icon size="small" color="grey" class="me-2">mdi-tools</v-icon>
                      <span class="text-caption text-medium-emphasis">可用工具 ({{ server.tools.length }})</span>
                    </div>
                    <v-chip-group class="tool-chips">
                      <v-chip v-for="(tool, idx) in server.tools" :key="idx" size="x-small" 
                              density="compact" color="info" class="text-caption">
                        {{ tool }}
                      </v-chip>
                    </v-chip-group>
                  </div>
                  <div v-else class="text-caption text-medium-emphasis mt-2">
                    <v-icon size="small" color="warning" class="me-1">mdi-alert-circle</v-icon>
                    无可用工具
                  </div>
                </v-card-text>
                
                <v-divider></v-divider>
                
                <v-card-actions class="pa-2">
                  <v-spacer></v-spacer>
                  <v-btn variant="text" size="small" color="error" prepend-icon="mdi-delete" 
                         @click="deleteServer(server.name)">
                    删除
                  </v-btn>
                  <v-btn variant="text" size="small" color="primary" prepend-icon="mdi-pencil" 
                         @click="editServer(server)">
                    编辑
                  </v-btn>
                </v-card-actions>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 函数工具部分 -->
      <v-card elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-function</v-icon>
          <span class="text-h6">函数工具</span>
          <v-chip color="info" size="small" class="ml-2">{{ tools.length }}</v-chip>
          <v-spacer></v-spacer>
          <v-btn variant="text" color="primary" @click="showTools = !showTools">
            {{ showTools ? '收起' : '展开' }}
            <v-icon>{{ showTools ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-expand-transition>
          <v-card-text class="pa-3" v-if="showTools">
            <div v-if="tools.length === 0" class="text-center pa-8">
              <v-icon size="64" color="grey-lighten-1">mdi-api-off</v-icon>
              <p class="text-grey mt-4">没有可用的函数工具</p>
            </div>
            
            <div v-else>
              <v-text-field
                v-model="toolSearch"
                prepend-inner-icon="mdi-magnify"
                label="搜索函数工具"
                variant="outlined"
                density="compact"
                class="mb-4"
                hide-details
                clearable
              ></v-text-field>

              <v-expansion-panels v-model="openedPanel" multiple>
                <v-expansion-panel
                  v-for="(tool, index) in filteredTools"
                  :key="index"
                  :value="index"
                  class="mb-2 tool-panel"
                  rounded="lg"
                >
                  <v-expansion-panel-title>
                    <v-row no-gutters align="center">
                      <v-col cols="3">
                        <div class="d-flex align-center">
                          <v-icon color="primary" class="me-2" size="small">
                            {{ tool.function.name.includes(':') ? 'mdi-server-network' : 'mdi-function-variant' }}
                          </v-icon>
                          <span class="text-body-1 text-high-emphasis font-weight-medium text-truncate" 
                                :title="tool.function.name">
                            {{ formatToolName(tool.function.name) }}
                          </span>
                        </div>
                      </v-col>
                      <v-col cols="9" class="text-grey">
                        {{ tool.function.description }}
                      </v-col>
                    </v-row>
                  </v-expansion-panel-title>
                  
                  <v-expansion-panel-text>
                    <v-card flat>
                      <v-card-text>
                        <p class="text-body-1 font-weight-medium mb-3">
                          <v-icon color="primary" size="small" class="me-1">mdi-information</v-icon>
                          功能描述
                        </p>
                        <p class="text-body-2 ml-6 mb-4">{{ tool.function.description }}</p>
                        
                        <template v-if="tool.function.parameters && tool.function.parameters.properties">
                          <p class="text-body-1 font-weight-medium mb-3">
                            <v-icon color="primary" size="small" class="me-1">mdi-code-json</v-icon>
                            参数列表
                          </p>
                          
                          <v-table density="compact" class="params-table mt-1">
                            <thead>
                              <tr>
                                <th>参数名</th>
                                <th>类型</th>
                                <th>描述</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr v-for="(param, paramName) in tool.function.parameters.properties" :key="paramName">
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
                          <p>此工具没有参数</p>
                        </div>
                      </v-card-text>
                    </v-card>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </div>
          </v-card-text>
        </v-expand-transition>
      </v-card>
    </v-container>

    <!-- 添加/编辑 MCP 服务器对话框 -->
    <v-dialog v-model="showMcpServerDialog" max-width="750px" persistent>
      <v-card>
        <v-card-title class="bg-primary text-white py-3">
          <v-icon color="white" class="me-2">{{ isEditMode ? 'mdi-pencil' : 'mdi-plus' }}</v-icon>
          <span>{{ isEditMode ? '编辑' : '新增' }} MCP 服务器</span>
        </v-card-title>
        
        <v-card-text class="py-4">
          <v-form @submit.prevent="saveServer" ref="form">
            <v-text-field
              v-model="currentServer.name"
              label="服务器名称"
              variant="outlined"
              :rules="[v => !!v || '名称是必填项']"
              required
              class="mb-3"
            ></v-text-field>
            
            <v-switch
              v-model="currentServer.active"
              label="启用服务器"
              color="primary"
              hide-details
              class="mb-3"
            ></v-switch>
            
            <div class="mb-2 d-flex align-center">
              <span class="text-subtitle-1">服务器配置</span>
              <v-tooltip location="top">
                <template v-slot:activator="{ props }">
                  <v-icon v-bind="props" class="ms-2" size="small" color="primary">mdi-information</v-icon>
                </template>
                <div>
                  <p class="mb-1">MCP 服务器(stdio)配置支持以下字段:</p>
                  <p class="mb-1"><code>command</code>: 命令名称 (例如 python 或 uv)</p>
                  <p class="mb-1"><code>args</code>: 命令参数数组 (例如 ["run", "server.py"])</p>
                  <p class="mb-1"><code>env</code>: 环境变量对象 (例如 {"api_key": "abc"})</p>
                  <p class="mb-1"><code>cwd</code>: 工作目录路径 (例如 /path/to/server)</p>
                  <p class="mb-1"><code>encoding</code>: 输出编码 (默认 utf-8)</p>
                  <p class="mb-1"><code>encoding_error_handler</code>: The text encoding error handler. Defaults to strict.</p>
                  <p class="mb-1">其他字段请参考 MCP 文档</p>
                  <p class="mb-1">⚠️ 如果您使用 Docker 部署 AstrBot, 请务必将 MCP 服务器装在 AstrBot 挂载好的 data 目录下</p>
                </div>
              </v-tooltip>
              <v-spacer></v-spacer>
              <v-btn 
                size="small" 
                color="info" 
                variant="text" 
                @click="setConfigTemplate"
                class="me-1"
              >
                使用模板
              </v-btn>
            </div>
            
            <div class="monaco-container">
              <VueMonacoEditor
                v-model:value="serverConfigJson"
                theme="vs-dark"
                language="json"
                :options="{
                  minimap: {
                    enabled: false
                  },
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  lineNumbers: 'on',
                  roundedSelection: true,
                  tabSize: 2
                }"
                @change="validateJson"
              />
            </div>

            <div v-if="jsonError" class="mt-2 text-error">
              <v-icon color="error" size="small" class="me-1">mdi-alert-circle</v-icon>
              <span>{{ jsonError }}</span>
            </div>
            
          </v-form>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeServerDialog" :disabled="loading">
            取消
          </v-btn>
          <v-btn 
            color="primary" 
            @click="saveServer" 
            :loading="loading"
            :disabled="!isServerFormValid"
          >
            保存
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

export default {
  name: 'ToolUsePage',
  components: {
    AstrBotConfig,
    VueMonacoEditor
  },
  data() {
    return {
      mcpServers: [],
      tools: [],
      showMcpServerDialog: false,
      showTools: true,
      loading: false,
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
        tool.function.name.toLowerCase().includes(searchTerm) || 
        tool.function.description.toLowerCase().includes(searchTerm)
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
          return `配置: ${configKeys.join(', ')}`;
        }
        
        return '未设置配置';
      }
    }
  },

  mounted() {
    this.getServers();
    this.getTools();
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
      axios.get('/api/tools/mcp/servers')
        .then(response => {
          this.mcpServers = response.data.data || [];
        })
        .catch(error => {
          this.showError("获取 MCP 服务器列表失败: " + error.message);
        });
    },
    
    getTools() {
      axios.get('/api/config/llmtools')
        .then(response => {
          this.tools = response.data.data || [];
        })
        .catch(error => {
          this.showError("获取函数工具列表失败: " + error.message);
        });
    },
    
    validateJson() {
      try {
        if (!this.serverConfigJson.trim()) {
          this.jsonError = '配置不能为空';
          return false;
        }
        
        JSON.parse(this.serverConfigJson);
        this.jsonError = null;
        return true;
      } catch (e) {
        this.jsonError = `JSON 格式错误: ${e.message}`;
        return false;
      }
    },
    
    setConfigTemplate() {
      // 设置一个基本的配置模板
      const template = {
        command: "python",
        args: ["-m", "your_module"],
        // 可以添加其他 MCP 支持的配置项
      };
      
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
            this.getServers();
            this.getTools();
            this.showSuccess(response.data.message || "保存成功!");
            this.resetForm();
          })
          .catch(error => {
            this.loading = false;
            this.showError("保存失败: " + (error.response?.data?.message || error.message));
          });
      } catch (e) {
        this.loading = false;
        this.showError(`JSON 解析错误: ${e.message}`);
      }
    },
    
    deleteServer(serverName) {
      if (confirm(`确定要删除服务器 ${serverName} 吗?`)) {
        axios.post('/api/tools/mcp/delete', { name: serverName })
          .then(response => {
            this.getServers();
            this.getTools();
            this.showSuccess(response.data.message || "删除成功!");
          })
          .catch(error => {
            this.showError("删除失败: " + (error.response?.data?.message || error.message));
          });
      }
    },
    
    editServer(server) {
      // 创建一个不包含基本字段的配置对象副本
      const configCopy = { ...server };
      
      // 移除基本字段，只保留配置相关字段
      delete configCopy.name;
      delete configCopy.active;
      delete configCopy.tools;
      
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
      axios.post('/api/tools/mcp/update', server)
        .then(response => {
          this.getServers();
          this.showSuccess(response.data.message || "更新成功!");
        })
        .catch(error => {
          this.showError("更新失败: " + (error.response?.data?.message || error.message));
          // 回滚状态
          server.active = !server.active;
        });
    },
    
    closeServerDialog() {
      this.showMcpServerDialog = false;
      this.resetForm();
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
    }
  }
}
</script>

<style scoped>
.tools-page {
  padding: 20px;
  padding-top: 8px;
}

.server-card {
  position: relative;
  border-radius: 8px;
  transition: all 0.3s ease;
  overflow: hidden;
}

.server-status-indicator {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 4px;
  background-color: #e0e0e0;
}

.server-status-indicator.active {
  background-color: #4CAF50;
}

.hover-elevation:hover {
  box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
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
  border-radius: 4px;
  height: 300px;
  overflow: hidden;
}
</style>