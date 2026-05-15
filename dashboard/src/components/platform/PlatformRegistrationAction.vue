<template>
  <div v-if="action" class="platform-registration-panel">
    <div class="registration-scan-title">
      {{ tm(action.scanTitleKey) }}
    </div>

    <div class="registration-scan-content">
      <div class="registration-qr-stage">
        <div
          class="registration-qr-shell"
          :class="{ 'registration-qr-shell-created': flow.status === 'created' }"
        >
          <QrCodeViewer
            v-if="qrValue"
            :value="qrValue"
            :alt="tm(action.titleKey)"
            :size="150"
            :margin="1"
          />
          <div v-else class="registration-qr-loading">
            <v-progress-circular indeterminate color="primary"></v-progress-circular>
          </div>
        </div>

        <div v-if="flow.status === 'created'" class="registration-created-overlay">
          <div class="registration-created-mark">
            <v-icon size="58" color="white">mdi-check</v-icon>
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

<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';
import QrCodeViewer from '@/components/shared/QrCodeViewer.vue';

const FEISHU_DOMAIN = 'https://open.feishu.cn';

const REGISTRATION_ACTIONS = {
  lark: {
    endpoint: '/api/platform/registration/lark',
    icon: 'mdi-qrcode',
    titleKey: 'registrationAction.lark.title',
    scanTitleKey: 'registrationAction.lark.scanTitle',
    successKey: 'registrationAction.created',
  },
  weixin_oc: {
    endpoint: '/api/platform/registration/weixin_oc',
    icon: 'mdi-qrcode',
    titleKey: 'registrationAction.weixinOc.title',
    scanTitleKey: 'registrationAction.weixinOc.scanTitle',
    successKey: 'registrationAction.weixinOc.created',
    statusKeyPrefix: 'registrationAction.weixinOc.status',
  },
};

export default {
  name: 'PlatformRegistrationAction',
  components: { QrCodeViewer },
  emits: ['success', 'error', 'created'],
  props: {
    platformConfig: {
      type: Object,
      default: null,
    },
    active: {
      type: Boolean,
      default: true,
    },
  },
  setup() {
    const { tm } = useModuleI18n('features/platform');
    return { tm };
  },
  data() {
    return {
      flow: {
        status: 'idle',
      },
      loading: false,
      pollTimer: null,
    };
  },
  computed: {
    action() {
      return REGISTRATION_ACTIONS[this.platformConfig?.type] || null;
    },
    selectedDomain() {
      return this.platformConfig?.domain || FEISHU_DOMAIN;
    },
    qrValue() {
      return this.flow.verification_uri_complete
        || this.flow.qrcode_img_content
        || this.flow.qrcode
        || '';
    },
  },
  watch: {
    active: {
      immediate: true,
      handler(active) {
        if (active) {
          this.ensureStarted();
        } else {
          this.stopPolling();
        }
      },
    },
    'platformConfig.type'() {
      this.resetFlow();
      this.ensureStarted();
    },
  },
  beforeUnmount() {
    this.stopPolling();
  },
  methods: {
    resetFlow() {
      this.stopPolling();
      this.flow = { status: 'idle' };
    },
    ensureStarted() {
      if (!this.active || !this.action || this.flow.status !== 'idle') {
        return;
      }
      this.startAction();
    },
    buildPayload(action, extra = {}) {
      return {
        action,
        platform_config: {
          ...this.platformConfig,
          domain: this.selectedDomain,
        },
        ...extra,
      };
    },
    async startAction() {
      if (!this.action || this.loading) {
        return;
      }
      this.stopPolling();
      this.loading = true;
      this.flow = { status: 'starting' };
      try {
        const res = await axios.post(this.action.endpoint, this.buildPayload('start'));
        if (res.data.status !== 'ok') {
          throw new Error(res.data.message || this.tm('registrationAction.startFailed'));
        }
        this.flow = {
          ...res.data.data,
          status: res.data.data?.status || 'pending',
        };
        if (this.flow.registration_code && this.flow.status === 'pending') {
          this.schedulePoll(this.flow.interval || 5);
        }
      } catch (err) {
        this.flow = {
          status: 'error',
          message: err.response?.data?.message || err.message || this.tm('registrationAction.startFailed'),
        };
        this.$emit('error', this.flow.message);
      } finally {
        this.loading = false;
      }
    },
    schedulePoll(intervalSeconds) {
      this.stopPolling();
      const seconds = Math.max(Number(intervalSeconds || 3), 1);
      this.pollTimer = setTimeout(() => {
        this.pollAction();
      }, seconds * 1000);
    },
    stopPolling() {
      if (this.pollTimer) {
        clearTimeout(this.pollTimer);
        this.pollTimer = null;
      }
    },
    async pollAction() {
      if (!this.action || !this.flow.registration_code) {
        return;
      }
      try {
        const res = await axios.post(this.action.endpoint, this.buildPayload('poll', {
          registration_code: this.flow.registration_code,
        }));
        if (res.data.status !== 'ok') {
          throw new Error(res.data.message || this.tm('registrationAction.pollFailed'));
        }
        const data = res.data.data || {};
        this.flow = {
          ...this.flow,
          ...data,
          status: data.status || 'error',
        };
        if (this.flow.status === 'created') {
          this.applyRegistrationResult(data);
          this.stopPolling();
          this.$emit('created', data);
          this.$emit('success', this.tm(this.action.successKey || 'registrationAction.created'));
          return;
        }
        if (this.flow.status === 'pending' || this.flow.status === 'slow_down') {
          const nextInterval = this.flow.status === 'slow_down'
            ? Number(this.flow.interval || 5) + 5
            : Number(this.flow.interval || 5);
          this.flow.interval = nextInterval;
          this.schedulePoll(nextInterval);
          return;
        }
        this.stopPolling();
      } catch (err) {
        this.flow = {
          ...this.flow,
          status: 'error',
          message: err.response?.data?.message || err.message || this.tm('registrationAction.pollFailed'),
        };
        this.$emit('error', this.flow.message);
        this.stopPolling();
      }
    },
    applyRegistrationResult(data) {
      if (!this.platformConfig || !data) {
        return;
      }
      if (data.app_id) {
        this.platformConfig.app_id = data.app_id;
      }
      if (data.app_secret) {
        this.platformConfig.app_secret = data.app_secret;
      }
      if (data.domain) {
        this.platformConfig.domain = data.domain;
      }
      if (data.weixin_oc_token) {
        this.platformConfig.weixin_oc_token = data.weixin_oc_token;
      }
      if (data.weixin_oc_account_id) {
        this.platformConfig.weixin_oc_account_id = data.weixin_oc_account_id;
      }
      if (data.weixin_oc_base_url) {
        this.platformConfig.weixin_oc_base_url = data.weixin_oc_base_url;
      }
    },
    getStatusText(status) {
      const normalizedStatus = status || 'idle';
      if (this.action?.statusKeyPrefix) {
        const platformStatusKey = `${this.action.statusKeyPrefix}.${normalizedStatus}`;
        const platformStatusText = this.tm(platformStatusKey);
        if (platformStatusText && platformStatusText !== platformStatusKey) {
          return platformStatusText;
        }
      }
      return this.tm(`registrationAction.status.${normalizedStatus}`);
    },
    getStatusColor(status) {
      switch (status) {
        case 'created': return 'success';
        case 'error':
        case 'denied':
        case 'expired': return 'error';
        case 'starting':
        case 'pending':
        case 'slow_down': return 'warning';
        default: return 'grey';
      }
    },
    getStatusIcon(status) {
      switch (status) {
        case 'created': return 'mdi-check-circle';
        case 'error':
        case 'denied':
        case 'expired': return 'mdi-alert-circle';
        case 'starting': return 'mdi-loading';
        case 'pending':
        case 'slow_down': return 'mdi-timer-sand';
        default: return 'mdi-circle-outline';
      }
    },
  },
};
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
  color: rgba(0, 0, 0, 0.78);
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
  transition: filter 160ms ease, opacity 160ms ease;
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
  border: 1px solid rgba(0, 0, 0, 0.12);
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
  color: rgba(0, 0, 0, 0.72);
  word-break: break-word;
}
</style>
