<template>
  <div class="platform-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row>
        <v-col cols="12">
          <h1 class="text-h4 font-weight-bold mb-2">
            <v-icon size="x-large" color="primary" class="me-2">mdi-connection</v-icon>{{ tm('title') }}
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4">
            {{ tm('subtitle') }}
          </p>
        </v-col>
      </v-row>

      <!-- 平台适配器部分 -->
      <v-card class="mb-6" elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-apps</v-icon>
          <span class="text-h6">{{ tm('adapters') }}</span>
          <v-chip color="info" size="small" class="ml-2">{{ config_data.platform?.length || 0 }}</v-chip>
          <v-spacer></v-spacer>
          <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="showAddPlatformDialog = true">
            {{ tm('addAdapter') }}
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="px-4 py-3">
          <item-card-grid :items="config_data.platform || []" title-field="id" enabled-field="enable"
            empty-icon="mdi-connection" :empty-text="tm('emptyText')" @toggle-enabled="platformStatusChange"
            @delete="deletePlatform" @edit="editPlatform">
            <template v-slot:item-details="{ item }">
              <div class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-tag</v-icon>
                <span class="text-caption text-medium-emphasis">
                  {{ tm('details.adapterType') }}:
                  <v-chip size="x-small" color="primary" class="ml-1">{{ item.type }}</v-chip>
                </span>
              </div>
              <div v-if="item.token" class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-key</v-icon>
                <span class="text-caption text-medium-emphasis">{{ tm('details.token') }}: ••••••••</span>
              </div>
              <div v-if="item.description" class="d-flex align-center">
                <v-icon size="small" color="grey" class="me-2">mdi-information-outline</v-icon>
                <span class="text-caption text-medium-emphasis text-truncate">{{ item.description }}</span>
              </div>
            </template>
          </item-card-grid>
        </v-card-text>
      </v-card>

      <!-- 日志部分 -->
      <v-card elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-console-line</v-icon>
          <span class="text-h6">{{ tm('logs.title') }}</span>
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
    <v-dialog v-model="showAddPlatformDialog" max-width="900px" min-height="80%">
      <v-card class="platform-selection-dialog">
        <v-card-title class="bg-primary text-white py-3 px-4" style="display: flex; align-items: center;">
          <v-icon color="white" class="me-2">mdi-plus-circle</v-icon>
          <span>{{ tm('dialog.addPlatform') }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="showAddPlatformDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text class="pa-4" style="overflow-y: auto;">
          <v-row class="mt-1">
            <v-col v-for="(template, name) in metadata['platform_group']?.metadata?.platform?.config_template || {}"
              :key="name" cols="12" sm="6" md="6">
              <v-card variant="outlined" hover class="platform-card" @click="selectPlatformTemplate(name)">
                <div class="platform-card-content">
                  <div class="platform-card-text">
                    <v-card-title class="platform-card-title">接入 {{ name }}</v-card-title>
                    <v-card-text class="text-caption text-medium-emphasis platform-card-description">
                      {{ getPlatformDescription(template, name) }}
                    </v-card-text>
                  </div>
                  <div class="platform-card-logo">
                    <img :src="getPlatformIcon(name)" v-if="getPlatformIcon(name)" class="platform-logo-img">
                    <div v-else class="platform-logo-fallback">
                      {{ name[0].toUpperCase() }}
                    </div>
                  </div>
                </div>
              </v-card>
            </v-col>
            <v-col
              v-if="Object.keys(metadata['platform_group']?.metadata?.platform?.config_template || {}).length === 0"
              cols="12">
              <v-alert type="info" variant="tonal">
                {{ tm('dialog.noTemplates') }}
              </v-alert>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 配置对话框 -->
    <v-dialog v-model="showPlatformCfg" persistent width="900px" max-width="90%">
      <v-card>
        <v-card-title class="bg-primary text-white py-3">
          <v-icon color="white" class="me-2">{{ updatingMode ? 'mdi-pencil' : 'mdi-plus' }}</v-icon>
          <span>{{ updatingMode ? tm('dialog.edit') : tm('dialog.add') }} {{ newSelectedPlatformName }} {{
            tm('dialog.adapter') }}</span>
        </v-card-title>

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
                查看接入教程
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
  </div>
</template>

<script>
import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import ItemCardGrid from '@/components/shared/ItemCardGrid.vue';
import { useCommonStore } from '@/stores/common';
import { useI18n, useModuleI18n } from '@/i18n/composables';

export default {
  name: 'PlatformPage',
  components: {
    AstrBotConfig,
    WaitingForRestart,
    ConsoleDisplayer,
    ItemCardGrid
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

      store: useCommonStore()
    }
  },

  watch: {
    showIdConflictDialog(newValue) {
      // 当对话框关闭时，如果 Promise 还在等待，则拒绝它以防止内存泄漏
      if (!newValue && this.idConflictResolve) {
        this.idConflictResolve(false);
        this.idConflictResolve = null;
      }
    }
  },

  mounted() {
    this.getConfig();
  },

  methods: {
    openTutorial() {
      const tutorialUrl = this.getTutorialLink(this.newSelectedPlatformConfig.type);
      window.open(tutorialUrl, '_blank');
    },

    getPlatformIcon(name) {
      if (name.includes('QQ')) {
        return '/src/assets/images/platform_logos/qq.png'
      } else if (name.includes('企业微信')) {
        return '/src/assets/images/platform_logos/wecom.png'
      } else if (name.includes('微信')) {
        return '/src/assets/images/platform_logos/wechat.png';
      } else if (name.includes('Lark')) {
        return '/src/assets/images/platform_logos/lark.png';
      } else if (name.includes('DingTalk')) {
        return '/src/assets/images/platform_logos/dingtalk.svg';
      } else if (name.includes('Telegram')) {
        return '/src/assets/images/platform_logos/telegram.svg';
      } else if (name.includes('Discord')) {
        return '/src/assets/images/platform_logos/discord.svg';
      } else if (name.includes('Slack')) {
        return '/src/assets/images/platform_logos/slack.svg';
      } else if (name.includes('kook')) {
        return '/src/assets/images/platform_logos/kook.png';
      } else if (name.includes('vocechat')) {
        return '/src/assets/images/platform_logos/vocechat.png';
      }
    },

    getTutorialLink(platform_type) {
      let tutorial_map = {
        "qq_official_webhook": "https://astrbot.app/deploy/platform/qqofficial/webhook.html",
        "qq_official": "https://astrbot.app/deploy/platform/qqofficial/websockets.html",
        "aiocqhttp": "https://astrbot.app/deploy/platform/aiocqhttp/napcat.html",
        "wecom": "https://astrbot.app/deploy/platform/wecom.html",
        "gewechat": "https://astrbot.app/deploy/platform/wechat/gewechat.html",
        "lark": "https://astrbot.app/deploy/platform/lark.html",
        "telegram": "https://astrbot.app/deploy/platform/telegram.html",
        "dingtalk": "https://astrbot.app/deploy/platform/dingtalk.html",
        "wechatpadpro": "https://astrbot.app/deploy/platform/wechat/wechatpadpro.html",
        "weixin_official_account": "https://astrbot.app/deploy/platform/weixin-official-account.html",
        "discord": "https://astrbot.app/deploy/platform/discord.html",
        "slack": "https://astrbot.app/deploy/platform/slack.html",
        "kook": "https://astrbot.app/deploy/platform/kook.html",
        "vocechat": "https://astrbot.app/deploy/platform/vocechat.html",
      }
      return tutorial_map[platform_type] || "https://docs.astrbot.app";
    },

    getPlatformDescription(template, name) {
      // special judge for community platforms
      if (name.includes('vocechat')) {
        return "由 @HikariFroya 提供。";
      } else if (name.includes('kook')) {
        return "由 @wuyan1003 提供。"
      }
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

    // 添加一个新方法来选择平台模板
    selectPlatformTemplate(name) {
      this.newSelectedPlatformName = name;
      this.showPlatformCfg = true;
      this.updatingMode = false;
      this.newSelectedPlatformConfig = JSON.parse(JSON.stringify(
        this.metadata['platform_group']?.metadata?.platform?.config_template[name] || {}
      ));
      this.showAddPlatformDialog = false;
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
        axios.post('/api/config/platform/update', {
          id: this.newSelectedPlatformName,
          config: this.newSelectedPlatformConfig
        }).then((res) => {
          this.loading = false;
          this.showPlatformCfg = false;
          this.getConfig();
          this.$refs.wfr.check();
          this.showSuccess(res.data.message || this.messages.updateSuccess);
        }).catch((err) => {
          this.loading = false;
          this.showError(err.response?.data?.message || err.message);
        });
        this.updatingMode = false;
      } else {
        this.savePlatform();
      }
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

    deletePlatform(platform) {
      if (confirm(`${this.messages.deleteConfirm} ${platform.id}?`)) {
        axios.post('/api/config/platform/delete', { id: platform.id }).then((res) => {
          this.getConfig();
          this.$refs.wfr.check();
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
        this.$refs.wfr.check();
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

.platform-selection-dialog .v-card-title {
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
}

.platform-card {
  transition: all 0.3s ease;
  height: 100%;
  cursor: pointer;
  overflow: hidden;
  position: relative;
}

.platform-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 25px 0 rgba(0, 0, 0, 0.05);
  border-color: var(--v-primary-base);
}

.platform-card-content {
  display: flex;
  align-items: center;
  height: 100px;
  padding: 16px;
  position: relative;
  z-index: 2;
}

.platform-card-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.platform-card-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
  padding: 0;
}

.platform-card-description {
  padding: 0;
  margin: 0;
}

.platform-card-logo {
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

.platform-logo-img {
  max-width: 60px;
  max-height: 60px;
  opacity: 0.6;
  object-fit: contain;
}

.platform-logo-fallback {
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
</style>