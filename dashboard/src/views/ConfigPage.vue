<template>
  <div class="config-page-root">
    <div class="config-page__content">
      <div v-if="selectedConfigID || isSystemConfig" class="mt-4 config-panel">
        <div class="config-toolbar">
          <div class="config-toolbar-controls">
            <v-select
              v-if="!isSystemConfig"
              class="config-select"
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
            >
            </v-select>
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
              @update:model-value="onConfigSearchInput"
            />
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
              {{ tm('messages.unsavedChangesNotice') }}
            </v-banner>
          </div>
        </v-slide-y-transition>
        <!-- <v-progress-linear v-if="!fetched" indeterminate color="primary"></v-progress-linear> -->

        <v-slide-y-transition mode="out-in">
          <div
            v-if="(selectedConfigID || isSystemConfig) && fetched"
            :key="configContentKey"
            class="config-content"
          >
            <!-- 可视化编辑 -->
            <AstrBotCoreConfigWrapper
              :metadata="metadata"
              :config-data="config_data"
              :search-keyword="configSearchKeyword"
            />
          </div>
        </v-slide-y-transition>

        <!-- 浮动按钮放在 transition 外部 -->
        <FloatingActionStack
          v-if="(selectedConfigID || isSystemConfig) && fetched"
          :label="tm('actions.save')"
        >
          <v-tooltip :text="tm('actions.save')" location="left">
            <template #activator="{ props: tooltipProps }">
              <v-btn
                v-bind="tooltipProps"
                icon="mdi-content-save"
                size="x-large"
                color="primary"
                @click="updateConfig"
              >
              </v-btn>
            </template>
          </v-tooltip>

          <v-tooltip :text="tm('codeEditor.title')" location="left">
            <template #activator="{ props: tooltipProps }">
              <v-btn
                v-bind="tooltipProps"
                icon="mdi-code-json"
                size="x-large"
                color="primary"
                @click="
                  configToString();
                  codeEditorDialog = true;
                "
              >
              </v-btn>
            </template>
          </v-tooltip>

          <v-tooltip v-if="!isSystemConfig" text="测试当前配置" location="left">
            <template #activator="{ props: tooltipProps }">
              <v-btn
                v-bind="tooltipProps"
                icon="mdi-chat-processing"
                size="x-large"
                color="secondary"
                @click="openTestChat"
              >
              </v-btn>
            </template>
          </v-tooltip>
        </FloatingActionStack>
      </div>
    </div>

    <!-- Full Screen Editor Dialog -->
    <v-dialog
      v-model="codeEditorDialog"
      fullscreen
      transition="dialog-bottom-transition"
      scrollable
    >
      <v-card class="app-dialog config-editor-dialog">
        <v-toolbar color="primary">
          <v-btn
            icon
            :aria-label="tm('buttons.close')"
            @click="codeEditorDialog = false"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
          <v-toolbar-title>{{ tm('codeEditor.title') }}</v-toolbar-title>
          <v-spacer></v-spacer>
          <v-toolbar-items class="config-editor-toolbar-actions">
            <v-btn class="ms-4" size="small" @click="configToString()">{{
              tm('editor.revertCode')
            }}</v-btn>
            <v-btn
              v-if="config_data_has_changed"
              class="ms-4"
              size="small"
              @click="applyStrConfig()"
              >{{ tm('editor.applyConfig') }}</v-btn
            >
            <small class="ms-4">💡 {{ tm('editor.applyTip') }}</small>
          </v-toolbar-items>
        </v-toolbar>
        <v-card-text class="pa-0">
          <VueMonacoEditor
            v-model:value="config_data_str"
            language="json"
            theme="vs-dark"
            class="config-editor"
          >
          </VueMonacoEditor>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Config Management Dialog -->
    <v-dialog v-model="configManageDialog" max-width="800px" scrollable>
      <v-card class="app-dialog config-manage-dialog__card">
        <v-card-title class="d-flex align-center justify-space-between">
          <span class="text-h4">{{ tm('configManagement.title') }}</span>
          <v-btn
            icon="mdi-close"
            variant="text"
            :aria-label="tm('buttons.close')"
            @click="configManageDialog = false"
          ></v-btn>
        </v-card-title>

        <v-card-text class="config-manage-dialog__content">
          <small>{{ tm('configManagement.description') }}</small>
          <div class="mt-6 mb-4">
            <v-btn
              prepend-icon="mdi-plus"
              variant="tonal"
              color="primary"
              @click="startCreateConfig"
            >
              {{ tm('configManagement.newConfig') }}
            </v-btn>
          </div>

          <!-- Config List -->
          <v-list lines="two">
            <v-list-item
              v-for="config in configInfoList"
              :key="config.id"
              :title="config.name"
            >
              <template #append>
                <div class="inline-control-row">
                  <v-btn
                    icon="mdi-content-copy"
                    size="small"
                    variant="text"
                    color="primary"
                    :aria-label="tm('configManagement.copyConfig')"
                    @click="startCopyConfig(config)"
                  ></v-btn>
                  <v-btn
                    v-if="config.id !== 'default'"
                    icon="mdi-pencil"
                    size="small"
                    variant="text"
                    color="warning"
                    :aria-label="tm('configManagement.editConfig')"
                    @click="startEditConfig(config)"
                  ></v-btn>
                  <v-btn
                    v-if="config.id !== 'default'"
                    icon="mdi-delete"
                    size="small"
                    variant="text"
                    color="error"
                    :aria-label="tm('configManagement.deleteConfig')"
                    @click="confirmDeleteConfig(config)"
                  ></v-btn>
                </div>
              </template>
            </v-list-item>
          </v-list>

          <!-- Create/Edit Form -->
          <v-divider v-if="showConfigForm" class="my-6"></v-divider>

          <div v-if="showConfigForm">
            <h3 class="mb-4">{{ configFormTitle }}</h3>

            <h4>{{ tm('configManagement.configName') }}</h4>

            <v-text-field
              v-model="configFormData.name"
              :label="tm('configManagement.fillConfigName')"
              variant="outlined"
              class="mt-4 mb-4"
              hide-details
            ></v-text-field>

            <div class="d-flex justify-end mt-4 ga-2">
              <v-btn variant="text" @click="cancelConfigForm">{{
                tm('buttons.cancel')
              }}</v-btn>
              <v-btn
                color="primary"
                :disabled="isConfigFormSaveDisabled"
                @click="saveConfigForm"
              >
                {{
                  isEditingConfig ? tm('buttons.update') : tm('buttons.create')
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
      elevation="4"
      :color="save_message_success"
    >
      {{ save_message }}
    </v-snackbar>

    <DashboardTwoFactorDialog
      v-model="configSave2faDialogVisible"
      :error-message="configSave2faError"
      :saving="configSave2faSaving"
      :rotation-hint="configSave2faRotationHint"
      @confirm="handleConfigSave2faConfirm"
      @cancel="handleConfigSave2faCancel"
    />

    <!-- 测试聊天抽屉 -->
    <v-overlay
      v-model="testChatDrawer"
      class="test-chat-overlay"
      location="right"
      transition="slide-x-reverse-transition"
      :scrim="true"
      @click:outside="closeTestChat"
    >
      <v-card class="test-chat-card" elevation="4">
        <div class="test-chat-header">
          <div>
            <span class="text-h6">测试配置</span>
            <div
              v-if="selectedConfigInfo.name"
              class="text-caption text-medium-emphasis"
            >
              {{ selectedConfigInfo.name }} ({{ testConfigId }})
            </div>
          </div>
          <v-btn
            icon
            variant="text"
            :aria-label="tm('buttons.close')"
            @click="closeTestChat"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </div>
        <v-divider></v-divider>
        <div class="test-chat-content">
          <StandaloneChat v-if="testChatDrawer" :config-id="testConfigId" />
        </div>
      </v-card>
    </v-overlay>

    <!-- 未保存更改确认弹窗 -->
    <UnsavedChangesConfirmDialog ref="unsavedChangesDialog" />

    <DashboardStepUpDialog
      v-model="stepUpDialogOpen"
      :loading="stepUpLoading"
      :error-message="stepUpErrorMessage"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { configProfileApi, systemConfigApi, type OpenConfig } from '@/api/v1';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';
import StandaloneChat from '@/components/chat/StandaloneChat.vue';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import '@/utils/monacoLoader';
import { useModuleI18n } from '@/i18n/composables';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import UnsavedChangesConfirmDialog from '@/components/config/UnsavedChangesConfirmDialog.vue';
import FloatingActionStack from '@/components/ui/FloatingActionStack.vue';
import DashboardTwoFactorDialog from '@/components/shared/DashboardTwoFactorDialog.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { runConfigMutationWithStepUp } from '@/utils/configStepUp';
import { stepUpHeaders } from '@/utils/stepUp';
import { normalizeTextInput } from '@/utils/inputValue';

defineOptions({
  name: 'ConfigPage',
});

type ConfigType = 'normal' | 'system';
type ConfigFormMode = 'create' | 'edit' | 'copy';
type SnackbarColor = '' | 'success' | 'error' | 'warning';
type UnsavedDialogResult = boolean | 'close';

interface ConfigInfoItem {
  id: string;
  name: string;
  umop?: unknown[];
}

interface ConfigFormData {
  name: string;
}

interface ConfigPostData {
  conf_id?: string;
  config: OpenConfig;
}

interface SaveResult {
  success: boolean;
  requires2fa?: boolean;
}

interface UnsavedDialogOptions {
  title: string;
  message: string;
  confirmHint: string;
  cancelHint: string;
  closeHint: string;
}

interface UnsavedChangesDialogExposed {
  open(options: UnsavedDialogOptions): Promise<UnsavedDialogResult>;
}

const props = withDefaults(
  defineProps<{
    initialConfigId?: string | null;
  }>(),
  {
    initialConfigId: null,
  },
);

const route = useRoute();
const router = useRouter();
const { tm } = useModuleI18n('features/config');
const { tm: tmMeta } = useModuleI18n('features/config-metadata');
const confirmDialog = useConfirmDialog();
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const unsavedChangesDialog = ref<UnsavedChangesDialogExposed | null>(null);

const codeEditorDialog = ref(false);
const configManageDialog = ref(false);
const showConfigForm = ref(false);
const isEditingConfig = ref(false);
const isCopyingConfig = ref(false);
const config_data_has_changed = ref(false);
const config_data_str = ref('');
const config_data = ref<OpenConfig>({ config: {} });
const fetched = ref(false);
const metadata = ref<OpenConfig>({});
const save_message_snack = ref(false);
const save_message = ref('');
const save_message_success = ref<SnackbarColor>('');
const configContentKey = ref(0);
const lastSavedConfigSnapshot = ref('');
const configSave2faDialogVisible = ref(false);
const configSave2faError = ref('');
const configSave2faSaving = ref(false);
const configSave2faRotationHint = ref('');
const configSavePendingPostData = ref<ConfigPostData | null>(null);
const configSavePendingHeaders = ref<Record<string, string>>({});
const configType = ref<ConfigType>('normal');
const configSearchKeyword = ref('');
const isSystemConfig = ref(false);
const selectedConfigID = ref<string | null>(null);
const currentConfigId = ref<string | null>(null);
const configInfoList = ref<ConfigInfoItem[]>([]);
const configFormData = ref<ConfigFormData>({ name: '' });
const editingConfigId = ref<string | null>(null);
const copySourceConfigId = ref('');
const testChatDrawer = ref(false);
const testConfigId = ref<string | null>(null);
const syncingConfigString = ref(false);

const messages = computed(() => ({
  loadError: tm('messages.loadError'),
  saveSuccess: tm('messages.saveSuccess'),
  saveError: tm('messages.saveError'),
  configApplied: tm('messages.configApplied'),
  configApplyError: tm('messages.configApplyError'),
}));

const selectedConfigInfo = computed<ConfigInfoItem>(() => {
  return (
    configInfoList.value.find((info) => info.id === selectedConfigID.value) ?? {
      id: '',
      name: '',
      umop: [],
    }
  );
});

const configFormTitle = computed(() => {
  if (isEditingConfig.value) {
    return tm('configManagement.editConfig');
  }
  if (isCopyingConfig.value) {
    return tm('configManagement.copyConfig');
  }
  return tm('configManagement.newConfig');
});

const isConfigFormSaveDisabled = computed(() => {
  const isNameEmpty = !normalizeConfigName(configFormData.value.name);
  return isNameEmpty || (isCopyingConfig.value && !copySourceConfigId.value);
});

const configSelectItems = computed<ConfigInfoItem[]>(() => {
  return [
    ...configInfoList.value,
    {
      id: '_%manage%_',
      name: tm('configManagement.manageConfigs'),
      umop: [],
    },
  ];
});

const hasUnsavedChanges = computed(() => {
  if (!fetched.value) {
    return false;
  }
  return getConfigSnapshot(config_data.value) !== lastSavedConfigSnapshot.value;
});

watch(config_data_str, () => {
  if (!syncingConfigString.value) {
    config_data_has_changed.value = true;
  }
});

watch(
  () => route.fullPath,
  async (newVal) => {
    if (extractConfigTypeFromHash(newVal) === 'system') {
      await router.replace('/settings#system-config');
      return;
    }
    await syncConfigTypeFromHash(newVal);
  },
);

watch(
  () => props.initialConfigId,
  (newVal) => {
    if (!newVal) {
      return;
    }
    if (selectedConfigID.value !== newVal) {
      void getConfigInfoList(newVal);
    }
  },
);

onMounted(() => {
  const hashConfigType = extractConfigTypeFromHash(route.fullPath || '');
  if (hashConfigType === 'system') {
    void router.replace('/settings#system-config');
    return;
  }

  configType.value = 'normal';
  isSystemConfig.value = false;

  void getConfigInfoList(props.initialConfigId ?? 'default');
  window.addEventListener('astrbot-locale-changed', handleLocaleChange);
});

onBeforeUnmount(() => {
  window.removeEventListener('astrbot-locale-changed', handleLocaleChange);
});

onBeforeRouteLeave(async () => {
  if (!hasUnsavedChanges.value) {
    return true;
  }

  const confirmed = await openUnsavedChangesDialog(
    tm('unsavedChangesWarning.leavePage'),
  );
  if (confirmed === 'close') {
    return false;
  }
  if (!confirmed) {
    return true;
  }

  const result = await updateConfig();
  if (isSystemConfig.value) {
    return false;
  }
  if (result?.success) {
    await delay(800);
    return true;
  }
  return false;
});

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function getString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function normalizeConfigInfo(value: unknown): ConfigInfoItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = getString(record?.id);
  const name = getString(record?.name);
  if (!id || !name) {
    return null;
  }
  return {
    id,
    name,
    umop: Array.isArray(record.umop) ? record.umop : undefined,
  };
}

function toOpenConfig(value: unknown): OpenConfig {
  return asRecord(value) ?? {};
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function delay(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function extractErrorMessage(error: unknown): string | null {
  const errorRecord = asRecord(error);
  const response = asRecord(errorRecord?.response);
  const data = asRecord(response?.data);
  return getString(data?.message);
}

function showSnack(message: string, color: SnackbarColor) {
  save_message.value = message;
  save_message_success.value = color;
  save_message_snack.value = true;
}

function createUnsavedChangesDialogOptions(
  message: string,
): UnsavedDialogOptions {
  return {
    title: tm('unsavedChangesWarning.dialogTitle'),
    message,
    confirmHint: `${tm('unsavedChangesWarning.options.saveAndSwitch')}:${tm('unsavedChangesWarning.options.confirm')}`,
    cancelHint: `${tm('unsavedChangesWarning.options.discardAndSwitch')}:${tm('unsavedChangesWarning.options.cancel')}`,
    closeHint: `${tm('unsavedChangesWarning.options.closeCard')}:"x"`,
  };
}

async function openUnsavedChangesDialog(message: string) {
  return (
    (await unsavedChangesDialog.value?.open(
      createUnsavedChangesDialogOptions(message),
    )) ?? false
  );
}

function normalizeConfigName(name: unknown) {
  return typeof name === 'string' ? name.trim() : '';
}

function getConfigSnapshot(config: OpenConfig) {
  return JSON.stringify(config ?? {});
}

function extractConfigTypeFromHash(hash: string): ConfigType | null {
  const rawHash = String(hash || '');
  const lastHashIndex = rawHash.lastIndexOf('#');
  if (lastHashIndex === -1) {
    return null;
  }
  const cleanHash = rawHash.slice(lastHashIndex + 1);
  return cleanHash === 'system' || cleanHash === 'normal' ? cleanHash : null;
}

async function syncConfigTypeFromHash(hash: string) {
  const nextConfigType = extractConfigTypeFromHash(hash);
  if (!nextConfigType || nextConfigType === configType.value) {
    return false;
  }

  configType.value = nextConfigType;
  await onConfigTypeToggle();
  return true;
}

function handleLocaleChange() {
  if (isSystemConfig.value) {
    void getConfig();
  } else if (selectedConfigID.value) {
    void getConfig(selectedConfigID.value);
  }
}

function onConfigSearchInput(value: unknown) {
  configSearchKeyword.value = normalizeTextInput(value);
}

async function getConfigInfoList(targetConfigId?: string | null) {
  try {
    const res = await configProfileApi.list();
    const payload = asRecord(res.data.data);
    const items = Array.isArray(payload?.info_list) ? payload.info_list : [];
    configInfoList.value = items
      .map(normalizeConfigInfo)
      .filter((item): item is ConfigInfoItem => item !== null);

    if (!targetConfigId) {
      return;
    }

    const matchedItem = configInfoList.value.find(
      (item) => item.id === targetConfigId,
    );
    const activeItem = matchedItem ?? configInfoList.value[0];
    if (!activeItem) {
      return;
    }

    selectedConfigID.value = activeItem.id;
    currentConfigId.value = activeItem.id;
    await getConfig(activeItem.id);
  } catch {
    showSnack(messages.value.loadError, 'error');
  }
}

async function getConfig(targetConfigId?: string | null) {
  fetched.value = false;

  try {
    const res = isSystemConfig.value
      ? await systemConfigApi.get()
      : await configProfileApi.get(
          targetConfigId || selectedConfigID.value || '',
        );
    const payload = asRecord(res.data.data);
    config_data.value = toOpenConfig(payload?.config);
    metadata.value = toOpenConfig(payload?.metadata);
    lastSavedConfigSnapshot.value = getConfigSnapshot(config_data.value);
    fetched.value = true;
    configContentKey.value += 1;

    await nextTick();
    if (!isSystemConfig.value) {
      currentConfigId.value = targetConfigId || selectedConfigID.value;
    }
  } catch {
    showSnack(messages.value.loadError, 'error');
  }
}

async function updateConfig(): Promise<SaveResult | undefined> {
  if (!fetched.value) {
    return undefined;
  }

  const postData: ConfigPostData = {
    config: deepClone(config_data.value),
    conf_id: isSystemConfig.value
      ? 'default'
      : (selectedConfigID.value ?? undefined),
  };
  return saveAstrbotConfig(postData);
}

async function saveAstrbotConfig(
  postData: ConfigPostData,
  headers: Record<string, string> = {},
  allow2faPrompt = true,
): Promise<SaveResult> {
  try {
    const confId = postData.conf_id || 'default';
    const requestHeaders = { ...headers };
    const res = await runConfigMutationWithStepUp(
      (stepUp) => {
        if (stepUp) {
          Object.assign(requestHeaders, stepUpHeaders(stepUp));
        }
        const requestConfig = {
          headers: requestHeaders,
          validateStatus: (status: number) =>
            (status >= 200 && status < 300) || status === 401,
        };
        return isSystemConfig.value
          ? systemConfigApi.update(postData.config, requestConfig)
          : configProfileApi.update(confId, postData.config, requestConfig);
      },
      confId,
      requestStepUp,
    );
    if (!res) {
      return { success: false };
    }

    const responseData = asRecord(res.data.data);
    if (res.status === 401 && responseData?.totp_required === true) {
      if (allow2faPrompt && !headers['X-2FA-Code']) {
        configSavePendingPostData.value = deepClone(postData);
        configSavePendingHeaders.value = { ...requestHeaders };
        configSave2faError.value = '';
        configSave2faRotationHint.value = getConfigSaveRotationHint(postData);
        configSave2faDialogVisible.value = true;
        return { success: false, requires2fa: true };
      }

      configSave2faError.value = tmMeta(
        'system_group.system.dashboard.totp.configSaveError',
      );
      configSave2faDialogVisible.value = true;
      return { success: false, requires2fa: true };
    }

    if (res.data.status === 'ok') {
      configSavePendingPostData.value = null;
      configSavePendingHeaders.value = {};
      configSave2faDialogVisible.value = false;
      configSave2faError.value = '';
      lastSavedConfigSnapshot.value = getConfigSnapshot(config_data.value);
      showSnack(res.data.message || messages.value.saveSuccess, 'success');
      return { success: true };
    }

    showSnack(res.data.message || messages.value.saveError, 'error');
    return { success: false };
  } catch {
    showSnack(messages.value.saveError, 'error');
    return { success: false };
  }
}

async function handleConfigSave2faConfirm(payload: string) {
  if (!configSavePendingPostData.value || configSave2faSaving.value) {
    return;
  }

  configSave2faSaving.value = true;
  configSave2faError.value = '';
  try {
    await saveAstrbotConfig(
      deepClone(configSavePendingPostData.value),
      {
        ...configSavePendingHeaders.value,
        'X-2FA-Code': payload,
      },
      false,
    );
  } finally {
    configSave2faSaving.value = false;
  }
}

function handleConfigSave2faCancel() {
  try {
    const savedConfig = JSON.parse(lastSavedConfigSnapshot.value) as unknown;
    const savedDashboard = asRecord(asRecord(savedConfig)?.dashboard);
    const savedTotp = asRecord(savedDashboard?.totp);
    const currentDashboard = asRecord(config_data.value.dashboard);
    const currentTotp = asRecord(currentDashboard?.totp);
    if (savedTotp && currentTotp) {
      currentTotp.enable = savedTotp.enable;
      currentTotp.secret = savedTotp.secret;
      currentTotp.recovery_code_hash = savedTotp.recovery_code_hash;
    }
  } catch {
    // ignore parse errors
  }

  configSavePendingPostData.value = null;
  configSavePendingHeaders.value = {};
  configSave2faError.value = '';
  configSave2faDialogVisible.value = false;
}

function getConfigSaveRotationHint(postData: ConfigPostData) {
  const postedDashboard = asRecord(postData.config.dashboard);
  const postedTotp = asRecord(postedDashboard?.totp);
  const postedSecret = getString(postedTotp?.secret);
  if (postedSecret?.trim()) {
    return tmMeta('system_group.system.dashboard.totp.configSaveRotationHint');
  }
  return '';
}

function configToString() {
  syncingConfigString.value = true;
  config_data_str.value = JSON.stringify(config_data.value, null, 2);
  config_data_has_changed.value = false;
  void nextTick(() => {
    syncingConfigString.value = false;
  });
}

function applyStrConfig() {
  try {
    config_data.value = JSON.parse(config_data_str.value) as OpenConfig;
    config_data_has_changed.value = false;
    showSnack(messages.value.configApplied, 'success');
  } catch {
    showSnack(messages.value.configApplyError, 'error');
  }
}

async function createNewConfig(configName: string) {
  try {
    const res = await configProfileApi.create({
      name: configName,
    });
    if (res.data.status === 'ok') {
      const payload = asRecord(res.data.data);
      const confId = getString(payload?.conf_id);
      showSnack(res.data.message || messages.value.saveSuccess, 'success');
      await getConfigInfoList(confId || 'default');
      cancelConfigForm();
      return;
    }

    showSnack(res.data.message || tm('configManagement.createFailed'), 'error');
  } catch {
    showSnack(tm('configManagement.createFailed'), 'error');
  }
}

function hasDuplicateConfigName(name: string, excludeId: string | null = null) {
  const normalizedName = normalizeConfigName(name);
  if (!normalizedName) {
    return false;
  }
  return configInfoList.value.some((config) => {
    if (!config.name) {
      return false;
    }
    if (excludeId && config.id === excludeId) {
      return false;
    }
    return normalizeConfigName(config.name) === normalizedName;
  });
}

async function onConfigSelect(value: unknown) {
  const nextConfigId = getString(value);
  if (!nextConfigId) {
    return;
  }

  if (nextConfigId === '_%manage%_') {
    configManageDialog.value = true;
    await nextTick();
    selectedConfigID.value = selectedConfigInfo.value.id || 'default';
    await getConfig(selectedConfigID.value);
    return;
  }

  if (!hasUnsavedChanges.value) {
    selectedConfigID.value = nextConfigId;
    await getConfig(nextConfigId);
    return;
  }

  const prevConfigId = isSystemConfig.value
    ? 'default'
    : currentConfigId.value || selectedConfigID.value || 'default';
  const saveAndSwitch = await openUnsavedChangesDialog(
    tm('unsavedChangesWarning.switchConfig'),
  );
  if (saveAndSwitch === 'close') {
    return;
  }
  if (saveAndSwitch) {
    const currentSelectedId = selectedConfigID.value;
    selectedConfigID.value = prevConfigId;
    const result = await updateConfig();
    selectedConfigID.value = currentSelectedId;
    if (result?.success) {
      selectedConfigID.value = nextConfigId;
      await getConfig(nextConfigId);
    }
    return;
  }

  selectedConfigID.value = nextConfigId;
  await getConfig(nextConfigId);
}

function setConfigFormState(options?: {
  mode?: ConfigFormMode;
  config?: ConfigInfoItem | null;
  visible?: boolean;
}) {
  const { mode = 'create', config = null, visible = true } = options ?? {};
  showConfigForm.value = visible;
  isEditingConfig.value = mode === 'edit';
  isCopyingConfig.value = mode === 'copy';
  editingConfigId.value = isEditingConfig.value && config ? config.id : null;
  copySourceConfigId.value = isCopyingConfig.value && config ? config.id : '';

  let name = '';
  if (isEditingConfig.value && config) {
    name = config.name || '';
  } else if (isCopyingConfig.value && config) {
    name = `${config.name || ''}-copy`;
  }
  configFormData.value = { name };
}

function startCreateConfig() {
  setConfigFormState({ mode: 'create' });
}

function startEditConfig(config: ConfigInfoItem) {
  setConfigFormState({ mode: 'edit', config });
}

function startCopyConfig(config: ConfigInfoItem) {
  setConfigFormState({ mode: 'copy', config });
}

function cancelConfigForm() {
  setConfigFormState({ visible: false });
}

function saveConfigForm() {
  const normalizedName = normalizeConfigName(configFormData.value.name);
  if (!normalizedName) {
    showSnack(tm('configManagement.pleaseEnterName'), 'error');
    return;
  }

  const excludeId = isEditingConfig.value ? editingConfigId.value : null;
  if (hasDuplicateConfigName(normalizedName, excludeId)) {
    showSnack(tm('configManagement.nameExists'), 'error');
    return;
  }

  configFormData.value.name = normalizedName;
  if (isEditingConfig.value) {
    void updateConfigInfo(normalizedName);
  } else if (isCopyingConfig.value) {
    void copyConfig(normalizedName);
  } else {
    void createNewConfig(normalizedName);
  }
}

async function copyConfig(configName: string) {
  try {
    const sourceRes = await configProfileApi.get(copySourceConfigId.value);
    const sourcePayload = asRecord(sourceRes.data.data);
    const sourceConfig = sourcePayload?.config;
    if (!sourceConfig) {
      showSnack(tm('configManagement.copyFailed'), 'error');
      return;
    }

    const createRes = await configProfileApi.create({
      name: configName,
      config: toOpenConfig(sourceConfig),
    });
    if (createRes.data.status === 'ok') {
      const createPayload = asRecord(createRes.data.data);
      const confId = getString(createPayload?.conf_id);
      showSnack(
        createRes.data.message || messages.value.saveSuccess,
        'success',
      );
      await getConfigInfoList(confId || 'default');
      cancelConfigForm();
      return;
    }

    showSnack(
      createRes.data.message || tm('configManagement.copyFailed'),
      'error',
    );
  } catch (error) {
    showSnack(
      extractErrorMessage(error) || tm('configManagement.copyFailed'),
      'error',
    );
  }
}

async function confirmDeleteConfig(config: ConfigInfoItem) {
  const message = tm('configManagement.confirmDelete').replace(
    '{name}',
    config.name,
  );
  if (await askForConfirmationDialog(message, confirmDialog)) {
    await deleteConfig(config.id);
  }
}

async function deleteConfig(configId: string) {
  try {
    const res = await configProfileApi.delete(configId);
    if (res.data.status === 'ok') {
      showSnack(res.data.message || messages.value.saveSuccess, 'success');
      cancelConfigForm();
      await getConfigInfoList('default');
      return;
    }

    showSnack(res.data.message || tm('configManagement.deleteFailed'), 'error');
  } catch {
    showSnack(tm('configManagement.deleteFailed'), 'error');
  }
}

async function updateConfigInfo(configName: string) {
  if (!editingConfigId.value) {
    return;
  }

  try {
    const res = await configProfileApi.rename(
      editingConfigId.value,
      configName,
    );
    if (res.data.status === 'ok') {
      showSnack(res.data.message || messages.value.saveSuccess, 'success');
      await getConfigInfoList(editingConfigId.value);
      cancelConfigForm();
      return;
    }

    showSnack(res.data.message || tm('configManagement.updateFailed'), 'error');
  } catch {
    showSnack(tm('configManagement.updateFailed'), 'error');
  }
}

async function onConfigTypeToggle() {
  if (hasUnsavedChanges.value) {
    const saveAndSwitch = await openUnsavedChangesDialog(
      tm('unsavedChangesWarning.leavePage'),
    );
    if (saveAndSwitch === 'close') {
      const originalHash = isSystemConfig.value ? '#system' : '#normal';
      await router.replace(`/config${originalHash}`);
      configType.value = isSystemConfig.value ? 'system' : 'normal';
      return;
    }
    if (saveAndSwitch) {
      await updateConfig();
      if (isSystemConfig.value) {
        await router.replace('/settings#system-config');
        return;
      }
    }
  }

  isSystemConfig.value = configType.value === 'system';
  fetched.value = false;
  if (isSystemConfig.value) {
    await getConfig();
  } else if (selectedConfigID.value) {
    await getConfig(selectedConfigID.value);
  } else {
    await getConfigInfoList('default');
  }
}

function openTestChat() {
  if (!selectedConfigID.value) {
    showSnack('请先选择一个配置文件', 'warning');
    return;
  }
  testConfigId.value = selectedConfigID.value;
  testChatDrawer.value = true;
}

function closeTestChat() {
  testChatDrawer.value = false;
  testConfigId.value = null;
}
</script>

<style scoped>
.config-page__content,
.config-panel {
  display: flex;
  flex-direction: column;
}

.config-page__content {
  align-items: center;
}

.config-panel {
  align-items: flex-start;
}

.config-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: var(--astrbot-space-3);
  margin-bottom: var(--astrbot-space-4);
  padding-right: var(--astrbot-space-4);
}

.config-toolbar-controls {
  display: flex;
  align-items: center;
  gap: var(--astrbot-space-3);
}

.config-select {
  min-width: 130px;
}

.config-search-input {
  min-width: 280px;
}

.config-content {
  width: 100%;
}

.unsaved-changes-banner {
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant));
}

.unsaved-changes-banner-wrap {
  position: sticky;
  top: calc(var(--v-layout-top, 64px));
  z-index: 20;
  width: 100%;
  margin-bottom: 6px;
}

.text-warning code {
  padding: 2px var(--astrbot-space-1);
  border-radius: 4px;
  background-color: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-warning));
  font-size: 13px;
  font-weight: 500;
}

.text-warning strong {
  color: rgb(var(--v-theme-warning));
}

.text-warning small {
  color: rgb(var(--v-theme-on-surface-variant));
  font-style: italic;
}

.config-editor-toolbar-actions {
  display: flex;
  align-items: center;
}

.config-editor {
  height: calc(100dvh - 64px);
}

@media (min-width: 768px) {
  .config-panel {
    width: 750px;
  }
}

@media (max-width: 767px) {
  .config-panel {
    width: 100%;
  }

  .config-toolbar {
    padding-right: 0;
  }

  .config-toolbar-controls {
    width: 100%;
    flex-wrap: wrap;
  }

  .config-select,
  .config-search-input {
    width: 100%;
    min-width: 0;
  }
}

/* 测试聊天抽屉样式 */
.test-chat-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.test-chat-card {
  width: clamp(320px, 50vw, 720px);
  height: calc(100dvh - 32px);
  display: flex;
  flex-direction: column;
  margin: 16px;
}

.config-manage-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 960px);
}

.config-manage-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
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
  border-radius: 0 0 8px 8px;
}
</style>
