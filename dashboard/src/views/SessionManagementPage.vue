<template>
  <v-container fluid>
    <div class="d-flex justify-space-between align-center mb-4">
      <h2 class="text-h4 font-weight-bold">{{ tm('title') }}</h2>
      <v-btn 
        color="primary" 
        prepend-icon="mdi-refresh" 
        @click="refreshSessions"
        :loading="loading"
      >
        {{ tm('buttons.refresh') }}
      </v-btn>
    </div>

    <v-card rounded="12" class="session-card">
      <v-card-title class="bg-primary text-white py-3 px-4 session-card-title">
        <v-icon color="white" class="me-2">mdi-account-group</v-icon>
        <span>{{ tm('sessions.activeSessions') }}</span>
        <v-spacer></v-spacer>
        <v-chip color="white" text-color="primary" small>
          {{ sessions.length }} {{ tm('sessions.sessionCount') }}
        </v-chip>
      </v-card-title>

      <v-card-text class="pa-0">
        <!-- 搜索栏 -->
        <v-toolbar flat class="px-4">
          <v-text-field
            v-model="searchQuery"
            prepend-inner-icon="mdi-magnify"
            :label="tm('search.placeholder')"
            hide-details
            clearable
            variant="outlined"
            class="me-4"
          ></v-text-field>
          
          <v-select
            v-model="filterPlatform"
            :items="platformOptions"
            :label="tm('search.platformFilter')"
            hide-details
            clearable
            variant="outlined"
            class="me-4"
            style="max-width: 150px;"
          ></v-select>
        </v-toolbar>

        <v-divider></v-divider>

        <!-- 会话列表 -->
        <v-data-table
          :headers="headers"
          :items="filteredSessions"
          :loading="loading"
          :items-per-page="20"
          class="elevation-0"
        >
          <!-- 会话信息 -->
          <template v-slot:item.session_info="{ item }">
            <div class="py-2">
              <div class="d-flex align-center">
                <div class="flex-grow-1">
                  <div class="font-weight-medium d-flex align-center">
                    {{ item.session_name }}
                    <v-tooltip 
                      v-if="item.session_name !== item.session_raw_name" 
                      activator="parent" 
                      location="top"
                    >
                      <span class="text-caption">实际UMO: {{ item.session_raw_name }}</span>
                    </v-tooltip>
                    <v-icon 
                      v-if="item.session_name !== item.session_raw_name" 
                      size="12" 
                      color="warning" 
                      class="ml-1"
                    >
                      mdi-information-outline
                    </v-icon>
                  </div>
                  <div class="text-caption text-grey-600">
                    <v-chip 
                      :color="getPlatformColor(item.platform)" 
                      size="x-small" 
                      class="me-1"
                    >
                      {{ item.platform }}
                    </v-chip>
                    {{ item.message_type }}
                  </div>
                </div>
                <v-btn
                  icon
                  size="small"
                  variant="text"
                  color="primary"
                  @click="openNameEditor(item)"
                  :loading="item.updating"
                >
                  <v-icon size="16">mdi-pencil</v-icon>
                  <v-tooltip activator="parent" location="top">
                    {{ tm('buttons.editName') }}
                  </v-tooltip>
                </v-btn>
              </div>
            </div>
          </template>

          <!-- 人格 -->
          <template v-slot:item.persona="{ item }">
            <v-select
              :model-value="item.persona_id || ''"
              :items="personaOptions"
              item-title="label"
              item-value="value"
              hide-details
              density="compact"
              variant="outlined"
              @update:model-value="(value) => updatePersona(item, value)"
              :loading="item.updating"
            >
              <template v-slot:selection="{ item: selection }">
                <v-chip 
                  size="small" 
                  :color="selection.raw.value === '[%None]' ? 'grey' : 'primary'"
                >
                  {{ selection.raw.label }}
                </v-chip>
              </template>
            </v-select>
          </template>

          <!-- Chat Provider -->
          <template v-slot:item.chat_provider="{ item }">
            <v-select
              :model-value="item.chat_provider_id || ''"
              :items="chatProviderOptions"
              item-title="label"
              item-value="value"
              hide-details
              density="compact"
              variant="outlined"
              @update:model-value="(value) => updateProvider(item, value, 'chat_completion')"
              :loading="item.updating"
            >
              <template v-slot:selection="{ item: selection }">
                <v-chip size="small" color="success">
                  {{ selection.raw.label }}
                </v-chip>
              </template>
            </v-select>
          </template>

          <!-- STT Provider -->
          <template v-slot:item.stt_provider="{ item }">
            <v-select
              :model-value="item.stt_provider_id || ''"
              :items="sttProviderOptions"
              item-title="label"
              item-value="value"
              hide-details
              density="compact"
              variant="outlined"
              @update:model-value="(value) => updateProvider(item, value, 'speech_to_text')"
              :loading="item.updating"
              :disabled="sttProviderOptions.length === 0"
            >
              <template v-slot:selection="{ item: selection }">
                <v-chip size="small" color="info">
                  {{ selection.raw.label }}
                </v-chip>
              </template>
            </v-select>
          </template>

          <!-- TTS Provider -->
          <template v-slot:item.tts_provider="{ item }">
            <v-select
              :model-value="item.tts_provider_id || ''"
              :items="ttsProviderOptions"
              item-title="label"
              item-value="value"
              hide-details
              density="compact"
              variant="outlined"
              @update:model-value="(value) => updateProvider(item, value, 'text_to_speech')"
              :loading="item.updating"
              :disabled="ttsProviderOptions.length === 0"
            >
              <template v-slot:selection="{ item: selection }">
                <v-chip size="small" color="warning">
                  {{ selection.raw.label }}
                </v-chip>
              </template>
            </v-select>          </template>

          <!-- LLM启停 -->
          <template v-slot:item.llm_enabled="{ item }">
            <v-switch
              :model-value="item.llm_enabled"
              @update:model-value="(value) => updateLLM(item, value)"
              :loading="item.updating"
              hide-details
              density="compact"
              color="primary"
              inset
            >
            </v-switch>
          </template>

          <!-- TTS启停 -->
          <template v-slot:item.tts_enabled="{ item }">
            <v-switch
              :model-value="item.tts_enabled"
              @update:model-value="(value) => updateTTS(item, value)"
              :loading="item.updating"
              hide-details
              density="compact"
              color="secondary"
              inset
            >
            </v-switch>
          </template>

          <!-- MCP启停 -->
          <template v-slot:item.mcp_enabled="{ item }">
            <v-switch
              :model-value="item.mcp_enabled"
              @update:model-value="(value) => updateMCP(item, value)"
              :loading="item.updating"
              hide-details
              density="compact"
              color="info"
              inset
            >
            </v-switch>
          </template>

          <!-- 插件管理 -->
          <template v-slot:item.plugins="{ item }">
            <v-btn
              size="small"
              variant="outlined"
              color="primary"
              @click="openPluginManager(item)"
              :loading="item.loadingPlugins"
            >
              {{ tm('buttons.edit') }}
            </v-btn>
          </template>

          <!-- 空状态 -->
          <template v-slot:no-data>
            <div class="text-center py-8">
              <v-icon size="64" color="grey-400">mdi-account-group-outline</v-icon>
              <div class="text-h6 mt-4 text-grey-600">{{ tm('sessions.noActiveSessions') }}</div>
              <div class="text-body-2 text-grey-500">{{ tm('sessions.noActiveSessionsDesc') }}</div>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- 批量操作面板 -->
    <v-card class="mt-4" v-if="availablePersonas.length > 0 || availableChatProviders.length > 0">
      <v-card-title class="bg-secondary text-white py-3 px-4">
        <v-icon color="white" class="me-2">mdi-cog-outline</v-icon>
        <span>{{ tm('batchOperations.title') }}</span>
      </v-card-title>
      
      <v-card-text class="pa-4">
        <v-row>
          <v-col cols="12" md="4" v-if="availablePersonas.length > 0">
            <v-select
              v-model="batchPersona"
              :items="personaOptions"
              item-title="label"
              item-value="value"
              :label="tm('batchOperations.setPersona')"
              hide-details
              clearable
              variant="outlined"
            ></v-select>
          </v-col>
          
          <v-col cols="12" md="4" v-if="availableChatProviders.length > 0">
            <v-select
              v-model="batchChatProvider"
              :items="chatProviderOptions"
              item-title="label"
              item-value="value"
              :label="tm('batchOperations.setChatProvider')"
              hide-details
              clearable
              variant="outlined"
            ></v-select>
          </v-col>
          
          <v-col cols="12" md="4">
            <v-btn
              color="primary"
              block
              @click="applyBatchChanges"
              :disabled="!batchPersona && !batchChatProvider"
              :loading="batchUpdating"
            >
              {{ tm('buttons.apply') }}
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- 插件管理对话框 -->
    <v-dialog v-model="pluginDialog" max-width="800">
      <v-card v-if="selectedSessionForPlugin">
        <v-card-title class="bg-primary text-white py-3 px-4">
          <v-icon color="white" class="me-2">mdi-pencil</v-icon>
          <span>{{ tm('pluginManagement.title') }} - {{ selectedSessionForPlugin.session_name }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="pluginDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text class="pa-4" v-if="!loadingPlugins">
          <div v-if="sessionPlugins.length === 0" class="text-center py-8">
            <v-icon size="64" color="grey-400">mdi-puzzle-outline</v-icon>
            <div class="text-h6 mt-4 text-grey-600">{{ tm('pluginManagement.noPlugins') }}</div>
            <div class="text-body-2 text-grey-500">{{ tm('pluginManagement.noPluginsDesc') }}</div>
          </div>
          
          <v-list v-else>
            <v-list-item
              v-for="plugin in sessionPlugins"
              :key="plugin.name"
              class="px-0"
            >
              <template v-slot:prepend>
                <v-icon :color="plugin.enabled ? 'success' : 'grey'">
                  {{ plugin.enabled ? 'mdi-check-circle' : 'mdi-circle-outline' }}
                </v-icon>
              </template>
              
              <v-list-item-title class="font-weight-medium">
                {{ plugin.name }}
              </v-list-item-title>
              
              <v-list-item-subtitle>
                {{ tm('pluginManagement.author') }}: {{ plugin.author }}
              </v-list-item-subtitle>
              
              <template v-slot:append>
                <v-switch
                  :model-value="plugin.enabled"
                  hide-details
                  color="primary"
                  @update:model-value="(value) => togglePlugin(plugin, value)"
                  :loading="plugin.updating"
                ></v-switch>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        
        <v-card-text v-else class="text-center py-8">
          <v-progress-circular indeterminate color="primary" size="48"></v-progress-circular>
          <div class="text-body-1 mt-4">{{ tm('pluginManagement.loading') }}</div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 会话命名编辑对话框 -->
    <v-dialog v-model="nameEditDialog" max-width="500">
      <v-card v-if="selectedSessionForName">
        <v-card-title class="bg-primary text-white py-3 px-4 d-flex align-center">
          <v-icon color="white" class="me-2">mdi-rename-box</v-icon>
          <span>{{ tm('nameEditor.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="nameEditDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text class="pa-4">
          <v-text-field
            v-model="newSessionName"
            :label="tm('nameEditor.customName')"
            :placeholder="tm('nameEditor.placeholder')"
            variant="outlined"
            hide-details="auto"
            clearable
            class="mb-4"
            @keyup.enter="saveSessionName"
          ></v-text-field>
          
          <div class="text-caption text-grey-600 mb-2">
            {{ tm('nameEditor.originalName') }}: {{ selectedSessionForName.session_raw_name }}
          </div>
          
          <div class="text-caption text-grey-600 mb-2">
            {{ tm('nameEditor.fullSessionId') }}: {{ selectedSessionForName.session_id }}
          </div>
          
          <v-alert 
            variant="tonal" 
            type="info" 
            density="compact" 
            class="mb-4"
          >
            {{ tm('nameEditor.hint') }}
          </v-alert>
        </v-card-text>

        <v-card-actions class="px-4 pb-4">
          <v-spacer></v-spacer>
          <v-btn 
            color="grey" 
            variant="text" 
            @click="nameEditDialog = false"
            :disabled="nameEditLoading"
          >
            {{ tm('buttons.cancel') }}
          </v-btn>
          <v-btn 
            color="primary" 
            @click="saveSessionName"
            :loading="nameEditLoading"
          >
            {{ tm('buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 提示信息 -->
    <v-snackbar v-model="snackbar" :timeout="3000" :color="snackbarColor">
      {{ snackbarText }}
    </v-snackbar>
  </v-container>
</template>

<script>
import axios from 'axios'
import { useI18n, useModuleI18n } from '@/i18n/composables'

export default {
  name: 'SessionManagementPage',
  setup() {
    const { t } = useI18n()
    const { tm } = useModuleI18n('features/session-management')
    
    return {
      t,
      tm
    }
  },
  data() {
    return {
      loading: false,
      sessions: [],
      searchQuery: '',
      filterPlatform: null,
      
      // 可用选项
      availablePersonas: [],
      availableChatProviders: [],
      availableSttProviders: [],
      availableTtsProviders: [],
      
      // 批量操作
      batchPersona: null,
      batchChatProvider: null,
      batchUpdating: false,
      
      // 插件管理
      pluginDialog: false,
      selectedSessionForPlugin: null,
      sessionPlugins: [],
      loadingPlugins: false,
      
      // 会话命名编辑器
      nameEditDialog: false,
      selectedSessionForName: null,
      newSessionName: '',
      nameEditLoading: false,
      
      // 提示信息
      snackbar: false,
      snackbarText: '',
      snackbarColor: 'success',
    }
  },
  
  computed: {
    headers() {
      return [
        { title: this.tm('table.headers.sessionInfo'), key: 'session_info', sortable: false, width: '200px' },
        { title: this.tm('table.headers.persona'), key: 'persona', sortable: false, width: '180px' },
        { title: this.tm('table.headers.chatProvider'), key: 'chat_provider', sortable: false, width: '180px' },
        { title: this.tm('table.headers.sttProvider'), key: 'stt_provider', sortable: false, width: '150px' },
        { title: this.tm('table.headers.ttsProvider'), key: 'tts_provider', sortable: false, width: '150px' },
        { title: this.tm('table.headers.llmStatus'), key: 'llm_enabled', sortable: false, width: '120px' },
        { title: this.tm('table.headers.ttsStatus'), key: 'tts_enabled', sortable: false, width: '120px' },
        { title: this.tm('table.headers.mcpStatus'), key: 'mcp_enabled', sortable: false, width: '120px' },
        { title: this.tm('table.headers.pluginManagement'), key: 'plugins', sortable: false, width: '120px' },
      ]
    },
    filteredSessions() {
      let filtered = this.sessions;
      
      // 搜索筛选
      if (this.searchQuery) {
        const query = this.searchQuery.toLowerCase();
        filtered = filtered.filter(session => 
          session.session_name.toLowerCase().includes(query) ||
          session.platform.toLowerCase().includes(query) ||
          session.persona_name?.toLowerCase().includes(query) ||
          session.chat_provider_name?.toLowerCase().includes(query)
        );
      }
      
      // 平台筛选
      if (this.filterPlatform) {
        filtered = filtered.filter(session => session.platform === this.filterPlatform);
      }
      
      return filtered;
    },
    
    platformOptions() {
      const platforms = [...new Set(this.sessions.map(s => s.platform))];
      return platforms.map(p => ({ title: p, value: p }));
    },
    
    personaOptions() {
      const options = [
        { label: this.tm('persona.none'), value: '[%None]' },
        ...this.availablePersonas.map(p => ({
          label: p.name,
          value: p.name
        }))
      ];
      return options;
    },
    
    chatProviderOptions() {
      return this.availableChatProviders.map(p => ({
        label: `${p.name} (${p.model})`,
        value: p.id
      }));
    },
    
    sttProviderOptions() {
      return this.availableSttProviders.map(p => ({
        label: `${p.name} (${p.model})`,
        value: p.id
      }));
    },
    
    ttsProviderOptions() {
      return this.availableTtsProviders.map(p => ({
        label: `${p.name} (${p.model})`,
        value: p.id
      }));
    },
  },
  
  mounted() {
    this.loadSessions();
  },
  
  methods: {
    async loadSessions() {
      this.loading = true;
      try {
        const response = await axios.get('/api/session/list');
        if (response.data.status === 'ok') {
          const data = response.data.data;
          this.sessions = data.sessions.map(session => ({
            ...session,
            updating: false, // 添加更新状态标志
            loadingPlugins: false // 添加插件加载状态标志
          }));
          this.availablePersonas = data.available_personas;
          this.availableChatProviders = data.available_chat_providers;
          this.availableSttProviders = data.available_stt_providers;
          this.availableTtsProviders = data.available_tts_providers;
        } else {
          this.showError(response.data.message || this.tm('messages.loadSessionsError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.loadSessionsError'));
      }
      this.loading = false;
    },
    
    async refreshSessions() {
      await this.loadSessions();
      this.showSuccess(this.tm('messages.refreshSuccess'));
    },
    
    async updatePersona(session, personaName) {
      session.updating = true;
      try {
        const response = await axios.post('/api/session/update_persona', {
          session_id: session.session_id,
          persona_name: personaName
        });
        
        if (response.data.status === 'ok') {
          session.persona_id = personaName;
          session.persona_name = personaName === '[%None]' ? this.tm('persona.none') : 
            this.availablePersonas.find(p => p.name === personaName)?.name || personaName;
          this.showSuccess(this.tm('messages.personaUpdateSuccess'));
        } else {
          this.showError(response.data.message || this.tm('messages.personaUpdateError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.personaUpdateError'));
      }
      session.updating = false;
    },
    
    async updateProvider(session, providerId, providerType) {
      session.updating = true;
      try {
        const response = await axios.post('/api/session/update_provider', {
          session_id: session.session_id,
          provider_id: providerId,
          provider_type: providerType
        });
        
        if (response.data.status === 'ok') {
          // 更新本地数据
          if (providerType === 'chat_completion') {
            session.chat_provider_id = providerId;
            const provider = this.availableChatProviders.find(p => p.id === providerId);
            session.chat_provider_name = provider?.name || providerId;
          } else if (providerType === 'speech_to_text') {
            session.stt_provider_id = providerId;
            const provider = this.availableSttProviders.find(p => p.id === providerId);
            session.stt_provider_name = provider?.name || providerId;
          } else if (providerType === 'text_to_speech') {
            session.tts_provider_id = providerId;
            const provider = this.availableTtsProviders.find(p => p.id === providerId);
            session.tts_provider_name = provider?.name || providerId;
          }
          this.showSuccess(this.tm('messages.providerUpdateSuccess'));
        } else {
          this.showError(response.data.message || this.tm('messages.providerUpdateError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.providerUpdateError'));
      }      session.updating = false;
    },
    
    async updateLLM(session, enabled) {
      session.updating = true;
      try {
        const response = await axios.post('/api/session/update_llm', {
          session_id: session.session_id,
          enabled: enabled
        });
        
        if (response.data.status === 'ok') {
          session.llm_enabled = enabled;
          this.showSuccess(this.tm('messages.llmStatusSuccess', { status: enabled ? this.tm('status.enabled') : this.tm('status.disabled') }));
        } else {
          this.showError(response.data.message || this.tm('messages.statusUpdateError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.statusUpdateError'));
      }
      session.updating = false;
    },
    
    async updateTTS(session, enabled) {
      session.updating = true;
      try {
        const response = await axios.post('/api/session/update_tts', {
          session_id: session.session_id,
          enabled: enabled
        });
        
        if (response.data.status === 'ok') {
          session.tts_enabled = enabled;
          this.showSuccess(this.tm('messages.ttsStatusSuccess', { status: enabled ? this.tm('status.enabled') : this.tm('status.disabled') }));
        } else {
          this.showError(response.data.message || this.tm('messages.statusUpdateError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.statusUpdateError'));
      }
      session.updating = false;
    },
    
    async updateMCP(session, enabled) {
      session.updating = true;
      try {
        const response = await axios.post('/api/session/update_mcp', {
          session_id: session.session_id,
          enabled: enabled
        });
        
        if (response.data.status === 'ok') {
          session.mcp_enabled = enabled;
          this.showSuccess(this.tm('messages.mcpStatusSuccess', { status: enabled ? this.tm('status.enabled') : this.tm('status.disabled') }));
        } else {
          this.showError(response.data.message || this.tm('messages.statusUpdateError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.statusUpdateError'));
      }
      session.updating = false;
    },
    
    async applyBatchChanges() {
      if (!this.batchPersona && !this.batchChatProvider) {
        return;
      }
      
      this.batchUpdating = true;
      let successCount = 0;
      let errorCount = 0;
      
      for (const session of this.filteredSessions) {
        try {
          // 批量更新人格
          if (this.batchPersona) {
            await this.updatePersona(session, this.batchPersona);
            successCount++;
          }
          
          // 批量更新 Chat Provider
          if (this.batchChatProvider) {
            await this.updateProvider(session, this.batchChatProvider, 'chat_completion');
            successCount++;
          }
        } catch (error) {
          errorCount++;
        }
      }
      
      this.batchUpdating = false;
      
      if (errorCount === 0) {
        this.showSuccess(this.tm('messages.batchUpdateSuccess', { count: successCount }));
      } else {
        this.showError(this.tm('messages.batchUpdatePartial', { success: successCount, error: errorCount }));
      }
      
      // 清空批量设置
      this.batchPersona = null;
      this.batchChatProvider = null;
    },
    
    async openPluginManager(session) {
      this.selectedSessionForPlugin = session;
      this.pluginDialog = true;
      this.loadingPlugins = true;
      this.sessionPlugins = [];
      
      try {
        const response = await axios.get('/api/session/plugins', {
          params: { session_id: session.session_id }
        });
        
        if (response.data.status === 'ok') {
          this.sessionPlugins = response.data.data.plugins.map(plugin => ({
            ...plugin,
            updating: false
          }));
        } else {
          this.showError(response.data.message || this.tm('messages.loadPluginsError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.loadPluginsError'));
      }
      
      this.loadingPlugins = false;
    },
    
    async togglePlugin(plugin, enabled) {
      plugin.updating = true;
      
      try {
        const response = await axios.post('/api/session/update_plugin', {
          session_id: this.selectedSessionForPlugin.session_id,
          plugin_name: plugin.name,
          enabled: enabled
        });
        
        if (response.data.status === 'ok') {
          plugin.enabled = enabled;
          this.showSuccess(this.tm('messages.pluginStatusSuccess', { 
            name: plugin.name, 
            status: enabled ? this.tm('status.enabled') : this.tm('status.disabled') 
          }));
        } else {
          this.showError(response.data.message || this.tm('messages.pluginStatusError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.pluginStatusError'));
      }
      
      plugin.updating = false;
    },
    
    openNameEditor(session) {
      this.selectedSessionForName = session;
      this.newSessionName = session.session_name === session.session_raw_name ? '' : session.session_name;
      this.nameEditDialog = true;
    },
    
    async saveSessionName() {
      if (!this.selectedSessionForName) return;
      
      this.nameEditLoading = true;
      try {
        const response = await axios.post('/api/session/update_name', {
          session_id: this.selectedSessionForName.session_id,
          custom_name: this.newSessionName || ''
        });
        
        if (response.data.status === 'ok') {
          // 更新本地数据
          this.selectedSessionForName.session_name = response.data.data.display_name;
          this.showSuccess(response.data.data.message || this.tm('messages.nameUpdateSuccess'));
          this.nameEditDialog = false;
        } else {
          this.showError(response.data.message || this.tm('messages.nameUpdateError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.nameUpdateError'));
      }
      
      this.nameEditLoading = false;
    },
    
    getPlatformColor(platform) {
      const colors = {
        'aiocqhttp': 'blue',
        'wechatpadpro': 'green',
        'gewechat': 'green',
        'qq_official': 'purple',
        'telegram': 'light-blue',
        'discord': 'indigo',
        'default': 'grey'
      };
      return colors[platform] || colors.default;
    },
    
    showSuccess(message) {
      this.snackbarText = message;
      this.snackbarColor = 'success';
      this.snackbar = true;
    },
    
    showError(message) {
      this.snackbarText = message;
      this.snackbarColor = 'error';
      this.snackbar = true;
    },
  }
}
</script>

<style scoped>
.v-data-table >>> .v-data-table__td {
  padding: 8px 16px !important;
  vertical-align: middle !important;
}

.v-data-table >>> .v-data-table__th {
  vertical-align: middle !important;
}

.v-select >>> .v-field__input {
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}

.session-card {
  border-radius: 12px !important;
  overflow: hidden;
}

.session-card-title {
  border-top-left-radius: 12px !important;
  border-top-right-radius: 12px !important;
}
</style>
