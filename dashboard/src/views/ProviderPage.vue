<template>
  <div class="provider-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
        <div>
          <h1 class="text-h1 font-weight-bold mb-2">
            <v-icon color="black" class="me-2">mdi-creation</v-icon>{{ tm('title') }}
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4">
            {{ tm('subtitle') }}
          </p>
        </div>
        <div>
          <v-btn color="success" prepend-icon="mdi-cog" variant="tonal" class="me-2" @click="showSettingsDialog = true" rounded="xl" size="x-large">
            {{ tm('providers.settings') }}
          </v-btn>
          <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="showAddProviderDialog = true" rounded="xl" size="x-large">
            {{ tm('providers.addProvider') }}
          </v-btn>
        </div>
      </v-row>

      <div>
        <!-- 添加分类标签页 -->
        <v-tabs v-model="activeProviderTypeTab" bg-color="transparent" class="mb-4">
          <v-tab value="all" class="font-weight-medium px-3">
            <v-icon start>mdi-filter-variant</v-icon>
            {{ tm('providers.tabs.all') }}
          </v-tab>
          <v-tab value="chat_completion" class="font-weight-medium px-3">
            <v-icon start>mdi-message-text</v-icon>
            {{ tm('providers.tabs.chatCompletion') }}
          </v-tab>
          <v-tab value="speech_to_text" class="font-weight-medium px-3">
            <v-icon start>mdi-microphone-message</v-icon>
            {{ tm('providers.tabs.speechToText') }}
          </v-tab>
          <v-tab value="text_to_speech" class="font-weight-medium px-3">
            <v-icon start>mdi-volume-high</v-icon>
            {{ tm('providers.tabs.textToSpeech') }}
          </v-tab>
          <v-tab value="embedding" class="font-weight-medium px-3">
            <v-icon start>mdi-code-json</v-icon>
            {{ tm('providers.tabs.embedding') }}
          </v-tab>
        </v-tabs>

        <v-row v-if="filteredProviders.length === 0">
          <v-col cols="12" class="text-center pa-8">
            <v-icon size="64" color="grey-lighten-1">mdi-api-off</v-icon>
            <p class="text-grey mt-4">{{ getEmptyText() }}</p>
          </v-col>
        </v-row>

        <v-row v-else>
          <v-col v-for="(provider, index) in filteredProviders" :key="index" cols="12" md="6" lg="4" xl="3">
            <item-card 
              :item="provider" 
              title-field="id" 
              enabled-field="enable"
              @toggle-enabled="providerStatusChange"
              :bglogo="getProviderIcon(provider.provider)"
              @delete="deleteProvider" 
              @edit="configExistingProvider">
              <template v-slot:details="{ item }">
              </template>
            </item-card>
          </v-col>
        </v-row>
      </div>

      <!-- 供应商状态部分 -->
      <v-card elevation="0" class="mt-4">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon class="me-2">mdi-heart-pulse</v-icon>
          <span class="text-h4">{{ tm('availability.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="tonal" :loading="loadingStatus" @click="fetchProviderStatus">
            <v-icon left>mdi-refresh</v-icon>
            {{ tm('availability.refresh') }}
          </v-btn>
          <v-btn variant="text" color="primary" @click="showStatus = !showStatus" style="margin-left: 8px;">
            {{ showStatus ? tm('logs.collapse') : tm('logs.expand') }}
            <v-icon>{{ showStatus ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-expand-transition>
          <v-card-text class="pa-0" v-if="showStatus">
            <v-card-text class="px-4 py-3">
              <v-alert v-if="providerStatuses.length === 0" type="info" variant="tonal">
                {{ tm('availability.noData') }}
              </v-alert>
              
              <v-container v-else class="pa-0">
                <v-row>
                  <v-col v-for="status in providerStatuses" :key="status.id" cols="12" sm="6" md="4">
                    <v-card variant="outlined" class="status-card" :class="`status-${status.status}`">
                      <v-card-item>
                        <v-icon v-if="status.status === 'available'" color="success" class="me-2">mdi-check-circle</v-icon>
                        <v-icon v-else-if="status.status === 'unavailable'" color="error" class="me-2">mdi-alert-circle</v-icon>
                        <v-progress-circular
                          v-else-if="status.status === 'pending'"
                          indeterminate
                          color="primary"
                          size="20"
                          width="2"
                          class="me-2"
                        ></v-progress-circular>

                        <span class="font-weight-bold">{{ status.id }}</span>
                        
                        <v-chip :color="getStatusColor(status.status)" size="small" class="ml-2">
                          {{ getStatusText(status.status) }}
                        </v-chip>
                      </v-card-item>
                      <v-card-text v-if="status.status === 'unavailable'" class="text-caption text-medium-emphasis">
                        <span class="font-weight-bold">{{ tm('availability.errorMessage') }}:</span> {{ status.error }}
                      </v-card-text>
                    </v-card>
                  </v-col>
                </v-row>
              </v-container>
            </v-card-text>
          </v-card-text>
        </v-expand-transition>
      </v-card>

      <!-- 日志部分 -->
      <v-card elevation="0" class="mt-4">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon class="me-2">mdi-console-line</v-icon>
          <span class="text-h4">{{ tm('logs.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn variant="text" color="primary" @click="showConsole = !showConsole">
            {{ showConsole ? tm('logs.collapse') : tm('logs.expand') }}
            <v-icon>{{ showConsole ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-expand-transition>
          <v-card-text class="pa-0" v-if="showConsole">
            <ConsoleDisplayer style="background-color: #1e1e1e; height: 300px; border-radius: 0"></ConsoleDisplayer>
          </v-card-text>
        </v-expand-transition>
      </v-card>
    </v-container>

    <!-- 添加提供商对话框 -->
    <v-dialog v-model="showAddProviderDialog" max-width="1100px" min-height="95%">
      <v-card class="provider-selection-dialog">
        <v-card-title class="bg-primary text-white py-3 px-4" style="display: flex; align-items: center;">
          <v-icon color="white" class="me-2">mdi-plus-circle</v-icon>
          <span>{{ tm('dialogs.addProvider.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="showAddProviderDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text class="pa-4" style="overflow-y: auto;">
          <v-tabs v-model="activeProviderTab" grow slider-color="primary" bg-color="background">
            <v-tab value="chat_completion" class="font-weight-medium px-3">
              <v-icon start>mdi-message-text</v-icon>
              {{ tm('dialogs.addProvider.tabs.basic') }}
            </v-tab>
            <v-tab value="speech_to_text" class="font-weight-medium px-3">
              <v-icon start>mdi-microphone-message</v-icon>
              {{ tm('dialogs.addProvider.tabs.speechToText') }}
            </v-tab>
            <v-tab value="text_to_speech" class="font-weight-medium px-3">
              <v-icon start>mdi-volume-high</v-icon>
              {{ tm('dialogs.addProvider.tabs.textToSpeech') }}
            </v-tab>
            <v-tab value="embedding" class="font-weight-medium px-3">
              <v-icon start>mdi-code-json</v-icon>
              {{ tm('dialogs.addProvider.tabs.embedding') }}
            </v-tab>
          </v-tabs>

          <v-window v-model="activeProviderTab" class="mt-4">
            <v-window-item v-for="tabType in ['chat_completion', 'speech_to_text', 'text_to_speech', 'embedding']"
                          :key="tabType"
                          :value="tabType">
              <v-row class="mt-1">
                <v-col v-for="(template, name) in getTemplatesByType(tabType)"
                      :key="name"
                      cols="12" sm="6" md="4">
                  <v-card variant="outlined" hover class="provider-card" @click="selectProviderTemplate(name)">
                    <div class="provider-card-content">
                      <div class="provider-card-text">
                        <v-card-title class="provider-card-title">接入 {{ name }}</v-card-title>
                        <v-card-text class="text-caption text-medium-emphasis provider-card-description">
                          {{ getProviderDescription(template, name) }}
                        </v-card-text>
                      </div>
                      <div class="provider-card-logo">
                        <img :src="getProviderIcon(template.provider)" v-if="getProviderIcon(template.provider)" class="provider-logo-img">
                        <div v-else class="provider-logo-fallback">
                          {{ name[0].toUpperCase() }}
                        </div>
                      </div>
                    </div>
                  </v-card>
                </v-col>
                <v-col v-if="Object.keys(getTemplatesByType(tabType)).length === 0" cols="12">
                  <v-alert type="info" variant="tonal">
                    {{ tm('dialogs.addProvider.noTemplates', { type: getTabTypeName(tabType) }) }}
                  </v-alert>
                </v-col>
              </v-row>
            </v-window-item>
          </v-window>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 配置对话框 -->
    <v-dialog v-model="showProviderCfg" width="900" persistent>
      <v-card>
        <v-card-title class="bg-primary text-white py-3">
          <v-icon color="white" class="me-2">{{ updatingMode ? 'mdi-pencil' : 'mdi-plus' }}</v-icon>
          <span>{{ updatingMode ? tm('dialogs.config.editTitle') : tm('dialogs.config.addTitle') }} {{ newSelectedProviderName }} {{ tm('dialogs.config.provider') }}</span>
        </v-card-title>

        <v-card-text class="py-4">
          <AstrBotConfig
            :iterable="newSelectedProviderConfig"
            :metadata="metadata['provider_group']?.metadata"
            metadataKey="provider"
          />
        </v-card-text>

        <v-divider></v-divider>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showProviderCfg = false" :disabled="loading">
            {{ tm('dialogs.config.cancel') }}
          </v-btn>
          <v-btn color="primary" @click="newProvider" :loading="loading">
            {{ tm('dialogs.config.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 设置对话框 -->
    <v-dialog v-model="showSettingsDialog" max-width="600px">
      <v-card>
        <v-card-title class="bg-primary text-white py-3 px-4" style="display: flex; align-items: center;">
          <v-icon color="white" class="me-2">mdi-cog</v-icon>
          <span>{{ tm('dialogs.settings.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="showSettingsDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text class="pa-4">
          <v-list>
            <v-list-item>
              <v-switch
                style="padding: 12px;"
                v-model="sessionSeparationEnabled"
                color="primary"
                :loading="sessionSettingLoading"
                @change="updateSessionSeparation"
                hide-details
              >
                <template v-slot:label>
                  <div>
                    <div class="text-subtitle-1">{{ tm('dialogs.settings.sessionSeparation.title') }}</div>
                    <div class="text-caption text-medium-emphasis">{{ tm('dialogs.settings.sessionSeparation.description') }}</div>
                  </div>
                </template>
              </v-switch>
            </v-list-item>
          </v-list>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showSettingsDialog = false">
            {{ tm('dialogs.settings.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack"
      location="top">
      {{ save_message }}
    </v-snackbar>

    <WaitingForRestart ref="wfr"></WaitingForRestart>

    <!-- ID冲突确认对话框 -->
    <v-dialog v-model="showIdConflictDialog" max-width="450" persistent>
      <v-card>
        <v-card-title class="text-h6 bg-warning d-flex align-center">
          <v-icon start class="me-2">mdi-alert-circle-outline</v-icon>
          ID 冲突警告
        </v-card-title>
        <v-card-text class="py-4 text-body-1 text-medium-emphasis">
          检测到 ID "{{ conflictId }}" 重复。请使用一个新的 ID。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="handleIdConflictConfirm(false)">好的</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Key为空的确认对话框 -->
    <v-dialog v-model="showKeyConfirm" max-width="450" persistent>
      <v-card>
        <v-card-title class="text-h6 bg-error d-flex align-center">
          <v-icon start class="me-2">mdi-alert-circle-outline</v-icon>
          确认保存
        </v-card-title>
        <v-card-text class="py-4 text-body-1 text-medium-emphasis">
          您没有填写 API Key，确定要保存吗？这可能会导致该服务提供商无法正常工作。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="handleKeyConfirm(false)">取消</v-btn>
          <v-btn color="error" variant="flat" @click="handleKeyConfirm(true)">确定</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import ItemCard from '@/components/shared/ItemCard.vue';
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'ProviderPage',
  components: {
    AstrBotConfig,
    WaitingForRestart,
    ConsoleDisplayer,
    ItemCard
  },
  setup() {
    const { tm } = useModuleI18n('features/provider');
    return { tm };
  },
  data() {
    return {
      config_data: {},
      fetched: false,
      metadata: {},
      showProviderCfg: false,

      // 设置对话框相关
      showSettingsDialog: false,
      sessionSeparationEnabled: false,
      sessionSettingLoading: false,

      // ID冲突确认对话框
      showIdConflictDialog: false,
      conflictId: '',
      idConflictResolve: null,

      // Key确认对话框
      showKeyConfirm: false,
      keyConfirmResolve: null,

      newSelectedProviderName: '',
      newSelectedProviderConfig: {},
      updatingMode: false,

      loading: false,

      save_message_snack: false,
      save_message: "",
      save_message_success: "success",

      showConsole: false,
      
      // 显示状态部分
      showStatus: false,
      
      // 供应商状态相关
      providerStatuses: [],
      loadingStatus: false,

      // 新增提供商对话框相关
      showAddProviderDialog: false,
      activeProviderTab: 'chat_completion',

      // 添加提供商类型分类
      activeProviderTypeTab: 'all',

      // 兼容旧版本（< v3.5.11）的 mapping，用于映射到对应的提供商能力类型
      oldVersionProviderTypeMapping: {
        "openai_chat_completion": "chat_completion",
        "anthropic_chat_completion": "chat_completion",
        "googlegenai_chat_completion": "chat_completion",
        "zhipu_chat_completion": "chat_completion",
        "dify": "chat_completion",
        "dashscope": "chat_completion",
        "openai_whisper_api": "speech_to_text",
        "openai_whisper_selfhost": "speech_to_text",
        "sensevoice_stt_selfhost": "speech_to_text",
        "openai_tts_api": "text_to_speech",
        "edge_tts": "text_to_speech",
        "gsvi_tts_api": "text_to_speech",
        "fishaudio_tts_api": "text_to_speech",
        "dashscope_tts": "text_to_speech",
        "azure_tts": "text_to_speech",
        "minimax_tts_api": "text_to_speech",
        "volcengine_tts": "text_to_speech",
      }
    }
  },

  watch: {
    showIdConflictDialog(newValue) {
      // 当对话框关闭时，如果 Promise 还在等待，则拒绝它以防止内存泄漏
      if (!newValue && this.idConflictResolve) {
        this.idConflictResolve(false);
        this.idConflictResolve = null;
      }
    },
    showKeyConfirm(newValue) {
      // 当对话框关闭时，如果 Promise 还在等待，则拒绝它以防止内存泄漏
      if (!newValue && this.keyConfirmResolve) {
        this.keyConfirmResolve(false);
        this.keyConfirmResolve = null;
      }
    }
  },

  computed: {
    // 翻译消息的计算属性
    messages() {
      return {
        emptyText: {
          all: this.tm('providers.empty.all'),
          typed: this.tm('providers.empty.typed')
        },
        tabTypes: {
          'chat_completion': this.tm('providers.tabs.chatCompletion'),
          'speech_to_text': this.tm('providers.tabs.speechToText'),
          'text_to_speech': this.tm('providers.tabs.textToSpeech'),
          'embedding': this.tm('providers.tabs.embedding')
        },
        success: {
          update: this.tm('messages.success.update'),
          add: this.tm('messages.success.add'),
          delete: this.tm('messages.success.delete'),
          statusUpdate: this.tm('messages.success.statusUpdate'),
          sessionSeparation: this.tm('messages.success.sessionSeparation')
        },
        error: {
          sessionSeparation: this.tm('messages.error.sessionSeparation'),
          fetchStatus: this.tm('messages.error.fetchStatus')
        },
        confirm: {
          delete: this.tm('messages.confirm.delete')
        },
        status: {
          available: this.tm('availability.available'),
          unavailable: this.tm('availability.unavailable'),
          pending: this.tm('availability.pending')
        }
      };
    },
    
    // 根据选择的标签过滤提供商列表
    filteredProviders() {
      if (!this.config_data.provider || this.activeProviderTypeTab === 'all') {
        return this.config_data.provider || [];
      }

      return this.config_data.provider.filter(provider => {
        // 如果provider.provider_type已经存在，直接使用它
        if (provider.provider_type) {
          return provider.provider_type === this.activeProviderTypeTab;
        }
        
        // 否则使用映射关系
        const mappedType = this.oldVersionProviderTypeMapping[provider.type];
        return mappedType === this.activeProviderTypeTab;
      });
    }
  },

  mounted() {
    this.getConfig();
    this.getSessionSeparationStatus();
  },

  methods: {
    getConfig() {
      axios.get('/api/config/get').then((res) => {
        this.config_data = res.data.data.config;
        this.fetched = true
        this.metadata = res.data.data.metadata;
      }).catch((err) => {
        this.showError(err.response?.data?.message || err.message);
      });
    },

    // 获取空列表文本
    getEmptyText() {
      if (this.activeProviderTypeTab === 'all') {
        return this.messages.emptyText.all;
      } else {
        return this.tm('providers.empty.typed', { type: this.getTabTypeName(this.activeProviderTypeTab) });
      }
    },

    // 按提供商类型获取模板列表
    getTemplatesByType(type) {
      const templates = this.metadata['provider_group']?.metadata?.provider?.config_template || {};
      const filtered = {};

      for (const [name, template] of Object.entries(templates)) {
        if (template.provider_type === type) {
          filtered[name] = template;
        }
      }

      return filtered;
    },

    // 获取提供商类型对应的图标
    getProviderIcon(type) {
      const icons = {
        'openai': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/openai.svg',
        'azure': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/azure.svg',
        'xai': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/xai.svg',
        'anthropic': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/anthropic.svg',
        'ollama': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/ollama.svg',
        'google': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/gemini-color.svg',
        'deepseek': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/deepseek.svg',
        'zhipu': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/zhipu.svg',
        'siliconflow': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/siliconcloud.svg',
        'moonshot': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/kimi.svg',
        'ppio': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/ppio.svg',
        'dify': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/dify-color.svg',
        'dashscope': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/alibabacloud-color.svg',
        'fastgpt': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/fastgpt-color.svg',
        'lm_studio': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/lmstudio.svg',
        'fishaudio': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/fishaudio.svg',
        'minimax': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/minimax.svg',
        '302ai': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/1.53.0/files/icons/ai302-color.svg',
        'microsoft': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/microsoft.svg',
      };
      return icons[type] || '';
    },

    // 获取Tab类型的中文名称
    getTabTypeName(tabType) {
      return this.messages.tabTypes[tabType] || tabType;
    },

    // 获取提供商简介
    getProviderDescription(template, name) {
      if (name == 'OpenAI') {
        return this.tm('providers.description.openai', { type: template.type });
      }
      return this.tm('providers.description.default', { type: template.type });
    },

    // 选择提供商模板
    selectProviderTemplate(name) {
      this.newSelectedProviderName = name;
      this.showProviderCfg = true;
      this.updatingMode = false;
      this.newSelectedProviderConfig = JSON.parse(JSON.stringify(
        this.metadata['provider_group']?.metadata?.provider?.config_template[name] || {}
      ));
      this.showAddProviderDialog = false;
    },

    // 废弃旧方法，保留为兼容
    addFromDefaultConfigTmpl(index) {
      this.selectProviderTemplate(index[0]);
    },

    configExistingProvider(provider) {
      this.newSelectedProviderName = provider.id;
      this.newSelectedProviderConfig = {};

      // 比对默认配置模版，看看是否有更新
      let templates = this.metadata['provider_group']?.metadata?.provider?.config_template || {};
      let defaultConfig = {};
      for (let key in templates) {
        if (templates[key]?.type === provider.type) {
          defaultConfig = templates[key];
          break;
        }
      }

      const mergeConfigWithOrder = (target, source, reference) => {
        // 首先复制所有source中的属性到target
        if (source && typeof source === 'object' && !Array.isArray(source)) {
          for (let key in source) {
            if (source.hasOwnProperty(key)) {
              if (typeof source[key] === 'object' && source[key] !== null) {
                target[key] = Array.isArray(source[key]) ? [...source[key]] : {...source[key]};
              } else {
                target[key] = source[key];
              }
            }
          }
        }

        // 然后根据reference的结构添加或覆盖属性
        for (let key in reference) {
          if (typeof reference[key] === 'object' && reference[key] !== null) {
            if (!(key in target)) {
              target[key] = Array.isArray(reference[key]) ? [] : {};
            }
            mergeConfigWithOrder(
              target[key],
              source && source[key] ? source[key] : {},
              reference[key]
            );
          } else if (!(key in target)) {
            // 只有当target中不存在该键时才从reference复制
            target[key] = reference[key];
          }
        }
      };

      if (defaultConfig) {
        mergeConfigWithOrder(this.newSelectedProviderConfig, provider, defaultConfig);
      }

      this.showProviderCfg = true;
      this.updatingMode = true;
    },

    async newProvider() {
      // 检查 key 是否为空
      if (
        'key' in this.newSelectedProviderConfig &&
        (!this.newSelectedProviderConfig.key || this.newSelectedProviderConfig.key.length === 0)
      ) {
        const confirmed = await this.confirmEmptyKey();
        if (!confirmed) {
          return; // 如果用户取消，则中止保存
        }
      }

      this.loading = true;
      const wasUpdating = this.updatingMode;
      try {
        if (wasUpdating) {
          const res = await axios.post('/api/config/provider/update', {
            id: this.newSelectedProviderName,
            config: this.newSelectedProviderConfig
          });
          this.showSuccess(res.data.message || "更新成功!");
        } else {
          // 检查 ID 是否已存在
          const existingProvider = this.config_data.provider?.find(p => p.id === this.newSelectedProviderConfig.id);
          if (existingProvider) {
            const confirmed = await this.confirmIdConflict(this.newSelectedProviderConfig.id);
            if (!confirmed) {
              this.loading = false;
              return; // 如果用户取消，则中止保存
            }
          }

          const res = await axios.post('/api/config/provider/new', this.newSelectedProviderConfig);
          this.showSuccess(res.data.message || "添加成功!");
        }
        this.showProviderCfg = false;
        this.getConfig();
      } catch (err) {
        this.showError(err.response?.data?.message || err.message);
      } finally {
        this.loading = false;
        if (wasUpdating) {
          this.updatingMode = false;
        }
      }
    },

    deleteProvider(provider) {
      if (confirm(this.tm('messages.confirm.delete', { id: provider.id }))) {
        axios.post('/api/config/provider/delete', { id: provider.id }).then((res) => {
          this.getConfig();
          this.showSuccess(res.data.message || this.messages.success.delete);
        }).catch((err) => {
          this.showError(err.response?.data?.message || err.message);
        });
      }
    },

    providerStatusChange(provider) {
      provider.enable = !provider.enable; // 切换状态

      axios.post('/api/config/provider/update', {
        id: provider.id,
        config: provider
      }).then((res) => {
        this.getConfig();
        this.showSuccess(res.data.message || this.messages.success.statusUpdate);
      }).catch((err) => {
        provider.enable = !provider.enable; // 发生错误时回滚状态
        this.showError(err.response?.data?.message || err.message);
      });
    },

    // 获取会话隔离配置状态
    getSessionSeparationStatus() {
      axios.get('/api/config/provider/get_session_seperate').then((res) => {
        if (res.data && res.data.status === 'ok') {
          this.sessionSeparationEnabled = res.data.data.enable;
        }
      }).catch((err) => {
        this.showError(err.response?.data?.message || this.messages.error.sessionSeparation);
      });
    },

    // 更新会话隔离配置
    updateSessionSeparation() {
      this.sessionSettingLoading = true;
      axios.post('/api/config/provider/set_session_seperate', {
        enable: this.sessionSeparationEnabled
      }).then((res) => {
        this.showSuccess(res.data.message || this.messages.success.sessionSeparation);
        this.sessionSettingLoading = false;
      }).catch((err) => {
        this.sessionSeparationEnabled = !this.sessionSeparationEnabled; // 发生错误时回滚状态
        this.showError(err.response?.data?.message || err.message);
        this.sessionSettingLoading = false;
      });
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
    
    // 获取供应商状态
    async fetchProviderStatus() {
      if (this.loadingStatus) return;

      this.loadingStatus = true;
      this.showStatus = true; // 自动展开状态部分
      
      // 1. 立即初始化UI为pending状态
      this.providerStatuses = this.config_data.provider.map(p => ({
        id: p.id,
        name: p.id,
        status: 'pending',
        error: null
      }));

      // 2. 为每个provider创建一个并发的测试请求
      const promises = this.config_data.provider.map(p => {
        return axios.get(`/api/config/provider/check_one?id=${p.id}`)
          .then(res => {
            if (res.data && res.data.status === 'ok') {
              // 成功，更新对应的provider状态
              const index = this.providerStatuses.findIndex(s => s.id === p.id);
              if (index !== -1) {
                this.providerStatuses.splice(index, 1, res.data.data);
              }
            } else {
              // 接口返回了业务错误
              throw new Error(res.data?.message || `Failed to check status for ${p.id}`);
            }
          })
          .catch(err => {
            // 网络错误或业务错误
            const errorMessage = err.response?.data?.message || err.message || 'Unknown error';
            const index = this.providerStatuses.findIndex(s => s.id === p.id);
            if (index !== -1) {
              const failedStatus = {
                ...this.providerStatuses[index],
                status: 'unavailable',
                error: errorMessage
              };
              this.providerStatuses.splice(index, 1, failedStatus);
            }
            // 可以在这里选择性地向上抛出错误，以便Promise.allSettled知道
            return Promise.reject(errorMessage);
          });
      });

      // 3. 等待所有请求完成（无论成功或失败）
      try {
        await Promise.allSettled(promises);
      } finally {
        // 4. 关闭全局加载状态
        this.loadingStatus = false;
      }
    },

    confirmEmptyKey() {
      this.showKeyConfirm = true;
      return new Promise((resolve) => {
        this.keyConfirmResolve = resolve;
      });
    },

    handleKeyConfirm(confirmed) {
      if (this.keyConfirmResolve) {
        this.keyConfirmResolve(confirmed);
      }
      this.showKeyConfirm = false;
    },

    confirmIdConflict(id) {
      this.conflictId = id;
      this.showIdConflictDialog = true;
      return new Promise((resolve) => {
        this.idConflictResolve = resolve;
      });
    },

    handleIdConflictConfirm(confirmed) {
      if (this.idConflictResolve) {
        this.idConflictResolve(confirmed);
      }
      this.showIdConflictDialog = false;
    },
    getStatusColor(status) {
      switch (status) {
        case 'available':
          return 'success';
        case 'unavailable':
          return 'error';
        case 'pending':
          return 'grey';
        default:
          return 'default';
      }
    },

    getStatusText(status) {
      return this.messages.status[status] || status;
    },
  }
}
</script>

<style scoped>
.provider-page {
  padding: 20px;
  padding-top: 8px;
}

.provider-card {
  transition: all 0.3s ease;
  height: 100%;
  cursor: pointer;
  overflow: hidden;
  position: relative;
}

.provider-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 25px 0 rgba(0, 0, 0, 0.05);
  border-color: var(--v-primary-base);
}

.provider-card-content {
  display: flex;
  align-items: center;
  height: 100px;
  padding: 16px;
  position: relative;
  z-index: 2;
}

.provider-card-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.provider-card-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
  padding: 0;
}

.provider-card-description {
  padding: 0;
  margin: 0;
}

.provider-card-logo {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.provider-logo-img {
  width: 60px;
  height: 60px;
  opacity: 0.6;
  object-fit: contain;
}

.provider-logo-fallback {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background-color: var(--v-primary-base);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  opacity: 0.3;
}

.v-tabs {
  border-radius: 8px;
}

.v-window {
  border-radius: 4px;
}
</style>
