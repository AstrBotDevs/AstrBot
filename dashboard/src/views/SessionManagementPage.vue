<template>
  <v-container fluid>
    <div class="d-flex justify-space-between align-center mb-4">
      <h2 class="text-h4 font-weight-bold">会话管理</h2>
      <v-btn 
        color="primary" 
        prepend-icon="mdi-refresh" 
        @click="refreshSessions"
        :loading="loading"
      >
        刷新
      </v-btn>
    </div>

    <v-card>
      <v-card-title class="bg-primary text-white py-3 px-4">
        <v-icon color="white" class="me-2">mdi-account-group</v-icon>
        <span>活跃会话</span>
        <v-spacer></v-spacer>
        <v-chip color="white" text-color="primary" small>
          {{ sessions.length }} 个会话
        </v-chip>
      </v-card-title>

      <v-card-text class="pa-0">
        <!-- 搜索栏 -->
        <v-toolbar flat class="px-4">
          <v-text-field
            v-model="searchQuery"
            prepend-inner-icon="mdi-magnify"
            label="搜索会话..."
            hide-details
            clearable
            class="me-4"
          ></v-text-field>
          
          <v-select
            v-model="filterPlatform"
            :items="platformOptions"
            label="平台筛选"
            hide-details
            clearable
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
              <div class="font-weight-medium">{{ item.session_name }}</div>
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
              @update:model-value="(value) => updateProvider(item, value, 'text_to_speech')"
              :loading="item.updating"
              :disabled="ttsProviderOptions.length === 0"
            >
              <template v-slot:selection="{ item: selection }">
                <v-chip size="small" color="warning">
                  {{ selection.raw.label }}
                </v-chip>
              </template>
            </v-select>
          </template>

          <!-- 操作 -->
          <template v-slot:item.actions="{ item }">
            <v-btn
              icon="mdi-information"
              size="small"
              variant="text"
              @click="showSessionDetail(item)"
            ></v-btn>
          </template>

          <!-- 空状态 -->
          <template v-slot:no-data>
            <div class="text-center py-8">
              <v-icon size="64" color="grey-400">mdi-account-group-outline</v-icon>
              <div class="text-h6 mt-4 text-grey-600">暂无活跃会话</div>
              <div class="text-body-2 text-grey-500">当有用户与机器人交互时，会话将会显示在这里</div>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- 批量操作面板 -->
    <v-card class="mt-4" v-if="availablePersonas.length > 0 || availableChatProviders.length > 0">
      <v-card-title class="bg-secondary text-white py-3 px-4">
        <v-icon color="white" class="me-2">mdi-cog-outline</v-icon>
        <span>批量操作</span>
      </v-card-title>
      
      <v-card-text class="pa-4">
        <v-row>
          <v-col cols="12" md="4" v-if="availablePersonas.length > 0">
            <v-select
              v-model="batchPersona"
              :items="personaOptions"
              item-title="label"
              item-value="value"
              label="批量设置人格"
              hide-details
              clearable
            ></v-select>
          </v-col>
          
          <v-col cols="12" md="4" v-if="availableChatProviders.length > 0">
            <v-select
              v-model="batchChatProvider"
              :items="chatProviderOptions"
              item-title="label"
              item-value="value"
              label="批量设置 Chat Provider"
              hide-details
              clearable
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
              应用批量设置
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- 会话详情对话框 -->
    <v-dialog v-model="detailDialog" max-width="600">
      <v-card v-if="selectedSession">
        <v-card-title class="bg-primary text-white py-3 px-4">
          <v-icon color="white" class="me-2">mdi-information</v-icon>
          <span>会话详情</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="detailDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text class="pa-4">
          <v-list>
            <v-list-item>
              <v-list-item-title>会话 ID</v-list-item-title>
              <v-list-item-subtitle>{{ selectedSession.session_id }}</v-list-item-subtitle>
            </v-list-item>
            
            <v-list-item>
              <v-list-item-title>对话 ID</v-list-item-title>
              <v-list-item-subtitle>{{ selectedSession.conversation_id }}</v-list-item-subtitle>
            </v-list-item>
            
            <v-list-item>
              <v-list-item-title>平台</v-list-item-title>
              <v-list-item-subtitle>
                <v-chip :color="getPlatformColor(selectedSession.platform)" size="small">
                  {{ selectedSession.platform }}
                </v-chip>
              </v-list-item-subtitle>
            </v-list-item>
            
            <v-list-item>
              <v-list-item-title>消息类型</v-list-item-title>
              <v-list-item-subtitle>{{ selectedSession.message_type }}</v-list-item-subtitle>
            </v-list-item>
            
            <v-list-item>
              <v-list-item-title>当前人格</v-list-item-title>
              <v-list-item-subtitle>
                <v-chip 
                  size="small" 
                  :color="selectedSession.persona_id === '[%None]' ? 'grey' : 'primary'"
                >
                  {{ selectedSession.persona_name || '默认' }}
                </v-chip>
              </v-list-item-subtitle>
            </v-list-item>
            
            <v-list-item>
              <v-list-item-title>Chat Provider</v-list-item-title>
              <v-list-item-subtitle>
                <v-chip size="small" color="success">
                  {{ selectedSession.chat_provider_name || '未设置' }}
                </v-chip>
              </v-list-item-subtitle>
            </v-list-item>
            
            <v-list-item v-if="selectedSession.stt_provider_name">
              <v-list-item-title>STT Provider</v-list-item-title>
              <v-list-item-subtitle>
                <v-chip size="small" color="info">
                  {{ selectedSession.stt_provider_name }}
                </v-chip>
              </v-list-item-subtitle>
            </v-list-item>
            
            <v-list-item v-if="selectedSession.tts_provider_name">
              <v-list-item-title>TTS Provider</v-list-item-title>
              <v-list-item-subtitle>
                <v-chip size="small" color="warning">
                  {{ selectedSession.tts_provider_name }}
                </v-chip>
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
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

export default {
  name: 'SessionManagementPage',
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
      
      // 对话框
      detailDialog: false,
      selectedSession: null,
      
      // 提示信息
      snackbar: false,
      snackbarText: '',
      snackbarColor: 'success',
      
      // 表格头部
      headers: [
        { title: '会话信息', key: 'session_info', sortable: false, width: '200px' },
        { title: '人格', key: 'persona', sortable: false, width: '180px' },
        { title: 'Chat Provider', key: 'chat_provider', sortable: false, width: '180px' },
        { title: 'STT Provider', key: 'stt_provider', sortable: false, width: '150px' },
        { title: 'TTS Provider', key: 'tts_provider', sortable: false, width: '150px' },
        { title: '操作', key: 'actions', sortable: false, width: '80px' },
      ],
    }
  },
  
  computed: {
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
        { label: '无人格', value: '[%None]' },
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
            updating: false // 添加更新状态标志
          }));
          this.availablePersonas = data.available_personas;
          this.availableChatProviders = data.available_chat_providers;
          this.availableSttProviders = data.available_stt_providers;
          this.availableTtsProviders = data.available_tts_providers;
        } else {
          this.showError(response.data.message || '加载会话列表失败');
        }
      } catch (error) {
        this.showError(error.response?.data?.message || '加载会话列表失败');
      }
      this.loading = false;
    },
    
    async refreshSessions() {
      await this.loadSessions();
      this.showSuccess('会话列表已刷新');
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
          session.persona_name = personaName === '[%None]' ? '无人格' : 
            this.availablePersonas.find(p => p.name === personaName)?.name || personaName;
          this.showSuccess('人格更新成功');
        } else {
          this.showError(response.data.message || '人格更新失败');
        }
      } catch (error) {
        this.showError(error.response?.data?.message || '人格更新失败');
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
          this.showSuccess('Provider 更新成功');
        } else {
          this.showError(response.data.message || 'Provider 更新失败');
        }
      } catch (error) {
        this.showError(error.response?.data?.message || 'Provider 更新失败');
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
        this.showSuccess(`成功批量更新 ${successCount} 项设置`);
      } else {
        this.showError(`批量更新完成，${successCount} 项成功，${errorCount} 项失败`);
      }
      
      // 清空批量设置
      this.batchPersona = null;
      this.batchChatProvider = null;
    },
    
    showSessionDetail(session) {
      this.selectedSession = session;
      this.detailDialog = true;
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
}

.v-select >>> .v-field__input {
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}
</style>
