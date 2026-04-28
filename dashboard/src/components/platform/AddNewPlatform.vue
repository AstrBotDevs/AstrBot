<template>
  <v-dialog
    v-model="showDialog"
    max-width="800px"
    max-height="90%"
    @after-enter="prepareData"
  >
    <v-card
      :title="
        updatingMode
          ? `${tm('dialog.edit')} ${updatingPlatformConfig.id} ${tm('dialog.adapter')}`
          : tm('dialog.addPlatform')
      "
    >
      <v-card-text
        ref="dialogScrollContainer"
        class="pa-4 ml-2 add-platform-body"
        style="overflow-y: auto"
      >
        <div class="d-flex align-start" style="width: 100%">
          <div>
            <v-icon icon="mdi-numeric-1-circle" class="mr-3" />
          </div>
          <div style="flex: 1">
            <h3>
              {{ tm("createDialog.step1Title") }}
            </h3>
            <small style="color: grey">{{
              tm("createDialog.step1Hint")
            }}</small>
            <div>
              <div v-if="!updatingMode">
                <v-select
                  v-model="selectedPlatformType"
                  :items="Object.keys(platformTemplates)"
                  item-title="name"
                  item-value="name"
                  :label="tm('createDialog.platformTypeLabel')"
                  variant="outlined"
                  rounded="md"
                  density="compact"
                  hide-details
                  class="mt-6 platform-type-field"
                >
                  <template #item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps">
                      <template #prepend>
                        <img
                          v-if="getPlatformOptionIcon(item)"
                          :src="getPlatformOptionIcon(item)"
                          class="platform-option-logo"
                        />
                        <v-icon v-else class="mr-4" color="medium-emphasis">
                          mdi-puzzle-outline
                        </v-icon>
                      </template>
                    </v-list-item>
                  </template>
                  <template #selection="{ item }">
                    <div class="d-flex align-center ga-2">
                      <img
                        v-if="getPlatformOptionIcon(item)"
                        :src="getPlatformOptionIcon(item)"
                        class="platform-selection-logo"
                      />
                      <v-icon v-else color="medium-emphasis">
                        mdi-puzzle-outline
                      </v-icon>
                      <span>{{ getPlatformOptionLabel(item) }}</span>
                    </div>
                  </template>
                </v-select>
                <div v-if="selectedPlatformConfig" class="mt-3">
                  <v-btn
                    color="info"
                    variant="tonal"
                    class="mt-2"
                    @click="openTutorial"
                  >
                    <v-icon start> mdi-book-open-variant </v-icon>
                    {{ tm("dialog.viewTutorial") }}
                  </v-btn>
                  <div class="mt-2">
                    <AstrBotConfig
                      :iterable="selectedPlatformConfig"
                      :metadata="metadata['platform_group']?.metadata"
                      metadata-key="platform"
                    />
                  </div>
                </div>
              </div>
              <div v-else>
                <v-text-field
                  :model-value="updatingPlatformConfig.type"
                  :label="tm('createDialog.platformTypeLabel')"
                  variant="outlined"
                  rounded="md"
                  density="compact"
                  hide-details
                  class="mt-6 platform-type-field"
                  disabled
                />
                <div class="mt-3">
                  <div class="mt-2">
                    <AstrBotConfig
                      :iterable="updatingPlatformConfig"
                      :metadata="metadata['platform_group']?.metadata"
                      metadata-key="platform"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="d-flex align-start mt-6">
          <div>
            <v-icon icon="mdi-numeric-2-circle" class="mr-3" />
          </div>
          <div style="flex: 1">
            <div class="d-flex align-center justify-space-between">
              <div>
                <div class="d-flex align-center">
                  <h3>
                    {{ tm("createDialog.configFileTitle") }}
                  </h3>
                  <v-chip
                    v-if="!updatingMode"
                    size="x-small"
                    color="primary"
                    variant="tonal"
                    rounded="sm"
                    class="ml-2"
                  >
                    {{ tm("createDialog.optional") }}
                  </v-chip>
                </div>
                <small style="color: grey">{{
                  tm("createDialog.configHint")
                }}</small>
                <small v-if="!updatingMode" style="color: grey">{{
                  tm("createDialog.configDefaultHint")
                }}</small>
              </div>
              <div>
                <v-btn
                  variant="plain"
                  icon
                  class="mt-2"
                  @click="toggleConfigSection"
                >
                  <v-icon>{{
                    showConfigSection ? "mdi-chevron-up" : "mdi-chevron-down"
                  }}</v-icon>
                </v-btn>
              </div>
            </div>

            <div v-if="showConfigSection">
              <div v-if="!updatingMode">
                <v-radio-group
                  v-model="aBConfigRadioVal"
                  class="mt-2"
                  hide-details
                >
                  <v-radio value="0">
                    <template #label>
                      <span>{{ tm("createDialog.useExistingConfig") }}</span>
                    </template>
                  </v-radio>
                  <div
                    v-if="aBConfigRadioVal === '0'"
                    class="d-flex align-center ml-10 my-2 config-mode-field-row"
                  >
                    <v-select
                      v-model="selectedAbConfId"
                      :items="configInfoList"
                      item-title="name"
                      item-value="id"
                      :label="tm('createDialog.selectConfigLabel')"
                      variant="outlined"
                      rounded="md"
                      density="compact"
                      hide-details
                      class="config-file-field"
                    />
                    <v-btn
                      icon
                      variant="text"
                      density="comfortable"
                      class="ml-2"
                      :disabled="!selectedAbConfId"
                      @click="openConfigDrawer(selectedAbConfId)"
                    >
                      <v-icon>mdi-arrow-top-right-thick</v-icon>
                    </v-btn>
                  </div>
                  <v-radio
                    value="1"
                    :label="tm('createDialog.createNewConfig')"
                  />
                  <div
                    v-if="aBConfigRadioVal === '1'"
                    class="d-flex align-center config-mode-field-row"
                  >
                    <v-text-field
                      v-model="selectedAbConfId"
                      :label="tm('createDialog.newConfigNameLabel')"
                      variant="outlined"
                      rounded="md"
                      density="compact"
                      hide-details
                      class="ml-10 my-2 config-file-field"
                    />
                  </div>
                </v-radio-group>

                <!-- 现有配置文件预览区域 -->
                <!-- <div v-if="aBConfigRadioVal === '0' && selectedAbConfId" class="mt-4">
                  <div v-if="configPreviewLoading" class="d-flex justify-center py-4">
                    <v-progress-circular indeterminate color="primary"></v-progress-circular>
                  </div>
                  <div v-else-if="selectedConfigData && selectedConfigMetadata" class="config-preview-container">
                    <h4 class="mb-3">配置文件预览</h4>
                    <AstrBotCoreConfigWrapper :metadata="selectedConfigMetadata" :config_data="selectedConfigData"
                      readonly="true" />
                  </div>
                  <div v-else class="text-center py-4 text-grey">
                    <v-icon>mdi-information-outline</v-icon>
                    <p class="mt-2">无法加载配置文件预览</p>
                  </div>
                </div> -->

                <!-- 新配置文件编辑区域 -->
                <div v-if="aBConfigRadioVal === '1'" class="mt-4">
                  <div
                    v-if="newConfigLoading"
                    class="d-flex justify-center py-4"
                  >
                    <v-progress-circular indeterminate color="primary" />
                  </div>
                  <div
                    v-else-if="newConfigData && newConfigMetadata"
                    class="config-preview-container"
                  >
                    <h4 class="mb-3">
                      {{ tm("createDialog.newConfigTitle") }}
                    </h4>
                    <AstrBotCoreConfigWrapper
                      :metadata="newConfigMetadata"
                      :config_data="newConfigData"
                    />
                  </div>
                  <div v-else class="text-center py-4 text-grey">
                    <v-icon>mdi-information-outline</v-icon>
                    <p class="mt-2">
                      {{ tm("createDialog.newConfigLoadFailed") }}
                    </p>
                  </div>
                </div>
              </div>

              <div v-else>
                <div
                  class="mb-3 d-flex align-center justify-space-between route-toolbar"
                >
                  <div>
                    <v-btn
                      v-if="isEditingRoutes"
                      color="primary"
                      variant="tonal"
                      size="small"
                      @click="addNewRoute"
                    >
                      <v-icon start> mdi-plus </v-icon>
                      {{ tm("createDialog.addRouteRule") }}
                    </v-btn>
                  </div>
                  <v-btn
                    :color="isEditingRoutes ? 'grey' : 'primary'"
                    variant="tonal"
                    size="small"
                    @click="toggleEditMode"
                  >
                    <v-icon start>
                      {{ isEditingRoutes ? "mdi-eye" : "mdi-pencil" }}
                    </v-icon>
                    {{
                      isEditingRoutes
                        ? tm("createDialog.viewMode")
                        : tm("createDialog.editMode")
                    }}
                  </v-btn>
                </div>

                <v-data-table
                  :headers="routeTableHeaders"
                  :items="platformRoutes"
                  item-value="umop"
                  :no-data-text="tm('createDialog.noRouteRules')"
                  hide-default-footer
                  :items-per-page="-1"
                  class="mt-2 platform-route-table"
                  variant="outlined"
                >
                  <template #item.source="{ item }">
                    <div class="d-flex align-center route-source-field">
                      <v-select
                        v-if="isEditingRoutes"
                        v-model="item.messageType"
                        :items="messageTypeOptions"
                        item-title="label"
                        item-value="value"
                        variant="outlined"
                        density="compact"
                        hide-details
                        class="route-message-type-field"
                      />
                      <small v-else>{{
                        getMessageTypeLabel(item.messageType)
                      }}</small>
                      <small class="mx-1">:</small>
                      <v-text-field
                        v-if="isEditingRoutes"
                        v-model="item.sessionId"
                        variant="outlined"
                        density="compact"
                        hide-details
                        :placeholder="tm('createDialog.sessionIdPlaceholder')"
                      />
                      <small v-else>{{
                        item.sessionId === "*"
                          ? tm("createDialog.allSessions")
                          : item.sessionId
                      }}</small>
                    </div>
                  </template>

                  <template #item.configId="{ item }">
                    <div class="d-flex align-center route-config-cell">
                      <v-select
                        v-if="isEditingRoutes"
                        v-model="item.configId"
                        :items="configInfoList"
                        item-title="name"
                        item-value="id"
                        variant="outlined"
                        density="compact"
                        class="route-config-field"
                        hide-details
                      />
                      <div v-else>
                        <small>{{ getConfigName(item.configId) }}</small>
                      </div>
                      <v-btn
                        icon
                        variant="text"
                        density="compact"
                        class="ml-2"
                        :disabled="!item.configId"
                        @click="openConfigDrawer(item.configId)"
                      >
                        <v-icon size="18"> mdi-arrow-top-right-thick </v-icon>
                      </v-btn>
                    </div>
                    <small
                      v-if="
                        configInfoList.findIndex(
                          (c) => c.id === item.configId,
                        ) === -1
                      "
                      style="color: red"
                      class="ml-2"
                      >{{ tm("createDialog.configMissing") }}</small
                    >
                  </template>

                  <template #item.actions="{ item, index }">
                    <div v-if="isEditingRoutes" class="d-flex align-center">
                      <v-btn
                        icon
                        size="x-small"
                        variant="text"
                        :disabled="index === 0"
                        @click="moveRouteUp(index)"
                      >
                        <v-icon>mdi-arrow-up</v-icon>
                      </v-btn>
                      <v-btn
                        icon
                        size="x-small"
                        variant="text"
                        :disabled="index === platformRoutes.length - 1"
                        @click="moveRouteDown(index)"
                      >
                        <v-icon>mdi-arrow-down</v-icon>
                      </v-btn>
                      <v-btn
                        icon
                        size="x-small"
                        variant="text"
                        color="error"
                        @click="deleteRoute(index)"
                      >
                        <v-icon>mdi-delete</v-icon>
                      </v-btn>
                    </div>
                    <span v-else class="text-grey">-</span>
                  </template>
                </v-data-table>
                <small class="ml-2 mt-2 d-block" style="color: grey">{{
                  tm("createDialog.routeHint")
                }}</small>
              </div>
            </div>
          </div>
        </div>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn text @click="closeDialog">
          {{ tm("dialog.cancel") }}
        </v-btn>
        <v-btn
          v-if="!updatingMode"
          :disabled="!canSave"
          color="primary"
          :loading="loading"
          @click="newPlatform"
        >
          {{ tm("dialog.save") }}
        </v-btn>
        <v-btn
          v-else
          :disabled="!selectedAbConfId"
          color="primary"
          :loading="loading"
          @click="newPlatform"
        >
          {{ tm("dialog.save") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ID冲突确认对话框 -->
  <v-dialog v-model="showIdConflictDialog" max-width="450" persistent>
    <v-card>
      <v-card-title class="text-h6 bg-warning d-flex align-center">
        <v-icon start class="me-2"> mdi-alert-circle-outline </v-icon>
        {{ tm("dialog.idConflict.title") }}
      </v-card-title>
      <v-card-text class="py-4 text-body-1 text-medium-emphasis">
        {{ tm("dialog.idConflict.message", { id: conflictId }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          color="grey"
          variant="text"
          @click="handleIdConflictConfirm(false)"
        >
          {{ tm("dialog.idConflict.confirm") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 安全警告对话框 -->
  <v-dialog v-model="showOneBotEmptyTokenWarnDialog" max-width="600" persistent>
    <v-card>
      <v-card-title>
        {{ tm("dialog.securityWarning.title") }}
      </v-card-title>
      <v-card-text class="py-4">
        <p>{{ tm("dialog.securityWarning.aiocqhttpTokenMissing") }}</p>
        <span
          ><a
            href="https://docs.astrbot.app/deploy/platform/aiocqhttp/napcat.html#%E9%99%84%E5%BD%95-%E5%A2%9E%E5%BC%BA%E8%BF%9E%E6%8E%A5%E5%AE%89%E5%85%A8%E6%80%A7"
            target="_blank"
            >{{ tm("dialog.securityWarning.learnMore") }}</a
          ></span
        >
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn
          color="error"
          @click="handleOneBotEmptyTokenWarningDismiss(true)"
        >
          {{ tm("createDialog.warningContinue") }}
        </v-btn>
        <v-btn
          color="primary"
          @click="handleOneBotEmptyTokenWarningDismiss(false)"
        >
          {{ tm("createDialog.warningEditAgain") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-overlay
    v-model="showConfigDrawer"
    class="config-drawer-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @click:outside="closeConfigDrawer"
  >
    <v-card class="config-drawer-card" elevation="12">
      <div class="config-drawer-header">
        <div>
          <span class="text-h6">{{
            tm("createDialog.configDrawerTitle")
          }}</span>
          <div v-if="configDrawerTargetId" class="text-caption text-grey">
            {{ tm("createDialog.configDrawerIdLabel") }}:
            {{ configDrawerTargetId }}
          </div>
        </div>
        <v-btn icon variant="text" @click="closeConfigDrawer">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </div>
      <v-divider />
      <div class="config-drawer-content">
        <ConfigPage
          v-if="showConfigDrawer"
          :initial-config-id="configDrawerTargetId ?? undefined"
        />
      </div>
    </v-card>
  </v-overlay>
</template>

<script lang="ts">
import axios from "@/utils/request";
import { resolveApiUrl } from "@/utils/request";
import { useModuleI18n } from "@/i18n/composables";
import {
  getPlatformIcon as getPlatformBuiltInIcon,
  getPlatformDescription,
  getTutorialLink,
} from "@/utils/platformUtils";
import AstrBotConfig from "@/components/shared/AstrBotConfig.vue";
import AstrBotCoreConfigWrapper from "@/components/config/AstrBotCoreConfigWrapper.vue";
import ConfigPage from "@/views/ConfigPage.vue";

interface RouteEntry {
  umop: string | null;
  originalUmop: string | null;
  messageType: string;
  sessionId: string;
  configId: string;
}

interface ConfigInfo {
  id: string;
  name: string;
}

interface ToastPayload {
  message: string;
  type: "success" | "error";
}

export default {
  name: "AddNewPlatform",
  components: { AstrBotConfig, AstrBotCoreConfigWrapper, ConfigPage },
  emits: ["update:show", "show-toast", "refresh-config"],
  props: {
    show: {
      type: Boolean,
      default: false,
    },
    metadata: {
      type: Object,
      default: () => ({}),
    },
    config_data: {
      type: Object,
      default: () => ({}),
    },
    updatingMode: {
      type: Boolean,
      default: false,
    },
    updatingPlatformConfig: {
      type: Object,
      default: null,
    },
  },
  setup() {
    const { tm } = useModuleI18n("features/platform");
    return { tm };
  },
  data() {
    return {
      selectedPlatformType: null as string | null,
      selectedPlatformConfig: null as Record<string, unknown> | null,

      aBConfigRadioVal: "0",
      selectedAbConfId: null as string | null,
      configInfoList: [] as ConfigInfo[],

      // 选中的配置文件预览数据
      selectedConfigData: null as Record<string, unknown> | null,
      selectedConfigMetadata: null as Record<string, unknown> | null,
      configPreviewLoading: false,

      // 新配置文件相关数据
      newConfigData: null as Record<string, unknown> | null,
      newConfigMetadata: null as Record<string, unknown> | null,
      newConfigLoading: false,

      // 平台配置文件表格（已弃用，改用 platformRoutes）
      platformConfigs: [] as Array<Record<string, unknown>>,

      // 平台路由表
      platformRoutes: [] as RouteEntry[],
      isEditingRoutes: false, // 编辑模式开关

      // ID冲突确认对话框
      showIdConflictDialog: false,
      conflictId: "",
      idConflictResolve: null as ((value: boolean) => void) | null,

      // OneBot Empty Token Warning #2639
      showOneBotEmptyTokenWarnDialog: false,
      oneBotEmptyTokenWarningResolve: null as ((value: boolean) => void) | null,

      loading: false,

      showConfigSection: false,

      // 配置抽屉
      showConfigDrawer: false,
      configDrawerTargetId: null as string | null,

      // 保存更新前的平台 ID，防止用户修改 ID 后丢失原始定位
      originalUpdatingPlatformId: null as string | null,
    };
  },
  computed: {
    showDialog: {
      get(): boolean {
        return this.show;
      },
      set(value: boolean) {
        this.$emit("update:show", value);
      },
    },
    platformTemplates(): Record<string, unknown> {
      const pg = this.metadata["platform_group"] as Record<string, unknown> | undefined;
      const meta = pg?.metadata as Record<string, unknown> | undefined;
      const plat = meta?.platform as Record<string, unknown> | undefined;
      return (plat?.config_template as Record<string, unknown>) || {};
    },
    canSave(): boolean {
      if (!this.selectedPlatformType) {
        return false;
      }
      const cfg = this.selectedPlatformConfig as Record<string, unknown> | null;
      if (!this.isPlatformIdValid(cfg?.id as string | undefined)) {
        return false;
      }
      if (this.aBConfigRadioVal === "0") {
        return !!this.selectedAbConfId;
      }
      if (this.aBConfigRadioVal === "1") {
        return !!(this.selectedAbConfId && this.newConfigData);
      }
      return false;
    },
    configTableHeaders() {
      return [
        {
          title: this.tm("createDialog.configTableHeaders.configId"),
          key: "name",
          sortable: false,
        },
        {
          title: this.tm("createDialog.configTableHeaders.scope"),
          key: "scope",
          sortable: false,
        },
      ];
    },
    routeTableHeaders() {
      return [
        {
          title: this.tm("createDialog.routeTableHeaders.source"),
          key: "source",
          sortable: false,
          width: "60%",
        },
        {
          title: this.tm("createDialog.routeTableHeaders.config"),
          key: "configId",
          sortable: false,
          width: "20%",
        },
        {
          title: this.tm("createDialog.routeTableHeaders.actions"),
          key: "actions",
          sortable: false,
          align: "center" as const,
          width: "20%",
        },
      ];
    },
    messageTypeOptions() {
      return [
        { label: this.tm("createDialog.messageTypeOptions.all"), value: "*" },
        {
          label: this.tm("createDialog.messageTypeOptions.group"),
          value: "GroupMessage",
        },
        {
          label: this.tm("createDialog.messageTypeOptions.friend"),
          value: "FriendMessage",
        },
      ];
    },
  },
  watch: {
    selectedPlatformType(newType: string | null) {
      const templates = this.platformTemplates as Record<string, unknown>;
      if (newType && templates[newType]) {
        this.selectedPlatformConfig = JSON.parse(
          JSON.stringify(templates[newType]),
        ) as Record<string, unknown>;
      } else {
        this.selectedPlatformConfig = null;
      }
    },
    selectedAbConfId(newConfigId: string | null) {
      if (!this.updatingMode && this.aBConfigRadioVal === "0" && newConfigId) {
        this.getConfigForPreview(newConfigId);
      } else {
        this.selectedConfigData = null;
        this.selectedConfigMetadata = null;
      }
    },
    aBConfigRadioVal(newVal: string) {
      if (newVal === "1") {
        this.selectedConfigData = null;
        this.selectedConfigMetadata = null;
        this.selectedAbConfId = null;
        this.getDefaultConfigTemplate();
      } else if (newVal === "0") {
        this.newConfigData = null;
        this.newConfigMetadata = null;
        if (!this.selectedAbConfId) {
          this.selectedAbConfId = "default";
        }
      }
    },
    showIdConflictDialog(newValue: boolean) {
      if (!newValue && this.idConflictResolve) {
        this.idConflictResolve(false);
        this.idConflictResolve = null;
      }
    },
    showOneBotEmptyTokenWarnDialog(newValue: boolean) {
      if (!newValue && this.oneBotEmptyTokenWarningResolve) {
        this.oneBotEmptyTokenWarningResolve(true);
        this.oneBotEmptyTokenWarningResolve = null;
      }
    },
    updatingPlatformConfig: {
      handler(newConfig: Record<string, unknown> | null) {
        if (this.updatingMode && newConfig && newConfig.id) {
          this.originalUpdatingPlatformId = newConfig.id as string;
          this.getPlatformConfigs(newConfig.id as string);
        }
      },
      immediate: true,
    },
    showConfigSection(newValue: boolean) {
      if (newValue && !this.updatingMode && this.aBConfigRadioVal === "0") {
        this.getConfigForPreview(this.selectedAbConfId);
      }
      if (newValue) {
        this.$nextTick(() => {
          this.scrollDialogToBottom();
        });
      }
    },
    updatingMode: {
      handler(newValue: boolean) {
        if (newValue) {
          this.showConfigSection = true;
          this.isEditingRoutes = false;
        }
      },
      immediate: true,
    },
  },
  methods: {
    getPlatformTemplateByName(platformName: string | null | undefined): Record<string, unknown> | null {
      if (!platformName) {
        return null;
      }
      const templates = this.platformTemplates as Record<string, unknown>;
      return (templates?.[platformName] as Record<string, unknown>) || null;
    },
    getPlatformOptionLabel(item: unknown): string {
      if (typeof item === "string") {
        return item;
      }
      const rec = item as Record<string, unknown>;
      if (typeof rec?.raw === "string") {
        return rec.raw as string;
      }
      if (typeof rec?.value === "string") {
        return rec.value as string;
      }
      if (typeof rec?.title === "string") {
        return rec.title as string;
      }
      return "";
    },
    getPlatformIcon(platformNameOrType: string): string {
      const template = this.getPlatformTemplateByName(platformNameOrType) as Record<string, unknown> | null;
      if (template && template.logo_token) {
        return resolveApiUrl(`/api/file/${String(template.logo_token)}`);
      }
      return (template ? getPlatformBuiltInIcon(String(template.type)) : getPlatformBuiltInIcon(platformNameOrType)) ?? "";
    },
    getPlatformOptionIcon(item: unknown): string {
      return this.getPlatformIcon(this.getPlatformOptionLabel(item));
    },
    getPlatformDescription,
    resetForm(): void {
      this.selectedPlatformType = null;
      this.selectedPlatformConfig = null;

      this.aBConfigRadioVal = "0";
      this.selectedAbConfId = "default";

      this.selectedConfigData = null;
      this.selectedConfigMetadata = null;
      this.configPreviewLoading = false;

      this.newConfigData = null;
      this.newConfigMetadata = null;
      this.newConfigLoading = false;

      this.showConfigSection = false;
      this.isEditingRoutes = false;

      this.showConfigDrawer = false;
      this.configDrawerTargetId = null;

      this.originalUpdatingPlatformId = null;
    },
    closeDialog(): void {
      this.resetForm();
      this.showDialog = false;
    },
    async getConfigInfoList(): Promise<void> {
      const res = await axios.get("/api/config/abconfs");
      this.configInfoList = res.data.data.info_list;
    },

    async getConfigForPreview(configId: string | null): Promise<void> {
      if (!configId) {
        this.selectedConfigData = null;
        this.selectedConfigMetadata = null;
        return;
      }

      this.configPreviewLoading = true;
      try {
        const response = await axios.get("/api/config/abconf", {
          params: { id: configId },
        });
        this.selectedConfigData = response.data.data.config;
        this.selectedConfigMetadata = response.data.data.metadata;
      } catch (_err) {
        console.error("获取配置文件预览数据失败:", _err);
        this.selectedConfigData = null;
        this.selectedConfigMetadata = null;
      } finally {
        this.configPreviewLoading = false;
      }
    },

    async getDefaultConfigTemplate(): Promise<void> {
      this.newConfigLoading = true;
      try {
        const response = await axios.get("/api/config/default");
        this.newConfigData = response.data.data.config;
        this.newConfigMetadata = response.data.data.metadata;
      } catch (_err) {
        console.error("获取默认配置模板失败:", _err);
        this.newConfigData = null;
        this.newConfigMetadata = null;
      } finally {
        this.newConfigLoading = false;
      }
    },
    openTutorial(): void {
      const config = this.selectedPlatformConfig as Record<string, unknown> | null;
      const tutorialUrl = getTutorialLink(config?.type as string);
      window.open(tutorialUrl, "_blank");
    },
    openConfigDrawer(configId: string | null | undefined): void {
      const targetId = configId || "default";

      if (
        configId &&
        this.configInfoList.findIndex((c: ConfigInfo) => c.id === configId) === -1
      ) {
        this.showError(this.tm("messages.configNotFoundOpenConfig"));
      }

      this.configDrawerTargetId = targetId;
      this.showConfigDrawer = true;
    },
    closeConfigDrawer(): void {
      this.showConfigDrawer = false;
    },
    newPlatform(): void {
      this.loading = true;
      if (this.updatingMode) {
        const config = this.updatingPlatformConfig as Record<string, unknown> | null;
        if (config?.type === "aiocqhttp") {
          const token = config?.ws_reverse_token as string | undefined;
          if (!token || token.trim() === "") {
            this.showOneBotEmptyTokenWarning().then((continueWithWarning) => {
              if (continueWithWarning) {
                this.updatePlatform();
              } else {
                this.loading = false;
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
    async updatePlatform(): Promise<void> {
      const config = this.updatingPlatformConfig as Record<string, unknown> | null;
      const id = this.originalUpdatingPlatformId || (config?.id as string);
      if (!id) {
        this.loading = false;
        this.showError(this.tm("messages.updateMissingPlatformId"));
        return;
      }

      if (!this.isPlatformIdValid(id)) {
        this.loading = false;
        this.showError(this.tm("dialog.invalidPlatformId"));
        return;
      }

      try {
        const resp = await axios.post("/api/config/platform/update", {
          id: id,
          config: config,
        });

        if (resp.data.status === "error") {
          throw new Error(
            resp.data.message || this.tm("messages.platformUpdateFailed"),
          );
        }

        await this.saveRoutesInternal();

        this.loading = false;
        this.showDialog = false;
        this.resetForm();
        this.$emit("refresh-config");
        this.showSuccess(this.tm("messages.updateSuccess"));
      } catch (_err) {
        this.loading = false;
        this.showError(this.getErrorMessage(_err));
      }
    },
    async savePlatform(): Promise<void> {
      const config = this.selectedPlatformConfig as Record<string, unknown> | null;

      if (!this.isPlatformIdValid(config?.id as string | undefined)) {
        this.loading = false;
        this.showError(this.tm("dialog.invalidPlatformId"));
        return;
      }

      const platformList = (this.config_data as Record<string, unknown>)?.platform as Array<Record<string, unknown>> | undefined;
      const existingPlatform = platformList?.find(
        (p: Record<string, unknown>) => p.id === config?.id,
      );
      if (existingPlatform || config?.id === "webchat") {
        const confirmed = await this.confirmIdConflict(config?.id as string);
        if (!confirmed) {
          this.loading = false;
          return;
        }
      }

      if (config?.type === "aiocqhttp") {
        const token = config?.ws_reverse_token as string | undefined;
        if (!token || token.trim() === "") {
          const continueWithWarning = await this.showOneBotEmptyTokenWarning();
          if (!continueWithWarning) {
            return;
          }
        }
      }

      try {
        const res = await axios.post(
          "/api/config/platform/new",
          config,
        );

        await this.handleConfigFile();

        this.loading = false;
        this.showDialog = false;
        this.resetForm();
        this.$emit("refresh-config");
        this.showSuccess(
          res.data.message || this.tm("messages.addSuccessWithConfig"),
        );
      } catch (_err) {
        this.loading = false;
        this.showError(this.getErrorMessage(_err));
      }
    },

    async handleConfigFile(): Promise<void> {
      if (!this.selectedAbConfId) {
        return;
      }

      const config = this.selectedPlatformConfig as Record<string, unknown> | null;
      const platformId = config?.id as string;
      const newUmop = `${platformId}:*:*`;

      let configId: string | null = null;

      if (this.aBConfigRadioVal === "0") {
        configId = this.selectedAbConfId;
      } else if (this.aBConfigRadioVal === "1") {
        configId = await this.createNewConfigFile(this.selectedAbConfId!);
      }

      if (!configId) {
        throw new Error(this.tm("messages.configIdMissing"));
      }

      await this.updateRoutingTable(newUmop, configId);
    },

    async updateRoutingTable(umop: string, configId: string): Promise<void> {
      try {
        await axios.post("/api/config/umo_abconf_route/update", {
          umo: umop,
          conf_id: configId,
        });

        console.info(`成功更新路由表: ${umop} -> ${configId}`);
      } catch (_err) {
        console.error("更新路由表失败:", _err);
        throw new Error(
          this.tm("messages.routingUpdateFailed", { message: this.getErrorMessage(_err) }),
        );
      }
    },

    async createNewConfigFile(configName: string): Promise<string> {
      try {
        const configData =
          this.aBConfigRadioVal === "1" && this.newConfigData
            ? this.newConfigData
            : undefined;

        const createRes = await axios.post("/api/config/abconf/new", {
          name: configName,
          config: configData,
        });

        const newConfigId: string = createRes.data.data.conf_id;
        console.info(`成功创建新配置文件 ${configName}，ID: ${newConfigId}`);

        return newConfigId;
      } catch (_err) {
        console.error("创建新配置文件失败:", _err);
        throw new Error(
          this.tm("messages.createConfigFailed", { message: this.getErrorMessage(_err) }),
        );
      }
    },

    confirmIdConflict(id: string): Promise<boolean> {
      this.conflictId = id;
      this.showIdConflictDialog = true;
      return new Promise<boolean>((resolve) => {
        this.idConflictResolve = resolve;
      });
    },

    handleIdConflictConfirm(confirmed: boolean): void {
      if (this.idConflictResolve) {
        this.idConflictResolve(confirmed);
      }
      this.showIdConflictDialog = false;
    },

    showOneBotEmptyTokenWarning(): Promise<boolean> {
      this.showOneBotEmptyTokenWarnDialog = true;
      return new Promise<boolean>((resolve) => {
        this.oneBotEmptyTokenWarningResolve = resolve;
      });
    },

    handleOneBotEmptyTokenWarningDismiss(continueWithWarning: boolean): void {
      this.showOneBotEmptyTokenWarnDialog = false;
      if (this.oneBotEmptyTokenWarningResolve) {
        this.oneBotEmptyTokenWarningResolve(continueWithWarning);
        this.oneBotEmptyTokenWarningResolve = null;
      }

      if (!continueWithWarning) {
        this.loading = false;
      }
    },

    showSuccess(message: string): void {
      this.$emit("show-toast", { message, type: "success" } as ToastPayload);
    },

    showError(message: string): void {
      this.$emit("show-toast", { message, type: "error" } as ToastPayload);
    },

    isPlatformIdValid(id: string | null | undefined): boolean {
      if (!id) {
        return false;
      }
      return !/[!:]/.test(id);
    },

    async getPlatformConfigs(platformId: string): Promise<void> {
      if (!platformId) {
        this.platformRoutes = [];
        return;
      }

      try {
        const routesRes = await axios.get("/api/config/umo_abconf_routes");
        const routingTable = routesRes.data.data.routing as Record<string, string>;

        const routes: RouteEntry[] = [];
        for (const [umop, confId] of Object.entries(routingTable)) {
          if (this.isUmopMatchPlatform(umop, platformId)) {
            const parts = umop.split(":");
            if (parts.length === 3) {
              routes.push({
                umop: umop,
                originalUmop: umop,
                messageType:
                  parts[1] === "" || parts[1] === "*" ? "*" : parts[1],
                sessionId: parts[2] === "" || parts[2] === "*" ? "*" : parts[2],
                configId: confId,
              });
            }
          }
        }

        this.platformRoutes = routes;

        if (this.platformRoutes.length === 0) {
          this.platformRoutes.push({
            umop: null,
            originalUmop: null,
            messageType: "*",
            sessionId: "*",
            configId: "default",
          });
        }
      } catch (_err) {
        console.error("获取平台路由配置失败:", _err);
        this.platformRoutes = [];
      }
    },

    addNewRoute(): void {
      this.platformRoutes.push({
        umop: null,
        originalUmop: null,
        messageType: "*",
        sessionId: "*",
        configId: "default",
      });
    },

    deleteRoute(index: number): void {
      this.platformRoutes.splice(index, 1);
    },

    moveRouteUp(index: number): void {
      if (index > 0) {
        const temp = this.platformRoutes[index];
        this.platformRoutes[index] = this.platformRoutes[index - 1];
        this.platformRoutes[index - 1] = temp;
        this.platformRoutes = [...this.platformRoutes];
      }
    },

    moveRouteDown(index: number): void {
      if (index < this.platformRoutes.length - 1) {
        const temp = this.platformRoutes[index];
        this.platformRoutes[index] = this.platformRoutes[index + 1];
        this.platformRoutes[index + 1] = temp;
        this.platformRoutes = [...this.platformRoutes];
      }
    },

    async saveRoutesInternal(): Promise<void> {
      const config = this.updatingPlatformConfig as Record<string, unknown> | null;
      const originalPlatformId = this.originalUpdatingPlatformId || (config?.id as string);
      const newPlatformId = (config?.id as string) || originalPlatformId;

      if (!originalPlatformId && !newPlatformId) {
        throw new Error(this.tm("messages.platformIdMissing"));
      }

      try {
        const routesRes = await axios.get("/api/config/umo_abconf_routes");
        const fullRoutingTable = routesRes.data.data.routing as Record<string, string>;

        for (const umop in fullRoutingTable) {
          if (
            (originalPlatformId &&
              this.isUmopMatchPlatform(umop, originalPlatformId)) ||
            (newPlatformId && this.isUmopMatchPlatform(umop, newPlatformId))
          ) {
            delete fullRoutingTable[umop];
          }
        }

        for (const route of this.platformRoutes) {
          const messageType =
            route.messageType === "*" ? "*" : route.messageType;
          const sessionId = route.sessionId === "*" ? "*" : route.sessionId;
          const platformIdForRoute = newPlatformId || originalPlatformId;
          const newUmop = `${platformIdForRoute}:${messageType}:${sessionId}`;

          if (route.configId) {
            fullRoutingTable[newUmop] = route.configId;
          }
        }

        await axios.post("/api/config/umo_abconf_route/update_all", {
          routing: fullRoutingTable,
        });
      } catch (_err) {
        console.error("保存路由表失败:", _err);
        throw new Error(
          this.tm("messages.routingSaveFailed", { message: this.getErrorMessage(_err) }),
        );
      }
    },

    toggleEditMode(): void {
      this.isEditingRoutes = !this.isEditingRoutes;
    },
    toggleConfigSection(): void {
      this.showConfigSection = !this.showConfigSection;
    },

    getConfigName(configId: string): string {
      const config = this.configInfoList.find((c: ConfigInfo) => c.id === configId);
      return config ? config.name : configId;
    },

    isUmopMatchPlatform(umop: string, platformId: string): boolean {
      if (!umop) return false;
      const parts = umop.split(":");
      if (parts.length !== 3) return false;
      const platform = parts[0];
      return platform === platformId || platform === "" || platform === "*";
    },

    getMessageTypeLabel(messageType: string): string {
      const typeMap: Record<string, string> = {
        "*": this.tm("createDialog.messageTypeLabels.all"),
        "": this.tm("createDialog.messageTypeLabels.all"),
        GroupMessage: this.tm("createDialog.messageTypeLabels.group"),
        FriendMessage: this.tm("createDialog.messageTypeLabels.friend"),
      };
      return typeMap[messageType] || messageType;
    },

    toggleShowConfigSection(): void {
      this.showConfigSection = false;
      this.showConfigSection = true;
    },

    prepareData(): void {
      this.getConfigInfoList();
      this.getConfigForPreview(this.selectedAbConfId);
      const config = this.updatingPlatformConfig as Record<string, unknown> | null;
      if (this.updatingMode && config && config.id) {
        this.getPlatformConfigs(config.id as string);
      }
    },
    scrollDialogToBottom(): void {
      const ref = this.$refs.dialogScrollContainer;
      if (!ref) return;
      const el = ((ref as { $el?: HTMLElement }).$el || ref) as HTMLElement;
      const scrollOptions: ScrollToOptions = { top: el.scrollHeight, behavior: "smooth" };
      if (typeof el.scrollTo === "function") {
        el.scrollTo(scrollOptions);
      } else {
        el.scrollTop = el.scrollHeight;
      }
    },
    getErrorMessage(err: unknown): string {
      const ae = err as { response?: { data?: { message?: string } }; message?: string };
      return ae.response?.data?.message || ae.message || String(err);
    },
  },
};
</script>

<style>
.v-select__selection-text {
  font-size: 12px;
}

.add-platform-body {
  overscroll-behavior: contain;
}

.platform-option-logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
  margin-right: 16px;
}

.platform-selection-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.platform-type-field {
  width: min(100%, 320px);
  max-width: 100%;
}

.config-file-field {
  width: min(100%, 320px);
  max-width: 100%;
}

.route-source-field {
  min-width: 250px;
  gap: 8px;
  flex-wrap: wrap;
}

.route-message-type-field {
  width: 140px;
  max-width: 140px;
  flex: 0 0 140px;
}

.route-config-cell {
  gap: 8px;
  flex-wrap: wrap;
}

.route-config-field {
  width: 100%;
  min-width: 200px;
  max-width: 260px;
}

.config-drawer-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.config-drawer-card {
  width: clamp(320px, 60vw, 820px);
  height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  margin: 16px;
}

.config-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px 20px;
}

.config-drawer-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 16px 24px 16px;
}

@media (max-width: 700px) {
  .add-platform-body {
    padding: 16px !important;
    margin-left: 0 !important;
  }

  .platform-option-logo {
    width: 28px;
    height: 28px;
    margin-right: 12px;
  }

  .platform-selection-logo {
    width: 18px;
    height: 18px;
  }

  .platform-type-field,
  .config-file-field {
    width: 100%;
  }

  .config-mode-field-row {
    margin-left: 0 !important;
    width: 100%;
    flex-wrap: wrap;
  }

  .route-toolbar {
    align-items: flex-start !important;
    gap: 8px;
    flex-direction: column;
  }

  .route-source-field {
    min-width: 0;
    width: 100%;
  }

  .route-message-type-field {
    width: 100%;
    max-width: none;
    flex-basis: 100%;
  }

  .route-config-field {
    min-width: 0;
    max-width: none;
  }

  .platform-route-table .v-table__wrapper {
    overflow-x: auto;
  }

  .platform-route-table .v-table__wrapper > table {
    min-width: 640px;
  }

  .config-drawer-card {
    width: calc(100vw - 16px);
    height: calc(100vh - 16px);
    margin: 8px;
  }

  .config-drawer-header {
    padding: 12px 14px 10px 14px;
  }

  .config-drawer-content {
    padding: 12px 12px 20px 12px;
  }
}
</style>
