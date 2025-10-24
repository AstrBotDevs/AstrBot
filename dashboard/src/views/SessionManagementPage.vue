<template>
  <div class="session-management-page">
    <v-container fluid class="pa-0">
      <v-card flat>
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h4">{{ tm('sessions.activeSessions') }}</span>
          <v-chip size="small" class="ml-2">{{ totalItems }} {{ tm('sessions.sessionCount') }}</v-chip>
          <v-row class="me-4 ms-4" dense>
            <v-text-field v-model="searchQuery" prepend-inner-icon="mdi-magnify" :label="tm('search.placeholder')"
              hide-details clearable variant="solo-filled" flat class="me-4" density="compact" @update:model-value="handleSearchChange"></v-text-field>
            <v-select v-model="filterPlatform" :items="platformOptions" :label="tm('search.platformFilter')"
              hide-details clearable variant="solo-filled" flat class="me-4" style="max-width: 150px;"
              density="compact" @update:model-value="handlePlatformChange"></v-select>
          </v-row>
          <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="refreshSessions" :loading="loading"
            size="small">
            {{ tm('buttons.refresh') }}
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="pa-0">
          <!-- 会话列表 -->
          <v-data-table-server
            :headers="headers"
            :items="sessions"
            :loading="loading"
            :items-per-page="itemsPerPage"
            :page="currentPage"
            :items-length="totalItems"
            @update:options="handlePaginationUpdate"
            density="compact"
            class="elevation-0"
            style="font-size: 11px;">

            <!-- 会话启停 -->
            <template v-slot:item.session_enabled="{ item }">
              <v-checkbox :model-value="item.session_enabled"
                @update:model-value="(value) => updateSessionStatus(item, value)" :loading="item.updating" hide-details
                density="compact" color="success">
              </v-checkbox>
            </template>

            <!-- 会话信息 -->
            <template v-slot:item.session_info="{ item }">
              <div>
                <div class="d-flex align-center">
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props: tooltipProps }">
                      <div v-if="item.session_name !== item.session_raw_name">
                        <span>{{ item.session_name }}</span>
                        <span style="color: grey;">({{ item.session_id }})</span>
                      </div>
                      <div v-else>
                        <span v-bind="tooltipProps">{{ item.session_id }}</span>
                      </div>
                    </template>
                    <div>
                      <p>使用 /sid 指令可查看会话 ID。</p>
                      <p>会话信息：</p>
                      <ul>
                        <li>机器人 ID: {{ item.platform }}</li>
                        <li v-if="item.message_type">消息类型: {{ item.message_type }}</li>
                        <li v-if="item.session_raw_name">会话 ID: {{ item.session_raw_name }}</li>
                        <li v-if="item.user_name">用户: {{ item.user_name }}</li>
                      </ul>
                    </div>
                  </v-tooltip>

                  <v-btn icon size="x-small" variant="plain" @click="openNameEditor(item)" class="ml-2"
                    :loading="item.updating">
                    <v-icon>mdi-pencil</v-icon>
                    <v-tooltip activator="parent" location="top">
                      {{ tm('buttons.editName') }}
                    </v-tooltip>
                  </v-btn>
                </div>
              </div>
            </template>

            <!-- 人格 -->
            <template v-slot:item.persona="{ item }">
              <v-select :model-value="item.persona_id || ''" :items="personaOptions" item-title="label"
                item-value="value" hide-details density="compact" variant="solo-filled" flat
                @update:model-value="(value) => updatePersona(item, value)" :loading="item.updating"
                :disabled="!item.session_enabled">
                <template v-slot:selection="{ item: selection }">
                  <span style="font-size: 12px;">{{ selection.raw.label }}</span>
                </template>
              </v-select>
            </template>

            <!-- Chat Provider -->
            <template v-slot:item.chat_provider="{ item }">
              <v-select :model-value="item.chat_provider_id || ''" :items="chatProviderOptions" item-title="label"
                item-value="value" hide-details density="compact" variant="solo-filled" flat
                @update:model-value="(value) => updateProvider(item, value, 'chat_completion')" :loading="item.updating"
                :disabled="!item.session_enabled">
                <template v-slot:selection="{ item: selection }">
                  <span style="font-size: 12px;">{{ selection.raw.label }}</span>
                </template>
              </v-select>
            </template>

            <!-- STT Provider -->
            <template v-slot:item.stt_provider="{ item }">
              <v-select :model-value="item.stt_provider_id || ''" :items="sttProviderOptions" item-title="label"
                item-value="value" hide-details density="compact" variant="solo-filled" flat
                @update:model-value="(value) => updateProvider(item, value, 'speech_to_text')" :loading="item.updating"
                :disabled="sttProviderOptions.length === 0 || !item.session_enabled">
                <template v-slot:selection="{ item: selection }">
                  <span style="font-size: 12px;">{{ selection.raw.label }}</span>
                </template>
              </v-select>
            </template>

            <!-- TTS Provider -->
            <template v-slot:item.tts_provider="{ item }">
              <v-select :model-value="item.tts_provider_id || ''" :items="ttsProviderOptions" item-title="label"
                item-value="value" hide-details density="compact" variant="solo-filled" flat
                @update:model-value="(value) => updateProvider(item, value, 'text_to_speech')" :loading="item.updating"
                :disabled="ttsProviderOptions.length === 0 || !item.session_enabled">
                <template v-slot:selection="{ item: selection }">
                  <span style="font-size: 12px;">{{ selection.raw.label }}</span>
                </template>
              </v-select> </template>

            <!-- LLM启停 -->
            <template v-slot:item.llm_enabled="{ item }">
              <v-checkbox :model-value="item.llm_enabled" @update:model-value="(value) => updateLLM(item, value)"
                :loading="item.updating" :disabled="!item.session_enabled" hide-details density="compact"
                color="primary">
              </v-checkbox>
            </template>

            <!-- TTS启停 -->
            <template v-slot:item.tts_enabled="{ item }">
              <v-checkbox :model-value="item.tts_enabled" @update:model-value="(value) => updateTTS(item, value)"
                :loading="item.updating" :disabled="!item.session_enabled" hide-details density="compact"
                color="secondary">
              </v-checkbox>
            </template>

            <!-- 知识库配置 -->
            <template v-slot:item.knowledge_base="{ item }">
              <v-btn size="x-small" variant="tonal" color="info" @click="openKBManager(item)"
                :loading="item.loadingKB" :disabled="!item.session_enabled">
                {{ tm('knowledgeBase.configure') }}
              </v-btn>
            </template>

            <!-- 插件管理 -->
            <template v-slot:item.plugins="{ item }">
              <v-btn size="x-small" variant="tonal" color="primary" @click="openPluginManager(item)"
                :loading="item.loadingPlugins" :disabled="!item.session_enabled">
                {{ tm('buttons.edit') }}
              </v-btn>
            </template>

            <!-- 操作按钮 -->
            <template v-slot:item.actions="{ item }">
              <v-btn size="x-small" variant="tonal" color="error" @click="deleteSession(item)"
                :loading="item.deleting" icon>
                <v-icon>mdi-delete</v-icon>
                <v-tooltip activator="parent" location="top">
                  {{ tm('buttons.delete') }}
                </v-tooltip>
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
          </v-data-table-server>
        </v-card-text>
      </v-card>

      <!-- 批量操作面板 -->
      <v-card flat class="mt-4">
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h4">{{ tm('batchOperations.title') }}</span>
        </v-card-title>

        <v-card-text>
          <div style="padding: 16px;">
            <v-row>
              <v-col cols="12" md="6" lg="3" v-if="availablePersonas.length > 0">
                <v-select v-model="batchPersona" :items="personaOptions" item-title="label" item-value="value"
                  :label="tm('batchOperations.setPersona')" hide-details clearable variant="solo-filled" flat
                  density="comfortable" class="batch-select"></v-select>
              </v-col>

              <v-col cols="12" md="6" lg="3" v-if="availableChatProviders.length > 0">
                <v-select v-model="batchChatProvider" :items="chatProviderOptions" item-title="label" item-value="value"
                  :label="tm('batchOperations.setChatProvider')" hide-details clearable variant="solo-filled" flat
                  density="comfortable" class="batch-select"></v-select>
              </v-col>

              <v-col cols="12" md="6" lg="3">
                <v-select v-model="batchSttProvider" :items="sttProviderOptions" item-title="label" item-value="value"
                  :label="tm('batchOperations.setSttProvider')" hide-details clearable variant="solo-filled" flat
                  density="comfortable" class="batch-select" :disabled="availableSttProviders.length === 0"
                  :placeholder="availableSttProviders.length === 0 ? tm('batchOperations.noSttProvider') : ''"></v-select>
              </v-col>

              <v-col cols="12" md="6" lg="3">
                <v-select v-model="batchTtsProvider" :items="ttsProviderOptions" item-title="label" item-value="value"
                  :label="tm('batchOperations.setTtsProvider')" hide-details clearable variant="solo-filled" flat
                  density="comfortable" class="batch-select" :disabled="availableTtsProviders.length === 0"
                  :placeholder="availableTtsProviders.length === 0 ? tm('batchOperations.noTtsProvider') : ''"></v-select>
              </v-col>
            </v-row>

            <v-row>
              <v-col cols="12" md="6" lg="3">
                <v-select v-model="batchLlmStatus"
                  :items="[{ label: tm('status.enabled'), value: true }, { label: tm('status.disabled'), value: false }]"
                  item-title="label" item-value="value" :label="tm('batchOperations.setLlmStatus')" hide-details
                  clearable variant="solo-filled" flat density="comfortable" class="batch-select"></v-select>
              </v-col>

              <v-col cols="12" md="6" lg="3">
                <v-select v-model="batchTtsStatus"
                  :items="[{ label: tm('status.enabled'), value: true }, { label: tm('status.disabled'), value: false }]"
                  item-title="label" item-value="value" :label="tm('batchOperations.setTtsStatus')" hide-details
                  clearable variant="solo-filled" flat density="comfortable" class="batch-select"></v-select>
              </v-col>
            </v-row>

            <div class="d-flex justify-end align-center mt-8">
              <v-btn color="primary" variant="tonal" size="large" rounded="lg" @click="applyBatchChanges"
                :disabled="!batchPersona && !batchChatProvider && !batchSttProvider && !batchTtsProvider && batchLlmStatus === null && batchTtsStatus === null"
                :loading="batchUpdating" class="me-3">
                <v-icon start>mdi-check-all</v-icon>
                {{ tm('buttons.apply') }}
              </v-btn>

            </div>
          </div>

        </v-card-text>
      </v-card>

      <!-- 插件管理对话框 -->
      <v-dialog v-model="pluginDialog" max-width="800" min-height="80%">
        <v-card v-if="selectedSessionForPlugin">
          <v-card-title class="bg-primary text-white py-3 px-4" style="display: flex; align-items: center;">
            <span>{{ tm('pluginManagement.title') }} - {{ selectedSessionForPlugin.session_name }}</span>
            <v-spacer></v-spacer>
            <v-btn icon variant="text" color="white" @click="pluginDialog = false">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>

          <v-card-text v-if="!loadingPlugins">
            <div style="padding-left: 16px; padding-right: 16px;">
              <div v-if="sessionPlugins.length === 0" class="text-center py-8">
                <v-icon size="64" color="grey-400">mdi-puzzle-outline</v-icon>
                <div class="text-h6 mt-4 text-grey-600">{{ tm('pluginManagement.noPlugins') }}</div>
                <div class="text-body-2 text-grey-500">{{ tm('pluginManagement.noPluginsDesc') }}</div>
              </div>

              <v-list v-else>
                <v-list-item v-for="plugin in sessionPlugins" :key="plugin.name" class="px-0">
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
                    <v-checkbox :model-value="plugin.enabled" hide-details color="primary"
                      @update:model-value="(value) => togglePlugin(plugin, value)"
                      :loading="plugin.updating"></v-checkbox>
                  </template>
                </v-list-item>
              </v-list>
            </div>

          </v-card-text>

          <v-card-text v-else class="text-center py-8">
            <v-progress-circular indeterminate color="primary" size="48"></v-progress-circular>
            <div class="text-body-1 mt-4">{{ tm('pluginManagement.loading') }}</div>
          </v-card-text>
        </v-card>
      </v-dialog>

      <!-- 会话命名编辑对话框 -->
      <v-dialog v-model="nameEditDialog" max-width="500" min-height="60%">
        <v-card v-if="selectedSessionForName">
          <v-card-title class="bg-primary text-white py-3 px-4" style="display: flex; align-items: center;">
            <span>{{ tm('nameEditor.title') }}</span>
            <v-spacer></v-spacer>
            <v-btn icon variant="text" color="white" @click="nameEditDialog = false">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>

          <v-card-text>
            <div style="padding-left: 16px; padding-right: 16px;">
              <v-text-field v-model="newSessionName" :label="tm('nameEditor.customName')"
                :placeholder="tm('nameEditor.placeholder')" variant="solo-filled" flat hide-details="auto" clearable
                class="mb-4" @keyup.enter="saveSessionName"></v-text-field>

              <div class="text-caption text-grey-600 mb-2">
                {{ tm('nameEditor.originalName') }}: {{ selectedSessionForName.session_raw_name }}
              </div>

              <div class="text-caption text-grey-600 mb-2">
                {{ tm('nameEditor.fullSessionId') }}: {{ selectedSessionForName.session_id }}
              </div>

              <v-alert variant="tonal" type="info" density="compact" class="mb-4">
                {{ tm('nameEditor.hint') }}
              </v-alert>
            </div>
          </v-card-text>

          <v-card-actions class="px-4 pb-4">
            <v-spacer></v-spacer>
            <v-btn color="grey" variant="text" @click="nameEditDialog = false" :disabled="nameEditLoading">
              {{ tm('buttons.cancel') }}
            </v-btn>
            <v-btn color="primary" variant="tonal" @click="saveSessionName" :loading="nameEditLoading">
              {{ tm('buttons.save') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 知识库配置对话框 -->
      <v-dialog v-model="kbDialog" max-width="800" min-height="60%">
        <v-card v-if="selectedSessionForKB">
          <v-card-title class="bg-primary text-white py-3 px-4" style="display: flex; align-items: center;">
            <span>{{ tm('knowledgeBase.title') }} - {{ selectedSessionForKB.session_name }}</span>
            <v-spacer></v-spacer>
            <v-btn icon variant="text" color="white" @click="kbDialog = false">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>

          <v-card-text v-if="!loadingKBConfig">
            <div style="padding: 16px;">
              <v-alert type="info" variant="tonal" class="mb-4">
                {{ tm('knowledgeBase.description') }}
              </v-alert>

              <!-- 知识库选择 -->
              <v-select
                v-model="sessionKBConfig.kb_ids"
                :items="availableKBs"
                item-title="kb_name"
                item-value="kb_id"
                :label="tm('knowledgeBase.selectKB')"
                multiple
                chips
                closable-chips
                variant="outlined"
                class="mb-4"
                :hint="tm('knowledgeBase.selectMultiple')"
                persistent-hint
              >
                <template v-slot:chip="{ item }">
                  <v-chip>
                    <span class="mr-1">{{ item.raw.emoji }}</span>
                    {{ item.raw.kb_name }}
                  </v-chip>
                </template>
                <template v-slot:item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template v-slot:prepend>
                      <span style="font-size: 20px; margin-right: 8px;">{{ item.raw.emoji }}</span>
                    </template>
                    <v-list-item-title>{{ item.raw.kb_name }}</v-list-item-title>
                    <v-list-item-subtitle>
                      {{ item.raw.description || tm('knowledgeBase.noKBDesc') }} - {{ item.raw.doc_count }} {{ tm('list.documents', { count: item.raw.doc_count }) }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </template>
              </v-select>

              <!-- 高级配置 -->
              <v-expansion-panels class="mb-4">
                <v-expansion-panel>
                  <v-expansion-panel-title>
                    <v-icon class="mr-2">mdi-cog</v-icon>
                    {{ tm('knowledgeBase.advancedSettings') }}
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <v-row>
                      <v-col cols="12" md="6">
                        <v-text-field
                          v-model.number="sessionKBConfig.top_k"
                          :label="tm('knowledgeBase.topK')"
                          type="number"
                          variant="outlined"
                          density="comfortable"
                          :hint="tm('knowledgeBase.topKHint')"
                          persistent-hint
                        />
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-checkbox
                          v-model="sessionKBConfig.enable_rerank"
                          :label="tm('knowledgeBase.enableRerank')"
                          color="primary"
                          :hint="tm('knowledgeBase.enableRerankHint')"
                          persistent-hint
                        />
                      </v-col>
                    </v-row>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>

              <div v-if="availableKBs.length === 0" class="text-center py-8">
                <v-icon size="64" color="grey-lighten-2">mdi-database-off</v-icon>
                <p class="mt-4 text-medium-emphasis">{{ tm('knowledgeBase.noKBAvailable') }}</p>
                <v-btn color="primary" variant="tonal" class="mt-2" @click="goToKBPage">
                  {{ tm('knowledgeBase.createKB') }}
                </v-btn>
              </div>
            </div>
          </v-card-text>

          <v-card-text v-else class="text-center py-8">
            <v-progress-circular indeterminate color="primary" size="48"></v-progress-circular>
            <div class="text-body-1 mt-4">{{ tm('knowledgeBase.loading') }}</div>
          </v-card-text>

          <v-divider />

          <v-card-actions class="pa-4">
            <v-btn variant="text" @click="clearKBConfig" :disabled="savingKBConfig || loadingKBConfig">
              {{ tm('knowledgeBase.clearConfig') }}
            </v-btn>
            <v-spacer />
            <v-btn variant="text" @click="kbDialog = false" :disabled="savingKBConfig">
              {{ tm('knowledgeBase.cancel') }}
            </v-btn>
            <v-btn color="primary" variant="tonal" @click="saveKBConfig" :loading="savingKBConfig">
              {{ tm('knowledgeBase.save') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 提示信息 -->
      <v-snackbar v-model="snackbar" :timeout="3000" elevation="24" :color="snackbarColor" location="top">
        {{ snackbarText }}
      </v-snackbar>
    </v-container>
  </div>
</template>

<script>
import axios from 'axios'
import { debounce } from 'lodash'
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

      // 分页相关
      currentPage: 1,
      itemsPerPage: 10,
      totalItems: 0,
      totalPages: 0,

      // 可用选项
      availablePersonas: [],
      availableChatProviders: [],
      availableSttProviders: [],
      availableTtsProviders: [],

      // 批量操作
      batchPersona: null,
      batchChatProvider: null,
      batchSttProvider: null,
      batchTtsProvider: null,
      batchLlmStatus: null,
      batchTtsStatus: null,
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

      // 知识库管理
      kbDialog: false,
      selectedSessionForKB: null,
      sessionKBConfig: {
        kb_ids: [],
        top_k: 5,
        enable_rerank: true
      },
      availableKBs: [],
      loadingKBConfig: false,
      savingKBConfig: false,

      // 提示信息
      snackbar: false,
      snackbarText: '',
      snackbarColor: 'success',
    }
  },

  computed: {
    // 安全访问翻译的计算属性
    messages() {
      return {
        updateSuccess: this.tm('messages.updateSuccess'),
        addSuccess: this.tm('messages.addSuccess'),
        deleteSuccess: this.tm('messages.deleteSuccess'),
        statusUpdateSuccess: this.tm('messages.statusUpdateSuccess'),
        deleteConfirm: this.tm('messages.deleteConfirm')
      };
    },

    subtitle() {
      return this.tm('subtitle') || '管理所有活跃的会话，配置人格、LLM提供商和插件';
    },

    headers() {
      return [
        { title: this.tm('table.headers.sessionStatus'), key: 'session_enabled', sortable: false, minWidth: '120px' },
        { title: this.tm('table.headers.sessionInfo'), key: 'session_info', sortable: false },
        { title: this.tm('table.headers.persona'), key: 'persona', sortable: false, minWidth: '150px' },
        { title: this.tm('table.headers.chatProvider'), key: 'chat_provider', sortable: false, minWidth: '200px' },
        { title: this.tm('table.headers.sttProvider'), key: 'stt_provider', sortable: false, minWidth: '200px' },
        { title: this.tm('table.headers.ttsProvider'), key: 'tts_provider', sortable: false, minWidth: '200px' },
        { title: this.tm('table.headers.llmStatus'), key: 'llm_enabled', sortable: false, minWidth: '120px' },
        { title: this.tm('table.headers.ttsStatus'), key: 'tts_enabled', sortable: false, minWidth: '120px' },
        { title: this.tm('table.headers.knowledgeBase'), key: 'knowledge_base', sortable: false, minWidth: '150px' },
        { title: this.tm('table.headers.pluginManagement'), key: 'plugins', sortable: false, minWidth: '120px' },
        { title: this.tm('table.headers.actions'), key: 'actions', sortable: false, minWidth: '100px' },
      ]
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
        const params = {
          page: this.currentPage,
          page_size: this.itemsPerPage
        };
        
        // 添加搜索和平台筛选参数
        if (this.searchQuery) {
          params.search = this.searchQuery;
        }
        if (this.filterPlatform) {
          params.platform = this.filterPlatform;
        }
        
        const response = await axios.get('/api/session/list', { params });
        if (response.data.status === 'ok') {
          const data = response.data.data;
          this.sessions = data.sessions.map(session => ({
            ...session,
            updating: false, // 添加更新状态标志
            loadingPlugins: false, // 添加插件加载状态标志
            deleting: false, // 添加删除状态标志
            loadingKB: false // 添加知识库加载状态标志
          }));
          this.availablePersonas = data.available_personas;
          this.availableChatProviders = data.available_chat_providers;
          this.availableSttProviders = data.available_stt_providers;
          this.availableTtsProviders = data.available_tts_providers;
          
          // 处理分页信息
          if (data.pagination) {
            this.totalItems = data.pagination.total;
            this.totalPages = data.pagination.total_pages;
            this.currentPage = data.pagination.page;
          }
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
      return this._updateSession('persona', session, { persona_name: personaName }, (s, success) => {
        if (success) {
          s.persona_id = personaName;
          s.persona_name = personaName === '[%None]' ? this.tm('persona.none') :
            this.availablePersonas.find(p => p.name === personaName)?.name || personaName;
        }
      });
    },

    async updateProvider(session, providerId, providerType) {
      return this._updateSession('provider', session, { 
        provider_id: providerId, 
        provider_type: providerType 
      }, (s, success) => {
        if (success) {
          if (providerType === 'chat_completion') {
            s.chat_provider_id = providerId;
            const provider = this.availableChatProviders.find(p => p.id === providerId);
            s.chat_provider_name = provider?.name || providerId;
          } else if (providerType === 'speech_to_text') {
            s.stt_provider_id = providerId;
            const provider = this.availableSttProviders.find(p => p.id === providerId);
            s.stt_provider_name = provider?.name || providerId;
          } else if (providerType === 'text_to_speech') {
            s.tts_provider_id = providerId;
            const provider = this.availableTtsProviders.find(p => p.id === providerId);
            s.tts_provider_name = provider?.name || providerId;
          }
        }
      });
    },

    async updateLLM(session, enabled) {
      return this._updateSession('llm', session, { enabled }, (s, success) => {
        if (success) s.llm_enabled = enabled;
      });
    },

    async updateTTS(session, enabled) {
      return this._updateSession('tts', session, { enabled }, (s, success) => {
        if (success) s.tts_enabled = enabled;
      });
    },

    // 通用的更新会话方法，支持单个和批量操作
    async _updateSession(type, sessionOrSessions, params, updateLocalData) {
      const isBatch = Array.isArray(sessionOrSessions);
      
      if (!isBatch) {
        // 单个操作
        const session = sessionOrSessions;
        session.updating = true;
        
        try {
          const payload = {
            is_batch: false,
            session_id: session.session_id,
            ...params
          };

          const response = await axios.post(`/api/session/update_${type}`, payload);

          if (response.data.status === 'ok') {
            updateLocalData(session, true);
            this.showSuccess(this.tm(`messages.${type}UpdateSuccess`));
            return { success: true };
          } else {
            this.showError(response.data.message || this.tm(`messages.${type}UpdateError`));
            return { success: false, error: response.data.message };
          }
        } catch (error) {
          this.showError(error.response?.data?.message || this.tm(`messages.${type}UpdateError`));
          return { success: false, error: error.message };
        } finally {
          session.updating = false;
        }
      } else {
        // 批量操作
        const sessions = sessionOrSessions;
        const sessionIds = sessions.map(s => s.session_id);
        
        try {
          const payload = {
            is_batch: true,
            session_ids: sessionIds,
            ...params
          };

          const response = await axios.post(`/api/session/update_${type}`, payload);

          if (response.data.status === 'ok') {
            const data = response.data.data;
            
            // 更新成功的会话的本地数据
            sessions.forEach(session => {
              const wasSuccessful = !data.error_sessions || !data.error_sessions.includes(session.session_id);
              updateLocalData(session, wasSuccessful);
            });

            return {
              success: true,
              successCount: data.success_count || 0,
              errorCount: data.error_count || 0,
              errorSessions: data.error_sessions || []
            };
          } else {
            return { 
              success: false, 
              error: response.data.message,
              errorCount: sessionIds.length,
              successCount: 0
            };
          }
        } catch (error) {
          return { 
            success: false, 
            error: error.response?.data?.message || error.message,
            errorCount: sessionIds.length,
            successCount: 0
          };
        }
      }
    },

    // 单独的会话状态更新方法（不支持批量操作）
    async updateSessionStatus(session, enabled) {
      session.updating = true;
      try {
        const response = await axios.post('/api/session/update_status', {
          session_id: session.session_id,
          session_enabled: enabled
        });

        if (response.data.status === 'ok') {
          session.session_enabled = enabled;
          this.showSuccess(this.tm('messages.sessionStatusSuccess', { 
            status: enabled ? this.tm('status.enabled') : this.tm('status.disabled') 
          }));
        } else {
          this.showError(response.data.message || this.tm('messages.statusUpdateError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.statusUpdateError'));
      }
      session.updating = false;
    },

    async applyBatchChanges() {
      if (!this.batchPersona && !this.batchChatProvider && !this.batchSttProvider && !this.batchTtsProvider && this.batchLlmStatus === null && this.batchTtsStatus === null) {
        return;
      }

      this.batchUpdating = true;
      let totalSuccessCount = 0;
      let totalErrorCount = 0;
      let allErrorSessions = [];

      const sessions = this.sessions;

      try {
        // 定义批量操作任务
        const batchTasks = [];

        if (this.batchPersona) {
          batchTasks.push({
            type: 'persona',
            params: { persona_name: this.batchPersona }
          });
        }

        if (this.batchChatProvider) {
          batchTasks.push({
            type: 'provider',
            params: { provider_id: this.batchChatProvider, provider_type: 'chat_completion' }
          });
        }

        if (this.batchSttProvider) {
          batchTasks.push({
            type: 'provider',
            params: { provider_id: this.batchSttProvider, provider_type: 'speech_to_text' }
          });
        }

        if (this.batchTtsProvider) {
          batchTasks.push({
            type: 'provider',
            params: { provider_id: this.batchTtsProvider, provider_type: 'text_to_speech' }
          });
        }

        if (this.batchLlmStatus !== null) {
          batchTasks.push({
            type: 'llm',
            params: { enabled: this.batchLlmStatus }
          });
        }

        if (this.batchTtsStatus !== null) {
          batchTasks.push({
            type: 'tts',
            params: { enabled: this.batchTtsStatus }
          });
        }

        // 执行所有批量任务
        for (const task of batchTasks) {
          let updateLocalData;
          
          // 定义本地数据更新逻辑
          switch (task.type) {
            case 'persona':
              updateLocalData = (s, success) => {
                if (success) s.persona_id = task.params.persona_name;
              };
              break;
            case 'provider':
              updateLocalData = (s, success) => {
                if (!success) return;
                const { provider_id, provider_type } = task.params;
                if (provider_type === 'chat_completion') {
                  s.chat_provider_id = provider_id;
                } else if (provider_type === 'speech_to_text') {
                  s.stt_provider_id = provider_id;
                } else if (provider_type === 'text_to_speech') {
                  s.tts_provider_id = provider_id;
                }
              };
              break;
            case 'llm':
              updateLocalData = (s, success) => {
                if (success) s.llm_enabled = task.params.enabled;
              };
              break;
            case 'tts':
              updateLocalData = (s, success) => {
                if (success) s.tts_enabled = task.params.enabled;
              };
              break;
          }

          const result = await this._updateSession(task.type, sessions, task.params, updateLocalData);
          
          totalSuccessCount += result.successCount || 0;
          totalErrorCount += result.errorCount || 0;
          if (result.errorSessions) {
            allErrorSessions.push(...result.errorSessions);
          }
        }

        // 显示最终结果
        if (totalErrorCount === 0) {
          this.showSuccess(this.tm('messages.batchUpdateSuccess', { count: totalSuccessCount }));
        } else {
          const uniqueErrorSessions = [...new Set(allErrorSessions)];
          this.showError(this.tm('messages.batchUpdatePartial', { 
            success: totalSuccessCount, 
            error: uniqueErrorSessions.length 
          }));
        }

      } catch (error) {
        this.showError(this.tm('messages.batchUpdateError'));
      }

      this.batchUpdating = false;

      // 清空批量设置
      this.batchPersona = null;
      this.batchChatProvider = null;
      this.batchSttProvider = null;
      this.batchTtsProvider = null;
      this.batchLlmStatus = null;
      this.batchTtsStatus = null;
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

    async deleteSession(session) {
      const confirmMessage = this.tm('deleteConfirm.message', { 
        sessionName: session.session_name || session.session_id 
      }) + '\n\n' + this.tm('deleteConfirm.warning');
      
      if (!confirm(confirmMessage)) {
        return;
      }

      session.deleting = true;
      try {
        const response = await axios.post('/api/session/delete', {
          session_id: session.session_id
        });

        if (response.data.status === 'ok') {
          this.showSuccess(response.data.data.message || this.tm('messages.deleteSuccess'));
          // 从列表中移除已删除的会话
          const index = this.sessions.findIndex(s => s.session_id === session.session_id);
          if (index > -1) {
            this.sessions.splice(index, 1);
          }
        } else {
          this.showError(response.data.message || this.tm('messages.deleteError'));
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.deleteError'));
      }

      session.deleting = false;
    },

    // 处理分页更新事件
    handlePaginationUpdate(options) {
      this.currentPage = options.page;
      this.itemsPerPage = options.itemsPerPage;
      this.loadSessions();
    },

    // 处理搜索变化
    handleSearchChange: debounce(function() {
      this.currentPage = 1; // 重置到第一页
      this.loadSessions();
    }, 300),

    // 处理平台筛选变化
    handlePlatformChange() {
      this.currentPage = 1; // 重置到第一页
      this.loadSessions();
    },

    // 知识库配置相关方法
    async openKBManager(session) {
      this.selectedSessionForKB = session;
      this.kbDialog = true;
      this.loadingKBConfig = true;

      try {
        // 加载可用的知识库列表
        const kbListResponse = await axios.get('/api/kb/list');
        if (kbListResponse.data.status === 'ok') {
          this.availableKBs = kbListResponse.data.data.items;
        }

        // 加载当前会话的知识库配置
        const configResponse = await axios.get('/api/kb/session/config/get', {
          params: { session_id: session.session_id }
        });

        if (configResponse.data.status === 'ok') {
          const config = configResponse.data.data;
          this.sessionKBConfig = {
            kb_ids: config.kb_ids || [],
            top_k: config.top_k || 5,
            enable_rerank: config.enable_rerank !== false
          };
        } else {
          // 如果没有配置,使用默认值
          this.sessionKBConfig = {
            kb_ids: [],
            top_k: 5,
            enable_rerank: true
          };
        }
      } catch (error) {
        console.error('加载知识库配置失败:', error);
        this.showError(this.tm('knowledgeBase.loadFailed'));
      } finally {
        this.loadingKBConfig = false;
      }
    },

    async saveKBConfig() {
      if (!this.selectedSessionForKB) return;

      this.savingKBConfig = true;
      try {
        const response = await axios.post('/api/kb/session/config/set', {
          scope: 'session',
          scope_id: this.selectedSessionForKB.session_id,
          kb_ids: this.sessionKBConfig.kb_ids,
          top_k: this.sessionKBConfig.top_k,
          enable_rerank: this.sessionKBConfig.enable_rerank
        });

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('knowledgeBase.saveSuccess'));
          this.kbDialog = false;
        } else {
          this.showError(response.data.message || this.tm('knowledgeBase.saveFailed'));
        }
      } catch (error) {
        console.error('保存知识库配置失败:', error);
        this.showError(error.response?.data?.message || this.tm('knowledgeBase.saveFailed'));
      } finally {
        this.savingKBConfig = false;
      }
    },

    async clearKBConfig() {
      if (!this.selectedSessionForKB) return;

      if (!confirm(this.tm('knowledgeBase.clearConfirm'))) {
        return;
      }

      this.savingKBConfig = true;
      try {
        const response = await axios.post('/api/kb/session/config/delete', {
          scope: 'session',
          scope_id: this.selectedSessionForKB.session_id
        });

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('knowledgeBase.clearSuccess'));
          this.sessionKBConfig = {
            kb_ids: [],
            top_k: 5,
            enable_rerank: true
          };
        } else {
          this.showError(response.data.message || this.tm('knowledgeBase.clearFailed'));
        }
      } catch (error) {
        console.error('清除知识库配置失败:', error);
        this.showError(error.response?.data?.message || this.tm('knowledgeBase.clearFailed'));
      } finally {
        this.savingKBConfig = false;
      }
    },

    goToKBPage() {
      this.$router.push('/knowledge-base');
    },
  },
}
</script>

<style scoped>

.v-data-table>>>.v-data-table__td {
  padding: 8px 16px !important;
  vertical-align: middle !important;
}

</style>
