<template>
  <div v-if="action" class="platform-registration-panel">
    <div class="registration-scan-title">
      {{ tm(action.scanTitleKey) }}
    </div>

    <div class="registration-scan-content">
      <div class="registration-qr-stage">
        <div
          class="registration-qr-shell"
          :class="{
            'registration-qr-shell-created': flow.status === 'created',
          }"
        >
          <QrCodeViewer
            v-if="qrValue"
            :value="qrValue"
            :alt="tm(action.titleKey)"
            :size="150"
            :margin="1"
          />
          <div v-else class="registration-qr-loading">
            <v-progress-circular
              indeterminate
              color="primary"
            ></v-progress-circular>
          </div>
        </div>

        <div
          v-if="flow.status === 'created'"
          class="registration-created-overlay"
        >
          <div class="registration-created-mark">
            <v-icon size="58" color="on-success">mdi-check</v-icon>
          </div>
        </div>
      </div>

      <div class="registration-action-status mt-2">
        <v-icon size="small" class="me-1" :color="getStatusColor(flow.status)">
          {{ getStatusIcon(flow.status) }}
        </v-icon>
        {{ getStatusText(flow.status) }}
      </div>
    </div>

    <div v-if="flow.message" class="registration-action-message mt-2">
      {{ flow.message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { botApi } from '@/api/v1';
import type { BotRegistrationRequest } from '@/api/generated/openapi-v1';
import QrCodeViewer from '@/components/shared/QrCodeViewer.vue';
import { useModuleI18n } from '@/i18n/composables';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { computed, onBeforeUnmount, ref, watch } from 'vue';

const FEISHU_DOMAIN = 'https://open.feishu.cn';

interface RegistrationAction {
  icon: string;
  titleKey: string;
  scanTitleKey: string;
  successKey: string;
  statusKeyPrefix?: string;
}

interface PlatformConfig {
  type?: string;
  domain?: string;
  app_id?: string;
  app_secret?: string;
  appid?: string;
  secret?: string;
  weixin_oc_token?: string;
  weixin_oc_account_id?: string;
  weixin_oc_base_url?: string;
  client_id?: string;
  client_secret?: string;
  [key: string]: unknown;
}

interface RegistrationFlow {
  status: string;
  message?: string;
  interval?: number;
  verification_uri_complete?: string;
  qrcode_img_content?: string;
  qrcode?: string;
  registration_code?: string;
  task_id?: string;
  bind_key?: string;
  app_id?: string;
  app_secret?: string;
  appid?: string;
  secret?: string;
  domain?: string;
  weixin_oc_token?: string;
  weixin_oc_account_id?: string;
  weixin_oc_base_url?: string;
  client_id?: string;
  client_secret?: string;
  [key: string]: unknown;
}

const REGISTRATION_ACTIONS: Record<string, RegistrationAction> = {
  lark: {
    icon: 'mdi-qrcode',
    titleKey: 'registrationAction.lark.title',
    scanTitleKey: 'registrationAction.lark.scanTitle',
    successKey: 'registrationAction.created',
  },
  weixin_oc: {
    icon: 'mdi-qrcode',
    titleKey: 'registrationAction.weixinOc.title',
    scanTitleKey: 'registrationAction.weixinOc.scanTitle',
    successKey: 'registrationAction.weixinOc.created',
    statusKeyPrefix: 'registrationAction.weixinOc.status',
  },
  dingtalk: {
    icon: 'mdi-qrcode',
    titleKey: 'registrationAction.dingtalk.title',
    scanTitleKey: 'registrationAction.dingtalk.scanTitle',
    successKey: 'registrationAction.dingtalk.created',
  },
  qq_official: {
    icon: 'mdi-qrcode',
    titleKey: 'registrationAction.qqOfficial.title',
    scanTitleKey: 'registrationAction.qqOfficial.scanTitle',
    successKey: 'registrationAction.qqOfficial.created',
    statusKeyPrefix: 'registrationAction.qqOfficial.status',
  },
  qq_official_webhook: {
    icon: 'mdi-qrcode',
    titleKey: 'registrationAction.qqOfficial.title',
    scanTitleKey: 'registrationAction.qqOfficial.scanTitle',
    successKey: 'registrationAction.qqOfficial.created',
    statusKeyPrefix: 'registrationAction.qqOfficial.status',
  },
};

const props = withDefaults(
  defineProps<{
    platformConfig?: PlatformConfig | null;
    active?: boolean;
  }>(),
  {
    platformConfig: null,
    active: true,
  },
);

const emit = defineEmits<{
  (event: 'success', message: string): void;
  (event: 'error', message: string): void;
  (event: 'created', data: RegistrationFlow): void;
}>();

const { tm } = useModuleI18n('features/platform');

const flow = ref<RegistrationFlow>({ status: 'idle' });
const loading = ref(false);
const pollTimer = ref<ReturnType<typeof window.setTimeout> | null>(null);

const action = computed<RegistrationAction | null>(
  () => REGISTRATION_ACTIONS[props.platformConfig?.type ?? ''] ?? null,
);

const selectedDomain = computed(
  () => props.platformConfig?.domain || FEISHU_DOMAIN,
);

const qrValue = computed(
  () =>
    flow.value.verification_uri_complete ||
    flow.value.qrcode_img_content ||
    flow.value.qrcode ||
    '',
);

function stopPolling(): void {
  if (pollTimer.value !== null) {
    clearTimeout(pollTimer.value);
    pollTimer.value = null;
  }
}

function resetFlow(): void {
  stopPolling();
  flow.value = { status: 'idle' };
}

function ensureStarted(): void {
  if (!props.active || !action.value || flow.value.status !== 'idle') {
    return;
  }
  void startAction();
}

function buildPayload(
  actionName: 'start' | 'poll',
  extra: Record<string, unknown> = {},
): BotRegistrationRequest {
  return {
    action: actionName,
    platform_config: {
      ...props.platformConfig,
      domain: selectedDomain.value,
    },
    ...extra,
  };
}

async function startAction(): Promise<void> {
  if (!action.value || loading.value || !props.platformConfig?.type) {
    return;
  }
  stopPolling();
  loading.value = true;
  flow.value = { status: 'starting' };
  try {
    const res = await botApi.registration(
      props.platformConfig.type,
      buildPayload('start'),
    );
    if (res.data.status !== 'ok') {
      throw new Error(res.data.message || tm('registrationAction.startFailed'));
    }
    flow.value = {
      ...(res.data.data || {}),
      status: res.data.data?.status || 'pending',
    };
    if (flow.value.registration_code && flow.value.status === 'pending') {
      schedulePoll(flow.value.interval || 5);
    }
  } catch (error) {
    const errorMessage = resolveErrorMessage(
      error,
      tm('registrationAction.startFailed'),
    );
    flow.value = {
      status: 'error',
      message: errorMessage,
    };
    emit('error', errorMessage);
  } finally {
    loading.value = false;
  }
}

function schedulePoll(intervalSeconds: number): void {
  stopPolling();
  const seconds = Math.max(Number(intervalSeconds || 3), 1);
  pollTimer.value = window.setTimeout(() => {
    void pollAction();
  }, seconds * 1000);
}

async function pollAction(): Promise<void> {
  if (
    !action.value ||
    !props.platformConfig?.type ||
    !flow.value.registration_code
  ) {
    return;
  }
  const pollPayload: Record<string, unknown> = {
    registration_code: flow.value.registration_code,
  };
  if (flow.value.task_id) {
    pollPayload.task_id = flow.value.task_id;
  }
  if (flow.value.bind_key) {
    pollPayload.bind_key = flow.value.bind_key;
  }
  try {
    const res = await botApi.registration(
      props.platformConfig.type,
      buildPayload('poll', pollPayload),
    );
    if (res.data.status !== 'ok') {
      throw new Error(res.data.message || tm('registrationAction.pollFailed'));
    }
    const data = (res.data.data || {}) as RegistrationFlow;
    flow.value = {
      ...flow.value,
      ...data,
      status: data.status || 'error',
    };
    if (flow.value.status === 'created') {
      applyRegistrationResult(data);
      stopPolling();
      emit('created', data);
      emit(
        'success',
        tm(action.value.successKey || 'registrationAction.created'),
      );
      return;
    }
    if (flow.value.status === 'pending' || flow.value.status === 'slow_down') {
      const nextInterval =
        flow.value.status === 'slow_down'
          ? Number(flow.value.interval || 5) + 5
          : Number(flow.value.interval || 5);
      flow.value.interval = nextInterval;
      schedulePoll(nextInterval);
      return;
    }
    stopPolling();
  } catch (error) {
    const errorMessage = resolveErrorMessage(
      error,
      tm('registrationAction.pollFailed'),
    );
    flow.value = {
      ...flow.value,
      status: 'error',
      message: errorMessage,
    };
    emit('error', errorMessage);
    stopPolling();
  }
}

function applyRegistrationResult(data: RegistrationFlow): void {
  if (!props.platformConfig) {
    return;
  }
  const fields: Array<keyof RegistrationFlow> = [
    'app_id',
    'app_secret',
    'appid',
    'secret',
    'domain',
    'weixin_oc_token',
    'weixin_oc_account_id',
    'weixin_oc_base_url',
    'client_id',
    'client_secret',
  ];
  for (const field of fields) {
    if (data[field]) {
      props.platformConfig[field] = data[field];
    }
  }
}

function getStatusText(status: string): string {
  const normalizedStatus = status || 'idle';
  if (action.value?.statusKeyPrefix) {
    const platformStatusKey = `${action.value.statusKeyPrefix}.${normalizedStatus}`;
    const platformStatusText = tm(platformStatusKey);
    if (platformStatusText && platformStatusText !== platformStatusKey) {
      return platformStatusText;
    }
  }
  return tm(`registrationAction.status.${normalizedStatus}`);
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'created':
      return 'success';
    case 'error':
    case 'denied':
    case 'expired':
      return 'error';
    case 'starting':
    case 'pending':
    case 'slow_down':
      return 'warning';
    default:
      return 'grey';
  }
}

function getStatusIcon(status: string): string {
  switch (status) {
    case 'created':
      return 'mdi-check-circle';
    case 'error':
    case 'denied':
    case 'expired':
      return 'mdi-alert-circle';
    case 'starting':
      return 'mdi-loading';
    case 'pending':
    case 'slow_down':
      return 'mdi-timer-sand';
    default:
      return 'mdi-circle-outline';
  }
}

watch(
  () => props.active,
  (active) => {
    if (active) {
      ensureStarted();
    } else {
      stopPolling();
    }
  },
  { immediate: true },
);

watch(
  () => props.platformConfig?.type,
  () => {
    resetFlow();
    ensureStarted();
  },
);

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<style scoped>
.platform-registration-panel {
  width: 320px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.registration-scan-title {
  width: 190px;
  margin-bottom: 4px;
  font-size: 14px;
  font-weight: 600;
  text-align: left;
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.registration-scan-content {
  margin-left: 8px;
}

.registration-qr-stage {
  position: relative;
  width: 190px;
  min-height: 190px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.registration-qr-shell {
  width: 190px;
  min-height: 190px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    filter 160ms ease,
    opacity 160ms ease;
}

.registration-qr-shell :deep(.qr-code-image) {
  width: 190px;
}

.registration-qr-shell-created {
  filter: blur(2px);
  opacity: 0.32;
}

.registration-qr-loading {
  width: 160px;
  height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
}

.registration-created-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.registration-created-mark {
  width: 86px;
  height: 86px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgb(var(--v-theme-success));
}

.registration-action-status,
.registration-action-message {
  width: 190px;
  text-align: center;
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  word-break: break-word;
}
</style>
