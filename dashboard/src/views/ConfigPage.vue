<template>
  <div style="display: flex; flex-direction: column; align-items: center">
    <div
      v-if="selectedConfigID || isSystemConfig"
      class="mt-4 config-panel"
      style="display: flex; flex-direction: column; align-items: start"
    >
      <div
        class="config-toolbar d-flex flex-row pr-4"
        style="
          margin-bottom: 16px;
          align-items: center;
          gap: 12px;
          width: 100%;
          justify-content: space-between;
        "
      >
        <div
          class="config-toolbar-controls d-flex flex-row align-center"
          style="gap: 12px"
        >
          <v-select
            v-if="!isSystemConfig"
            class="config-select"
            style="min-width: 130px"
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
          <v-text-field
            class="config-search-input"
            :model-value="configSearchKeyword"
            prepend-inner-icon="mdi-magnify"
            :label="tm('search.placeholder')"
            clearable
            hide-details
            density="compact"
            rounded="md"
            variant="outlined"
            style="min-width: 280px"
            @update:model-value="onConfigSearchInput"
          />
          <v-tooltip :text="tm('actions.refresh')" location="bottom">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-refresh"
                variant="text"
                color="primary"
                :loading="refreshingConfig"
                :disabled="!fetched && !selectedConfigID && !isSystemConfig"
                @click="refreshConfigFromFile"
              />
            </template>
          </v-tooltip>
          <!-- <a style="color: inherit;" href="https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6" target="_blank"><v-btn icon="mdi-help-circle" size="small" variant="plain"></v-btn></a> -->
        </div>
      </div>
      <v-slide-y-transition>
        <div
          v-if="fetched && hasUnsavedChanges"
          class="unsaved-changes-banner-wrap"
        >
          <v-banner
            icon="$warning"
            lines="one"
            class="unsaved-changes-banner my-4"
          >
            {{ tm("messages.unsavedChangesNotice") }}
          </v-banner>
        </div>
      </v-slide-y-transition>
      <!-- <v-progress-linear v-if="!fetched" indeterminate color="primary"></v-progress-linear> -->

      <v-slide-y-transition mode="out-in">
        <div
          v-if="(selectedConfigID || isSystemConfig) && fetched"
          :key="configContentKey"
          class="config-content"
          style="width: 100%"
        >
          <!-- 可视化编辑 -->
          <AstrBotCoreConfigWrapper
            :metadata="metadata"
            :config_data="config_data"
            :search-keyword="configSearchKeyword"
          />

          <v-tooltip :text="tm('actions.save')" location="left">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-content-save"
                size="x-large"
                style="position: fixed; right: 52px; bottom: 52px"
                color="darkprimary"
                @click="updateConfig"
              />
            </template>
          </v-tooltip>

          <v-tooltip :text="tm('codeEditor.title')" location="left">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-code-json"
                size="x-large"
                style="position: fixed; right: 52px; bottom: 124px"
                color="primary"
                @click="
                  configToString();
                  codeEditorDialog = true;
                "
              />
            </template>
          </v-tooltip>

          <v-tooltip v-if="!isSystemConfig" text="测试当前配置" location="left">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-chat-processing"
                size="x-large"
                style="position: fixed; right: 52px; bottom: 196px"
                color="secondary"
                @click="openTestChat"
              />
            </template>
          </v-tooltip>
        </div>
      </v-slide-y-transition>
    </div>
  </div>

  <!-- Full Screen Editor Dialog -->
  <v-dialog
    v-model="codeEditorDialog"
    fullscreen
    transition="dialog-bottom-transition"
    scrollable
  >
    <div class="editor-reactor-container">
      <v-card class="editor-glass-card">
        <v-toolbar class="editor-toolbar" elevation="0">
          <v-btn icon @click="codeEditorDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
          <v-toolbar-title>{{ tm("codeEditor.title") }}</v-toolbar-title>
          <v-spacer />
          <v-toolbar-items style="display: flex; align-items: center">
            <v-btn
              style="margin-left: 16px"
              size="small"
              @click="configToString()"
            >
              {{ tm("editor.revertCode") }}
            </v-btn>
            <v-btn
              v-if="config_data_has_changed"
              style="margin-left: 16px"
              size="small"
              @click="applyStrConfig()"
            >
              {{ tm("editor.applyConfig") }}
            </v-btn>
            <small style="margin-left: 16px"
              >💡 {{ tm("editor.applyTip") }}</small
            >
          </v-toolbar-items>
        </v-toolbar>
        <v-card-text class="pa-0 editor-monaco-wrapper">
          <VueMonacoEditor
            v-model:value="config_data_str"
            language="json"
            theme="reactor-dark"
            style="height: calc(100vh - 64px)"
          />
        </v-card-text>
      </v-card>
    </div>
  </v-dialog>

  <!-- Config Management Dialog -->
  <v-dialog v-model="configManageDialog" max-width="800px">
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span class="text-h4">{{ tm("configManagement.title") }}</span>
        <v-btn
          icon="mdi-close"
          variant="text"
          @click="configManageDialog = false"
        />
      </v-card-title>

      <v-card-text>
        <small>{{ tm("configManagement.description") }}</small>
        <div class="mt-6 mb-4">
          <v-btn
            prepend-icon="mdi-plus"
            variant="tonal"
            color="primary"
            @click="startCreateConfig"
          >
            {{ tm("configManagement.newConfig") }}
          </v-btn>
        </div>

        <!-- Config List -->
        <v-list lines="two">
          <v-list-item
            v-for="config in configInfoList"
            :key="config.id"
            :title="config.name"
          >
            <template v-if="config.id !== 'default'" #append>
              <div class="d-flex align-center" style="gap: 8px">
                <v-btn
                  icon="mdi-pencil"
                  size="small"
                  variant="text"
                  color="warning"
                  @click="startEditConfig(config)"
                />
                <v-btn
                  icon="mdi-delete"
                  size="small"
                  variant="text"
                  color="error"
                  @click="confirmDeleteConfig(config)"
                />
              </div>
            </template>
          </v-list-item>
        </v-list>

        <!-- Create/Edit Form -->
        <v-divider v-if="showConfigForm" class="my-6" />

        <div v-if="showConfigForm">
          <h3 class="mb-4">
            {{
              isEditingConfig
                ? tm("configManagement.editConfig")
                : tm("configManagement.newConfig")
            }}
          </h3>

          <h4>{{ tm("configManagement.configName") }}</h4>

          <v-text-field
            v-model="configFormData.name"
            :label="tm('configManagement.fillConfigName')"
            variant="outlined"
            class="mt-4 mb-4"
            hide-details
          />

          <div class="d-flex justify-end mt-4" style="gap: 8px">
            <v-btn variant="text" @click="cancelConfigForm">
              {{ tm("buttons.cancel") }}
            </v-btn>
            <v-btn
              color="primary"
              :disabled="!configFormData.name"
              @click="saveConfigForm"
            >
              {{
                isEditingConfig ? tm("buttons.update") : tm("buttons.create")
              }}
            </v-btn>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>

  <v-snackbar
    v-model="save_message_snack"
    :timeout="3000"
    elevation="24"
    :color="save_message_success"
  >
    {{ save_message }}
  </v-snackbar>

  <WaitingForRestart ref="wfr" />

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
      <v-divider />
      <div class="test-chat-content">
        <StandaloneChat v-if="testChatDrawer" :config-id="testConfigId" />
      </div>
    </v-card>
  </v-overlay>

  <!-- 未保存更改确认弹窗 -->
  <UnsavedChangesConfirmDialog ref="unsavedChangesDialog" />
</template>

<script lang="ts">
import axios from "@/utils/request";
import AstrBotCoreConfigWrapper from "@/components/config/AstrBotCoreConfigWrapper.vue";
import WaitingForRestart from "@/components/shared/WaitingForRestart.vue";
import StandaloneChat from "@/components/chat/StandaloneChat.vue";
import { VueMonacoEditor } from "@guolao/vue-monaco-editor";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { restartAstrBot as restartAstrBotRuntime } from "@/utils/restartAstrBot";
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from "@/utils/confirmDialog";
import UnsavedChangesConfirmDialog from "@/components/config/UnsavedChangesConfirmDialog.vue";
import { normalizeTextInput } from "@/utils/inputValue";
import { defineReactorMonacoTheme } from "@/utils/monacoTheme";
import type { RouteLocationNormalized } from "vue-router";

interface ConfigInfoItem {
  id: string;
  name: string;
}

type WfrRef = {
  check: (initialStartTime?: number | null) => void | Promise<void>;
  stop?: () => void;
};

interface UnsavedChangesOptions {
  title?: string;
  message?: string;
  confirmHint?: string;
  cancelHint?: string;
  closeHint?: string;
}

export default {
  name: "ConfigPage",
  components: {
    AstrBotCoreConfigWrapper,
    VueMonacoEditor,
    WaitingForRestart,
    StandaloneChat,
    UnsavedChangesConfirmDialog,
  },

  // 检查未保存的更改
  async beforeRouteLeave(
    _to: RouteLocationNormalized,
    _from: RouteLocationNormalized,
  ) {
    if (this.hasUnsavedChanges) {
      const confirmed = await (this.$refs.unsavedChangesDialog as undefined | { open: (opts: UnsavedChangesOptions) => Promise<boolean | "close"> })?.open({
        title: this.tm("unsavedChangesWarning.dialogTitle"),
        message: this.tm("unsavedChangesWarning.leavePage"),
        confirmHint: `${this.tm("unsavedChangesWarning.options.saveAndSwitch")}:${this.tm("unsavedChangesWarning.options.confirm")}`,
        cancelHint: `${this.tm("unsavedChangesWarning.options.discardAndSwitch")}:${this.tm("unsavedChangesWarning.options.cancel")}`,
        closeHint: `${this.tm("unsavedChangesWarning.options.closeCard")}:"x"`,
      });
      // 关闭弹窗不跳转
      if (confirmed === "close") {
        return false;
      } else if (confirmed) {
        const result = await this.updateConfig();
        if (this.isSystemConfig) {
          return false;
        } else {
          if (result?.success) {
            await new Promise((resolve) => setTimeout(resolve, 800));
            return true;
          } else {
            return false;
          }
        }
      } else {
        this.hasUnsavedChanges = false;
        return true;
      }
    } else {
      return true;
    }
  },
  props: {
    initialConfigId: {
      type: String,
      default: null,
    },
  },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n("features/config");
    const confirmDialog = useConfirmDialog();

    return {
      t,
      tm,
      confirmDialog,
    };
  },
  data() {
    return {
      codeEditorDialog: false,
      configManageDialog: false,
      showConfigForm: false,
      isEditingConfig: false,
      config_data_has_changed: false,
      config_data_str: "",
      config_data: {
        config: {},
      },
      fetched: false,
      metadata: {},
      save_message_snack: false,
      save_message: "",
      save_message_success: "",
      configContentKey: 0,
      lastSavedConfigSnapshot: "",
      refreshingConfig: false,

      // 配置类型切换
      configType: "normal", // 'normal' 或 'system'
      configSearchKeyword: "",

      // 系统配置开关
      isSystemConfig: false,

      // 多配置文件管理
      selectedConfigID: null as string | null, // 用于存储当前选中的配置项信息
      currentConfigId: null as string | null, // 跟踪当前正在编辑的配置id
      configInfoList: [] as ConfigInfoItem[],
      configFormData: {
        name: "",
      } as { name: string },
      editingConfigId: null as string | null,

      // 测试聊天
      testChatDrawer: false,
      testConfigId: null as string | null,

      // 未保存的更改状态
      // 存储原始配置
      originalConfigData: null,
      hasUnsavedChanges: false,
    };
  },

  computed: {
    messages() {
      return {
        loadError: this.tm("messages.loadError"),
        saveSuccess: this.tm("messages.saveSuccess"),
        saveError: this.tm("messages.saveError"),
        configApplied: this.tm("messages.configApplied"),
        configApplyError: this.tm("messages.configApplyError"),
      };
    },
    // 检查配置是否变化
    configHasChanges() {
      if (!this.originalConfigData || !this.config_data) return false;
      return (
        JSON.stringify(this.originalConfigData) !==
        JSON.stringify(this.config_data)
      );
    },
    configInfoNameList() {
      return this.configInfoList.map((info) => info.name);
    },
    selectedConfigInfo(): Partial<ConfigInfoItem> {
      return (
        this.configInfoList.find((info) => info.id === this.selectedConfigID) ||
        {}
      );
    },
    configSelectItems() {
      const items = [...this.configInfoList];
      items.push({
        id: "_%manage%_",
        name: this.tm("configManagement.manageConfigs"),
      });
      return items;
    },
  },
  watch: {
    config_data_str(val) {
      this.config_data_has_changed = true;
    },
    async "$route.fullPath"(newVal) {
      await this.syncConfigTypeFromHash(newVal);
    },
    initialConfigId(newVal) {
      if (!newVal) {
        return;
      }
      if (this.selectedConfigID !== newVal) {
        this.getConfigInfoList(newVal);
      }
    },
  },
  beforeMount() {
    defineReactorMonacoTheme();
  },
  mounted() {
    const hashConfigType = this.extractConfigTypeFromHash(
      this.$route?.fullPath || "",
    );
    this.configType = hashConfigType || "normal";
    this.isSystemConfig = this.configType === "system";

    const targetConfigId = this.initialConfigId || "default";
    this.getConfigInfoList(targetConfigId);
    // 初始化配置类型状态
    this.configType = this.isSystemConfig ? "system" : "normal";

    // 监听语言切换事件，重新加载配置以获取插件的 i18n 数据
    window.addEventListener("astrbot-locale-changed", this.handleLocaleChange);

    // 保存初始配置
    this.$watch(
      "config_data",
      (newVal) => {
        if (!this.originalConfigData && newVal) {
          this.originalConfigData = JSON.parse(JSON.stringify(newVal));
        }
      },
      { immediate: false, deep: true },
    );
  },

  beforeUnmount() {
    // 移除语言切换事件监听器
    window.removeEventListener(
      "astrbot-locale-changed",
      this.handleLocaleChange,
    );
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

    onConfigSearchInput(value: string) {
      this.configSearchKeyword = normalizeTextInput(value);
    },
    extractConfigTypeFromHash(hash: string): string | null {
      const rawHash = String(hash || "");
      const lastHashIndex = rawHash.lastIndexOf("#");
      if (lastHashIndex === -1) {
        return null;
      }
      const cleanHash = rawHash.slice(lastHashIndex + 1);
      return cleanHash === "system" || cleanHash === "normal"
        ? cleanHash
        : null;
    },
    async syncConfigTypeFromHash(hash: string): Promise<boolean> {
      const configType = this.extractConfigTypeFromHash(hash);
      if (!configType || configType === this.configType) {
        return false;
      }

      this.configType = configType;
      await this.onConfigTypeToggle();
      return true;
    },
    getConfigInfoList(abconf_id?: string) {
      // 获取配置列表
      axios
        .get("/api/config/abconfs")
        .then((res) => {
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
        })
        .catch((err) => {
          this.save_message = this.messages.loadError;
          this.save_message_snack = true;
          this.save_message_success = "error";
        });
    },
    getConfig(abconf_id?: string, reloadFromFile = false) {
      this.fetched = false;
      const params: Record<string, string> = {};

      if (this.isSystemConfig) {
        params.system_config = "1";
      } else {
        params.id = abconf_id || this.selectedConfigID || "";
      }
      if (reloadFromFile) {
        params.reload_from_file = "1";
      }

      return axios
        .get("/api/config/abconf", {
          params: params,
        })
        .then((res) => {
          this.config_data = res.data.data.config;
          this.lastSavedConfigSnapshot = this.getConfigSnapshot(
            this.config_data,
          );
          this.config_data_str = "";
          this.config_data_has_changed = false;
          this.fetched = true;
          this.metadata = res.data.data.metadata;
          this.configContentKey += 1;
          // 获取配置后更新
          this.$nextTick(() => {
            this.originalConfigData = JSON.parse(
              JSON.stringify(this.config_data),
            );
            if (!this.isSystemConfig) {
              this.currentConfigId = abconf_id || this.selectedConfigID;
            }
          });
          return res;
        })
        .catch((err) => {
          this.save_message = this.messages.loadError;
          this.save_message_snack = true;
          this.save_message_success = "error";
          throw err;
        });
    },
    async refreshConfigFromFile() {
      if (this.refreshingConfig) return;

      if (this.hasUnsavedChanges) {
        const shouldDiscard = await (this.$refs.unsavedChangesDialog as undefined | { open: (opts: UnsavedChangesOptions) => Promise<boolean | "close"> })?.open({
          title: this.tm("unsavedChangesWarning.dialogTitle"),
          message: this.tm("unsavedChangesWarning.reloadConfig"),
          confirmHint: `${this.tm("actions.refresh")}:${this.tm("unsavedChangesWarning.options.confirm")}`,
          cancelHint: `${this.tm("unsavedChangesWarning.options.cancelReload")}:${this.tm("unsavedChangesWarning.options.cancel")}`,
          closeHint: `${this.tm("unsavedChangesWarning.options.closeCard")}:"x"`,
        });
        if (shouldDiscard !== true) {
          return;
        }
      }

      this.refreshingConfig = true;
      try {
        await this.getConfig(
          this.isSystemConfig ? undefined : (this.selectedConfigID ?? undefined),
          true,
        );
        this.save_message = this.tm("messages.refreshSuccess");
        this.save_message_snack = true;
        this.save_message_success = "success";
      } catch (error) {
        this.save_message = this.tm("messages.refreshError");
        this.save_message_snack = true;
        this.save_message_success = "error";
      } finally {
        this.refreshingConfig = false;
      }
    },
    updateConfig() {
      if (!this.fetched) return;

      const postData: Record<string, unknown> = {
        config: JSON.parse(JSON.stringify(this.config_data)),
      };

      if (this.isSystemConfig) {
        postData.conf_id = "default";
      } else {
        postData.conf_id = this.selectedConfigID;
      }

      return axios
        .post("/api/config/astrbot/update", postData)
        .then((res) => {
          if (res.data.status === "ok") {
            this.lastSavedConfigSnapshot = this.getConfigSnapshot(
              this.config_data,
            );
            this.save_message = res.data.message || this.messages.saveSuccess;
            this.save_message_snack = true;
            this.save_message_success = "success";
            this.onConfigSaved();

            if (this.isSystemConfig) {
              restartAstrBotRuntime(this.$refs.wfr as WfrRef | null | undefined).catch(() => undefined);
            }
            return { success: true };
          } else {
            this.save_message = res.data.message || this.messages.saveError;
            this.save_message_snack = true;
            this.save_message_success = "error";
            return { success: false };
          }
        })
        .catch((err) => {
          this.save_message = this.messages.saveError;
          this.save_message_snack = true;
          this.save_message_success = "error";
          return { success: false };
        });
    },
    // 重置未保存状态
    onConfigSaved() {
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
    createNewConfig() {
      axios
        .post("/api/config/abconf/new", {
          name: this.configFormData.name,
        })
        .then((res) => {
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
        })
        .catch((err) => {
          console.error(err);
          this.save_message = this.tm("configManagement.createFailed");
          this.save_message_snack = true;
          this.save_message_success = "error";
        });
    },
    async onConfigSelect(value: string) {
      if (value === "_%manage%_") {
        this.configManageDialog = true;
        // 重置选择到之前的值
        this.$nextTick(() => {
          this.selectedConfigID = this.selectedConfigInfo.id || "default";
          this.getConfig(this.selectedConfigID);
        });
      } else {
        // 检查是否有未保存的更改
        if (this.hasUnsavedChanges) {
          // 获取之前正在编辑的配置id
          const prevConfigId = this.isSystemConfig
            ? "default"
            : this.currentConfigId || this.selectedConfigID || "default";
          const message = this.tm("unsavedChangesWarning.switchConfig");
          const saveAndSwitch = await (this.$refs.unsavedChangesDialog as undefined | { open: (opts: UnsavedChangesOptions) => Promise<boolean | "close"> })?.open({
            title: this.tm("unsavedChangesWarning.dialogTitle"),
            message: message,
            confirmHint: `${this.tm("unsavedChangesWarning.options.saveAndSwitch")}:${this.tm("unsavedChangesWarning.options.confirm")}`,
            cancelHint: `${this.tm("unsavedChangesWarning.options.discardAndSwitch")}:${this.tm("unsavedChangesWarning.options.cancel")}`,
            closeHint: `${this.tm("unsavedChangesWarning.options.closeCard")}:"x"`,
          });
          // 关闭弹窗不切换
          if (saveAndSwitch === "close") {
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
    startCreateConfig() {
      this.showConfigForm = true;
      this.isEditingConfig = false;
      this.configFormData = {
        name: "",
      };
      this.editingConfigId = null;
    },
    startEditConfig(config: ConfigInfoItem) {
      this.showConfigForm = true;
      this.isEditingConfig = true;
      this.editingConfigId = config.id;

      this.configFormData = {
        name: config.name || "",
      };
    },
    cancelConfigForm() {
      this.showConfigForm = false;
      this.isEditingConfig = false;
      this.editingConfigId = null;
      this.configFormData = {
        name: "",
      };
    },
    saveConfigForm() {
      if (!this.configFormData.name) {
        this.save_message = this.tm("configManagement.pleaseEnterName");
        this.save_message_snack = true;
        this.save_message_success = "error";
        return;
      }

      if (this.isEditingConfig) {
        this.updateConfigInfo();
      } else {
        this.createNewConfig();
      }
    },
    async confirmDeleteConfig(config: ConfigInfoItem) {
      const message = this.tm("configManagement.confirmDelete").replace(
        "{name}",
        config.name,
      );
      if (await askForConfirmationDialog(message, this.confirmDialog)) {
        this.deleteConfig(config.id);
      }
    },
    deleteConfig(configId: string) {
      axios
        .post("/api/config/abconf/delete", {
          id: configId,
        })
        .then((res) => {
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
        })
        .catch((err) => {
          console.error(err);
          this.save_message = this.tm("configManagement.deleteFailed");
          this.save_message_snack = true;
          this.save_message_success = "error";
        });
    },
    updateConfigInfo() {
      axios
        .post("/api/config/abconf/update", {
          id: this.editingConfigId,
          name: this.configFormData.name,
        })
        .then((res) => {
          if (res.data.status === "ok") {
            this.save_message = res.data.message;
            this.save_message_snack = true;
            this.save_message_success = "success";
            this.getConfigInfoList(this.editingConfigId ?? undefined);
            this.cancelConfigForm();
          } else {
            this.save_message = res.data.message;
            this.save_message_snack = true;
            this.save_message_success = "error";
          }
        })
        .catch((err) => {
          console.error(err);
          this.save_message = this.tm("configManagement.updateFailed");
          this.save_message_snack = true;
          this.save_message_success = "error";
        });
    },
    async onConfigTypeToggle() {
      // 检查是否有未保存的更改
      if (this.hasUnsavedChanges) {
        const message = this.tm("unsavedChangesWarning.leavePage");
        const saveAndSwitch = await (this.$refs.unsavedChangesDialog as undefined | { open: (opts: UnsavedChangesOptions) => Promise<boolean | "close"> })?.open({
          title: this.tm("unsavedChangesWarning.dialogTitle"),
          message: message,
          confirmHint: `${this.tm("unsavedChangesWarning.options.saveAndSwitch")}:${this.tm("unsavedChangesWarning.options.confirm")}`,
          cancelHint: `${this.tm("unsavedChangesWarning.options.discardAndSwitch")}:${this.tm("unsavedChangesWarning.options.cancel")}`,
          closeHint: `${this.tm("unsavedChangesWarning.options.closeCard")}:"x"`,
        });
        // 关闭弹窗
        if (saveAndSwitch === "close") {
          // 恢复路由
          const originalHash = this.isSystemConfig ? "#system" : "#normal";
          this.$router.replace("/config" + originalHash);
          this.configType = this.isSystemConfig ? "system" : "normal";
          return;
        }
        if (saveAndSwitch) {
          await this.updateConfig();
          // 系统配置保存后不跳转
          if (this.isSystemConfig) {
            this.$router.replace("/config#system");
            return;
          }
        }
      }
      this.isSystemConfig = this.configType === "system";
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
      this.configType = this.isSystemConfig ? "system" : "normal";

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
    getConfigSnapshot(config: Record<string, unknown>) {
      return JSON.stringify(config ?? {});
    },
  },
};
</script>

<style>
.v-tab {
  text-transform: none !important;
}

.unsaved-changes-banner {
  border-radius: 8px;
  background-color: rgba(var(--v-theme-warning), 0.1) !important;
  border: 1px solid rgba(var(--v-theme-warning), 0.16) !important;
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

/* Reactor glassmorphism editor container */
.editor-reactor-container {
  width: 100vw;
  height: 100vh;
  background: rgba(10, 10, 12, 0.92);
  backdrop-filter: blur(40px) saturate(1.3);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  box-sizing: border-box;
}

.editor-glass-card {
  width: 100%;
  max-width: 1400px;
  height: calc(100vh - 64px);
  background: rgba(15, 15, 22, 0.55) !important;
  backdrop-filter: blur(24px) saturate(1.2);
  border: 1px solid rgba(0, 242, 255, 0.15);
  border-radius: 28px !important;
  box-shadow:
    inset 0 0 40px rgba(0, 0, 0, 0.6),
    0 0 80px rgba(0, 26, 51, 0.4),
    0 0 0 0.5px rgba(0, 242, 255, 0.05);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.editor-toolbar {
  background: rgba(10, 10, 16, 0.8) !important;
  border-bottom: 1px solid rgba(0, 242, 255, 0.08) !important;
  backdrop-filter: blur(12px);
  flex-shrink: 0;
}

.editor-monaco-wrapper {
  flex: 1;
  overflow: hidden;
  border-radius: 0 0 28px 28px;
}
</style>
