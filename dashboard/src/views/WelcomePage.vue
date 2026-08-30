<template>
  <div class="welcome-page">
    <v-container fluid class="pa-0">
      <v-row class="px-4 py-3 pb-6">
        <v-col cols="12">
          <h1 class="text-h1 font-weight-bold mb-2 d-flex align-center">
            {{ greetingText }} {{ greetingEmoji }}
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-0">
            {{ tm('subtitle') }}
          </p>
        </v-col>
      </v-row>

      <v-row class="px-4">
        <v-col cols="12">
          <v-card class="welcome-card pa-6" elevation="0" border>
            <div class="mb-4 text-h3 font-weight-bold">
              {{ tm('onboard.title') }}
            </div>

            <v-timeline
              align="start"
              side="end"
              density="compact"
              class="welcome-timeline"
              truncate-line="both"
            >
              <v-timeline-item
                :dot-color="
                  providerStepState === 'completed' ? 'success' : 'primary'
                "
                icon="mdi-numeric-1"
                fill-dot
                size="small"
              >
                <div class="pl-2">
                  <div class="text-h6 font-weight-bold mb-1">
                    {{ tm('onboard.step1Title') }}
                  </div>
                  <p class="text-body-2 text-medium-emphasis mb-3">
                    {{ tm('onboard.step1Desc') }}
                  </p>
                  <div class="d-flex align-center">
                    <v-btn
                      color="primary"
                      variant="flat"
                      rounded="md"
                      class="px-6"
                      @click="openProviderDialog"
                    >
                      {{ tm('onboard.configure') }}
                    </v-btn>
                    <div
                      v-if="providerStepState === 'completed'"
                      class="text-success d-flex align-center text-body-2 font-weight-medium ml-3"
                    >
                      {{ tm('onboard.completed') }}
                    </div>
                  </div>
                </div>
              </v-timeline-item>

              <v-timeline-item
                :dot-color="
                  platformStepState === 'completed' ? 'success' : 'primary'
                "
                icon="mdi-numeric-2"
                fill-dot
                size="small"
              >
                <div class="pl-2">
                  <div class="text-h6 font-weight-bold mb-1">
                    {{ tm('onboard.step2Title') }}
                  </div>
                  <p class="text-body-2 text-medium-emphasis mb-3">
                    {{ tm('onboard.step2Desc') }}
                  </p>
                  <div class="d-flex align-center">
                    <v-btn
                      color="primary"
                      variant="flat"
                      rounded="md"
                      class="px-6"
                      :loading="loadingPlatformDialog"
                      @click="openPlatformDialog"
                    >
                      {{ tm('onboard.configure') }}
                    </v-btn>
                    <div
                      v-if="platformStepState === 'completed'"
                      class="text-success d-flex align-center text-body-2 font-weight-medium ml-3"
                    >
                      {{ tm('onboard.completed') }}
                    </div>
                  </div>
                </div>
              </v-timeline-item>

              <v-timeline-item
                :dot-color="
                  computerAccessStepState === 'completed'
                    ? 'success'
                    : 'primary'
                "
                icon="mdi-numeric-3"
                fill-dot
                size="small"
              >
                <div class="pl-2">
                  <div class="d-flex align-center mb-1">
                    <div class="text-h6 font-weight-bold">
                      {{ tm('onboard.step3Title') }}
                    </div>
                    <v-btn
                      icon
                      variant="text"
                      density="comfortable"
                      size="small"
                      class="ml-1"
                      @click="showComputerAccessHelpDialog = true"
                    >
                      <span class="text-body-2 font-weight-bold">?</span>
                    </v-btn>
                  </div>
                  <p class="text-body-2 text-medium-emphasis mb-3">
                    {{ tm('onboard.step3Desc') }}
                  </p>
                  <div class="d-flex flex-wrap align-center ga-3">
                    <v-select
                      v-model="computerAccessRuntime"
                      :items="computerAccessOptions"
                      item-title="title"
                      item-value="value"
                      :label="tm('onboard.step3SelectLabel')"
                      :loading="savingComputerAccess"
                      :disabled="savingComputerAccess"
                      hide-details
                      density="comfortable"
                      variant="outlined"
                      class="computer-access-select"
                    />
                  </div>
                </div>
              </v-timeline-item>
            </v-timeline>
          </v-card>
        </v-col>
      </v-row>
    </v-container>

    <AddNewPlatform
      v-model:show="showAddPlatformDialog"
      :metadata="platformMetadata"
      :config-data="platformConfigData"
      @refresh-config="loadPlatformConfigBase"
    />
    <ProviderConfigDialog v-model="showProviderDialog" />
    <v-dialog v-model="showComputerAccessHelpDialog" max-width="640" scrollable>
      <v-card class="computer-access-help-dialog">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ tm('onboard.step3HelpTitle') }}
        </v-card-title>
        <v-card-text class="computer-access-help-dialog__content">
          <ol class="computer-access-help-list">
            <li>{{ tm('onboard.step3HelpItem1') }}</li>
            <li>{{ tm('onboard.step3HelpItem2') }}</li>
            <li>{{ tm('onboard.step3HelpItem3') }}</li>
          </ol>
        </v-card-text>
        <v-card-actions class="px-6 pb-4 computer-access-help-dialog__actions">
          <v-spacer />
          <v-btn
            color="primary"
            variant="text"
            @click="showComputerAccessHelpDialog = false"
          >
            {{ tm('onboard.step3HelpClose') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import ProviderConfigDialog from '@/components/chat/ProviderConfigDialog.vue';
import { configProfileApi, providerApi, systemConfigApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { useToast } from '@/utils/toast';

type StepState = 'pending' | 'completed' | 'skipped';
type ComputerAccessRuntime = 'local' | 'none';

interface ProviderSettings {
  computer_use_runtime?: unknown;
  [key: string]: unknown;
}

interface DefaultConfigPayload {
  provider_settings?: ProviderSettings;
  agent_runner?: {
    runner_type?: string;
    config?: {
      model?: {
        provider_id?: string;
      };
    };
  };
  [key: string]: unknown;
}

interface PlatformConfigPayload {
  platform?: unknown[];
  [key: string]: unknown;
}

interface RuntimeConfigPayload {
  metadata?: Record<string, unknown>;
  config?: PlatformConfigPayload;
}

interface ProviderSourceEntry {
  id?: string;
  provider_type?: string;
  [key: string]: unknown;
}

interface ProviderEntry {
  id?: string;
  enable?: boolean;
  provider_type?: string;
  [key: string]: unknown;
}

interface ProviderTemplatePayload {
  providers?: ProviderEntry[];
  provider_sources?: ProviderSourceEntry[];
}

const { tm } = useModuleI18n('features/welcome');
const { success: showSuccess, error: showError } = useToast();

const showAddPlatformDialog = ref(false);
const showProviderDialog = ref(false);
const showComputerAccessHelpDialog = ref(false);
const loadingPlatformDialog = ref(false);

const platformMetadata = ref<Record<string, unknown>>({});
const platformConfigData = ref<PlatformConfigPayload>({});
const platformCountBeforeOpen = ref(0);
const providerCountBeforeOpen = ref(0);

const platformStepState = ref<StepState>('pending');
const providerStepState = ref<StepState>('pending');
const computerAccessStepState = ref<StepState>('pending');
const computerAccessRuntime = ref<ComputerAccessRuntime>('none');
const savedComputerAccessRuntime = ref<ComputerAccessRuntime>('none');
const savingComputerAccess = ref(false);

const springFestivalDates: Record<number, string> = {
  2025: '01-29',
  2026: '02-17',
  2027: '02-06',
  2028: '01-26',
  2029: '02-13',
  2030: '02-03',
};

function isSpringFestival() {
  const now = new Date();
  const year = now.getFullYear();
  const dateStr = springFestivalDates[year];

  if (!dateStr) return false;

  const [month, day] = dateStr.split('-').map(Number);
  const festivalDate = new Date(year, month - 1, day);

  const start = new Date(festivalDate);
  start.setDate(festivalDate.getDate() - 5);

  const end = new Date(festivalDate);
  end.setDate(festivalDate.getDate() + 5);

  // start of day for comparison
  const nowTime = now.setHours(0, 0, 0, 0);
  const startTime = start.setHours(0, 0, 0, 0);
  const endTime = end.setHours(0, 0, 0, 0);

  return nowTime >= startTime && nowTime <= endTime;
}

function isExactSpringFestivalDay() {
  const now = new Date();
  const year = now.getFullYear();
  const dateStr = springFestivalDates[year];

  if (!dateStr) return false;

  const [month, day] = dateStr.split('-').map(Number);
  const festivalDate = new Date(year, month - 1, day);

  const nowTime = new Date(now).setHours(0, 0, 0, 0);
  const festivalTime = festivalDate.setHours(0, 0, 0, 0);

  return nowTime === festivalTime;
}

const greetingEmoji = computed(() => {
  if (isExactSpringFestivalDay()) {
    return '🧨';
  }
  const hour = new Date().getHours();
  if (hour >= 0 && hour < 5) {
    return '😴';
  }
  return '😊';
});

const greetingText = computed(() => {
  if (isSpringFestival()) {
    return tm('greeting.newYear');
  }
  const hour = new Date().getHours();
  if (hour < 12) return tm('greeting.morning');
  if (hour < 18) return tm('greeting.afternoon');
  return tm('greeting.evening');
});

async function loadPlatformConfigBase() {
  const res = await systemConfigApi.runtime();
  const payload = (res.data.data || {}) as RuntimeConfigPayload;
  platformMetadata.value = payload.metadata || {};
  platformConfigData.value = payload.config || {};
}

async function fetchDefaultConfig(): Promise<DefaultConfigPayload> {
  const res = await configProfileApi.get('default');
  const payload = res.data?.data as
    { config?: DefaultConfigPayload } | undefined;
  return payload?.config || {};
}

function getChatProvidersFromTemplatePayload(payload: ProviderTemplatePayload) {
  const providers = payload?.providers || [];
  return providers.filter(
    (provider) => provider.provider_type === 'chat_completion',
  );
}

async function fetchChatProviders() {
  const response = await providerApi.schema();
  if (response.data.status !== 'ok') {
    throw new Error(response.data.message || tm('onboard.providerLoadFailed'));
  }
  return getChatProvidersFromTemplatePayload(response.data.data);
}

function pickDefaultProviderId(providers: ProviderEntry[]) {
  if (!providers.length) return '';
  const enabledProvider = providers.find(
    (provider) => provider.enable !== false,
  );
  return (enabledProvider || providers[0]).id || '';
}

async function syncDefaultConfigProviderIfNeeded() {
  const providers = await fetchChatProviders();
  if (!providers.length) return;

  const targetProviderId = pickDefaultProviderId(providers);
  if (!targetProviderId) return;

  const configData = await fetchDefaultConfig();
  if (configData?.agent_runner?.runner_type !== 'local') {
    return;
  }
  const modelConfig = configData.agent_runner.config?.model;
  if (!modelConfig) return;

  if (modelConfig.provider_id === targetProviderId) return;

  modelConfig.provider_id = targetProviderId;

  const updateRes = await configProfileApi.update('default', configData);
  if (updateRes.data.status !== 'ok') {
    throw new Error(
      updateRes.data.message || tm('onboard.providerUpdateFailed'),
    );
  }

  showSuccess(tm('onboard.providerDefaultUpdated', { id: targetProviderId }));
}

function normalizeComputerAccessRuntime(
  runtime: unknown,
): ComputerAccessRuntime {
  return runtime === 'local' || runtime === 'sandbox' ? 'local' : 'none';
}

function syncComputerAccessRuntime(configData: DefaultConfigPayload) {
  const providerSettings = configData?.provider_settings || {};
  const currentRuntime = providerSettings?.computer_use_runtime;
  const normalizedRuntime = normalizeComputerAccessRuntime(currentRuntime);

  computerAccessRuntime.value = normalizedRuntime;
  savedComputerAccessRuntime.value = normalizedRuntime;
  computerAccessStepState.value =
    currentRuntime === 'local' ||
    currentRuntime === 'none' ||
    currentRuntime === 'sandbox'
      ? 'completed'
      : 'pending';
}

const computerAccessOptions = computed(() => [
  { title: tm('onboard.step3Allow'), value: 'local' },
  { title: tm('onboard.step3Deny'), value: 'none' },
]);

async function saveComputerAccessRuntime() {
  savingComputerAccess.value = true;
  try {
    const configData = await fetchDefaultConfig();
    if (!configData.provider_settings) {
      configData.provider_settings = {};
    }

    configData.provider_settings.computer_use_runtime =
      computerAccessRuntime.value;

    const updateRes = await configProfileApi.update('default', configData);
    if (updateRes.data.status !== 'ok') {
      throw new Error(
        updateRes.data.message || tm('onboard.computerAccessUpdateFailed'),
      );
    }

    savedComputerAccessRuntime.value = computerAccessRuntime.value;
    computerAccessStepState.value = 'completed';
    showSuccess(
      tm(
        computerAccessRuntime.value === 'local'
          ? 'onboard.computerAccessAllowed'
          : 'onboard.computerAccessDenied',
      ),
    );
  } catch (err: unknown) {
    showError(
      resolveErrorMessage(err, tm('onboard.computerAccessUpdateFailed')),
    );
  } finally {
    savingComputerAccess.value = false;
  }
}

onMounted(async () => {
  try {
    await loadPlatformConfigBase();
    if ((platformConfigData.value.platform || []).length > 0) {
      platformStepState.value = 'completed';
    }
  } catch (e) {
    console.error(e);
  }

  try {
    const providers = await fetchChatProviders();
    if (providers.length > 0) {
      providerStepState.value = 'completed';
    }
  } catch (e) {
    console.error(e);
  }

  try {
    const defaultConfig = await fetchDefaultConfig();
    syncComputerAccessRuntime(defaultConfig);
  } catch (e) {
    console.error(e);
  }
});

async function openPlatformDialog() {
  loadingPlatformDialog.value = true;
  try {
    await loadPlatformConfigBase();
    platformCountBeforeOpen.value = (
      platformConfigData.value.platform || []
    ).length;
    showAddPlatformDialog.value = true;
  } catch (err: unknown) {
    showError(resolveErrorMessage(err, tm('onboard.platformLoadFailed')));
  } finally {
    loadingPlatformDialog.value = false;
  }
}

async function openProviderDialog() {
  try {
    const providers = await fetchChatProviders();
    providerCountBeforeOpen.value = providers.length;
    showProviderDialog.value = true;
  } catch (err: unknown) {
    showError(resolveErrorMessage(err, tm('onboard.providerLoadFailed')));
  }
}

watch(showAddPlatformDialog, async (visible, wasVisible) => {
  if (!wasVisible || visible) return;
  try {
    await loadPlatformConfigBase();
    const newCount = (platformConfigData.value.platform || []).length;
    if (newCount > platformCountBeforeOpen.value) {
      platformStepState.value = 'completed';
    }
  } catch (err: unknown) {
    showError(resolveErrorMessage(err, tm('onboard.platformLoadFailed')));
  }
});

watch(showProviderDialog, async (visible, wasVisible) => {
  if (!wasVisible || visible) return;
  try {
    const providers = await fetchChatProviders();
    if (providers.length > providerCountBeforeOpen.value) {
      providerStepState.value = 'completed';
      await syncDefaultConfigProviderIfNeeded();
    }
  } catch (err: unknown) {
    showError(resolveErrorMessage(err, tm('onboard.providerUpdateFailed')));
  }
});

watch(computerAccessRuntime, async (value, oldValue) => {
  if (value === oldValue) return;
  if (value === savedComputerAccessRuntime.value) return;
  if (savingComputerAccess.value) return;

  try {
    await saveComputerAccessRuntime();
  } catch {
    computerAccessRuntime.value = savedComputerAccessRuntime.value;
  }
});
</script>

<style scoped>
.welcome-page {
  height: 100%;
}

.welcome-card {
  border-radius: 16px;
}

.welcome-announcement-markdown {
  line-height: 1.7;
}

.computer-access-select {
  max-width: 240px;
  min-width: 220px;
}

.computer-access-help-list {
  margin: 0;
  padding-left: 1.25rem;
}

.computer-access-help-dialog {
  display: flex;
  flex-direction: column;
  max-height: min(80vh, 560px);
}

.computer-access-help-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.computer-access-help-dialog__actions {
  flex: 0 0 auto;
}
</style>
