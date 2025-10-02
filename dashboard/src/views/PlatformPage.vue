<template>
  <div class="platform-page">
    <v-container fluid class="pa-0">
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
        <div>
          <h1 class="text-h1 font-weight-bold mb-2">
            <v-icon color="black" class="me-2">mdi-connection</v-icon>{{ tm('title') }}
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4">
            {{ tm('subtitle') }}
          </p>
        </div>
        <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="showAddPlatformDialog = true"
          rounded="xl" size="x-large">
          {{ tm('addAdapter') }}
        </v-btn>
      </v-row>

      <div>
        <v-row v-if="(config_data.platform || []).length === 0">
          <v-col cols="12" class="text-center pa-8">
            <v-icon size="64" color="grey-lighten-1">mdi-connection</v-icon>
            <p class="text-grey mt-4">{{ tm('emptyText') }}</p>
          </v-col>
        </v-row>

        <v-row v-else>
          <v-col v-for="(platform, index) in config_data.platform || []" :key="index" cols="12" md="6" lg="4" xl="3">
            <item-card :item="platform" title-field="id" enabled-field="enable"
              :bglogo="getPlatformIcon(platform.type || platform.id)" @toggle-enabled="platformStatusChange"
              @delete="deletePlatform" @edit="editPlatform">
            </item-card>
          </v-col>
        </v-row>
      </div>

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

    <!-- 添加平台适配器对话框 -->
    <AddNewPlatform v-model:show="showAddPlatformDialog" :metadata="metadata"
      @select-template="selectPlatformTemplate" />

    <!-- 配置对话框 -->
    <v-dialog v-model="showPlatformCfg" persistent width="900px" max-width="90%">
      <v-card
        :title="updatingMode ? tm('dialog.edit') : tm('dialog.add') + ` ${newSelectedPlatformName} ` + tm('dialog.adapter')">
        <v-card-text class="py-4">
          <v-row>
            <v-col cols="12">
              <AstrBotConfig :iterable="newSelectedPlatformConfig" :metadata="metadata['platform_group']?.metadata"
                metadataKey="platform" />
            </v-col>
          </v-row>
          <v-row class="mt-2">
            <v-col cols="12" class="text-center">
              <v-btn color="info" variant="outlined" @click="openTutorial">
                <v-icon start>mdi-book-open-variant</v-icon>
                {{ tm('dialog.viewTutorial') }}
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>

        <v-divider></v-divider>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showPlatformCfg = false" :disabled="loading">
            {{ tm('dialog.cancel') }}
          </v-btn>
          <v-btn color="primary" @click="newPlatform" :loading="loading">
            {{ tm('dialog.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack"
      location="top">
      {{ save_message }}
    </v-snackbar>

    <!-- ID冲突确认对话框 -->
    <v-dialog v-model="showIdConflictDialog" max-width="450" persistent>
      <v-card>
        <v-card-title class="text-h6 bg-warning d-flex align-center">
          <v-icon start class="me-2">mdi-alert-circle-outline</v-icon>
          {{ tm('dialog.idConflict.title') }}
        </v-card-title>
        <v-card-text class="py-4 text-body-1 text-medium-emphasis">
          {{ tm('dialog.idConflict.message', { id: conflictId }) }}
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="handleIdConflictConfirm(false)">{{ tm('dialog.idConflict.confirm')
          }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 安全警告对话框 -->
    <v-dialog v-model="showOneBotEmptyTokenWarnDialog" max-width="600" persistent>
      <v-card>
        <v-card-title>
          {{ tm('dialog.securityWarning.title') }}
        </v-card-title>
        <v-card-text class="py-4">
          <p>{{ tm('dialog.securityWarning.aiocqhttpTokenMissing') }}</p>
          <span><a
              href="https://docs.astrbot.app/deploy/platform/aiocqhttp/napcat.html#%E9%99%84%E5%BD%95-%E5%A2%9E%E5%BC%BA%E8%BF%9E%E6%8E%A5%E5%AE%89%E5%85%A8%E6%80%A7"
              target="_blank">{{ tm('dialog.securityWarning.learnMore') }}</a></span>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer></v-spacer>
          <v-btn color="error" @click="handleOneBotEmptyTokenWarningDismiss(true)">
            无视警告并继续创建
          </v-btn>
          <v-btn color="primary" @click="handleOneBotEmptyTokenWarningDismiss(false)">
            重新修改
          </v-btn>
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
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import { useCommonStore } from '@/stores/common';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { getPlatformIcon, getTutorialLink } from '@/utils/platformUtils';

export default {
  name: 'PlatformPage',
  components: {
    AstrBotConfig,
    WaitingForRestart,
    ConsoleDisplayer,
    ItemCard,
    AddNewPlatform
  },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n('features/platform');

    return {
      t,
      tm
    };
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
    }
  },
  data() {
    return {
      config_data: {},
      fetched: false,
      metadata: {},
      showPlatformCfg: false,
      showAddPlatformDialog: false,

      newSelectedPlatformName: '',
      newSelectedPlatformConfig: {},
      updatingMode: false,

      loading: false,

      save_message_snack: false,
      save_message: "",
      save_message_success: "success",

      showConsole: false,

      // ID冲突确认对话框
      showIdConflictDialog: false,
      conflictId: '',
      idConflictResolve: null,

      // OneBot Empty Token Warning #2639
      showOneBotEmptyTokenWarnDialog: false,
      oneBotEmptyTokenWarningResolve: null,

      store: useCommonStore()
    }
  },

  watch: {
    showIdConflictDialog(newValue) {
      if (!newValue && this.idConflictResolve) {
        this.idConflictResolve(false);
        this.idConflictResolve = null;
      }
    },

    showOneBotEmptyTokenWarnDialog(newValue) {
      if (!newValue && this.oneBotEmptyTokenWarningResolve) {
        this.oneBotEmptyTokenWarningResolve(true);
        this.oneBotEmptyTokenWarningResolve = null;
      }
    }
  },

  mounted() {
    this.getConfig();
  },

  methods: {
    // 从工具函数导入
    getPlatformIcon(platform_id) {
      // 首先检查是否有来自插件的 logo_token
      const template = this.metadata['platform_group']?.metadata?.platform?.config_template?.[platform_id];
      if (template && template.logo_token) {
          // 通过文件服务访问插件提供的 logo
        return `/api/file/${template.logo_token}`;
      }
      return getPlatformIcon(platform_id);
    },

    openTutorial() {
      const tutorialUrl = getTutorialLink(this.newSelectedPlatformConfig.type);
      window.open(tutorialUrl, '_blank');
    },

    getConfig() {
      axios.get('/api/config/get').then((res) => {
        this.config_data = res.data.data.config;
        this.fetched = true
        this.metadata = res.data.data.metadata;
      }).catch((err) => {
        this.showError(err);
      });
    },

    // 选择平台模板
    selectPlatformTemplate(name) {
      this.newSelectedPlatformName = name;
      this.showPlatformCfg = true;
      this.updatingMode = false;
      this.newSelectedPlatformConfig = JSON.parse(JSON.stringify(
        this.metadata['platform_group']?.metadata?.platform?.config_template[name] || {}
      ));
    },

    addFromDefaultConfigTmpl(index) {
      this.newSelectedPlatformName = index[0];
      this.showPlatformCfg = true;
      this.updatingMode = false;
      this.newSelectedPlatformConfig = JSON.parse(JSON.stringify(
        this.metadata['platform_group']?.metadata?.platform?.config_template[index[0]] || {}
      ));
    },

    editPlatform(platform) {
      this.newSelectedPlatformName = platform.id;
      this.newSelectedPlatformConfig = JSON.parse(JSON.stringify(platform));
      this.updatingMode = true;
      this.showPlatformCfg = true;
    },

    newPlatform() {
      this.loading = true;
      if (this.updatingMode) {
        if (this.newSelectedPlatformConfig.type === 'aiocqhttp') {
          const token = this.newSelectedPlatformConfig.ws_reverse_token;
          if (!token || token.trim() === '') {
            this.showOneBotEmptyTokenWarning().then((continueWithWarning) => {
              if (continueWithWarning) {
                this.updatePlatform();
              }
            });
            return;
          }
        }
        this.updatePlatform();
      } else {
        this.savePlatform();
      }
    },

    updatePlatform() {
      axios.post('/api/config/platform/update', {
        id: this.newSelectedPlatformName,
        config: this.newSelectedPlatformConfig
      }).then((res) => {
        this.loading = false;
        this.showPlatformCfg = false;
        this.getConfig();
        this.showSuccess(res.data.message || this.messages.updateSuccess);
      }).catch((err) => {
        this.loading = false;
        this.showError(err.response?.data?.message || err.message);
      });
      this.updatingMode = false;
    },

    async savePlatform() {
      // 检查 ID 是否已存在
      const existingPlatform = this.config_data.platform?.find(p => p.id === this.newSelectedPlatformConfig.id);
      if (existingPlatform) {
        const confirmed = await this.confirmIdConflict(this.newSelectedPlatformConfig.id);
        if (!confirmed) {
          this.loading = false;
          return; // 如果用户取消，则中止保存
        }
      }

      // 检查 aiocqhttp 适配器的安全设置
      if (this.newSelectedPlatformConfig.type === 'aiocqhttp') {
        const token = this.newSelectedPlatformConfig.ws_reverse_token;
        if (!token || token.trim() === '') {
          const continueWithWarning = await this.showOneBotEmptyTokenWarning();
          if (!continueWithWarning) {
            return;
          }
        }
      }

      try {
        const res = await axios.post('/api/config/platform/new', this.newSelectedPlatformConfig);
        this.loading = false;
        this.showPlatformCfg = false;
        this.getConfig();
        this.showSuccess(res.data.message || this.messages.addSuccess);
      } catch (err) {
        this.loading = false;
        this.showError(err.response?.data?.message || err.message);
      }
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

    showOneBotEmptyTokenWarning() {
      this.showOneBotEmptyTokenWarnDialog = true;
      return new Promise((resolve) => {
        this.oneBotEmptyTokenWarningResolve = resolve;
      });
    },

    handleOneBotEmptyTokenWarningDismiss(continueWithWarning) {
      this.showOneBotEmptyTokenWarnDialog = false;
      if (this.oneBotEmptyTokenWarningResolve) {
        this.oneBotEmptyTokenWarningResolve(continueWithWarning);
        this.oneBotEmptyTokenWarningResolve = null;
      }

      if (!continueWithWarning) {
        this.loading = false;
      }
    },

    deletePlatform(platform) {
      if (confirm(`${this.messages.deleteConfirm} ${platform.id}?`)) {
        axios.post('/api/config/platform/delete', { id: platform.id }).then((res) => {
          this.getConfig();
          this.showSuccess(res.data.message || this.messages.deleteSuccess);
        }).catch((err) => {
          this.showError(err.response?.data?.message || err.message);
        });
      }
    },

    platformStatusChange(platform) {
      platform.enable = !platform.enable; // 切换状态

      axios.post('/api/config/platform/update', {
        id: platform.id,
        config: platform
      }).then((res) => {
        this.getConfig();
        this.showSuccess(res.data.message || this.messages.statusUpdateSuccess);
      }).catch((err) => {
        platform.enable = !platform.enable; // 发生错误时回滚状态
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
    }
  }
}
</script>

<style scoped>
.platform-page {
  padding: 20px;
  padding-top: 8px;
}
</style>
