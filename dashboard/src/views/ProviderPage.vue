<template>
  <div class="provider-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row>
        <v-col cols="12">
          <h1 class="text-h4 font-weight-bold mb-2">
            <v-icon size="x-large" color="primary" class="me-2">mdi-creation</v-icon>服务提供商管理
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4">
            管理AI服务提供商，连接到不同的大语言模型
          </p>
        </v-col>
      </v-row>

      <!-- 服务提供商部分 -->
      <v-card class="mb-6" elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-api</v-icon>
          <span class="text-h6">服务提供商</span>
          <v-chip color="info" size="small" class="ml-2">{{ config_data.provider?.length || 0 }}</v-chip>
          <v-spacer></v-spacer>
          <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="showAddProviderDialog = true">
            新增服务提供商
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <!-- 添加分类标签页 -->
        <v-card-text class="px-4 pt-3 pb-0">
          <v-tabs v-model="activeProviderTypeTab" bg-color="transparent">
            <v-tab value="all" class="font-weight-medium px-3">
              <v-icon start>mdi-filter-variant</v-icon>
              全部
            </v-tab>
            <v-tab value="chat_completion" class="font-weight-medium px-3">
              <v-icon start>mdi-message-text</v-icon>
              基本对话
            </v-tab>
            <v-tab value="speech_to_text" class="font-weight-medium px-3">
              <v-icon start>mdi-microphone-message</v-icon>
              语音转文字
            </v-tab>
            <v-tab value="text_to_speech" class="font-weight-medium px-3">
              <v-icon start>mdi-volume-high</v-icon>
              文字转语音
            </v-tab>
            <v-tab value="embedding" class="font-weight-medium px-3">
              <v-icon start>mdi-code-json</v-icon>
              Embedding
            </v-tab>
          </v-tabs>
        </v-card-text>

        <v-card-text class="px-4 py-3">
          <item-card-grid
            :items="filteredProviders"
            title-field="id"
            enabled-field="enable"
            empty-icon="mdi-api-off"
            :empty-text="getEmptyText()"
            @toggle-enabled="providerStatusChange"
            @delete="deleteProvider"
            @edit="configExistingProvider"
          >
            <template v-slot:item-details="{ item }">
              <div class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-tag</v-icon>
                <span class="text-caption text-medium-emphasis">
                  提供商类型:
                  <v-chip size="x-small" color="primary" class="ml-1">{{ item.type }}</v-chip>
                </span>
              </div>
              <div v-if="item.api_base" class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-web</v-icon>
                <span class="text-caption text-medium-emphasis text-truncate" :title="item.api_base">
                  API Base: {{ item.api_base }}
                </span>
              </div>
              <div v-if="item.api_key" class="d-flex align-center">
                <v-icon size="small" color="grey" class="me-2">mdi-key</v-icon>
                <span class="text-caption text-medium-emphasis">API Key: ••••••••</span>
              </div>
            </template>
          </item-card-grid>
        </v-card-text>
      </v-card>

      <!-- 供应商状态部分 -->
      <v-card class="mb-6" elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-heart-pulse</v-icon>
          <span class="text-h6">供应商可用性</span>
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="tonal" :loading="loadingStatus" @click="fetchProviderStatus">
            <v-icon left>mdi-refresh</v-icon>
            刷新状态
          </v-btn>
        </v-card-title>
        <v-card-subtitle class="px-4 py-1 text-caption text-medium-emphasis">
          通过测试模型对话可用性判断，可能产生API费用
        </v-card-subtitle>

        <v-divider></v-divider>

        <v-card-text class="px-4 py-3">
          <v-alert v-if="providerStatuses.length === 0" type="info" variant="tonal">
            点击"刷新状态"按钮获取供应商可用性
          </v-alert>
          
          <v-container v-else class="pa-0">
            <v-row>
              <v-col v-for="status in providerStatuses" :key="status.id" cols="12" sm="6" md="4">
                <v-card variant="outlined" class="status-card">
                  <v-card-item>
                    <v-icon :color="status.status === 'available' ? 'success' : 'error'" class="me-2">
                      {{ status.status === 'available' ? 'mdi-check-circle' : 'mdi-alert-circle' }}
                    </v-icon>
                    <span class="font-weight-bold">{{ status.id }}</span>
                    <v-chip :color="status.status === 'available' ? 'success' : 'error'" size="small" class="ml-2">
                      {{ status.status === 'available' ? '可用' : '不可用' }}
                    </v-chip>
                  </v-card-item>
                  <v-card-text v-if="status.status === 'unavailable'" class="text-caption text-medium-emphasis">
                    <span class="font-weight-bold">错误信息:</span> {{ status.error }}
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>
      </v-card>

      <!-- 日志部分 -->
      <v-card elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-console-line</v-icon>
          <span class="text-h6">服务日志</span>
          <v-spacer></v-spacer>
          <v-btn variant="text" color="primary" @click="showConsole = !showConsole">
            {{ showConsole ? '收起' : '展开' }}
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
          <span>服务提供商</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="showAddProviderDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text class="pa-4" style="overflow-y: auto;">
          <v-tabs v-model="activeProviderTab" grow slider-color="primary" bg-color="background">
            <v-tab value="chat_completion" class="font-weight-medium px-3">
              <v-icon start>mdi-message-text</v-icon>
              基本
            </v-tab>
            <v-tab value="speech_to_text" class="font-weight-medium px-3">
              <v-icon start>mdi-microphone-message</v-icon>
              语音转文字
            </v-tab>
            <v-tab value="text_to_speech" class="font-weight-medium px-3">
              <v-icon start>mdi-volume-high</v-icon>
              文字转语音
            </v-tab>
            <v-tab value="embedding" class="font-weight-medium px-3">
              <v-icon start>mdi-code-json</v-icon>
              Embedding
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
                    <v-card-item>
                      <template v-slot:prepend>
                        <v-avatar color="primary" variant="tonal" class="mr-3">
                          <img :src="getProviderIcon(name)" v-if="getProviderIcon(name)" width="24" height="24">
                          <span v-else style="font-weight: 1000;">
                            {{ name[0].toUpperCase() }}
                          </span>
                        </v-avatar>
                      </template>
                      <v-card-title style="font-size: 15px;">{{ name }}</v-card-title>
                    </v-card-item>
                    <v-card-text class="text-caption text-medium-emphasis">
                      {{ getProviderDescription(template, name) }}
                    </v-card-text>
                  </v-card>
                </v-col>
                <v-col v-if="Object.keys(getTemplatesByType(tabType)).length === 0" cols="12">
                  <v-alert type="info" variant="tonal">
                    暂无{{ getTabTypeName(tabType) }}类型的提供商模板
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
          <span>{{ updatingMode ? '编辑' : '新增' }} {{ newSelectedProviderName }} 服务提供商</span>
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
            取消
          </v-btn>
          <v-btn color="primary" @click="newProvider" :loading="loading">
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

    <WaitingForRestart ref="wfr"></WaitingForRestart>
  </div>
</template>

<script>
import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import ItemCardGrid from '@/components/shared/ItemCardGrid.vue';

export default {
  name: 'ProviderPage',
  components: {
    AstrBotConfig,
    WaitingForRestart,
    ConsoleDisplayer,
    ItemCardGrid
  },
  data() {
    return {
      config_data: {},
      fetched: false,
      metadata: {},
      showProviderCfg: false,

      newSelectedProviderName: '',
      newSelectedProviderConfig: {},
      updatingMode: false,

      loading: false,

      save_message_snack: false,
      save_message: "",
      save_message_success: "success",

      showConsole: false,
      
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
        "llm_tuner": "chat_completion",
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

  computed: {
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
        return "暂无服务提供商，点击 新增服务提供商 添加";
      } else {
        return `暂无${this.getTabTypeName(this.activeProviderTypeTab)}类型的服务提供商，点击 新增服务提供商 添加`;
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
        'OpenAI': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/openai.svg',
        'Azure OpenAI': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/openai.svg',
        'Whisper': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/openai.svg',
        'xAI': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/xai.svg',
        'Anthropic': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/anthropic.svg',
        'Ollama': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/anthropic.svg',
        'Gemini': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/gemini-color.svg',
        'Gemini(OpenAI兼容)': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/gemini-color.svg',
        'DeepSeek': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/deepseek.svg',
        '智谱 AI': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/zhipu.svg',
        '硅基流动': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/siliconcloud.svg',
        'Kimi': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/kimi.svg',
        'PPIO派欧云': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/ppio.svg',
        'Dify': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/dify-color.svg',
        '阿里云百炼': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/alibabacloud-color.svg',
        'FastGPT': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/fastgpt-color.svg',
        'LM Studio': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/lmstudio.svg',
        'FishAudio': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/fishaudio.svg',
        'Azure': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/azure.svg',
        'MiniMax': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/minimax.svg',
      };
      for (const key in icons) {
        if (type.startsWith(key)) {
          return icons[key];
        }
      }
      return ''
    },

    // 获取Tab类型的中文名称
    getTabTypeName(tabType) {
      const names = {
        'chat_completion': '基本对话',
        'speech_to_text': '语音转文本',
        'text_to_speech': '文本转语音',
        'embedding': 'Embedding'
      };
      return names[tabType] || tabType;
    },

    // 获取提供商简介
    getProviderDescription(template, name) {
      if (name == 'OpenAI') {
        return `${template.type} 服务提供商。同时也支持所有兼容 OpenAI API 的模型提供商。`;
      }
      return `${template.type} 服务提供商`;
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

    newProvider() {
      this.loading = true;
      if (this.updatingMode) {
        axios.post('/api/config/provider/update', {
          id: this.newSelectedProviderName,
          config: this.newSelectedProviderConfig
        }).then((res) => {
          this.loading = false;
          this.showProviderCfg = false;
          this.getConfig();
          this.showSuccess(res.data.message || "更新成功!");
        }).catch((err) => {
          this.loading = false;
          this.showError(err.response?.data?.message || err.message);
        });
        this.updatingMode = false;
      } else {
        axios.post('/api/config/provider/new', this.newSelectedProviderConfig).then((res) => {
          this.loading = false;
          this.showProviderCfg = false;
          this.getConfig();
          this.showSuccess(res.data.message || "添加成功!");
        }).catch((err) => {
          this.loading = false;
          this.showError(err.response?.data?.message || err.message);
        });
      }
    },

    deleteProvider(provider) {
      if (confirm(`确定要删除服务提供商 ${provider.id} 吗?`)) {
        axios.post('/api/config/provider/delete', { id: provider.id }).then((res) => {
          this.getConfig();
          this.showSuccess(res.data.message || "删除成功!");
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
        this.showSuccess(res.data.message || "状态更新成功!");
      }).catch((err) => {
        provider.enable = !provider.enable; // 发生错误时回滚状态
        this.showError(err.response?.data?.message || err.message);
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
    fetchProviderStatus() {
      this.loadingStatus = true;
      axios.get('/api/config/provider/check_status').then((res) => {
        if (res.data && res.data.status === 'ok') {
          this.providerStatuses = res.data.data || [];
        } else {
          this.showError(res.data?.message || "获取供应商状态失败");
        }
        this.loadingStatus = false;
      }).catch((err) => {
        this.loadingStatus = false;
        this.showError(err.response?.data?.message || err.message);
      });
    }
  }
}
</script>

<style scoped>
.provider-page {
  padding: 20px;
  padding-top: 8px;
}

.provider-selection-dialog .v-card-title {
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
}

.provider-card {
  transition: all 0.3s ease;
  height: 100%;
  cursor: pointer;
}

.provider-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 25px 0 rgba(0, 0, 0, 0.05);
  border-color: var(--v-primary-base);
}

.v-tabs {
  border-radius: 8px;
}

.v-window {
  border-radius: 4px;
}
</style>
