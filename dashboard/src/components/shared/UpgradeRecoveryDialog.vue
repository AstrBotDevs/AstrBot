<template>
  <v-dialog v-model="visible" max-width="520">
    <v-card>
      <v-card-title class="upgrade-recovery-title">
        <span>{{ t('core.common.upgradeRecovery.title') }}</span>
      </v-card-title>

      <v-card-text>
        <p class="mb-3">
          {{
            t('core.common.upgradeRecovery.description', {
              coreVersion,
              dashboardVersion,
            })
          }}
        </p>
        <v-alert type="warning" variant="tonal" density="comfortable" class="mb-3">
          {{ t('core.common.upgradeRecovery.hint') }}
        </v-alert>
        <v-progress-linear
          v-if="restarting"
          indeterminate
          color="primary"
          class="mb-2"
        />
        <div v-if="statusMessage" class="text-medium-emphasis">
          {{ statusMessage }}
        </div>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="restarting" @click="dismiss">
          {{ t('core.common.upgradeRecovery.laterButton') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          prepend-icon="mdi-restart"
          :loading="restarting"
          @click="restartCore"
        >
          {{ t('core.common.upgradeRecovery.restartButton') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import axios, { type AxiosRequestConfig } from 'axios';
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import {
  UPGRADE_RECOVERY_EVENT,
  UPGRADE_RECOVERY_TOKEN_KEY,
  type ApiEnvelope,
  type VersionData,
} from '@/api/v1';
import { useI18n } from '@/i18n/composables';

type StartTimeData = {
  start_time?: number | string | null;
};

const { t } = useI18n();
const route = useRoute();

const visible = ref(false);
const restarting = ref(false);
const statusMessage = ref('');
const coreVersion = ref('');
const dashboardVersion = ref('');
const initialStartTime = ref<number | string | null>(null);

let restartTimer: ReturnType<typeof setInterval> | null = null;
let detecting = false;
const recoveryClient = axios.create();

function normalizeVersion(version?: string | null) {
  return (version || '').trim().replace(/^v/i, '');
}

function displayVersion(version?: string | null) {
  const normalized = normalizeVersion(version);
  return normalized ? `v${normalized}` : 'unknown';
}

function versionsMismatch(core?: string | null, dashboard?: string | null) {
  const normalizedCore = normalizeVersion(core);
  const normalizedDashboard = normalizeVersion(dashboard);
  return Boolean(
    normalizedCore &&
      normalizedDashboard &&
      normalizedCore !== normalizedDashboard,
  );
}

function isMissingApiKeyResponse(response: {
  data?: { message?: string | null } | string;
}) {
  const message =
    typeof response.data === 'string'
      ? response.data
      : response.data?.message || '';
  return message.toLowerCase().includes('missing api key');
}

function getDismissKey() {
  return `astrbot-upgrade-recovery-dismissed:${coreVersion.value}:${dashboardVersion.value}`;
}

function recoveryRequestConfig(validateStatus = false): AxiosRequestConfig {
  const headers: Record<string, string> = {};
  const token =
    localStorage.getItem('token') ||
    sessionStorage.getItem(UPGRADE_RECOVERY_TOKEN_KEY);
  const locale = localStorage.getItem('astrbot-locale');
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (locale) {
    headers['Accept-Language'] = locale;
  }
  return {
    headers,
    ...(validateStatus ? { validateStatus: () => true } : {}),
  };
}

async function fetchLegacyStartTime() {
  const response = await recoveryClient.get<ApiEnvelope<StartTimeData>>(
    '/api/stat/start-time',
    recoveryRequestConfig(),
  );
  return response.data?.data?.start_time ?? null;
}

function clearRestartTimer() {
  if (restartTimer !== null) {
    clearInterval(restartTimer);
    restartTimer = null;
  }
}

function dismiss() {
  sessionStorage.setItem(getDismissKey(), '1');
  sessionStorage.removeItem(UPGRADE_RECOVERY_TOKEN_KEY);
  visible.value = false;
}

function waitForRestart() {
  clearRestartTimer();
  let attempts = 0;
  restartTimer = setInterval(async () => {
    attempts += 1;
    try {
      const nextStartTime = await fetchLegacyStartTime();
      if (
        nextStartTime !== null &&
        String(nextStartTime) !== String(initialStartTime.value)
      ) {
        clearRestartTimer();
        sessionStorage.removeItem(UPGRADE_RECOVERY_TOKEN_KEY);
        window.location.reload();
      }
    } catch (_error) {
      // The backend may be temporarily unavailable during restart.
    }

    if (attempts >= 90) {
      clearRestartTimer();
      restarting.value = false;
      statusMessage.value = t('core.common.upgradeRecovery.failed');
    }
  }, 1000);
}

async function restartCore() {
  restarting.value = true;
  statusMessage.value = t('core.common.upgradeRecovery.restarting');
  try {
    initialStartTime.value =
      initialStartTime.value ?? (await fetchLegacyStartTime());
    await recoveryClient.post<ApiEnvelope<unknown>>(
      '/api/stat/restart-core',
      undefined,
      recoveryRequestConfig(),
    );
    statusMessage.value = t('core.common.upgradeRecovery.waiting');
    waitForRestart();
  } catch (_error) {
    restarting.value = false;
    statusMessage.value = t('core.common.upgradeRecovery.failed');
  }
}

async function showRecoveryDialog(versionData: VersionData) {
  if (visible.value || restarting.value) {
    return;
  }
  if (!versionsMismatch(versionData.version, versionData.dashboard_version)) {
    return;
  }

  coreVersion.value = displayVersion(versionData.version);
  dashboardVersion.value = displayVersion(versionData.dashboard_version);
  if (sessionStorage.getItem(getDismissKey())) {
    return;
  }

  initialStartTime.value = await fetchLegacyStartTime().catch(() => null);
  visible.value = true;
}

function handleRecoveryEvent(event: Event) {
  const versionData = (event as CustomEvent<VersionData>).detail || {};
  void showRecoveryDialog(versionData);
}

async function detectUpgradeMismatch() {
  if (detecting || visible.value || restarting.value) {
    return;
  }
  detecting = true;
  try {
    const v1Response = await recoveryClient.get<ApiEnvelope<unknown>>(
      '/api/v1/auth/setup-status',
      recoveryRequestConfig(true),
    );
    if (!isMissingApiKeyResponse(v1Response)) {
      return;
    }

    const legacyResponse = await recoveryClient.get<ApiEnvelope<VersionData>>(
      '/api/stat/version',
      recoveryRequestConfig(true),
    );
    if (legacyResponse.status === 401 || legacyResponse.status >= 400) {
      return;
    }

    await showRecoveryDialog(legacyResponse.data?.data || {});
  } catch (_error) {
    // This recovery dialog is best-effort and should never block the app.
  } finally {
    detecting = false;
  }
}

onMounted(() => {
  window.addEventListener(UPGRADE_RECOVERY_EVENT, handleRecoveryEvent);
  void detectUpgradeMismatch();
});

watch(
  () => route.fullPath,
  () => {
    void detectUpgradeMismatch();
  },
);

onBeforeUnmount(() => {
  window.removeEventListener(UPGRADE_RECOVERY_EVENT, handleRecoveryEvent);
  clearRestartTimer();
});
</script>

<style scoped>
.upgrade-recovery-title {
  align-items: center;
  display: flex;
  white-space: normal;
  word-break: break-word;
}
</style>
