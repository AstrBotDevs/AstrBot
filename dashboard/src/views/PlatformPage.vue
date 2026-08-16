<template>
  <div class="platform-page">
    <v-container fluid class="pa-0">
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
        <div>
          <h1 class="text-h1 font-weight-bold mb-2 d-flex align-center">
            <v-icon class="me-2">mdi-robot</v-icon>{{ tm('title') }}
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4">
            {{ tm('subtitle') }}
          </p>
        </div>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          variant="tonal"
          size="x-large"
          @click="
            updatingMode = false;
            showAddPlatformDialog = true;
          "
        >
          {{ tm('addAdapter') }}
        </v-btn>
      </v-row>

      <div>
        <v-row v-if="platformList.length === 0">
          <v-col cols="12" class="text-center pa-8">
            <v-icon size="64" color="on-surface-variant">mdi-connection</v-icon>
            <p class="text-medium-emphasis mt-4">{{ tm('emptyText') }}</p>
          </v-col>
        </v-row>

        <v-row v-else>
          <v-col
            v-for="(platform, index) in platformList"
            :key="index"
            cols="12"
            md="6"
            lg="4"
            xl="3"
          >
            <item-card
              :item="platform"
              title-field="id"
              enabled-field="enable"
              variant="outlined"
              :bglogo="getPlatformLogo(platform)"
              @toggle-enabled="platformStatusChange"
              @delete="deletePlatform"
              @edit="editPlatform"
            >
              <template #item-details>
                <!-- 平台运行状态 - 只在非运行状态或有错误时显示 -->
                <div
                  v-if="shouldShowPlatformStatus(platform)"
                  class="platform-status-row mb-2"
                >
                  <!-- 状态 chip - 只在非 running 状态时显示 -->
                  <v-chip
                    v-if="getPlatformStatus(platform) !== 'running'"
                    size="small"
                    :color="getStatusColor(getPlatformStatus(platform))"
                    variant="tonal"
                    class="status-chip"
                  >
                    <v-icon size="small" start>{{
                      getStatusIcon(getPlatformStatus(platform))
                    }}</v-icon>
                    {{ getRuntimeStatusLabel(platform) }}
                  </v-chip>
                  <!-- 错误数量提示 -->
                  <v-chip
                    v-if="getPlatformErrorCount(platform) > 0"
                    size="small"
                    color="error"
                    variant="tonal"
                    class="error-chip"
                    :class="{
                      'ms-2': getPlatformStatus(platform) !== 'running',
                    }"
                    @click.stop="showErrorDetails(platform)"
                  >
                    <v-icon size="small" start>mdi-bug</v-icon>
                    {{ getPlatformErrorCount(platform) }}
                    {{ tm('runtimeStatus.errors') }}
                  </v-chip>
                </div>
                <div
                  v-if="hasQrPayloadForPlatform(platform)"
                  class="platform-qr-chip"
                >
                  <v-chip
                    size="small"
                    color="primary"
                    variant="tonal"
                    class="platform-qr-chip-item"
                    @click.stop="openPlatformQrDialogByPlatform(platform)"
                  >
                    <v-icon size="small" start>mdi-qrcode</v-icon>
                    {{ tm('platformQr.show') }}
                  </v-chip>
                </div>
                <div v-if="hasUnifiedWebhook(platform)" class="webhook-info">
                  <v-chip
                    size="small"
                    color="primary"
                    variant="tonal"
                    class="webhook-chip"
                    @click.stop="openWebhookDialogForPlatform(platform)"
                  >
                    <v-icon size="small" start>mdi-webhook</v-icon>
                    {{ tm('viewWebhook') }}
                  </v-chip>
                </div>
                <div
                  v-if="getSupportedActions(platform).length > 0"
                  class="platform-actions"
                >
                  <div class="platform-actions__label">
                    {{ tm('capabilities.supportedActions') }}
                  </div>
                  <div class="platform-actions__chips">
                    <v-chip
                      v-for="action in getSupportedActions(platform)"
                      :key="action"
                      size="x-small"
                      variant="outlined"
                      color="secondary"
                    >
                      {{ getSupportedActionLabel(action) }}
                    </v-chip>
                  </div>
                  <div class="platform-actions__toolbar">
                    <v-btn
                      size="small"
                      variant="tonal"
                      color="secondary"
                      prepend-icon="mdi-lightning-bolt-outline"
                      @click.stop="openQuickActionDialog(platform)"
                    >
                      {{ tm('quickActions.trigger') }}
                    </v-btn>
                  </div>
                </div>
              </template>
            </item-card>
          </v-col>
        </v-row>
      </div>

      <!-- 日志部分 -->
      <v-card elevation="0" class="mt-4 mb-10">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon class="me-2">mdi-console-line</v-icon>
          <span class="text-h4">{{ tm('logs.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn
            variant="text"
            color="primary"
            @click="showConsole = !showConsole"
          >
            {{ showConsole ? tm('logs.collapse') : tm('logs.expand') }}
            <v-icon>{{
              showConsole ? 'mdi-chevron-up' : 'mdi-chevron-down'
            }}</v-icon>
          </v-btn>
        </v-card-title>

        <v-expand-transition>
          <v-card-text v-if="showConsole" class="pa-0">
            <ConsoleDisplayer class="platform-console"></ConsoleDisplayer>
          </v-card-text>
        </v-expand-transition>
      </v-card>
    </v-container>

    <!-- 添加平台适配器对话框 -->
    <AddNewPlatform
      v-model:show="showAddPlatformDialog"
      :metadata="metadata"
      :config-data="config_data"
      :updating-mode="updatingMode"
      :updating-platform-config="updatingPlatformConfig"
      :request-step-up="requestStepUp"
      @show-toast="showToast"
      @refresh-config="getConfig"
    />

    <!-- Webhook URL 对话框 -->
    <v-dialog v-model="showWebhookDialog" max-width="600">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
          <v-icon class="me-2" color="primary">mdi-webhook</v-icon>
          {{ tm('webhookDialog.title') }}
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <p class="text-body-2 text-medium-emphasis mb-3">
            {{ tm('webhookDialog.description') }}
          </p>
          <v-text-field
            :model-value="currentWebhookUrl"
            readonly
            variant="outlined"
            hide-details
            class="webhook-url-field"
          >
            <template #append-inner>
              <v-btn
                icon
                size="small"
                variant="text"
                @click="copyWebhookUrl(currentWebhookUuid)"
              >
                <v-icon>mdi-content-copy</v-icon>
              </v-btn>
            </template>
          </v-text-field>
        </v-card-text>
        <v-card-actions class="pa-4 pt-2">
          <v-spacer></v-spacer>
          <v-btn
            variant="tonal"
            color="primary"
            @click="showWebhookDialog = false"
          >
            {{ tm('webhookDialog.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="showQrDialog" max-width="480">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
          <v-icon class="me-2">mdi-qrcode</v-icon>
          {{ tm('platformQr.title') }}
        </v-card-title>
        <v-card-text class="px-4 pb-4">
          <div class="platform-qr-status">
            {{ tm('platformQr.status') }}:
            {{
              getPlatformQrLoginStat(currentQrPlatformId)?.qr_status ||
              tm('platformQr.waiting')
            }}
          </div>
          <QrCodeViewer
            :value="
              getPlatformQrLoginStat(currentQrPlatformId)?.qrcode_img_content ||
              getPlatformQrLoginStat(currentQrPlatformId)?.qrcode ||
              ''
            "
            :alt="tm('platformQr.title')"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer></v-spacer>
          <v-btn variant="tonal" color="primary" @click="showQrDialog = false">
            {{ tm('platformQr.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <PlatformQuickActionsDialog
      v-model="showQuickActionDialog"
      :platform-id="currentQuickActionPlatformId"
      :supported-actions="currentQuickActionSupportedActions"
      :request-step-up="requestStepUp"
      @show-toast="showToast"
      @action-complete="getPlatformStats"
    />

    <DashboardStepUpDialog
      v-model="stepUpDialogOpen"
      :loading="stepUpLoading"
      :error-message="stepUpErrorMessage"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />

    <!-- 错误详情对话框 -->
    <v-dialog v-model="showErrorDialog" max-width="700" scrollable>
      <v-card class="platform-error-dialog__card">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
          <v-icon class="me-2" color="error">mdi-alert-circle</v-icon>
          {{ tm('errorDialog.title') }}
        </v-card-title>
        <v-card-text
          v-if="currentErrorPlatform"
          class="px-4 pb-4 platform-error-dialog__content"
        >
          <div class="mb-3">
            <strong>{{ tm('errorDialog.platformId') }}:</strong>
            {{ currentErrorPlatform.id }}
          </div>
          <div class="mb-3">
            <strong>{{ tm('errorDialog.errorCount') }}:</strong>
            {{ currentErrorPlatform.error_count }}
          </div>
          <div v-if="currentErrorPlatform.last_error" class="error-details">
            <div class="mb-2">
              <strong>{{ tm('errorDialog.lastError') }}:</strong>
            </div>
            <v-alert type="error" variant="tonal" class="mb-3">
              <div class="error-message">
                {{ currentErrorPlatform.last_error.message }}
              </div>
              <div class="error-time text-caption text-medium-emphasis mt-1">
                {{ tm('errorDialog.occurredAt') }}:
                {{
                  formatRuntimeErrorTimestamp(currentErrorPlatform.last_error)
                }}
              </div>
            </v-alert>
            <div v-if="currentErrorPlatform.last_error.traceback">
              <div class="mb-2">
                <strong>{{ tm('errorDialog.traceback') }}:</strong>
              </div>
              <pre class="traceback-box">{{
                currentErrorPlatform.last_error.traceback
              }}</pre>
            </div>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0 platform-error-dialog__actions">
          <v-spacer></v-spacer>
          <v-btn
            variant="tonal"
            color="primary"
            @click="showErrorDialog = false"
          >
            {{ tm('errorDialog.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar
      :timeout="3000"
      elevation="4"
      :color="save_message_success"
      v-model="save_message_snack"
      location="top"
    >
      {{ save_message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { botApi, fileApi, systemConfigApi } from '@/api/v1';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import PlatformQuickActionsDialog from '@/components/platform/PlatformQuickActionsDialog.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import ItemCard from '@/components/shared/ItemCard.vue';
import QrCodeViewer from '@/components/shared/QrCodeViewer.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useModuleI18n, mergeDynamicTranslations } from '@/i18n/composables';
import { getPlatformIcon as getBasePlatformIcon } from '@/utils/platformUtils';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import { copyToClipboard } from '@/utils/clipboard';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { runBotMutationWithStepUp } from '@/utils/botStepUp';

defineOptions({
  name: 'PlatformPage',
});

type SnackbarColor = 'success' | 'error';
type PlatformStatus = 'running' | 'error' | 'pending' | 'stopped' | string;

interface PlatformConfigItem extends Record<string, unknown> {
  id?: string;
  type?: string;
  enable?: boolean;
  webhook_uuid?: string;
}

interface PlatformConfigState extends Record<string, unknown> {
  platform?: PlatformConfigItem[];
  callback_api_base?: string;
}

type PlatformMetadataState = Record<string, unknown>;

interface PlatformRuntimeError extends Record<string, unknown> {
  message?: string;
  timestamp?: string | number;
  traceback?: string;
}

interface PlatformQrPayload extends Record<string, unknown> {
  qrcode_img_content?: string;
  qrcode?: string;
  qr_status?: string;
}

interface PlatformStatMeta extends Record<string, unknown> {
  supported_actions?: string[];
}

interface PlatformStat extends Record<string, unknown> {
  id?: string;
  status?: PlatformStatus;
  error_count?: number;
  last_error?: PlatformRuntimeError;
  unified_webhook?: boolean;
  weixin_oc?: PlatformQrPayload;
  meta?: PlatformStatMeta;
}

interface ShowToastPayload {
  message: string;
  type: 'success' | 'error';
}

const { tm } = useModuleI18n('features/platform');
const confirmDialog = useConfirmDialog();
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const config_data = ref<PlatformConfigState>({});
const metadata = ref<PlatformMetadataState>({});
const showAddPlatformDialog = ref(false);
const updatingPlatformConfig = ref<PlatformConfigItem>({});
const updatingMode = ref(false);
const save_message_snack = ref(false);
const save_message = ref('');
const save_message_success = ref<SnackbarColor>('success');
const showConsole = ref(
  localStorage.getItem('platformPage_showConsole') === 'true',
);
const showWebhookDialog = ref(false);
const currentWebhookUuid = ref('');
const platformStats = ref<Record<string, PlatformStat>>({});
const platformTypeCapabilities = ref<Record<string, string[]>>({});
const statsRefreshInterval = ref<ReturnType<typeof setInterval> | null>(null);
const showErrorDialog = ref(false);
const currentErrorPlatform = ref<PlatformStat | null>(null);
const showQrDialog = ref(false);
const currentQrPlatformId = ref('');
const showQuickActionDialog = ref(false);
const currentQuickActionPlatformId = ref('');
const currentQuickActionSupportedActions = ref<string[]>([]);

const messages = computed(() => ({
  updateSuccess: tm('messages.updateSuccess'),
  addSuccess: tm('messages.addSuccess'),
  deleteSuccess: tm('messages.deleteSuccess'),
  statusUpdateSuccess: tm('messages.statusUpdateSuccess'),
  deleteConfirm: tm('messages.deleteConfirm'),
}));

const currentWebhookUrl = computed(() =>
  getWebhookUrl(currentWebhookUuid.value),
);
const platformList = computed(() => config_data.value.platform ?? []);

watch(showConsole, (newValue) => {
  localStorage.setItem('platformPage_showConsole', String(newValue));
});

onMounted(() => {
  void getConfig();
  void getPlatformTypes();
  void getPlatformStats();
  statsRefreshInterval.value = setInterval(() => {
    void getPlatformStats();
  }, 5000);
  window.addEventListener('astrbot-locale-changed', handleLocaleChange);
});

onBeforeUnmount(() => {
  if (statsRefreshInterval.value) {
    clearInterval(statsRefreshInterval.value);
  }
  window.removeEventListener('astrbot-locale-changed', handleLocaleChange);
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

function getBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function getNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function cloneConfigValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return [...value];
  }
  if (value && typeof value === 'object') {
    return { ...(value as Record<string, unknown>) };
  }
  return value;
}

function normalizePlatformConfig(value: unknown): PlatformConfigItem {
  const record = asRecord(value);
  if (!record) {
    return {};
  }
  return { ...record };
}

function normalizePlatformStat(value: unknown): PlatformStat | null {
  const record = asRecord(value);
  const id = getString(record?.id);
  if (!record || !id) {
    return null;
  }

  const lastErrorRecord = asRecord(record.last_error);
  const weixinOcRecord = asRecord(record.weixin_oc);
  const metaRecord = asRecord(record.meta);
  return {
    ...record,
    id,
    status: getString(record.status) ?? undefined,
    error_count: getNumber(record.error_count) ?? 0,
    unified_webhook: getBoolean(record.unified_webhook) ?? undefined,
    last_error: lastErrorRecord
      ? {
          ...lastErrorRecord,
          message: getString(lastErrorRecord.message) ?? undefined,
          timestamp:
            getString(lastErrorRecord.timestamp) ??
            getNumber(lastErrorRecord.timestamp) ??
            undefined,
          traceback: getString(lastErrorRecord.traceback) ?? undefined,
        }
      : undefined,
    weixin_oc: weixinOcRecord
      ? {
          ...weixinOcRecord,
          qrcode_img_content:
            getString(weixinOcRecord.qrcode_img_content) ?? undefined,
          qrcode: getString(weixinOcRecord.qrcode) ?? undefined,
          qr_status: getString(weixinOcRecord.qr_status) ?? undefined,
        }
      : undefined,
    meta: metaRecord
      ? {
          ...metaRecord,
          supported_actions: Array.isArray(metaRecord.supported_actions)
            ? metaRecord.supported_actions.filter(
                (item): item is string => typeof item === 'string',
              )
            : [],
        }
      : undefined,
  };
}

function normalizeTranslationLocales(
  value: unknown,
): Record<string, Record<string, unknown>> {
  const record = asRecord(value);
  if (!record) {
    return {};
  }

  const normalized: Record<string, Record<string, unknown>> = {};
  for (const [locale, localeValue] of Object.entries(record)) {
    const localeRecord = asRecord(localeValue);
    if (localeRecord) {
      normalized[locale] = localeRecord;
    }
  }
  return normalized;
}

function handleLocaleChange() {
  void getConfig();
}

function getPlatformIcon(platformId: string) {
  const platformGroup = asRecord(metadata.value.platform_group);
  const platformMetadata = asRecord(platformGroup?.metadata);
  const platformConfig = asRecord(platformMetadata?.platform);
  const templates = asRecord(platformConfig?.config_template);
  const template = asRecord(templates?.[platformId]);
  const logoToken = getString(template?.logo_token);
  if (logoToken) {
    return fileApi.tokenUrl(logoToken);
  }
  return getBasePlatformIcon(platformId);
}

function getPlatformId(platform: PlatformConfigItem): string | null {
  return getString(platform.id);
}

function getPlatformTypeOrId(platform: PlatformConfigItem): string {
  return getString(platform.type) ?? getPlatformId(platform) ?? '';
}

function getPlatformLogo(platform: PlatformConfigItem): string | undefined {
  return getPlatformIcon(getPlatformTypeOrId(platform));
}

async function getConfig() {
  try {
    const res = await systemConfigApi.runtime();
    const payload = asRecord(res.data.data);
    config_data.value =
      (asRecord(payload?.config) as PlatformConfigState) ?? {};
    metadata.value =
      (asRecord(payload?.metadata) as PlatformMetadataState) ?? {};

    const platformI18n = asRecord(payload?.platform_i18n_translations);
    if (platformI18n) {
      mergeDynamicTranslations(
        'features.config-metadata',
        normalizeTranslationLocales(platformI18n),
      );
    }
  } catch (error) {
    showError(resolveErrorMessage(error, tm('messages.platformUpdateFailed')));
  }
}

async function getPlatformStats() {
  try {
    const res = await botApi.stats();
    if (res.data.status !== 'ok') {
      return;
    }
    const stats: Record<string, PlatformStat> = {};
    const payload = asRecord(res.data.data);
    const platforms = Array.isArray(payload?.platforms)
      ? payload.platforms
      : [];
    for (const platform of platforms) {
      const normalized = normalizePlatformStat(platform);
      if (normalized?.id) {
        stats[normalized.id] = normalized;
      }
    }
    platformStats.value = stats;
  } catch (error) {
    console.warn('获取平台统计信息失败:', error);
  }
}

async function getPlatformTypes() {
  try {
    const res = await botApi.types();
    if (res.data.status !== 'ok') {
      return;
    }

    const payload = asRecord(res.data.data);
    const botTypes = Array.isArray(payload?.bot_types) ? payload.bot_types : [];
    const capabilities: Record<string, string[]> = {};

    for (const item of botTypes) {
      const record = asRecord(item);
      if (!record) {
        continue;
      }
      const supportedActions = normalizeStringArray(record.supported_actions);
      const typeKey = getString(record.type);
      const idKey = getString(record.id);
      if (typeKey) {
        capabilities[typeKey] = supportedActions;
      }
      if (idKey && !capabilities[idKey]) {
        capabilities[idKey] = supportedActions;
      }
    }

    platformTypeCapabilities.value = capabilities;
  } catch (error) {
    console.warn('获取平台能力信息失败:', error);
  }
}

function getPlatformStat(platformId: string) {
  return platformStats.value[platformId] ?? null;
}

function isQrPayload(value: unknown): value is PlatformQrPayload {
  const record = asRecord(value);
  return Boolean(
    record && ('qrcode_img_content' in record || 'qrcode' in record),
  );
}

function hasQrPayload(platformId: string) {
  const stat = getPlatformQrLoginStat(platformId);
  return Boolean(stat?.qrcode_img_content || stat?.qrcode);
}

function hasQrPayloadForPlatform(platform: PlatformConfigItem): boolean {
  const platformId = getPlatformId(platform);
  return platformId ? hasQrPayload(platformId) : false;
}

function getPlatformQrLoginStat(platformId: string) {
  const stat = getPlatformStat(platformId);
  if (stat?.weixin_oc) {
    return stat.weixin_oc;
  }
  if (stat) {
    for (const value of Object.values(stat)) {
      if (isQrPayload(value)) {
        return value;
      }
    }
  }
  return null;
}

function openPlatformQrDialog(platformId: string) {
  currentQrPlatformId.value = platformId;
  showQrDialog.value = true;
}

function openPlatformQrDialogByPlatform(platform: PlatformConfigItem) {
  const platformId = getPlatformId(platform);
  if (!platformId) {
    return;
  }
  openPlatformQrDialog(platformId);
}

function getPlatformStatus(
  platform: PlatformConfigItem,
): PlatformStatus | undefined {
  const platformId = getPlatformId(platform);
  return platformId ? getPlatformStat(platformId)?.status : undefined;
}

function getPlatformErrorCount(platform: PlatformConfigItem): number {
  const platformId = getPlatformId(platform);
  return platformId ? (getPlatformStat(platformId)?.error_count ?? 0) : 0;
}

function getSupportedActions(platform: PlatformConfigItem): string[] {
  const platformId = getPlatformId(platform);
  const runtimeActions = platformId
    ? (getPlatformStat(platformId)?.meta?.supported_actions ?? [])
    : [];
  if (runtimeActions.length > 0) {
    return runtimeActions;
  }

  const typeKey = getString(platform.type);
  if (typeKey && platformTypeCapabilities.value[typeKey]) {
    return platformTypeCapabilities.value[typeKey];
  }
  if (platformId && platformTypeCapabilities.value[platformId]) {
    return platformTypeCapabilities.value[platformId];
  }
  return [];
}

function getSupportedActionLabel(action: string): string {
  const translated = tm(`capabilities.actions.${action}`);
  return translated.startsWith('[MISSING:') ? action : translated;
}

function shouldShowPlatformStatus(platform: PlatformConfigItem): boolean {
  const platformId = getPlatformId(platform);
  const stat = platformId ? getPlatformStat(platformId) : null;
  return Boolean(
    stat && (stat.status !== 'running' || (stat.error_count ?? 0) > 0),
  );
}

function getRuntimeStatusLabel(platform: PlatformConfigItem): string {
  return tm(`runtimeStatus.${getPlatformStatus(platform) ?? 'unknown'}`);
}

function getStatusColor(status: PlatformStatus | undefined) {
  switch (status) {
    case 'running':
      return 'success';
    case 'error':
      return 'error';
    case 'pending':
      return 'warning';
    case 'stopped':
      return 'grey';
    case undefined:
      return 'grey';
    default:
      return 'grey';
  }
}

function getStatusIcon(status: PlatformStatus | undefined) {
  switch (status) {
    case 'running':
      return 'mdi-check-circle';
    case 'error':
      return 'mdi-alert-circle';
    case 'pending':
      return 'mdi-clock-outline';
    case 'stopped':
      return 'mdi-stop-circle';
    case undefined:
      return 'mdi-help-circle';
    default:
      return 'mdi-help-circle';
  }
}

function showErrorDetails(platform: PlatformConfigItem) {
  const platformId = getString(platform.id);
  if (!platformId) {
    return;
  }
  const stat = getPlatformStat(platformId);
  if (stat && (stat.error_count ?? 0) > 0) {
    currentErrorPlatform.value = stat;
    showErrorDialog.value = true;
  }
}

function getWebhookUuid(platform: PlatformConfigItem): string | null {
  return getString(platform.webhook_uuid);
}

function hasUnifiedWebhook(platform: PlatformConfigItem): boolean {
  const platformId = getPlatformId(platform);
  const webhookUuid = getWebhookUuid(platform);
  if (!platformId || !webhookUuid) {
    return false;
  }
  return Boolean(getPlatformStat(platformId)?.unified_webhook);
}

function openWebhookDialogForPlatform(platform: PlatformConfigItem) {
  const webhookUuid = getWebhookUuid(platform);
  if (!webhookUuid) {
    return;
  }
  openWebhookDialog(webhookUuid);
}

function findPlatformTemplate(platform: PlatformConfigItem) {
  const platformGroup = asRecord(metadata.value.platform_group);
  const platformMetadata = asRecord(platformGroup?.metadata);
  const platformConfig = asRecord(platformMetadata?.platform);
  const templates = asRecord(platformConfig?.config_template);
  if (!templates) {
    return null;
  }

  const platformType = getString(platform.type);
  const platformId = getString(platform.id);
  const typeTemplate = platformType ? asRecord(templates[platformType]) : null;
  if (typeTemplate) {
    return typeTemplate;
  }
  const idTemplate = platformId ? asRecord(templates[platformId]) : null;
  if (idTemplate) {
    return idTemplate;
  }

  for (const template of Object.values(templates)) {
    const templateRecord = asRecord(template);
    if (getString(templateRecord?.type) === platformType) {
      return templateRecord;
    }
  }
  return null;
}

function mergeConfigWithTemplate(
  sourceConfig: unknown,
  templateConfig: unknown,
) {
  const merge = (
    source: unknown,
    reference: unknown,
  ): Record<string, unknown> => {
    const target: Record<string, unknown> = {};
    const sourceObj = asRecord(source) ?? {};
    const referenceObj = asRecord(reference);

    if (!referenceObj) {
      for (const [key, value] of Object.entries(sourceObj)) {
        target[key] = cloneConfigValue(value);
      }
      return target;
    }

    for (const [key, refValue] of Object.entries(referenceObj)) {
      const hasSourceKey = Object.hasOwn(sourceObj, key);
      const sourceValue = sourceObj[key];

      if (
        refValue &&
        typeof refValue === 'object' &&
        !Array.isArray(refValue)
      ) {
        target[key] = merge(
          hasSourceKey &&
            sourceValue &&
            typeof sourceValue === 'object' &&
            !Array.isArray(sourceValue)
            ? sourceValue
            : {},
          refValue,
        );
        continue;
      }

      if (hasSourceKey) {
        target[key] = cloneConfigValue(sourceValue);
      } else if (Array.isArray(refValue)) {
        target[key] = [...refValue];
      } else {
        target[key] = refValue;
      }
    }

    for (const [key, value] of Object.entries(sourceObj)) {
      if (Object.hasOwn(referenceObj, key)) {
        continue;
      }
      target[key] = cloneConfigValue(value);
    }

    return target;
  };

  return merge(sourceConfig, templateConfig);
}

function editPlatform(platform: PlatformConfigItem) {
  const platformCopy = deepClone(platform);
  const template = findPlatformTemplate(platformCopy);
  updatingPlatformConfig.value = template
    ? normalizePlatformConfig(mergeConfigWithTemplate(platformCopy, template))
    : platformCopy;
  updatingMode.value = true;
  showAddPlatformDialog.value = true;
}

async function deletePlatform(platform: PlatformConfigItem) {
  const platformId = getString(platform.id);
  if (!platformId) {
    return;
  }
  const message = `${messages.value.deleteConfirm} ${platformId}?`;
  if (!(await askForConfirmationDialog(message, confirmDialog))) {
    return;
  }

  try {
    const res = await runBotMutationWithStepUp(
      (stepUp) =>
        stepUp ? botApi.delete(platformId, stepUp) : botApi.delete(platformId),
      platformId,
      requestStepUp,
    );
    if (!res) {
      return;
    }
    await getConfig();
    showSuccess(res.data.message || messages.value.deleteSuccess);
  } catch (error) {
    showError(resolveErrorMessage(error, tm('messages.platformUpdateFailed')));
  }
}

async function platformStatusChange(platform: PlatformConfigItem) {
  const platformId = getString(platform.id);
  if (!platformId) {
    return;
  }
  const currentEnabled = Boolean(platform.enable);
  platform.enable = !currentEnabled;

  try {
    const enabled = Boolean(platform.enable);
    const res = await runBotMutationWithStepUp(
      (stepUp) =>
        stepUp
          ? botApi.setEnabled(platformId, { enabled }, stepUp)
          : botApi.setEnabled(platformId, { enabled }),
      platformId,
      requestStepUp,
    );
    if (!res) {
      platform.enable = currentEnabled;
      return;
    }
    await getConfig();
    showSuccess(res.data.message || messages.value.statusUpdateSuccess);
  } catch (error) {
    platform.enable = currentEnabled;
    showError(resolveErrorMessage(error, tm('messages.platformUpdateFailed')));
  }
}

function openQuickActionDialog(platform: PlatformConfigItem) {
  const platformId = getPlatformId(platform);
  if (!platformId) {
    return;
  }
  currentQuickActionPlatformId.value = platformId;
  currentQuickActionSupportedActions.value = getSupportedActions(platform);
  showQuickActionDialog.value = true;
}

function showToast({ message, type }: ShowToastPayload) {
  if (type === 'success') {
    showSuccess(message);
  } else {
    showError(message);
  }
}

function showSuccess(message: string) {
  save_message.value = message;
  save_message_success.value = 'success';
  save_message_snack.value = true;
}

function showError(message: string) {
  save_message.value = message;
  save_message_success.value = 'error';
  save_message_snack.value = true;
}

function getWebhookUrl(webhookUuid: string) {
  let callbackBase = getString(config_data.value.callback_api_base) ?? '';
  if (!callbackBase) {
    callbackBase = 'http(s)://<your-domain-or-ip>';
  }
  if (callbackBase) {
    return `${callbackBase.replace(/\/$/, '')}/api/v1/webhooks/platforms/${webhookUuid}`;
  }
  return `/api/v1/webhooks/platforms/${webhookUuid}`;
}

function openWebhookDialog(webhookUuid: string) {
  currentWebhookUuid.value = webhookUuid;
  showWebhookDialog.value = true;
}

async function copyWebhookUrl(webhookUuid: string) {
  const url = getWebhookUrl(webhookUuid);
  const ok = await copyToClipboard(url);
  if (ok) {
    showSuccess(tm('webhookCopied'));
  } else {
    showError(tm('webhookCopyFailed'));
  }
}

function formatRuntimeErrorTimestamp(
  error: PlatformRuntimeError | undefined,
): string {
  if (!error?.timestamp) {
    return '';
  }
  return new Date(error.timestamp).toLocaleString();
}
</script>

<style scoped>
.platform-page {
  padding: var(--astrbot-space-2) var(--astrbot-space-4) var(--astrbot-space-8);
}

.webhook-info {
  margin-top: 4px;
}

.webhook-chip {
  cursor: pointer;
}

.platform-status-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.status-chip {
  font-size: 12px;
}

.error-chip {
  cursor: pointer;
  font-size: 12px;
}

.error-details {
  margin-top: 8px;
}

.platform-error-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 840px);
}

.platform-error-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.platform-error-dialog__actions {
  flex-shrink: 0;
}

.error-message {
  word-break: break-word;
}

.traceback-box {
  background-color: rgb(var(--v-theme-code-surface));
  color: rgb(var(--v-theme-code-text));
  padding: var(--astrbot-space-3);
  border-radius: 8px;
  font-size: 12px;
  line-height: 18px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.platform-qr-chip {
  margin-top: 4px;
}

.platform-actions {
  margin-top: 8px;
}

.platform-actions__label {
  margin-bottom: 4px;
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}

.platform-actions__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.platform-actions__toolbar {
  margin-top: 8px;
}

.platform-qr-status {
  font-size: 13px;
  margin-bottom: var(--astrbot-space-2);
  color: rgb(var(--v-theme-on-surface-variant));
}

.quick-actions__intro,
.quick-actions__platform,
.quick-actions__result-label {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}

.quick-actions__categories-label,
.quick-actions__result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.quick-actions__summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--astrbot-space-2);
  margin-top: 8px;
}

.quick-actions__result-box {
  margin-top: 8px;
  padding: var(--astrbot-space-3);
  border-radius: 8px;
  background-color: rgb(var(--v-theme-code-surface));
  color: rgb(var(--v-theme-code-text));
  font-size: 12px;
  line-height: 18px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
}

.platform-console {
  height: 300px;
  border-radius: 0;
  background: rgb(var(--v-theme-code-surface));
}
</style>
