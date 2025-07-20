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
        <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="showMcpServerDialog = true" rounded="xl"
          size="x-large">
          {{ tm('mcpServers.buttons.add') }}
        </v-btn>
      </v-row>

      <!-- 标签页切换 -->
      <v-tabs v-model="activeTab" color="primary" class="mb-6" show-arrows>
        <v-tab value="local" class="font-weight-medium">
          <v-icon start>mdi-server</v-icon>
          {{ tm('tabs.local') }}
        </v-tab>
        <v-tab value="marketplace" class="font-weight-medium">
          <v-icon start>mdi-store</v-icon>
          {{ tm('tabs.marketplace') }}
          <v-tooltip location="top" activator="parent">
            <span>{{ tm('tooltip.marketplace') }}</span>
          </v-tooltip>
        </v-tab>
      </v-tabs>

      <v-window v-model="activeTab">
        <!-- 本地服务器标签页内容 -->
        <v-window-item value="local">
          <!-- MCP 服务器部分 -->
          <v-card class="mb-6" elevation="2">
            <v-card-title class="d-flex align-center py-3 px-4">
              <v-icon color="primary" class="me-2">mdi-server</v-icon>
              <span class="text-h6">{{ tm('mcpServers.title') }}</span>
              <v-spacer></v-spacer>
              <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="getServers"
                :loading="loadingGettingServers">
                {{ tm('mcpServers.buttons.refresh') }}
              </v-btn>
              <v-btn color="primary" style="margin-left: 8px;" prepend-icon="mdi-plus" variant="tonal"
                @click="showMcpServerDialog = true">
                {{ tm('mcpServers.buttons.add') }}
              </v-btn>
            </v-card-title>

            <v-divider></v-divider>

            <v-card-text class="px-4 py-3">
              <div v-if="mcpServers.length === 0" class="text-center pa-8">
                <v-icon size="64" color="grey-lighten-1">mdi-server-off</v-icon>
                <p class="text-grey mt-4">{{ tm('mcpServers.empty') }}</p>
              </div>

              <v-row v-else>
                <v-col v-for="(server, index) in mcpServers || []" :key="index" cols="12" md="6" lg="4" xl="3">
                  <item-card style="background-color: #f7f2f9;" :item="server" title-field="name" enabled-field="active"
                    @toggle-enabled="updateServerStatus" @delete="deleteServer" @edit="editServer">
                    <template v-slot:item-details="{ item }">
                      <div class="d-flex align-center mb-2">
                        <v-icon size="small" color="grey" class="me-2">mdi-file-code</v-icon>
                        <span class="text-caption text-medium-emphasis text-truncate"
                          :title="getServerConfigSummary(item)">
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
            </v-card-text>
          </v-card>

          <!-- 函数工具部分 -->
          <v-card elevation="0" class="mt-4">
            <v-card-title class="d-flex align-center py-3 px-4">
              <v-icon color="primary" class="me-2">mdi-function</v-icon>
              <span class="text-h4">{{ tm('functionTools.title') }}</span>
              <v-chip color="info" size="small" class="ml-2">{{ tools.length }}</v-chip>
              <v-spacer></v-spacer>
              <v-btn variant="text" color="primary" @click="showTools = !showTools">
                {{ showTools ? tm('functionTools.buttons.collapse') : tm('functionTools.buttons.expand') }}
                <v-icon>{{ showTools ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
              </v-btn>
            </v-card-title>

            <v-divider></v-divider>

            <v-expand-transition>
              <v-card-text class="pa-0" v-if="showTools">
                <div class="pa-4">
                  <div v-if="tools.length === 0" class="text-center pa-8">
                    <v-icon size="64" color="grey-lighten-1">mdi-api-off</v-icon>
                    <p class="text-grey mt-4">{{ tm('functionTools.empty') }}</p>
                  </div>

                  <div v-else>
                    <v-text-field v-model="toolSearch" prepend-inner-icon="mdi-magnify"
                      :label="tm('functionTools.search')" variant="outlined" density="compact" class="mb-4" hide-details
                      clearable></v-text-field>

                    <v-expansion-panels v-model="openedPanel" multiple>
                      <v-expansion-panel v-for="(tool, index) in filteredTools" :key="index" :value="index"
                        class="mb-2 tool-panel" rounded="lg">
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
                                {{ tm('functionTools.description') }}
                              </p>
                              <p class="text-body-2 ml-6 mb-4">{{ tool.function.description }}</p>

                              <template v-if="tool.function.parameters && tool.function.parameters.properties">
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
                                    <tr v-for="(param, paramName) in tool.function.parameters.properties"
                                      :key="paramName">
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
          </v-card>
        </v-window-item>

        <!-- MCP市场标签页内容 -->
        <v-window-item value="marketplace">
          <v-card elevation="2">
            <v-card-title class="d-flex align-center py-3 px-4">
              <v-icon color="primary" class="me-2">mdi-store</v-icon>
              <span class="text-h6">{{ tm('marketplace.title') }}</span>
              <v-spacer></v-spacer>
              <v-text-field v-model="marketplaceSearch" prepend-inner-icon="mdi-magnify"
                :label="tm('marketplace.search')" variant="outlined" density="compact" hide-details class="mx-2"
                style="max-width: 300px" clearable @update:model-value="searchMarketplaceServers"></v-text-field>
              <v-btn color="primary" prepend-icon="mdi-refresh" variant="text" @click="fetchMarketplaceServers(1)"
                :loading="marketplaceLoading">
                {{ tm('marketplace.buttons.refresh') }}
              </v-btn>
            </v-card-title>

            <v-divider></v-divider>

            <v-card-text class="pa-3">
              <!-- 加载中 -->
              <div v-if="marketplaceLoading" class="text-center pa-8">
                <v-progress-circular indeterminate color="primary" size="64"></v-progress-circular>
                <p class="text-grey mt-4">{{ tm('marketplace.loading') }}</p>
              </div>

              <!-- 无数据 -->
              <div v-else-if="filteredMarketplaceServers.length === 0" class="text-center pa-8">
                <v-icon size="64" color="grey-lighten-1">mdi-store-off</v-icon>
                <p class="text-grey mt-4">{{ tm('marketplace.empty') }}</p>
              </div>

              <v-row v-else>
                <v-col v-for="(server, index) in filteredMarketplaceServers" :key="index" cols="12" md="6" lg="4">
                  <v-card class="marketplace-card hover-elevation" height="100%">
                    <v-card-title class="d-flex align-center pb-1 pt-3">
                      <span class="text-h4 text-truncate" :title="server.name">
                        {{ server.name_h }}({{ server.name }})
                      </span>
                      <v-btn icon="mdi-open-in-new" variant="text" color="primary" class="ms-auto"
                        @click.stop="openurl(server.origin)"></v-btn>
                    </v-card-title>

                    <v-card-text>

                      <div class="d-flex align-center mb-2">
                        <v-icon size="small" color="grey" class="me-2">mdi-tools</v-icon>
                        <span class="text-caption text-medium-emphasis">
                          {{ tm('marketplace.status.availableTools', { count: server.tools ? server.tools.length : 0 })
                          }}
                        </span>
                      </div>

                      <v-chip-group class="tool-chips mb-2" v-if="server.tools && server.tools.length > 0">
                        <v-chip v-for="(tool, idx) in server.tools" :key="idx" size="x-small" density="compact"
                          color="info" class="text-caption">
                          {{ tool.name }}
                        </v-chip>
                      </v-chip-group>
                      <div v-else class="text-caption text-medium-emphasis mb-2">
                        <v-icon size="small" color="warning" class="me-1">mdi-alert-circle</v-icon>
                        {{ tm('marketplace.status.noToolsInfo') }}
                      </div>
                    </v-card-text>

                    <v-divider></v-divider>

                    <v-card-actions class="pa-2">
                      <v-spacer></v-spacer>
                      <v-btn variant="text" size="small" color="info" prepend-icon="mdi-information-outline"
                        @click="showServerDetail(server)">
                        {{ tm('marketplace.buttons.detail') }}
                      </v-btn>
                      <v-btn variant="text" size="small" color="primary" prepend-icon="mdi-plus"
                        @click="importServerConfig(server)">
                        {{ tm('marketplace.buttons.import') }}
                      </v-btn>
                    </v-card-actions>
                  </v-card>
                </v-col>
              </v-row>

              <!-- 分页控件 -->
              <div class="d-flex justify-center mt-4">
                <v-pagination v-if="!marketplaceLoading && totalMarketPages > 1" v-model="currentMarketPage"
                  :length="totalMarketPages" total-visible="7" rounded @update:model-value="changePage"></v-pagination>
              </div>
            </v-card-text>
          </v-card>
        </v-window-item>
      </v-window>
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

    <!-- 服务器详情对话框 -->
    <v-dialog v-model="showServerDetailDialog" max-width="800px">
      <v-card>
        <v-card-title class="bg-primary text-white py-3">
          <v-icon color="white" class="me-2">mdi-information-outline</v-icon>
          <span>{{ tm('dialogs.serverDetail.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="showServerDetailDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text v-if="selectedMarketplaceServer" class="py-4">
          <h2 class="text-h5 mb-3">{{ selectedMarketplaceServer.name }}</h2>

          <div class="mb-4">
            <h3 class="text-subtitle-1 font-weight-bold mb-2">{{ tm('dialogs.serverDetail.installConfig') }}</h3>
            <div class="monaco-container" style="height: 200px">
              <VueMonacoEditor v-model:value="selectedServerConfigDisplay" theme="vs-dark" language="json" :options="{
                readOnly: true,
                minimap: {
                  enabled: false
                },
                scrollBeyondLastLine: false,
                automaticLayout: true,
                lineNumbers: 'on',
                tabSize: 2
              }" />
            </div>
          </div>

          <div v-if="selectedMarketplaceServer.tools && selectedMarketplaceServer.tools.length > 0">
            <h3 class="text-subtitle-1 font-weight-bold mb-2">
              {{ tm('dialogs.serverDetail.availableTools') }}
              <v-chip color="info" size="small" class="ml-1">{{ selectedMarketplaceServer.tools.length }}</v-chip>
            </h3>

            <v-expansion-panels>
              <v-expansion-panel v-for="(tool, index) in selectedMarketplaceServer.tools" :key="index" class="mb-2">
                <v-expansion-panel-title>
                  <div class="d-flex align-center">
                    <v-icon color="primary" class="me-2" size="small">mdi-function-variant</v-icon>
                    <span class="font-weight-medium">{{ tool.name }}</span>
                  </div>
                </v-expansion-panel-title>

                <v-expansion-panel-text>
                  <p class="mb-3">{{ tool.description }}</p>

                  <template v-if="tool.inputSchema && tool.inputSchema.properties">
                    <h4 class="text-subtitle-2 mb-2">{{ tm('functionTools.parameters') }}</h4>
                    <v-table density="compact">
                      <thead>
                        <tr>
                          <th>{{ tm('functionTools.table.paramName') }}</th>
                          <th>{{ tm('functionTools.table.type') }}</th>
                          <th>{{ tm('functionTools.table.required') }}</th>
                          <th>{{ tm('functionTools.table.description') }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(param, paramName) in tool.inputSchema.properties" :key="paramName">
                          <td class="font-weight-medium">{{ paramName }}</td>
                          <td>
                            <v-chip size="x-small" color="primary" text>
                              {{ param.type }}
                            </v-chip>
                          </td>
                          <td>
                            <v-icon v-if="tool.inputSchema.required && tool.inputSchema.required.includes(paramName)"
                              color="error" size="small">
                              mdi-check
                            </v-icon>
                            <span v-else>{{ t('core.common.no') }}</span>
                          </td>
                          <td>{{ param.description }}</td>
                        </tr>
                      </tbody>
                    </v-table>
                  </template>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </div>
        </v-card-text>

        <v-divider></v-divider>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showServerDetailDialog = false">
            {{ tm('dialogs.serverDetail.buttons.close') }}
          </v-btn>
          <v-btn color="primary" prepend-icon="mdi-plus" @click="importServerConfig(selectedMarketplaceServer)">
            {{ tm('dialogs.serverDetail.buttons.importConfig') }}
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
      activeTab: 'local', // 当前激活的标签页
      mcpServers: [],
      tools: [],
      showMcpServerDialog: false,
      showServerDetailDialog: false,
      addServerDialogMessage: "",
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

      // MCP 市场相关
      marketplaceServers: [],
      marketplaceLoading: false,
      marketplaceSearch: '',
      selectedMarketplaceServer: null,
      selectedServerConfigDisplay: '',

      // 分页相关
      currentMarketPage: 1,
      marketPageSize: 9, // 每页显示9个服务器，适合3列布局
      totalMarketPages: 1,
      totalMarketItems: 0,
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
          return this.tm('mcpServers.status.configSummary', { keys: configKeys.join(', ') });
        }

        return this.tm('mcpServers.status.noConfig');
      }
    },

    // 过滤后的市场服务器
    filteredMarketplaceServers() {
      if (!this.marketplaceSearch.trim()) {
        return this.marketplaceServers;
      }

      const searchTerm = this.marketplaceSearch.toLowerCase();
      return this.marketplaceServers.filter(server =>
        server.name.toLowerCase().includes(searchTerm) ||
        (server.name_h && server.name_h.toLowerCase().includes(searchTerm)) ||
        (server.description && server.description.toLowerCase().includes(searchTerm))
      );
    },
  },

  mounted() {
    this.getServers();
    this.getTools();
    this.fetchMarketplaceServers();

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
      axios.get('/api/config/llmtools')
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

    // MCP 市场相关方法

    // 获取市场服务器列表
    fetchMarketplaceServers(page = 1) {
      this.marketplaceLoading = true;

      // 构建请求参数
      const params = {
        page: page,
        page_size: this.marketPageSize
      };

      // 如果有搜索关键词，添加到请求参数
      if (this.marketplaceSearch.trim()) {
        params.search = this.marketplaceSearch.trim();
      }

      axios.get('/api/tools/mcp/market', { params })
        .then(response => {
          this.marketplaceServers = response.data.data.mcpservers || [];

          // 更新分页信息
          if (response.data.data.pagination) {
            this.totalMarketItems = response.data.data.pagination.total || 0;
            this.totalMarketPages = response.data.data.pagination.totalPages || 1;
            this.currentMarketPage = response.data.data.pagination.currentPage || 1;
          } else {
            // 如果后端没有返回分页信息，根据返回的数据量估算
            this.totalMarketPages = Math.ceil(this.marketplaceServers.length / this.marketPageSize) || 1;
          }

          this.marketplaceLoading = false;
        })
        .catch(error => {
          this.showError(this.tm('messages.getMarketError', { error: error.message }));
          this.marketplaceLoading = false;
        });
    },

    // 搜索市场服务器
    searchMarketplaceServers() {
      // 重置到第一页，然后获取结果
      this.currentMarketPage = 1;
      this.fetchMarketplaceServers(1);
    },

    // 切换分页
    changePage(page) {
      this.fetchMarketplaceServers(page);
    },

    // 显示服务器详情
    showServerDetail(server) {
      this.selectedMarketplaceServer = server;

      // 格式化服务器配置的显示
      try {
        if (server.config) {
          const configs = JSON.parse(server.config);
          this.selectedServerConfigDisplay = JSON.stringify(configs[0], null, 2);
        } else {
          this.selectedServerConfigDisplay = '// ' + this.tm('messages.noAvailableConfig');
        }
      } catch (e) {
        this.selectedServerConfigDisplay = '// ' + this.tm('messages.configParseError', { error: e.message });
      }

      this.showServerDetailDialog = true;
    },

    // 导入服务器配置
    importServerConfig(server) {
      try {
        // 解析服务器配置
        if (!server.config) {
          this.showError(this.tm('messages.importError.noConfig'));
          return;
        }

        const configs = JSON.parse(server.config);
        if (!configs || !configs[0] || !configs[0].mcpServers) {
          this.showError(this.tm('messages.importError.invalidFormat'));
          return;
        }

        // 找到服务器名称和配置
        const serverName = server.name;
        const serverConfig = configs[0]

        // 设置表单数据
        this.currentServer = {
          name: serverName,
          active: true,
          tools: []
        };

        // 设置配置JSON
        this.serverConfigJson = JSON.stringify(serverConfig, null, 2);

        // 关闭详情对话框(如果打开的话)
        this.showServerDetailDialog = false;

        // 打开添加服务器对话框
        this.isEditMode = false;
        this.showMcpServerDialog = true;

      } catch (e) {
        this.showError(this.tm('messages.importError.failed', { error: e.message }));
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

.marketplace-card {
  position: relative;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.text-truncate-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>