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
import { onBeforeUnmount, onMounted, ref } from 'vue';

import type { ApiEnvelope, VersionData } from '@/api/v1';
import { httpClient } from '@/api/http';
import { useI18n } from '@/i18n/composables';

type StartTimeData = {
  start_time?: number | string | null;
};

const { t } = useI18n();

const visible = ref(false);
const restarting = ref(false);
const statusMessage = ref('');
const coreVersion = ref('');
const dashboardVersion = ref('');
const initialStartTime = ref<number | string | null>(null);

let restartTimer: ReturnType<typeof setInterval> | null = null;

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

async function fetchLegacyStartTime() {
  const response = await httpClient.get<ApiEnvelope<StartTimeData>>(
    '/api/stat/start-time',
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
    await httpClient.post<ApiEnvelope<unknown>>('/api/stat/restart-core');
    statusMessage.value = t('core.common.upgradeRecovery.waiting');
    waitForRestart();
  } catch (_error) {
    restarting.value = false;
    statusMessage.value = t('core.common.upgradeRecovery.failed');
  }
}

async function detectUpgradeMismatch() {
  try {
    const v1Response = await httpClient.get<ApiEnvelope<unknown>>(
      '/api/v1/auth/setup-status',
      { validateStatus: () => true },
    );
    if (!isMissingApiKeyResponse(v1Response)) {
      return;
    }

    const legacyResponse = await httpClient.get<ApiEnvelope<VersionData>>(
      '/api/stat/version',
      { validateStatus: () => true },
    );
    if (legacyResponse.status === 401 || legacyResponse.status >= 400) {
      return;
    }

    const versionData = legacyResponse.data?.data || {};
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
  } catch (_error) {
    // This recovery dialog is best-effort and should never block the app.
  }
}

onMounted(() => {
  void detectUpgradeMismatch();
});

onBeforeUnmount(() => {
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
