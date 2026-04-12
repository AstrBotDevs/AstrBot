<template>

  <div style="display: flex; flex-direction: column; align-items: center;">
    <div v-if="selectedConfigID || isSystemConfig" class="mt-4 config-panel"
      style="display: flex; flex-direction: column; align-items: start;">

      <div class="config-toolbar d-flex flex-row pr-4"
        style="margin-bottom: 16px; align-items: center; gap: 12px; width: 100%; justify-content: space-between;">
        <div class="config-toolbar-controls d-flex flex-row align-center" style="gap: 12px;">
          <v-select class="config-select" style="min-width: 130px;" :model-value="selectedConfigID" :items="configSelectItems" item-title="name" :disabled="initialConfigId !== null"
            v-if="!isSystemConfig" item-value="id" :label="tm('configSelection.selectConfig')" hide-details density="compact" rounded="md"
            variant="outlined" @update:model-value="onConfigSelect">
          </v-select>
          <v-text-field
            class="config-search-input"
            :model-value="configSearchKeyword"
            @update:model-value="onConfigSearchInput"
            prepend-inner-icon="mdi-magnify"
            :label="tm('search.placeholder')"
            clearable
            hide-details
            density="compact"
            rounded="md"
            variant="outlined"
            style="min-width: 280px;"
          />
          <!-- <a style="color: inherit;" href="https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6" target="_blank"><v-btn icon="mdi-help-circle" size="small" variant="plain"></v-btn></a> -->

        </div>
      </div>
      <v-slide-y-transition>
        <div v-if="fetched && hasUnsavedChanges" class="unsaved-changes-banner-wrap">
          <v-banner
            icon="$warning"
            lines="one"
            class="unsaved-changes-banner my-4"
          >
            {{ tm('messages.unsavedChangesNotice') }}
          </v-banner>
        </div>
      </v-slide-y-transition>
      <!-- <v-progress-linear v-if="!fetched" indeterminate color="primary"></v-progress-linear> -->

      <v-slide-y-transition mode="out-in">
        <div v-if="(selectedConfigID || isSystemConfig) && fetched" :key="configContentKey" class="config-content" style="width: 100%;">
          <!-- 可视化编辑 -->
          <AstrBotCoreConfigWrapper
            :metadata="metadata"
            :config_data="config_data"
            :search-keyword="configSearchKeyword"
          />
        </div>
      </v-slide-y-transition>

      <!-- 浮动按钮放在 transition 外部 -->
      <template v-if="(selectedConfigID || isSystemConfig) && fetched">
        <v-tooltip :text="tm('actions.save')" location="left">
          <template v-slot:activator="{ props }">
            <v-btn v-bind="props" icon="mdi-content-save" size="x-large" style="position: fixed; right: 52px; bottom: 52px;"
              color="darkprimary" @click="updateConfig">
            </v-btn>
          </template>
        </v-tooltip>

        <v-tooltip :text="tm('codeEditor.title')" location="left">
          <template v-slot:activator="{ props }">
            <v-btn v-bind="props" icon="mdi-code-json" size="x-large" style="position: fixed; right: 52px; bottom: 124px;" color="primary"
              @click="configToString(); codeEditorDialog = true">
            </v-btn>
          </template>
        </v-tooltip>

        <v-tooltip text="测试当前配置" location="left" v-if="!isSystemConfig">
          <template v-slot:activator="{ props }">
            <v-btn v-bind="props" icon="mdi-chat-processing" size="x-large"
              style="position: fixed; right: 52px; bottom: 196px;" color="secondary"
              @click="openTestChat">
            </v-btn>
          </template>
        </v-tooltip>
      </template>

    </div>
  </div>


  <!-- Full Screen Editor Dialog -->
  <v-dialog v-model="codeEditorDialog" fullscreen transition="dialog-bottom-transition" scrollable>
    <v-card>
      <v-toolbar color="primary" dark>
        <v-btn icon @click="codeEditorDialog = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
        <v-toolbar-title>{{ tm('codeEditor.title') }}</v-toolbar-title>
        <v-spacer></v-spacer>
        <v-toolbar-items style="display: flex; align-items: center;">
          <v-btn style="margin-left: 16px;" size="small" @click="configToString()">{{
            tm('editor.revertCode') }}</v-btn>
          <v-btn v-if="config_data_has_changed" style="margin-left: 16px;" size="small" @click="applyStrConfig()">{{
            tm('editor.applyConfig') }}</v-btn>
          <small style="margin-left: 16px;">💡 {{ tm('editor.applyTip') }}</small>
        </v-toolbar-items>
      </v-toolbar>
      <v-card-text class="pa-0">
        <VueMonacoEditor language="json" theme="vs-dark" style="height: calc(100vh - 64px);"
          v-model:value="config_data_str">
        </VueMonacoEditor>
      </v-card-text>
    </v-card>
  </v-dialog>

  <!-- Config Management Dialog -->
  <v-dialog v-model="configManageDialog" max-width="800px">
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span class="text-h4">{{ tm('configManagement.title') }}</span>
        <v-btn icon="mdi-close" variant="text" @click="configManageDialog = false"></v-btn>
      </v-card-title>

      <v-card-text>
        <small>{{ tm('configManagement.description') }}</small>
        <div class="mt-6 mb-4">
          <v-btn prepend-icon="mdi-plus" @click="startCreateConfig" variant="tonal" color="primary">
            {{ tm('configManagement.newConfig') }}
          </v-btn>
        </div>

        <!-- Config List -->
        <v-list lines="two">
          <v-list-item v-for="config in configInfoList" :key="config.id" :title="config.name">
            <template v-slot:append>
              <div class="d-flex align-center" style="gap: 8px;">
                <v-btn icon="mdi-content-copy" size="small" variant="text" color="primary"
                  @click="startCopyConfig(config)"></v-btn>
                <v-btn icon="mdi-pencil" size="small" variant="text" color="warning"
                  v-if="config.id !== 'default'"
                  @click="startEditConfig(config)"></v-btn>
                <v-btn icon="mdi-delete" size="small" variant="text" color="error"
                  v-if="config.id !== 'default'"
                  @click="confirmDeleteConfig(config)"></v-btn>
              </div>
            </template>
          </v-list-item>
        </v-list>

        <!-- Create/Edit Form -->
        <v-divider v-if="showConfigForm" class="my-6"></v-divider>

        <div v-if="showConfigForm">
          <h3 class="mb-4">{{ configFormTitle }}</h3>

          <h4>{{ tm('configManagement.configName') }}</h4>

          <v-text-field v-model="configFormData.name" :label="tm('configManagement.fillConfigName')" variant="outlined" class="mt-4 mb-4"
            hide-details></v-text-field>

          <div class="d-flex justify-end mt-4" style="gap: 8px;">
            <v-btn variant="text" @click="cancelConfigForm">{{ tm('buttons.cancel') }}</v-btn>
            <v-btn color="primary" @click="saveConfigForm"
              :disabled="isConfigFormSaveDisabled">
              {{ isEditingConfig ? tm('buttons.update') : tm('buttons.create') }}
            </v-btn>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>

  <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack">
    {{ save_message }}
  </v-snackbar>

  <WaitingForRestart ref="wfr"></WaitingForRestart>

  <!-- 测试聊天抽屉 -->
  <v-overlay
    v-model="testChatDrawer"
    class="test-chat-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @click:outside="closeTestChat"
  >
    <v-card class="test-chat-card" elevation="12">
      <div class="test-chat-header">
        <div>
          <span class="text-h6">测试配置</span>
          <div v-if="selectedConfigInfo.name" class="text-caption text-grey">
            {{ selectedConfigInfo.name }} ({{ testConfigId }})
          </div>
        </div>
        <v-btn icon variant="text" @click="closeTestChat">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </div>
      <v-divider></v-divider>
      <div class="test-chat-content">
        <StandaloneChat v-if="testChatDrawer" :configId="testConfigId" />
      </div>
    </v-card>
  </v-overlay>

  <!-- 未保存更改确认弹窗 -->
  <UnsavedChangesConfirmDialog ref="unsavedChangesDialog" />

</template>


<script>
import axios from 'axios';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import StandaloneChat from '@/components/chat/StandaloneChat.vue';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { restartAstrBot as restartAstrBotRuntime } from '@/utils/restartAstrBot';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog
} from '@/utils/confirmDialog';
import UnsavedChangesConfirmDialog from '@/components/config/UnsavedChangesConfirmDialog.vue';
import { normalizeTextInput } from '@/utils/inputValue';

export default {
  name: 'ConfigPage',
  components: {
    AstrBotCoreConfigWrapper,
    VueMonacoEditor,
    WaitingForRestart,
    StandaloneChat,
    UnsavedChangesConfirmDialog
  },
  props: {
    initialConfigId: {
      type: String,
      default: null
    }
  },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n('features/config');
    const confirmDialog = useConfirmDialog();

    return {
      t,
      tm,
      confirmDialog
    };
  },

// 检查未保存的更改
  async beforeRouteLeave(to, from, next) {
    if (this.hasUnsavedChanges) {
      const confirmed = await this.$refs.unsavedChangesDialog?.open({
        title: this.tm('unsavedChangesWarning.dialogTitle'),
        message: this.tm('unsavedChangesWarning.leavePage'),
        confirmHint: `${this.tm('unsavedChangesWarning.options.saveAndSwitch')}:${this.tm('unsavedChangesWarning.options.confirm')}`,
        cancelHint: `${this.tm('unsavedChangesWarning.options.discardAndSwitch')}:${this.tm('unsavedChangesWarning.options.cancel')}`,
        closeHint: `${this.tm('unsavedChangesWarning.options.closeCard')}:"x"`
      });
      // 关闭弹窗不跳转
      if (confirmed === 'close') {
        next(false);
      } else if (confirmed) {
        const result = await this.updateConfig();
        if (this.isSystemConfig) {
          next(false);
        } else {
          if (result?.success) {
            await new Promise(resolve => setTimeout(resolve, 800));
            next();
          } else {
            next(false);
          }
        }
      } else {
        this.hasUnsavedChanges = false;
        next();
      }
    } else {
      next();
    }
  },

  computed: {
    messages() {
      return {
        loadError: this.tm('messages.loadError'),
        saveSuccess: this.tm('messages.saveSuccess'),
        saveError: this.tm('messages.saveError'),
        configApplied: this.tm('messages.configApplied'),
        configApplyError: this.tm('messages.configApplyError')
      };
    },
    // 检查配置是否变化
    configHasChanges() {
      if (!this.originalConfigData || !this.config_data) return false;
      return JSON.stringify(this.originalConfigData) !== JSON.stringify(this.config_data);
    },
    configInfoNameList() {
      return this.configInfoList.map(info => info.name);
    },
    selectedConfigInfo() {
      return this.configInfoList.find(info => info.id === this.selectedConfigID) || {};
    },
    configFormTitle() {
      if (this.isEditingConfig) {
        return this.tm('configManagement.editConfig');
      }
      if (this.isCopyingConfig) {
        return this.tm('configManagement.copyConfig');
      }
      return this.tm('configManagement.newConfig');
    },
    isConfigFormSaveDisabled() {
      const isNameEmpty = !this.normalizeConfigName(this.configFormData.name);
      return isNameEmpty || (this.isCopyingConfig && !this.copySourceConfigId);
    },
    configSelectItems() {
      const items = [...this.configInfoList];
      items.push({
        id: '_%manage%_',
        name: this.tm('configManagement.manageConfigs'),
        umop: []
      });
      return items;
    },
    hasUnsavedChanges() {
      if (!this.fetched) {
        return false;
      }
      return this.getConfigSnapshot(this.config_data) !== this.lastSavedConfigSnapshot;
    }
  },
  watch: {
    config_data_str(val) {
      this.config_data_has_changed = true;
    },
    config_data: {
      deep: true,
      handler() {
        if (this.fetched) {
          this.hasUnsavedChanges = this.configHasChanges;
        }
      }
    },
    async '$route.fullPath'(newVal) {
      await this.syncConfigTypeFromHash(newVal);
    },
    initialConfigId(newVal) {
      if (!newVal) {
        return;
      }
      if (this.selectedConfigID !== newVal) {
        this.getConfigInfoList(newVal);
      }
    }
  },
  data() {
    return {
      codeEditorDialog: false,
      configManageDialog: false,
      showConfigForm: false,
      isEditingConfig: false,
      isCopyingConfig: false,
      config_data_has_changed: false,
      config_data_str: "",
      config_data: {
        config: {}
      },
      fetched: false,
      metadata: {},
      save_message_snack: false,
      save_message: "",
      save_message_success: "",
  configContentKey: 0,
      lastSavedConfigSnapshot: '',

      // 配置类型切换
      configType: 'normal', // 'normal' 或 'system'
      configSearchKeyword: '',

      // 系统配置开关
      isSystemConfig: false,

      // 多配置文件管理
      selectedConfigID: null, // 用于存储当前选中的配置项信息
      currentConfigId: null, // 跟踪当前正在编辑的配置id
      configInfoList: [],
      configFormData: {
        name: '',
      },
      editingConfigId: null,
      copySourceConfigId: '',

      // 测试聊天
      testChatDrawer: false,
      testConfigId: null,

      // 未保存的更改状态
      hasUnsavedChanges: false,
      // 存储原始配置
      originalConfigData: null,
    }
  },
  mounted() {
    const hashConfigType = this.extractConfigTypeFromHash(
      this.$route?.fullPath || ''
    );
    this.configType = hashConfigType || 'normal';
    this.isSystemConfig = this.configType === 'system';

    const targetConfigId = this.initialConfigId || 'default';
    this.getConfigInfoList(targetConfigId);
    // 初始化配置类型状态
    this.configType = this.isSystemConfig ? 'system' : 'normal';
    
    // 监听语言切换事件，重新加载配置以获取插件的 i18n 数据
    window.addEventListener('astrbot-locale-changed', this.handleLocaleChange);

    // 保存初始配置
    this.$watch('config_data', (newVal) => {
      if (!this.originalConfigData && newVal) {
        this.originalConfigData = JSON.parse(JSON.stringify(newVal));
      }
    }, { immediate: false, deep: true });
  },

  beforeUnmount() {
    // 移除语言切换事件监听器
    window.removeEventListener('astrbot-locale-changed', this.handleLocaleChange);
  },
  methods: {
    // 处理语言切换事件，重新加载配置以获取插件的 i18n 数据
    handleLocaleChange() {
      // 重新加载当前配置
      if (this.selectedConfigID) {
        this.getConfig(this.selectedConfigID);
      } else if (this.isSystemConfig) {
        this.getConfig();
      }
    },

  },
  methods: {
    onConfigSearchInput(value) {
      this.configSearchKeyword = normalizeTextInput(value);
    },
    extractConfigTypeFromHash(hash) {
      const rawHash = String(hash || '');
      const lastHashIndex = rawHash.lastIndexOf('#');
      if (lastHashIndex === -1) {
        return null;
      }
      const cleanHash = rawHash.slice(lastHashIndex + 1);
      return cleanHash === 'system' || cleanHash === 'normal' ? cleanHash : null;
    },
    async syncConfigTypeFromHash(hash) {
      const configType = this.extractConfigTypeFromHash(hash);
      if (!configType || configType === this.configType) {
        return false;
      }

      this.configType = configType;
      await this.onConfigTypeToggle();
      return true;
    },
    getConfigInfoList(abconf_id) {
      // 获取配置列表
      axios.get('/api/config/abconfs').then((res) => {
        this.configInfoList = res.data.data.info_list;

        if (abconf_id) {
          let matched = false;
          for (let i = 0; i < this.configInfoList.length; i++) {
            if (this.configInfoList[i].id === abconf_id) {
              this.selectedConfigID = this.configInfoList[i].id;
              this.currentConfigId = this.configInfoList[i].id;
              this.getConfig(abconf_id);
              matched = true;
              break;
            }
          }

          if (!matched && this.configInfoList.length) {
            // 当找不到目标配置时，默认展示列表中的第一个配置
            this.selectedConfigID = this.configInfoList[0].id;
            this.currentConfigId = this.configInfoList[0].id;
            this.getConfig(this.selectedConfigID);
          }
        }
      }).catch((err) => {
        this.save_message = this.messages.loadError;
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    getConfig(abconf_id) {
      this.fetched = false
      const params = {};

      if (this.isSystemConfig) {
        params.system_config = '1';
      } else {
        params.id = abconf_id || this.selectedConfigID;
      }

      axios.get('/api/config/abconf', {
        params: params
      }).then((res) => {
        this.config_data = res.data.data.config;
        this.lastSavedConfigSnapshot = this.getConfigSnapshot(this.config_data);
        this.fetched = true
        this.metadata = res.data.data.metadata;
        this.configContentKey += 1;
        // 获取配置后更新
          this.$nextTick(() => {
            this.originalConfigData = JSON.parse(JSON.stringify(this.config_data));
            this.hasUnsavedChanges = false;
            if (!this.isSystemConfig) {
              this.currentConfigId = abconf_id || this.selectedConfigID;
            }
          });
      }).catch((err) => {
        this.save_message = this.messages.loadError;
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    updateConfig() {
      if (!this.fetched) return;

      const postData = {
        config: JSON.parse(JSON.stringify(this.config_data)),
      };

      if (this.isSystemConfig) {
        postData.conf_id = 'default';
      } else {
        postData.conf_id = this.selectedConfigID;
      }

      return axios.post('/api/config/astrbot/update', postData).then((res) => {
        if (res.data.status === "ok") {
          this.lastSavedConfigSnapshot = this.getConfigSnapshot(this.config_data);
          this.save_message = res.data.message || this.messages.saveSuccess;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.onConfigSaved();

          if (this.isSystemConfig) {
            restartAstrBotRuntime(this.$refs.wfr).catch(() => {})
          }
          return { success: true };
        } else {
          this.save_message = res.data.message || this.messages.saveError;
          this.save_message_snack = true;
          this.save_message_success = "error";
          return { success: false };
        }
      }).catch((err) => {
        this.save_message = this.messages.saveError;
        this.save_message_snack = true;
        this.save_message_success = "error";
        return { success: false };
      });
    },
    // 重置未保存状态
    onConfigSaved() {
      this.hasUnsavedChanges = false;
      this.originalConfigData = JSON.parse(JSON.stringify(this.config_data));
    },

    configToString() {
      this.config_data_str = JSON.stringify(this.config_data, null, 2);
      this.config_data_has_changed = false;
    },
    applyStrConfig() {
      try {
        this.config_data = JSON.parse(this.config_data_str);
        this.config_data_has_changed = false;
        this.save_message_success = "success";
        this.save_message = this.messages.configApplied;
        this.save_message_snack = true;
      } catch (e) {
        this.save_message_success = "error";
        this.save_message = this.messages.configApplyError;
        this.save_message_snack = true;
      }
    },
    createNewConfig(configName) {
      axios.post('/api/config/abconf/new', {
        name: configName
      }).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.getConfigInfoList(res.data.data.conf_id);
          this.cancelConfigForm();
        } else {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "error";
        }
      }).catch((err) => {
        console.error(err);
        this.save_message = this.tm('configManagement.createFailed');
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    normalizeConfigName(name) {
      return typeof name === 'string' ? name.trim() : '';
    },
    hasDuplicateConfigName(name, excludeId = null) {
      const normalizedName = this.normalizeConfigName(name);
      if (!normalizedName) {
        return false;
      }
      return this.configInfoList.some((config) => {
        if (!config || !config.name) {
          return false;
        }
        if (excludeId && config.id === excludeId) {
          return false;
        }
        return this.normalizeConfigName(config.name) === normalizedName;
      });
    },
    async onConfigSelect(value) {
      if (value === '_%manage%_') {
        this.configManageDialog = true;
        // 重置选择到之前的值
        this.$nextTick(() => {
          this.selectedConfigID = this.selectedConfigInfo.id || 'default';
          this.getConfig(this.selectedConfigID);
        });
      } else {
        // 检查是否有未保存的更改
        if (this.hasUnsavedChanges) {
          // 获取之前正在编辑的配置id
          const prevConfigId = this.isSystemConfig ? 'default' : (this.currentConfigId || this.selectedConfigID || 'default');
          const message = this.tm('unsavedChangesWarning.switchConfig');
          const saveAndSwitch = await this.$refs.unsavedChangesDialog?.open({
            title: this.tm('unsavedChangesWarning.dialogTitle'),
            message: message,
            confirmHint: `${this.tm('unsavedChangesWarning.options.saveAndSwitch')}:${this.tm('unsavedChangesWarning.options.confirm')}`,
            cancelHint: `${this.tm('unsavedChangesWarning.options.discardAndSwitch')}:${this.tm('unsavedChangesWarning.options.cancel')}`,
            closeHint: `${this.tm('unsavedChangesWarning.options.closeCard')}:"x"`
          });
          // 关闭弹窗不切换
          if (saveAndSwitch === 'close') {
            return;
          }
          if (saveAndSwitch) {
            // 设置临时变量保存切换后的id
            const currentSelectedId = this.selectedConfigID;
            // 把id设置回切换前的用于保存上一次的配置，保存完后恢复id为切换后的
            this.selectedConfigID = prevConfigId;
            const result = await this.updateConfig();
            this.selectedConfigID = currentSelectedId;
            if (result?.success) {
              this.selectedConfigID = value;
              this.getConfig(value);
            }
            return;
          } else {
            // 取消保存并切换配置
            this.selectedConfigID = value;
            this.getConfig(value);
          }
        } else {
          // 无未保存更改直接切换
          this.selectedConfigID = value;
          this.getConfig(value);
        }
      }
    },
    setConfigFormState({ mode = 'create', config = null, visible = true } = {}) {
      this.showConfigForm = visible;
      this.isEditingConfig = mode === 'edit';
      this.isCopyingConfig = mode === 'copy';
      this.editingConfigId = this.isEditingConfig && config ? config.id : null;
      this.copySourceConfigId = this.isCopyingConfig && config ? config.id : '';

      let name = '';
      if (this.isEditingConfig && config) {
        name = config.name || '';
      } else if (this.isCopyingConfig && config) {
        name = `${config.name || ''}-copy`;
      }
      this.configFormData = { name };
    },
    startCreateConfig() {
      this.setConfigFormState({ mode: 'create' });
    },
    startEditConfig(config) {
      this.setConfigFormState({ mode: 'edit', config });
    },
    startCopyConfig(config) {
      this.setConfigFormState({ mode: 'copy', config });
    },
    cancelConfigForm() {
      this.setConfigFormState({ visible: false });
    },
    saveConfigForm() {
      const normalizedName = this.normalizeConfigName(this.configFormData.name);
      if (!normalizedName) {
        this.save_message = this.tm('configManagement.pleaseEnterName');
        this.save_message_snack = true;
        this.save_message_success = "error";
        return;
      }
      const excludeId = this.isEditingConfig ? this.editingConfigId : null;
      if (this.hasDuplicateConfigName(normalizedName, excludeId)) {
        this.save_message = this.tm('configManagement.nameExists');
        this.save_message_snack = true;
        this.save_message_success = "error";
        return;
      }
      this.configFormData.name = normalizedName;
      if (this.isEditingConfig) {
        this.updateConfigInfo(normalizedName);
      } else if (this.isCopyingConfig) {
        this.copyConfig(normalizedName);
      } else {
        this.createNewConfig(normalizedName);
      }
    },
    copyConfig(configName) {
      axios.get('/api/config/abconf', {
        params: { id: this.copySourceConfigId }
      }).then((res) => {
        const sourceConfig = res.data?.data?.config;
        if (!sourceConfig) {
          this.save_message = this.tm('configManagement.copyFailed');
          this.save_message_snack = true;
          this.save_message_success = "error";
          return;
        }
        return axios.post('/api/config/abconf/new', {
          name: configName,
          config: sourceConfig
        });
      }).then((res) => {
        if (!res) return;
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.getConfigInfoList(res.data.data.conf_id);
          this.cancelConfigForm();
        } else {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "error";
        }
      }).catch((err) => {
        console.error(err);
        this.save_message = err?.response?.data?.message || this.tm('configManagement.copyFailed');
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    async confirmDeleteConfig(config) {
      const message = this.tm('configManagement.confirmDelete').replace('{name}', config.name);
      if (await askForConfirmationDialog(message, this.confirmDialog)) {
        this.deleteConfig(config.id);
      }
    },
    deleteConfig(configId) {
      axios.post('/api/config/abconf/delete', {
        id: configId
      }).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.cancelConfigForm();
          // 删除成功后，更新配置列表
          this.getConfigInfoList("default");
        } else {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "error";
        }
      }).catch((err) => {
        console.error(err);
        this.save_message = this.tm('configManagement.deleteFailed');
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    updateConfigInfo(configName) {
      axios.post('/api/config/abconf/update', {
        id: this.editingConfigId,
        name: configName
      }).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.getConfigInfoList(this.editingConfigId);
          this.cancelConfigForm();
        } else {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "error";
        }
      }).catch((err) => {
        console.error(err);
        this.save_message = this.tm('configManagement.updateFailed');
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    async onConfigTypeToggle() {
      // 检查是否有未保存的更改
      if (this.hasUnsavedChanges) {
        const message = this.tm('unsavedChangesWarning.leavePage');
        const saveAndSwitch = await this.$refs.unsavedChangesDialog?.open({
          title: this.tm('unsavedChangesWarning.dialogTitle'),
          message: message,
          confirmHint: `${this.tm('unsavedChangesWarning.options.saveAndSwitch')}:${this.tm('unsavedChangesWarning.options.confirm')}`,
          cancelHint: `${this.tm('unsavedChangesWarning.options.discardAndSwitch')}:${this.tm('unsavedChangesWarning.options.cancel')}`,
          closeHint: `${this.tm('unsavedChangesWarning.options.closeCard')}:"x"`
        });
        // 关闭弹窗
        if (saveAndSwitch === 'close') {
          // 恢复路由
          const originalHash = this.isSystemConfig ? '#system' : '#normal';
          this.$router.replace('/config' + originalHash);
          this.configType = this.isSystemConfig ? 'system' : 'normal';
          return;
        }
        if (saveAndSwitch) {
          await this.updateConfig();
          // 系统配置保存后不跳转
          if (this.isSystemConfig) {
            this.$router.replace('/config#system');
            return;
          }
        }
      }
      this.isSystemConfig = this.configType === 'system';
      this.fetched = false; // 重置加载状态

      if (this.isSystemConfig) {
        // 切换到系统配置
        this.getConfig();
      } else {
        // 切换回普通配置，如果有选中的配置文件则加载，否则加载default
        if (this.selectedConfigID) {
          this.getConfig(this.selectedConfigID);
        } else {
          this.getConfigInfoList("default");
        }
      }
    },
    onSystemConfigToggle() {
      // 保持向后兼容性，更新 configType
      this.configType = this.isSystemConfig ? 'system' : 'normal';

      this.onConfigTypeToggle();
    },
    openTestChat() {
      if (!this.selectedConfigID) {
        this.save_message = "请先选择一个配置文件";
        this.save_message_snack = true;
        this.save_message_success = "warning";
        return;
      }
      this.testConfigId = this.selectedConfigID;
      this.testChatDrawer = true;
    },
    closeTestChat() {
      this.testChatDrawer = false;
      this.testConfigId = null;
    },
    getConfigSnapshot(config) {
      return JSON.stringify(config ?? {});
    }
  },
}

</script>

<style>
.v-tab {
  text-transform: none !important;
}

.unsaved-changes-banner {
  border-radius: 8px;
}

.v-theme--light .unsaved-changes-banner {
  background-color: #f1f4f9 !important;
}

.v-theme--dark .unsaved-changes-banner {
  background-color: #2d2d2d !important;
}

.unsaved-changes-banner-wrap {
  position: sticky;
  top: calc(var(--v-layout-top, 64px));
  z-index: 20;
  width: 100%;
  margin-bottom: 6px;
}

/* 按钮切换样式优化 */
.v-btn-toggle .v-btn {
  transition: all 0.3s ease !important;
}

.v-btn-toggle .v-btn:not(.v-btn--active) {
  opacity: 0.7;
}

.v-btn-toggle .v-btn.v-btn--active {
  opacity: 1;
  font-weight: 600;
}

/* 冲突消息样式 */
.text-warning code {
  background-color: rgba(255, 193, 7, 0.1);
  color: #e65100;
  padding: 2px 4px;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 500;
}

.text-warning strong {
  color: #f57c00;
}

.text-warning small {
  color: #6c757d;
  font-style: italic;
}

@media (min-width: 768px) {
  .config-panel {
    width: 750px;
  }
}

@media (max-width: 767px) {
  .v-container {
    padding: 4px;
  }

  .config-panel {
    width: 100%;
  }

  .config-toolbar {
    padding-right: 0 !important;
  }

  .config-toolbar-controls {
    width: 100%;
    flex-wrap: wrap;
  }

  .config-select,
  .config-search-input {
    width: 100%;
    min-width: 0 !important;
  }
}

/* 测试聊天抽屉样式 */
.test-chat-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.test-chat-card {
  width: clamp(320px, 50vw, 720px);
  height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  margin: 16px;
}

.test-chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px 20px;
}

.test-chat-content {
  flex: 1;
  overflow: hidden;
  padding: 0;
  border-radius: 0 0 16px 16px;
}
</style>
