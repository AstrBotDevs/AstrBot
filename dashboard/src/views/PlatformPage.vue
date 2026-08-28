<template>
  <div class="platform-page">
    <v-container fluid class="pa-0">
      <div class="platform-content">
        <div class="platform-workbench">
          <aside class="platform-workbench__sidebar">
            <div class="bot-list-panel">
              <div class="bot-list-panel__head">
                <h3 class="bot-list-panel__title">
                  {{ tm('workspace.listTitle') }}
                </h3>
                <v-btn
                  color="primary"
                  prepend-icon="mdi-plus"
                  size="small"
                  variant="text"
                  rounded="md"
                  @click="showAddPlatformDialog = true"
                >
                  {{ tm('addAdapter') }}
                </v-btn>
                <v-progress-linear
                  v-if="loadingPlatforms"
                  class="bot-list-panel__progress"
                  color="primary"
                  height="2"
                  indeterminate
                />
              </div>

              <div
                v-if="platforms.length"
                class="bot-list-panel__mobile-controls"
              >
                <v-select
                  v-model="selectedPlatformId"
                  :items="platformOptions"
                  item-title="title"
                  item-value="value"
                  density="compact"
                  variant="solo-filled"
                  flat
                  hide-details
                  :placeholder="tm('workspace.selectHint')"
                >
                  <template #selection="{ item }">
                    <div class="bot-mobile-selection">
                      <img
                        :src="getPlatformIconFor(item.platform)"
                        class="bot-list-icon bot-list-icon--mobile"
                        alt="bot logo"
                      />
                      <span>{{ item.title }}</span>
                    </div>
                  </template>
                  <template #item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps" :subtitle="item.subtitle">
                      <template #prepend>
                        <img
                          :src="getPlatformIconFor(item.platform)"
                          class="bot-list-icon bot-list-icon--mobile me-2"
                          alt="bot logo"
                        />
                      </template>
                    </v-list-item>
                  </template>
                </v-select>
                <v-btn
                  v-if="selectedPlatform"
                  icon="mdi-delete-outline"
                  size="small"
                  variant="text"
                  :aria-label="tm('workspace.delete')"
                  :title="tm('workspace.delete')"
                  @click="deletePlatform(selectedPlatform)"
                />
              </div>

              <div v-if="platforms.length" class="bot-list">
                <div
                  v-for="platform in platforms"
                  :key="platform.id"
                  class="bot-list-item"
                  :class="{
                    'bot-list-item--active': selectedPlatformId === platform.id,
                  }"
                >
                  <button
                    type="button"
                    class="bot-list-item__main"
                    @click="selectedPlatformId = platform.id"
                  >
                    <img
                      :src="getPlatformIconFor(platform)"
                      class="bot-list-icon"
                      alt="bot logo"
                    />
                    <div class="bot-list-item__copy">
                      <div class="bot-list-item__title">{{ platform.id }}</div>
                      <div class="bot-list-item__subtitle">
                        <span
                          class="bot-list-item__status-dot"
                          :class="getPlatformStatusClass(platform)"
                        ></span>
                        <span>{{ getPlatformStatusLabel(platform) }}</span>
                        <span v-if="platform.type">· {{ platform.type }}</span>
                      </div>
                    </div>
                  </button>
                  <div class="bot-list-item__actions">
                    <v-btn
                      v-if="getSupportedActions(platform).length"
                      icon="mdi-lightning-bolt-outline"
                      size="small"
                      variant="text"
                      :aria-label="tm('quickActions.title')"
                      :title="tm('quickActions.title')"
                      @click="openQuickActionDialog(platform)"
                    />
                    <v-btn
                      icon="mdi-delete-outline"
                      size="small"
                      variant="text"
                      :aria-label="tm('workspace.delete')"
                      :title="tm('workspace.delete')"
                      @click="deletePlatform(platform)"
                    />
                  </div>
                </div>
              </div>

              <div v-else-if="!loadingPlatforms" class="bot-list-empty">
                <v-icon size="42" color="grey-lighten-1"
                  >mdi-robot-outline</v-icon
                >
                <p>{{ tm('workspace.empty') }}</p>
                <v-btn
                  color="primary"
                  prepend-icon="mdi-plus"
                  size="small"
                  variant="tonal"
                  @click="showAddPlatformDialog = true"
                >
                  {{ tm('addAdapter') }}
                </v-btn>
              </div>
            </div>
          </aside>

          <div class="platform-workbench__divider"></div>

          <main class="platform-workbench__main">
            <PlatformEditor
              v-if="selectedPlatform"
              :key="selectedPlatform.id"
              :platform="selectedPlatform"
              :metadata="metadata"
              :runtime-stat="getPlatformStat(selectedPlatform.id)"
              :has-qr-payload="hasQrPayload(selectedPlatform.id)"
              :request-step-up="requestStepUp"
              @saved="handlePlatformSaved"
              @show-toast="showToast"
              @show-error="showErrorDetails(selectedPlatform)"
              @show-qr="openPlatformQrDialog(selectedPlatform.id)"
              @show-webhook="openWebhookDialog"
            />

            <div v-else class="platform-empty-state">
              <v-icon size="48" color="grey-lighten-1"
                >mdi-cursor-default-click</v-icon
              >
              <p>{{ tm('workspace.selectHint') }}</p>
            </div>
          </main>
        </div>
      </div>
    </v-container>

    <AddNewPlatform
      v-model:show="showAddPlatformDialog"
      :metadata="metadata"
      :config_data="configData"
      :updating-mode="false"
      :request-step-up="requestStepUp"
      @show-toast="showToast"
      @refresh-config="handlePlatformCreated"
    />

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
          >
            <template #append-inner>
              <v-btn
                icon="mdi-content-copy"
                size="small"
                variant="text"
                @click="copyWebhookUrl(currentWebhookUuid)"
              />
            </template>
          </v-text-field>
        </v-card-text>
        <v-card-actions class="pa-4 pt-2">
          <v-spacer />
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
          <v-spacer />
          <v-btn variant="tonal" color="primary" @click="showQrDialog = false">
            {{ tm('platformQr.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="showErrorDialog" max-width="700">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
          <v-icon class="me-2" color="error">mdi-alert-circle</v-icon>
          {{ tm('errorDialog.title') }}
        </v-card-title>
        <v-card-text v-if="currentErrorPlatform" class="px-4 pb-4">
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
                  new Date(
                    currentErrorPlatform.last_error.timestamp,
                  ).toLocaleString()
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
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
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

    <v-snackbar
      v-model="snackbar.show"
      :timeout="3000"
      :color="snackbar.color"
      elevation="6"
      location="top"
    >
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { botApi, fileApi, systemConfigApi } from '@/api/v1';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import PlatformEditor from '@/components/platform/PlatformEditor.vue';
import PlatformQuickActionsDialog from '@/components/platform/PlatformQuickActionsDialog.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import QrCodeViewer from '@/components/shared/QrCodeViewer.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { mergeDynamicTranslations, useModuleI18n } from '@/i18n/composables';
import { copyToClipboard } from '@/utils/clipboard';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { runBotMutationWithStepUp } from '@/utils/botStepUp';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import { getPlatformIcon } from '@/utils/platformUtils';

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

const configData = ref({});
const metadata = ref({});
const loadingPlatforms = ref(true);
const selectedPlatformId = ref(null);
const showAddPlatformDialog = ref(false);
const platformStats = ref({});
const showWebhookDialog = ref(false);
const currentWebhookUuid = ref('');
const showQrDialog = ref(false);
const currentQrPlatformId = ref('');
const showErrorDialog = ref(false);
const currentErrorPlatform = ref(null);
const showQuickActionDialog = ref(false);
const currentQuickActionPlatformId = ref('');
const currentQuickActionSupportedActions = ref([]);
const snackbar = ref({ show: false, message: '', color: 'success' });
let statsRefreshInterval = null;

const platforms = computed(() => configData.value.platform || []);

const selectedPlatform = computed(
  () =>
    platforms.value.find(
      (platform) => platform.id === selectedPlatformId.value,
    ) || null,
);

const platformOptions = computed(() =>
  platforms.value.map((platform) => ({
    title: platform.id,
    subtitle: `${getPlatformStatusLabel(platform)} · ${platform.type || ''}`,
    value: platform.id,
    platform,
  })),
);

const currentWebhookUrl = computed(() =>
  getWebhookUrl(currentWebhookUuid.value),
);

onMounted(() => {
  void getConfig();
  void getPlatformStats();
  statsRefreshInterval = window.setInterval(getPlatformStats, 5000);
  window.addEventListener('astrbot-locale-changed', handleLocaleChange);
});

onBeforeUnmount(() => {
  if (statsRefreshInterval) {
    window.clearInterval(statsRefreshInterval);
  }
  window.removeEventListener('astrbot-locale-changed', handleLocaleChange);
});

async function getConfig(preferredPlatformId = null) {
  loadingPlatforms.value = true;
  try {
    const response = await systemConfigApi.runtime();
    configData.value = response.data.data.config;
    metadata.value = response.data.data.metadata;

    const platformI18n = response.data.data.platform_i18n_translations;
    if (platformI18n && typeof platformI18n === 'object') {
      mergeDynamicTranslations('features.config-metadata', platformI18n);
    }

    const nextSelectedId = preferredPlatformId || selectedPlatformId.value;
    if (platforms.value.some((platform) => platform.id === nextSelectedId)) {
      selectedPlatformId.value = nextSelectedId;
    } else {
      selectedPlatformId.value = platforms.value[0]?.id || null;
    }
  } catch (error) {
    showError(error);
  } finally {
    loadingPlatforms.value = false;
  }
}

async function getPlatformStats() {
  try {
    const response = await botApi.stats();
    if (response.data.status !== 'ok') return;
    platformStats.value = Object.fromEntries(
      (response.data.data.platforms || []).map((platform) => [
        platform.id,
        platform,
      ]),
    );
  } catch (error) {
    console.warn('Failed to load bot runtime status:', error);
  }
}

function handleLocaleChange() {
  void getConfig(selectedPlatformId.value);
}

function getPlatformIconFor(platform) {
  const templates =
    metadata.value.platform_group?.metadata?.platform?.config_template || {};
  const template =
    templates[platform?.type] ||
    templates[platform?.id] ||
    Object.values(templates).find((item) => item?.type === platform?.type);
  if (template?.logo_token) {
    return fileApi.tokenUrl(template.logo_token);
  }
  return getPlatformIcon(platform?.type || platform?.id);
}

function getPlatformStat(platformId) {
  return platformStats.value[platformId] || null;
}

function getPlatformStatusLabel(platform) {
  if (platform.enable === false) {
    return tm('workspace.disabled');
  }
  const status = getPlatformStat(platform.id)?.status || 'unknown';
  return tm(`runtimeStatus.${status}`);
}

function getPlatformStatusClass(platform) {
  if (platform.enable === false) return 'bot-list-item__status-dot--disabled';
  const status = getPlatformStat(platform.id)?.status;
  if (status === 'running') return 'bot-list-item__status-dot--success';
  if (status === 'error') return 'bot-list-item__status-dot--error';
  if (status === 'pending') return 'bot-list-item__status-dot--warning';
  return 'bot-list-item__status-dot--disabled';
}

function getSupportedActions(platform) {
  return getPlatformStat(platform.id)?.meta?.supported_actions || [];
}

function openQuickActionDialog(platform) {
  if (!platform?.id) return;
  currentQuickActionPlatformId.value = platform.id;
  currentQuickActionSupportedActions.value = getSupportedActions(platform);
  showQuickActionDialog.value = true;
}

async function deletePlatform(platform) {
  const message = `${tm('messages.deleteConfirm')} ${platform.id}?`;
  if (!(await askForConfirmationDialog(message, confirmDialog))) return;

  try {
    const response = await runBotMutationWithStepUp(
      (stepUp) =>
        stepUp
          ? botApi.delete(platform.id, stepUp)
          : botApi.delete(platform.id),
      platform.id,
      requestStepUp,
    );
    if (!response) return;
    if (selectedPlatformId.value === platform.id) {
      selectedPlatformId.value = null;
    }
    await getConfig();
    showSuccess(response.data.message || tm('messages.deleteSuccess'));
  } catch (error) {
    showError(resolveErrorMessage(error, tm('messages.platformUpdateFailed')));
  }
}

function handlePlatformCreated(platformId) {
  void getConfig(platformId || null);
  void getPlatformStats();
}

function handlePlatformSaved(platformId) {
  void getConfig(platformId);
  void getPlatformStats();
}

function getPlatformQrLoginStat(platformId) {
  const stat = getPlatformStat(platformId);
  if (stat?.weixin_oc) return stat.weixin_oc;
  if (stat && typeof stat === 'object') {
    return Object.values(stat).find(
      (value) =>
        value &&
        typeof value === 'object' &&
        ('qrcode_img_content' in value || 'qrcode' in value),
    );
  }
  return null;
}

function hasQrPayload(platformId) {
  const stat = getPlatformQrLoginStat(platformId);
  return Boolean(stat?.qrcode_img_content || stat?.qrcode);
}

function openPlatformQrDialog(platformId) {
  currentQrPlatformId.value = platformId;
  showQrDialog.value = true;
}

function showErrorDetails(platform) {
  const stat = getPlatformStat(platform.id);
  if (!stat || stat.error_count <= 0) return;
  currentErrorPlatform.value = stat;
  showErrorDialog.value = true;
}

function getWebhookUrl(webhookUuid) {
  const callbackBase =
    configData.value.callback_api_base || 'http(s)://<your-domain-or-ip>';
  return `${callbackBase.replace(
    /\/$/,
    '',
  )}/api/v1/webhooks/platforms/${webhookUuid}`;
}

function openWebhookDialog(webhookUuid) {
  currentWebhookUuid.value = webhookUuid;
  showWebhookDialog.value = true;
}

async function copyWebhookUrl(webhookUuid) {
  const copied = await copyToClipboard(getWebhookUrl(webhookUuid));
  if (copied) {
    showSuccess(tm('webhookCopied'));
  } else {
    showError(tm('webhookCopyFailed'));
  }
}

function showToast({ message, type }) {
  snackbar.value = {
    show: true,
    message,
    color: type === 'error' ? 'error' : 'success',
  };
}

function showSuccess(message) {
  showToast({ message, type: 'success' });
}

function showError(error) {
  const message =
    error?.response?.data?.message || error?.message || String(error);
  showToast({ message, type: 'error' });
}
</script>

<style scoped>
.platform-page {
  --platform-border: rgba(var(--v-theme-on-surface), 0.08);
  --platform-surface: rgb(var(--v-theme-surface));
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  width: 100%;
}

.platform-page > .v-container {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.platform-content {
  display: flex;
  flex: 1;
  margin: 0 auto;
  max-width: 1200px;
  min-height: 0;
  padding: 16px 12px 12px;
  width: 100%;
}

.platform-workbench {
  background: var(--platform-surface);
  border: 1px solid var(--platform-border);
  border-radius: 16px;
  display: grid;
  flex: 1;
  grid-template-columns: minmax(280px, 320px) 1px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  width: 100%;
}

.platform-workbench__sidebar,
.platform-workbench__main {
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.platform-workbench__divider {
  background: var(--platform-border);
}

.platform-workbench__main {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.bot-list-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.bot-list-panel__head {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  gap: 12px;
  justify-content: space-between;
  padding: 20px 20px 12px;
  position: relative;
}

.bot-list-panel__progress {
  bottom: 0;
  left: 0;
  position: absolute;
  right: 0;
}

.bot-list-panel__title {
  font-size: 16px;
  font-weight: 650;
  line-height: 1.3;
  margin: 0;
}

.bot-list-panel__mobile-controls {
  align-items: center;
  display: none;
  gap: 8px;
  padding: 0 16px 12px;
}

.bot-list-panel__mobile-controls > .v-select {
  flex: 1;
  min-width: 0;
}

.bot-mobile-selection {
  align-items: center;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.bot-mobile-selection span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bot-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 6px 12px 16px;
}

.bot-list-item {
  align-items: center;
  border-radius: 12px;
  display: flex;
  min-width: 0;
}

.bot-list-item:hover,
.bot-list-item--active {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.bot-list-item__main {
  align-items: center;
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  display: flex;
  flex: 1;
  gap: 10px;
  min-width: 0;
  padding: 10px 4px 10px 12px;
  text-align: left;
}

.bot-list-icon {
  flex: 0 0 auto;
  height: 30px;
  object-fit: contain;
  width: 30px;
}

.bot-list-icon--mobile {
  height: 24px;
  width: 24px;
}

.bot-list-item__copy {
  flex: 1;
  min-width: 0;
}

.bot-list-item__title {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bot-list-item__subtitle {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.54);
  display: flex;
  font-size: 12px;
  gap: 4px;
  line-height: 1.4;
  margin-top: 4px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bot-list-item__status-dot {
  background: rgba(var(--v-theme-on-surface), 0.35);
  border-radius: 50%;
  flex: 0 0 auto;
  height: 7px;
  width: 7px;
}

.bot-list-item__status-dot--success {
  background: rgb(var(--v-theme-success));
}

.bot-list-item__status-dot--error {
  background: rgb(var(--v-theme-error));
}

.bot-list-item__status-dot--warning {
  background: rgb(var(--v-theme-warning));
}

.bot-list-item__actions {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  opacity: 0;
  padding-right: 4px;
}

.bot-list-item:hover .bot-list-item__actions,
.bot-list-item--active .bot-list-item__actions {
  opacity: 1;
}

.bot-list-empty,
.platform-empty-state {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.56);
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  justify-content: center;
  padding: 24px;
  text-align: center;
}

.bot-list-empty p,
.platform-empty-state p {
  font-size: 13px;
  margin: 0;
}

.platform-empty-state {
  min-height: 420px;
}

.platform-qr-status {
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 13px;
  margin-bottom: 10px;
}

.error-message {
  word-break: break-word;
}

.traceback-box {
  background: #1e1e1e;
  border-radius: 8px;
  color: #d4d4d4;
  font-size: 12px;
  line-height: 1.5;
  max-height: 300px;
  overflow: auto;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 960px) {
  .platform-workbench {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1px minmax(0, 1fr);
  }

  .platform-workbench__divider {
    height: 1px;
  }

  .bot-list-panel {
    height: auto;
  }

  .bot-list-panel__head {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
    padding: 16px 16px 8px;
  }

  .bot-list-panel__head :deep(.v-btn) {
    align-self: flex-start;
  }

  .bot-list-panel__mobile-controls {
    display: flex;
  }

  .bot-list {
    display: none;
  }

  .bot-list-empty {
    min-height: 160px;
  }
}

@media (max-width: 600px) {
  .platform-content {
    padding-inline: 4px;
  }

  .platform-workbench {
    border-radius: 12px;
  }

  .platform-empty-state {
    min-height: 260px;
  }
}
</style>
