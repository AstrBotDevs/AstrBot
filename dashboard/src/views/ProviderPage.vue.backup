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
          <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="showAddProviderDialog = true"
            rounded="xl" size="x-large">
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
          <v-tab value="agent_runner" class="font-weight-medium px-3">
            <v-icon start>mdi-message-text</v-icon>
            {{ tm('providers.tabs.agentRunner') }}
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
          <v-tab value="rerank" class="font-weight-medium px-3">
            <v-icon start>mdi-compare-vertical</v-icon>
            {{ tm('providers.tabs.rerank') }}
          </v-tab>
        </v-tabs>

        <template v-if="activeProviderTypeTab === 'all'">
          <v-row v-if="groupedProviders.length === 0">
            <v-col cols="12" class="text-center pa-8">
              <v-icon size="64" color="grey-lighten-1">mdi-api-off</v-icon>
              <p class="text-grey mt-4">{{ getEmptyText() }}</p>
            </v-col>
          </v-row>
          <div v-else>
            <div v-for="group in groupedProviders" :key="group.typeKey" class="mb-8">
              <h1 class="text-h3 font-weight-bold mb-4">{{ group.label }}</h1>
              <v-row>
                <v-col v-for="(provider, index) in group.items" :key="`${group.typeKey}-${index}`" cols="12" md="6"
                  lg="4" xl="3">
                  <item-card :item="provider" title-field="id" enabled-field="enable"
                    :loading="isProviderTesting(provider.id)" @toggle-enabled="providerStatusChange"
                    :bglogo="getProviderIcon(provider.provider)" @delete="deleteProvider" @edit="configExistingProvider"
                    @copy="copyProvider" :show-copy-button="true">
                    <template #item-details="{ item }">
                      <!-- 测试状态 chip -->
                      <v-tooltip v-if="getProviderStatus(item.id)" location="top" max-width="300">
                        <template v-slot:activator="{ props }">
                          <v-chip v-bind="props" :color="getStatusColor(getProviderStatus(item.id).status)" size="small">
                            <v-icon start size="small">
                              {{ getProviderStatus(item.id).status === 'available' ? 'mdi-check-circle' :
                                getProviderStatus(item.id).status === 'unavailable' ? 'mdi-alert-circle' :
                                  'mdi-clock-outline' }}
                            </v-icon>
                            {{ getStatusText(getProviderStatus(item.id).status) }}
                          </v-chip>
                        </template>
                        <span v-if="getProviderStatus(item.id).status === 'unavailable'">
                          {{ getProviderStatus(item.id).error }}
                        </span>
                        <span v-else>{{ getStatusText(getProviderStatus(item.id).status) }}</span>
                      </v-tooltip>
                    </template>
                    <template #actions="{ item }">
                      <v-btn style="z-index: 100000;" variant="tonal" color="info" rounded="xl" size="small"
                        :loading="isProviderTesting(item.id)" @click="testSingleProvider(item)">
                        {{ tm('availability.test') }}
                      </v-btn>
                    </template>
                    <template v-slot:details="{ item }">
                    </template>
                  </item-card>
                </v-col>
              </v-row>
            </div>
          </div>
        </template>
        <template v-else>
          <v-row v-if="filteredProviders.length === 0">
            <v-col cols="12" class="text-center pa-8">
              <v-icon size="64" color="grey-lighten-1">mdi-api-off</v-icon>
              <p class="text-grey mt-4">{{ getEmptyText() }}</p>
            </v-col>
          </v-row>
          <v-row v-else>
            <v-col v-for="(provider, index) in filteredProviders" :key="index" cols="12" md="6" lg="4" xl="3">
              <item-card :item="provider" title-field="id" enabled-field="enable"
                :loading="isProviderTesting(provider.id)" @toggle-enabled="providerStatusChange"
                :bglogo="getProviderIcon(provider.provider)" @delete="deleteProvider" @edit="configExistingProvider"
                @copy="copyProvider" :show-copy-button="true">

                <template #item-details="{ item }">
                  <!-- 测试状态 chip -->
                  <v-tooltip v-if="getProviderStatus(item.id)" location="top" max-width="300">
                    <template v-slot:activator="{ props }">
                      <v-chip v-bind="props" :color="getStatusColor(getProviderStatus(item.id).status)" size="small">
                        <v-icon start size="small">
                          {{ getProviderStatus(item.id).status === 'available' ? 'mdi-check-circle' :
                            getProviderStatus(item.id).status === 'unavailable' ? 'mdi-alert-circle' :
                              'mdi-clock-outline' }}
                        </v-icon>
                        {{ getStatusText(getProviderStatus(item.id).status) }}
                      </v-chip>
                    </template>
                    <span v-if="getProviderStatus(item.id).status === 'unavailable'">
                      {{ getProviderStatus(item.id).error }}
                    </span>
                    <span v-else>{{ getStatusText(getProviderStatus(item.id).status) }}</span>
                  </v-tooltip>
                </template>
                <template #actions="{ item }">
                  <v-btn style="z-index: 100000;" variant="tonal" color="info" rounded="xl" size="small"
                    :loading="isProviderTesting(item.id)" @click="testSingleProvider(item)">
                    {{ tm('availability.test') }}
                  </v-btn>
                </template>
              </item-card>
            </v-col>
          </v-row>
        </template>
      </div>

      <!-- 日志部分 -->
      <v-card elevation="0" class="mt-4 mb-10">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon class="me-2">mdi-console-line</v-icon>
          <span class="text-h4">{{ tm('logs.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn variant="text" color="primary" @click="showConsole = !showConsole">
            {{ showConsole ? tm('logs.collapse') : tm('logs.expand') }}
            <v-icon>{{ showConsole ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
          </v-btn>
        </v-card-title>

        <v-expand-transition>
          <v-card-text class="pa-0" v-if="showConsole">
            <ConsoleDisplayer style="background-color: #1e1e1e; height: 300px; border-radius: 0"></ConsoleDisplayer>
          </v-card-text>
        </v-expand-transition>
      </v-card>
    </v-container>

    <!-- 添加提供商对话框 -->
    <AddNewProvider v-model:show="showAddProviderDialog" :metadata="metadata"
      @select-template="selectProviderTemplate" />

    <!-- 配置对话框 -->
    <v-dialog v-model="showProviderCfg" width="900" persistent>
      <v-card
        :title="updatingMode ? tm('dialogs.config.editTitle') : tm('dialogs.config.addTitle') + ` ${newSelectedProviderName} ` + tm('dialogs.config.provider')">
        <v-card-text class="py-4">
          <AstrBotConfig :iterable="newSelectedProviderConfig" :metadata="metadata['provider_group']?.metadata"
            metadataKey="provider" :is-editing="updatingMode" />
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

    <!-- 消息提示 -->
    <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack"
      location="top">
      {{ save_message }}
    </v-snackbar>

    <WaitingForRestart ref="wfr"></WaitingForRestart>

    <!-- Agent Runner 测试提示对话框 -->
    <v-dialog v-model="showAgentRunnerDialog" max-width="520" persistent>
      <v-card>
        <v-card-title class="text-h3 d-flex align-center">
          <v-icon start class="me-2">mdi-information</v-icon>
          请前往「配置文件」页测试 Agent 执行器
        </v-card-title>
        <v-card-text class="py-4 text-body-1 text-medium-emphasis">
          Agent 执行器的测试请在「配置文件」页进行。
          <ol class="ml-4 mt-4 mb-4">
            <li>找到对应的配置文件并打开。</li>
            <li>找到 Agent 执行方式部分，修改执行器后点击保存。</li>
            <li>点击右下角的 💬 聊天按钮进行测试。</li>
          </ol>
          要让机器人应用这个 Agent 执行器，你也需要前往修改 Agent 执行器。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="showAgentRunnerDialog = false">好的</v-btn>
          <v-btn color="primary" variant="flat" @click="goToConfigPage">点击前往</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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
          您没有填写 API Key，确定要保存吗？这可能会导致该模型无法正常工作。
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
import AddNewProvider from '@/components/provider/AddNewProvider.vue';
import { useModuleI18n } from '@/i18n/composables';
import { getProviderIcon } from '@/utils/providerUtils';

export default {
  name: 'ProviderPage',
  components: {
    AstrBotConfig,
    WaitingForRestart,
    ConsoleDisplayer,
    ItemCard,
    AddNewProvider
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

      // ID冲突确认对话框
      showIdConflictDialog: false,
      conflictId: '',
      idConflictResolve: null,

      // Key确认对话框
      showKeyConfirm: false,
      keyConfirmResolve: null,

      // Agent Runner 提示对话框
      showAgentRunnerDialog: false,

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
      testingProviders: [], // 存储正在测试的 provider ID

      // 新增提供商对话框相关
      showAddProviderDialog: false,

      // 添加提供商类型分类
      activeProviderTypeTab: 'all',

      // 兼容旧版本（< v3.5.11）的 mapping，用于映射到对应的提供商能力类型
      oldVersionProviderTypeMapping: {
        "openai_chat_completion": "chat_completion",
        "anthropic_chat_completion": "chat_completion",
        "googlegenai_chat_completion": "chat_completion",
        "zhipu_chat_completion": "chat_completion",
        "dify": "agent_runner",
        "coze": "agent_runner",
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
          'agent_runner': this.tm('providers.tabs.agentRunner'),
          'speech_to_text': this.tm('providers.tabs.speechToText'),
          'text_to_speech': this.tm('providers.tabs.textToSpeech'),
          'embedding': this.tm('providers.tabs.embedding'),
          'rerank': this.tm('providers.tabs.rerank')
        },
        success: {
          update: this.tm('messages.success.update'),
          add: this.tm('messages.success.add'),
          delete: this.tm('messages.success.delete'),
          statusUpdate: this.tm('messages.success.statusUpdate'),
        },
        error: {
          fetchStatus: this.tm('messages.error.fetchStatus'),
          testError: this.tm('messages.error.testError')
        },
        confirm: {
          delete: this.tm('messages.confirm.delete')
        },
        status: {
          available: this.tm('availability.available'),
          unavailable: this.tm('availability.unavailable'),
          pending: this.tm('availability.pending')
        },
        availability: {
          test: this.tm('availability.test')
        }
      };
    },

    groupedProviders() {
      if (!this.config_data.provider) {
        return [];
      }

      const typeOrder = [
        'chat_completion',
        'agent_runner',
        'speech_to_text',
        'text_to_speech',
        'embedding',
        'rerank',
      ];

      const assigned = new Set();
      const groups = typeOrder
        .map((typeKey) => {
          const items = this.config_data.provider.filter((provider) => {
            const resolved = this.getProviderType(provider);
            if (resolved === typeKey) {
              assigned.add(provider.id);
              return true;
            }
            return false;
          });
          return {
            typeKey,
            label: this.messages.tabTypes[typeKey] || typeKey,
            items,
          };
        })
        .filter((group) => group.items.length > 0);

      const remaining = this.config_data.provider.filter(
        (provider) => !assigned.has(provider.id),
      );
      if (remaining.length > 0) {
        groups.push({
          typeKey: 'others',
          label: this.tm('providers.tabs.all'),
          items: remaining,
        });
      }
      return groups;
    },

    // 根据选择的标签过滤提供商列表
    filteredProviders() {
      if (!this.config_data.provider || this.activeProviderTypeTab === 'all') {
        return this.config_data.provider || [];
      }

      return this.config_data.provider.filter(provider => {
        // 如果provider.provider_type已经存在，直接使用它
        return this.getProviderType(provider) === this.activeProviderTypeTab;
      });
    }
  },

  mounted() {
    this.getConfig();
  },

  methods: {
    getProviderType(provider) {
      if (!provider) return undefined;
      if (provider.provider_type) {
        return provider.provider_type;
      }
      return this.oldVersionProviderTypeMapping[provider.type];
    },

    getConfig() {
      axios.get('/api/config/get').then((res) => {
        this.config_data = res.data.data.config;
        this.fetched = true
        this.metadata = res.data.data.metadata;
      }).catch((err) => {
        this.showError(err.response?.data?.message || err.message);
      });
    },

    // 从工具函数导入
    getProviderIcon,

    // 获取空列表文本
    getEmptyText() {
      if (this.activeProviderTypeTab === 'all') {
        return this.messages.emptyText.all;
      } else {
        return this.tm('providers.empty.typed', { type: this.getTabTypeName(this.activeProviderTypeTab) });
      }
    },

    // 获取Tab类型的中文名称
    getTabTypeName(tabType) {
      return this.messages.tabTypes[tabType] || tabType;
    },

    // 选择提供商模板
    selectProviderTemplate(name) {
      this.newSelectedProviderName = name;
      this.showProviderCfg = true;
      this.updatingMode = false;
      this.newSelectedProviderConfig = JSON.parse(JSON.stringify(
        this.metadata['provider_group']?.metadata?.provider?.config_template[name] || {}
      ));
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
                target[key] = Array.isArray(source[key]) ? [...source[key]] : { ...source[key] };
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
              // 如果target中没有这个key
              if (Array.isArray(reference[key])) {
                // 复制
                target[key] = [...reference[key]]
              } else {
                target[key] = {};
              }
            }
            if (!Array.isArray(reference[key])) {
              mergeConfigWithOrder(
                target[key],
                source && source[key] ? source[key] : {},
                reference[key]
              );
            }
          } else if (!(key in target)) {
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
          if (res.data.status === 'error') {
            this.showError(res.data.message || "更新失败!");
            return
          }
          this.showSuccess(res.data.message || "更新成功!");
          if (wasUpdating) {
            this.updatingMode = false;
          }
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
          if (res.data.status === 'error') {
            this.showError(res.data.message || "添加失败!");
            return
          }
          this.showSuccess(res.data.message || "添加成功!");
        }
        this.showProviderCfg = false;
      } catch (err) {
        this.showError(err.response?.data?.message || err.message);
      } finally {
        this.loading = false;
        this.getConfig();
      }
    },

    async copyProvider(providerToCopy) {
      console.log('copyProvider triggered for:', providerToCopy);
      // 1. 创建深拷贝
      const newProviderConfig = JSON.parse(JSON.stringify(providerToCopy));

      // 2. 生成唯一的 ID
      const generateUniqueId = (baseId) => {
        let newId = `${baseId}_copy`;
        let counter = 1;
        const existingIds = this.config_data.provider.map(p => p.id);
        while (existingIds.includes(newId)) {
          newId = `${baseId}_copy_${counter}`;
          counter++;
        }
        return newId;
      };
      newProviderConfig.id = generateUniqueId(providerToCopy.id);

      // 3. 设置为禁用状态，等待用户手动开启
      newProviderConfig.enable = false;

      this.loading = true;
      try {
        // 4. 调用后端接口创建
        const res = await axios.post('/api/config/provider/new', newProviderConfig);
        this.showSuccess(res.data.message || `成功复制并创建了 ${newProviderConfig.id}`);
        this.getConfig(); // 5. 刷新列表
      } catch (err) {
        this.showError(err.response?.data?.message || err.message);
      } finally {
        this.loading = false;
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
        if (res.data.status === 'error') {
          this.showError(res.data.message)
          return
        }
        this.getConfig();
        this.showSuccess(res.data.message || this.messages.success.statusUpdate);
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
    async fetchProviderStatus() {
      if (this.testingProviders.length > 0) return;

      this.showStatus = true; // 自动展开状态部分

      const providersToTest = this.config_data.provider.filter(p => p.enable);
      if (providersToTest.length === 0) return;

      // 1. 初始化UI为pending状态，并将所有待测试的 provider ID 加入 loading 列表
      this.providerStatuses = providersToTest.map(p => {
        this.testingProviders.push(p.id);
        return { id: p.id, name: p.id, status: 'pending', error: null };
      });

      // 2. 为每个provider创建一个并发的测试请求
      const promises = providersToTest.map(p =>
        axios.get(`/api/config/provider/check_one?id=${p.id}`)
          .then(res => {
            if (res.data && res.data.status === 'ok') {
              const index = this.providerStatuses.findIndex(s => s.id === p.id);
              if (index !== -1) this.providerStatuses.splice(index, 1, res.data.data);
            } else {
              throw new Error(res.data?.message || `Failed to check status for ${p.id}`);
            }
          })
          .catch(err => {
            const errorMessage = err.response?.data?.message || err.message || 'Unknown error';
            const index = this.providerStatuses.findIndex(s => s.id === p.id);
            if (index !== -1) {
              const failedStatus = { ...this.providerStatuses[index], status: 'unavailable', error: errorMessage };
              this.providerStatuses.splice(index, 1, failedStatus);
            }
            return Promise.reject(errorMessage); // Propagate error for Promise.allSettled
          })
      );

      // 3. 等待所有请求完成
      try {
        await Promise.allSettled(promises);
      } finally {
        // 4. 关闭所有加载状态
        this.testingProviders = [];
      }
    },

    isProviderTesting(providerId) {
      return this.testingProviders.includes(providerId);
    },

    getProviderStatus(providerId) {
      return this.providerStatuses.find(s => s.id === providerId);
    },

    async testSingleProvider(provider) {
      if (this.isProviderTesting(provider.id)) return;

      this.testingProviders.push(provider.id);

      // 更新UI为pending状态
      const statusIndex = this.providerStatuses.findIndex(s => s.id === provider.id);
      const pendingStatus = {
        id: provider.id,
        name: provider.id,
        status: 'pending',
        error: null
      };
      if (statusIndex !== -1) {
        this.providerStatuses.splice(statusIndex, 1, pendingStatus);
      } else {
        this.providerStatuses.unshift(pendingStatus);
      }

      try {
        if (!provider.enable) {
          throw new Error('该提供商未被用户启用');
        }
        if (provider.provider_type === 'agent_runner') {
          this.showAgentRunnerDialog = true;
          this.providerStatuses = this.providerStatuses.filter(s => s.id !== provider.id);
          return;
        }

        const res = await axios.get(`/api/config/provider/check_one?id=${provider.id}`);
        if (res.data && res.data.status === 'ok') {
          const index = this.providerStatuses.findIndex(s => s.id === provider.id);
          if (index !== -1) {
            this.providerStatuses.splice(index, 1, res.data.data);
          }
        } else {
          throw new Error(res.data?.message || `Failed to check status for ${provider.id}`);
        }
      } catch (err) {
        const errorMessage = err.response?.data?.message || err.message || 'Unknown error';
        const index = this.providerStatuses.findIndex(s => s.id === provider.id);
        const failedStatus = {
          id: provider.id,
          name: provider.id,
          status: 'unavailable',
          error: errorMessage
        };
        if (index !== -1) {
          this.providerStatuses.splice(index, 1, failedStatus);
        }
        // 不再显示全局的错误提示，因为卡片本身会显示错误信息
        // this.showError(this.tm('messages.error.testError', { id: provider.id, error: errorMessage }));
      } finally {
        const index = this.testingProviders.indexOf(provider.id);
        if (index > -1) {
          this.testingProviders.splice(index, 1);
        }
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
    goToConfigPage() {
      this.showAgentRunnerDialog = false;
      this.$router.push({ name: 'Configs' });
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
  padding-bottom: 40px;
}

.status-card {
  height: 120px;
  overflow-y: auto;
}
</style>
