<template>
  <v-dialog
    v-model="visible"
    max-width="520"
    :persistent="blockingRecovery || restarting"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
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
        <v-alert
          type="warning"
          variant="tonal"
          density="comfortable"
          class="mb-3"
        >
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
        <v-btn
          v-if="!blockingRecovery"
          variant="text"
          :disabled="restarting"
          @click="dismiss"
        >
          {{ t('core.common.upgradeRecovery.laterButton') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-restart"
          :loading="restarting"
          @click="restartCore"
        >
          {{ t('core.common.upgradeRecovery.restartButton') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
  <DashboardStepUpDialog
    v-model="stepUpDialogOpen"
    :loading="stepUpLoading"
    :error-message="stepUpErrorMessage"
    @confirm="submitStepUp"
    @cancel="cancelStepUp"
  />
</template>

<script setup lang="ts">
import type { AxiosRequestConfig } from 'axios';
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import {
  authApi,
  statsApi,
  UPGRADE_RECOVERY_EVENT,
  UPGRADE_RECOVERY_TOKEN_KEY,
  type VersionData,
} from '@/api/v1';
import { useI18n } from '@/i18n/composables';
import DashboardStepUpDialog from './DashboardStepUpDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { stepUpHeaders } from '@/utils/stepUp';

type RecoveryEventDetail = VersionData & {
  blocking?: boolean;
};

const { t } = useI18n();
const route = useRoute();
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const visible = ref(false);
const restarting = ref(false);
const blockingRecovery = ref(false);
const statusMessage = ref('');
const coreVersion = ref('');
const dashboardVersion = ref('');
const initialStartTime = ref<number | string | null>(null);

let restartTimer: ReturnType<typeof setInterval> | null = null;
let detecting = false;

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
  const response = await statsApi.startTime(recoveryRequestConfig());
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
  blockingRecovery.value = false;
  visible.value = false;
}

function reloadWithCacheBuster() {
  const url = new URL(window.location.href);
  url.searchParams.set('_r', Date.now().toString());
  window.location.replace(url.toString());
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
        reloadWithCacheBuster();
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
  const stepUp = await requestStepUp({
    action: 'system.restart',
    resourceType: 'system',
    resourceId: 'restart',
  });
  if (!stepUp) return;
  restarting.value = true;
  statusMessage.value = t('core.common.upgradeRecovery.restarting');
  try {
    initialStartTime.value =
      initialStartTime.value ?? (await fetchLegacyStartTime());
    const recoveryConfig = recoveryRequestConfig();
    await statsApi.restart({
      ...recoveryConfig,
      headers: {
        ...(recoveryConfig.headers as Record<string, string>),
        ...stepUpHeaders(stepUp),
      },
    });
    statusMessage.value = t('core.common.upgradeRecovery.waiting');
    waitForRestart();
  } catch (_error) {
    restarting.value = false;
    statusMessage.value = t('core.common.upgradeRecovery.failed');
  }
}

async function showRecoveryDialog(versionData: VersionData, blocking = false) {
  if (visible.value || restarting.value) {
    return;
  }
  if (!versionsMismatch(versionData.version, versionData.dashboard_version)) {
    return;
  }

  coreVersion.value = displayVersion(versionData.version);
  dashboardVersion.value = displayVersion(versionData.dashboard_version);
  if (!blocking && sessionStorage.getItem(getDismissKey())) {
    return;
  }

  blockingRecovery.value = blocking;
  initialStartTime.value = await fetchLegacyStartTime().catch(() => null);
  visible.value = true;
}

function handleRecoveryEvent(event: Event) {
  const versionData = (event as CustomEvent<RecoveryEventDetail>).detail || {};
  void showRecoveryDialog(versionData, Boolean(versionData.blocking));
}

async function detectUpgradeMismatch() {
  if (detecting || visible.value || restarting.value) {
    return;
  }
  detecting = true;
  try {
    const authResponse = await authApi.setupStatus(recoveryRequestConfig(true));
    if (authResponse.status === 401) {
      return;
    }
    const versionResponse = await statsApi.version(recoveryRequestConfig(true));
    if (versionResponse.status === 401 || versionResponse.status >= 400) {
      return;
    }
    await showRecoveryDialog(versionResponse.data?.data || {});
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
