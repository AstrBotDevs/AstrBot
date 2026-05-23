<template>

  <div class="config-page-wrap">
    <div v-if="selectedConfigID || isSystemConfig" class="mt-4 config-panel">
      <div class="config-workbench" :class="{ 'config-workbench--system': isSystemConfig || !!initialConfigId }">
        <aside v-if="!isSystemConfig && !initialConfigId" class="config-sidebar">
          <ConfigProfileSidebar
            :configs="configInfoList"
            :selected-config-id="selectedConfigID"
            :bindings-by-config-id="configBindingsById"
            :disabled="initialConfigId !== null"
            @select="onConfigSelect"
            @manage="openConfigManageDialog"
            @manage-routes="openRouteManageDialog"
          />
        </aside>

        <section class="config-main">
          <div class="config-toolbar d-flex flex-row">
            <div class="config-toolbar-controls d-flex flex-row align-center">
              <div v-if="!isSystemConfig" class="config-current-title">
                <h2 class="config-current-title__name">
                  {{ selectedConfigInfo.name || selectedConfigID }}
                </h2>
                <div class="config-current-title__id text-caption text-medium-emphasis">
                  ID: {{ selectedConfigID }}
                </div>
              </div>
              <v-select
                v-if="!isSystemConfig && !initialConfigId"
                class="config-select config-select--mobile"
                :model-value="selectedConfigID"
                :items="configSelectItems"
                item-title="name"
                :disabled="initialConfigId !== null"
                item-value="id"
                :label="tm('configSelection.selectConfig')"
                hide-details
                density="compact"
                rounded="md"
                variant="outlined"
                @update:model-value="onConfigSelect"
              />
              <v-tooltip v-if="!isSystemConfig && !initialConfigId" :text="tm('configManagement.manageConfigs')" location="top">
                <template #activator="{ props: tooltipProps }">
                  <v-btn
                    v-bind="tooltipProps"
                    class="config-manage-mobile"
                    variant="text"
                    icon="mdi-cog"
                    :disabled="initialConfigId !== null"
                    @click="openConfigManageDialog"
                  />
                </template>
              </v-tooltip>
              <v-text-field
                class="config-search-input"
                v-model="configSearchKeyword"
                prepend-inner-icon="mdi-magnify"
                :label="tm('search.placeholder')"
                hide-details
                density="compact"
                rounded="md"
                variant="outlined"
              />
            </div>
          </div>

          <v-fade-transition>
            <div v-if="fetched && hasUnsavedChanges && !isLoadingConfig" class="unsaved-changes-banner-wrap">
              <v-banner
                icon="$warning"
                lines="one"
                class="unsaved-changes-banner my-4"
              >
                {{ tm('messages.unsavedChangesNotice') }}
              </v-banner>
            </div>
          </v-fade-transition>

          <v-fade-transition mode="out-in">
            <div v-if="(selectedConfigID || isSystemConfig) && fetched" :key="configContentKey" class="config-content">
              <AstrBotCoreConfigWrapper
                :metadata="metadata"
                :config_data="config_data"
                :search-keyword="configSearchKeyword"
              />

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
            </div>
          </v-fade-transition>
        </section>
      </div>
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

  <ConfigRouteManagerDialog
    v-model="routeManageDialog"
    :config-id="routeManageConfigId"
    :config-name="routeManageConfigName"
    :loading="routeManageLoading"
    :saving="routeManageSaving"
    :items="routeManageItems"
    :platform-type-map="routeManagePlatformTypeMap"
    @remove-route="removeRouteItem"
    @save="saveRouteManageDialog"
  />

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
import ConfigProfileSidebar from '@/components/config/ConfigProfileSidebar.vue';
import ConfigRouteManagerDialog from '@/components/config/ConfigRouteManagerDialog.vue';
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
    ConfigProfileSidebar,
    ConfigRouteManagerDialog,
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
      return [...this.configInfoList];
    }
  },
  watch: {
    config_data_str(val) {
      this.config_data_has_changed = true;
    },
    config_data: {
      deep: true,
      handler() {
        if (this.fetched && !this.isLoadingConfig) {
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
      routeManageDialog: false,
      routeManageLoading: false,
      routeManageSaving: false,
      routeManageConfigId: '',
      routeManageConfigName: '',
      routeManageItems: [],
      routeManagePlatformTypeMap: {},
      showConfigForm: false,
      isEditingConfig: false,
      isCopyingConfig: false,
      config_data_has_changed: false,
      config_data_str: "",
      config_data: {
        config: {}
      },
      isLoadingConfig: false,
      fetched: false,
      metadata: {},
      save_message_snack: false,
      save_message: "",
      save_message_success: "",
      configContentKey: 0,

      // 配置类型切换
      configType: 'normal', // 'normal' 或 'system'
      configSearchKeyword: '',

      // 系统配置开关
      isSystemConfig: false,

      // 多配置文件管理
      selectedConfigID: null, // 用于存储当前选中的配置项信息
      currentConfigId: null, // 跟踪当前正在编辑的配置id
      configInfoList: [],
      configBindingsById: {},
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
      if (this.selectedConfigID) {
        this.getConfig(this.selectedConfigID);
      } else if (this.isSystemConfig) {
        this.getConfig();
      }
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
    openConfigManageDialog() {
      this.configManageDialog = true;
    },
    parseUmop(umop) {
      const raw = String(umop || '');
      const parts = raw.split(':');
      if (parts.length < 3) {
        return {
          platformId: raw || '*',
          messageType: '*',
          sessionId: '*'
        };
      }
      return {
        platformId: parts[0] || '*',
        messageType: parts[1] || '*',
        sessionId: parts.slice(2).join(':') || '*'
      };
    },
    createRouteItem(umop) {
      const parsed = this.parseUmop(umop);
      return {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        platformId: parsed.platformId,
        umop
      };
    },
    isRouteEntryForConfig(umop, confId, targetConfigId) {
      if (String(confId || '') !== String(targetConfigId || '')) {
        return false;
      }
      const parsed = this.parseUmop(umop);
      return parsed.platformId !== 'webchat';
    },
    async openRouteManageDialog(payload) {
      const configId = payload?.configId;
      if (!configId) {
        return;
      }

      this.routeManageDialog = true;
      this.routeManageLoading = true;
      this.routeManageConfigId = configId;
      this.routeManageConfigName = this.configInfoList.find((item) => item.id === configId)?.name || configId;
      this.routeManageItems = [];
      this.routeManagePlatformTypeMap = {};

      try {
        const [routeRes, platformRes] = await Promise.all([
          axios.get('/api/config/umo_abconf_routes'),
          axios.get('/api/config/platform/list')
        ]);
        const routing = routeRes?.data?.data?.routing || {};
        const platforms = platformRes?.data?.data?.platforms || [];

        const typeMap = {};
        for (const platform of platforms) {
          const pid = String(platform?.id || '').trim();
          if (!pid) {
            continue;
          }
          typeMap[pid] = platform.platform_type || platform.type || pid;
        }
        this.routeManagePlatformTypeMap = typeMap;

        const matched = [];
        for (const [umop, conf] of Object.entries(routing)) {
          if (!this.isRouteEntryForConfig(umop, conf, configId)) {
            continue;
          }
          matched.push(this.createRouteItem(umop));
        }
        this.routeManageItems = matched.sort((a, b) => {
          const platformCompare = a.platformId.localeCompare(b.platformId);
          if (platformCompare !== 0) {
            return platformCompare;
          }
          return a.umop.localeCompare(b.umop);
        });
      } catch (err) {
        console.error('Failed to load routes for route manager:', err);
        this.save_message = this.tm('routeManager.loadFailed');
        this.save_message_snack = true;
        this.save_message_success = "error";
        this.routeManageItems = [];
      } finally {
        this.routeManageLoading = false;
      }
    },
    removeRouteItem(entryId) {
      this.routeManageItems = this.routeManageItems.filter((item) => item.id !== entryId);
    },
    async saveRouteManageDialog() {
      if (!this.routeManageConfigId) {
        return;
      }

      this.routeManageSaving = true;
      try {
        const res = await axios.get('/api/config/umo_abconf_routes');
        const routing = res?.data?.data?.routing || {};
        const entries = Object.entries(routing);
        const nonTargetEntries = [];
        const nonTargetUmopSet = new Set();
        let firstTargetIndex = -1;

        entries.forEach(([umop, confId], index) => {
          if (this.isRouteEntryForConfig(umop, confId, this.routeManageConfigId)) {
            if (firstTargetIndex === -1) {
              firstTargetIndex = index;
            }
            return;
          }
          nonTargetEntries.push([umop, confId]);
          nonTargetUmopSet.add(umop);
        });

        const targetEntries = [];
        for (const item of this.routeManageItems) {
          const umop = String(item.umop || '').trim();
          if (!umop) {
            continue;
          }
          if (nonTargetUmopSet.has(umop)) {
            this.save_message = this.tm('routeManager.routeOccupied', { umop });
            this.save_message_snack = true;
            this.save_message_success = "error";
            this.routeManageSaving = false;
            return;
          }
          targetEntries.push([umop, this.routeManageConfigId]);
        }

        const insertIndex = firstTargetIndex === -1 ? nonTargetEntries.length : Math.min(firstTargetIndex, nonTargetEntries.length);
        const mergedEntries = [
          ...nonTargetEntries.slice(0, insertIndex),
          ...targetEntries,
          ...nonTargetEntries.slice(insertIndex)
        ];
        const mergedRouting = Object.fromEntries(mergedEntries);

        await axios.post('/api/config/umo_abconf_route/update_all', {
          routing: mergedRouting
        });

        this.routeManageDialog = false;
        this.save_message = this.tm('routeManager.saveSuccess');
        this.save_message_snack = true;
        this.save_message_success = "success";
        await this.refreshConfigBindings();
      } catch (err) {
        console.error('Failed to save routes for route manager:', err);
        this.save_message = this.tm('routeManager.saveFailed');
        this.save_message_snack = true;
        this.save_message_success = "error";
      } finally {
        this.routeManageSaving = false;
      }
    },
    buildConfigBindingMap(routingTable, platforms) {
      const platformTypeMap = {};
      for (const platform of platforms || []) {
        if (!platform?.id) {
          continue;
        }
        platformTypeMap[platform.id] = platform.platform_type || platform.type || platform.id;
      }

      const grouped = {};
      for (const [umop, confId] of Object.entries(routingTable || {})) {
        const resolvedConfigId = String(confId || 'default');
        const parsed = this.parseUmop(umop);
        const platformId = parsed.platformId || '*';
        if (platformId === 'webchat') {
          continue;
        }

        if (!grouped[resolvedConfigId]) {
          grouped[resolvedConfigId] = {};
        }
        if (!grouped[resolvedConfigId][platformId]) {
          grouped[resolvedConfigId][platformId] = {
            platformId,
            platformType: platformTypeMap[platformId] || platformId,
            umops: []
          };
        }
        grouped[resolvedConfigId][platformId].umops.push(umop);
      }

      const bindingMap = {};
      for (const [confId, platformsById] of Object.entries(grouped)) {
        bindingMap[confId] = Object.values(platformsById).sort((a, b) => {
          return a.platformId.localeCompare(b.platformId);
        });
      }
      return bindingMap;
    },
    async refreshConfigBindings() {
      try {
        const [routesRes, platformsRes] = await Promise.all([
          axios.get('/api/config/umo_abconf_routes'),
          axios.get('/api/config/platform/list')
        ]);
        const routing = routesRes?.data?.data?.routing || {};
        const platforms = platformsRes?.data?.data?.platforms || [];
        this.configBindingsById = this.buildConfigBindingMap(routing, platforms);
      } catch (err) {
        console.error('Failed to load config bindings:', err);
        this.configBindingsById = {};
      }
    },
    getConfigInfoList(abconf_id) {
      // 获取配置列表
      axios.get('/api/config/abconfs').then((res) => {
        const infoList = Array.isArray(res.data?.data?.info_list) ? res.data.data.info_list : [];
        this.configInfoList = [...infoList].sort((a, b) => {
          if (a.id === 'default' && b.id !== 'default') {
            return -1;
          }
          if (a.id !== 'default' && b.id === 'default') {
            return 1;
          }
          return 0;
        });
        this.refreshConfigBindings();

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
        this.configBindingsById = {};
      });
    },
    getConfig(abconf_id) {
      this.isLoadingConfig = true;
      this.hasUnsavedChanges = false;
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
        this.metadata = res.data.data.metadata;
        this.originalConfigData = JSON.parse(JSON.stringify(this.config_data));
        this.hasUnsavedChanges = false;
        this.configContentKey += 1;
        if (!this.isSystemConfig) {
          this.currentConfigId = abconf_id || this.selectedConfigID;
        }
        this.fetched = true;
      }).catch((err) => {
        this.save_message = this.messages.loadError;
        this.save_message_snack = true;
        this.save_message_success = "error";
      }).finally(() => {
        this.isLoadingConfig = false;
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
      if (!value || value === this.selectedConfigID) {
        return;
      }
      if (this.hasUnsavedChanges) {
        const prevConfigId = this.isSystemConfig ? 'default' : (this.currentConfigId || this.selectedConfigID || 'default');
        const message = this.tm('unsavedChangesWarning.switchConfig');
        const saveAndSwitch = await this.$refs.unsavedChangesDialog?.open({
          title: this.tm('unsavedChangesWarning.dialogTitle'),
          message: message,
          confirmHint: `${this.tm('unsavedChangesWarning.options.saveAndSwitch')}:${this.tm('unsavedChangesWarning.options.confirm')}`,
          cancelHint: `${this.tm('unsavedChangesWarning.options.discardAndSwitch')}:${this.tm('unsavedChangesWarning.options.cancel')}`,
          closeHint: `${this.tm('unsavedChangesWarning.options.closeCard')}:"x"`
        });
        if (saveAndSwitch === 'close') {
          return;
        }
        if (saveAndSwitch) {
          const currentSelectedId = this.selectedConfigID;
          this.selectedConfigID = prevConfigId;
          const result = await this.updateConfig();
          this.selectedConfigID = currentSelectedId;
          if (result?.success) {
            this.selectedConfigID = value;
            this.getConfig(value);
          }
          return;
        }
        this.selectedConfigID = value;
        this.getConfig(value);
      } else {
        this.selectedConfigID = value;
        this.getConfig(value);
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
        this.refreshConfigBindings();
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
    }
  },
}

</script>

<style>
.v-tab {
  text-transform: none !important;
}

.config-page-wrap {
  display: flex;
  justify-content: center;
}

.config-panel {
  width: min(1160px, calc(100vw - 48px));
}

.config-workbench {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.config-workbench--system {
  grid-template-columns: minmax(0, 1fr);
}

.config-sidebar {
  position: sticky;
  top: calc(var(--v-layout-top, 64px) + 16px);
}

.config-main {
  min-width: 0;
}

.config-current-title {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
}

.config-current-title__name {
  font-family: inherit;
  font-size: 1.25rem;
  font-weight: 700;
  line-height: 1.2;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.config-current-title__id {
  line-height: 1.2;
}

.config-toolbar {
  margin-bottom: 16px;
  align-items: center;
  width: 100%;
}

.config-toolbar-controls {
  width: 100%;
  gap: 12px;
}

.config-search-input {
  min-width: 180px;
  max-width: 300px;
  width: 100%;
  margin-left: auto;
}

.config-select--mobile,
.config-manage-mobile {
  display: none;
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

@media (max-width: 959px) {
  .config-workbench {
    grid-template-columns: minmax(0, 1fr);
  }

  .config-sidebar {
    display: none;
  }

  .config-select--mobile,
  .config-manage-mobile {
    display: inline-flex;
  }

  .config-select--mobile {
    min-width: 180px;
    max-width: 280px;
  }
}

@media (max-width: 767px) {
  .config-panel {
    width: 100%;
    margin-top: 0 !important;
  }

  .config-page-wrap {
    padding: 0 8px;
  }

  .config-toolbar-controls {
    flex-wrap: wrap;
  }

  .config-select--mobile,
  .config-search-input {
    width: 100%;
    max-width: 100%;
    min-width: 0;
  }

  .config-manage-mobile {
    width: auto;
    max-width: none;
    min-width: auto;
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
