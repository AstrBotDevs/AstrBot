<script setup lang="ts">
import AuthLogin from '../authForms/AuthLogin.vue';
import AuthAppearanceMenu from '@/components/auth/AuthAppearanceMenu.vue';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { useModuleI18n } from '@/i18n/composables';
import { docsHref } from '@/utils/docsHref';
import { authApi, publicApi, type PublicVersionData } from '@/api/v1';

const cardVisible = ref(false);
const router = useRouter();
const authStore = useAuthStore();
const { tm: t } = useModuleI18n('features/auth');
const authLoginRef = ref<InstanceType<typeof AuthLogin> | null>(null);
const publicVersions = ref<PublicVersionData | null>(null);
const versionDialogVisible = ref(false);
let cardRevealTimer: ReturnType<typeof window.setTimeout> | null = null;
type VersionItem = { key: string; label: string; value: string };
type VersionWarning = { key: string; title: string; message: string };

const logoTitle = computed(() => {
  if (
    authLoginRef.value?.stage === 'totp' ||
    authLoginRef.value?.stage === 'recovery'
  ) {
    return t('logo.totpTitle');
  }
  return t('logo.title');
});

const versionValues = computed(() => {
  const versions = publicVersions.value;
  if (!versions) {
    return { webui: '', runtime: '', code: '' };
  }

  return {
    webui: String(versions.webui_version || '').trim(),
    runtime: String(versions.astrbot_version || '').trim(),
    code: String(versions.astrbot_code_version || '').trim(),
  };
});

const normalizedVersionValues = computed(() => ({
  webui: versionValues.value.webui.replace(/^v/i, ''),
  runtime: versionValues.value.runtime.replace(/^v/i, ''),
  code: versionValues.value.code.replace(/^v/i, ''),
}));

const versionWarnings = computed(() => {
  const normalized = normalizedVersionValues.value;
  const warnings: VersionWarning[] = [];

  if (
    normalized.webui &&
    normalized.runtime &&
    normalized.webui !== normalized.runtime
  ) {
    warnings.push({
      key: 'webui-runtime',
      title: t('versions.webuiMismatchTitle'),
      message: t('versions.webuiMismatchMessage'),
    });
  }
  if (
    normalized.runtime &&
    normalized.code &&
    normalized.runtime !== normalized.code
  ) {
    warnings.push({
      key: 'runtime-code',
      title: t('versions.runtimeMismatchTitle'),
      message: t('versions.runtimeMismatchMessage'),
    });
  }

  return warnings;
});

const versionItems = computed(() => {
  const { webui, runtime, code } = versionValues.value;
  const normalized = normalizedVersionValues.value;
  const items: VersionItem[] = [];

  if (webui) {
    items.push({ key: 'webui', label: t('versions.webui'), value: webui });
  }
  if (runtime) {
    items.push({
      key: 'astrbot',
      label: t('versions.astrbotRuntime'),
      value: runtime,
    });
  }
  if (runtime && code && normalized.runtime !== normalized.code) {
    items.push({
      key: 'astrbot-code',
      label: t('versions.astrbotCode'),
      value: code,
    });
  }

  return items;
});

onMounted(async () => {
  publicApi
    .versions()
    .then((res) => {
      publicVersions.value = res.data?.data || null;
    })
    .catch(() => {
      if (import.meta.env.DEV) {
        console.warn('Failed to load public versions');
      }
    });

  // 检查用户是否已登录，如果已登录则重定向
  if (authStore.has_token()) {
    const onboardingCompleted = await authStore.checkOnboardingCompleted();
    if (onboardingCompleted) {
      void router.push('/dashboard');
    } else {
      void router.push('/welcome');
    }
    return;
  }

  try {
    const setupStatus = await authApi.setupStatus();
    if (
      setupStatus.data?.data?.setup_required &&
      setupStatus.data?.data?.skip_default_password_auth
    ) {
      void router.push('/auth/setup');
      return;
    }
  } catch {
    // Keep the normal login flow if setup status is unavailable.
  }

  // 添加一个小延迟以获得更好的动画效果
  cardRevealTimer = window.setTimeout(() => {
    cardVisible.value = true;
    cardRevealTimer = null;
  }, 100);
});

onBeforeUnmount(() => {
  if (cardRevealTimer !== null) {
    window.clearTimeout(cardRevealTimer);
    cardRevealTimer = null;
  }
});
</script>

<template>
  <div class="auth-page-container">
    <v-card class="auth-card login-card" elevation="0">
      <v-card-title>
        <div class="auth-header">
          <img
            data-testid="login-logo"
            width="80"
            :src="'/favicon.svg'"
            alt="AstrBot Logo"
          />
          <AuthAppearanceMenu />
        </div>
        <div class="auth-header__title">{{ logoTitle }}</div>
        <div
          v-if="
            authLoginRef?.stage !== 'totp' && authLoginRef?.stage !== 'recovery'
          "
          class="auth-header__subtitle"
        >
          {{ t('logo.subtitle') }}
        </div>
      </v-card-title>
      <v-card-text>
        <AuthLogin ref="authLoginRef" />
      </v-card-text>
      <div v-if="versionItems.length" class="login-version-info">
        <span
          v-for="item in versionItems"
          :key="item.key"
          class="login-version-item"
        >
          <span class="login-version-label">{{ item.label }}</span>
          <span class="login-version-value">{{ item.value }}</span>
        </span>
        <v-btn
          v-if="versionWarnings.length"
          class="version-help-btn"
          icon
          variant="text"
          size="x-small"
          :aria-label="t('versions.mismatchTooltip')"
          @click="versionDialogVisible = true"
        >
          <v-icon size="16">mdi-help-circle-outline</v-icon>
          <v-tooltip activator="parent" location="top">
            {{ t('versions.mismatchTooltip') }}
          </v-tooltip>
        </v-btn>
      </div>
    </v-card>
    <v-dialog v-model="versionDialogVisible" max-width="460">
      <v-card class="app-dialog version-dialog-card">
        <v-card-title class="version-dialog-title">
          <v-icon size="20" color="warning">mdi-alert-circle-outline</v-icon>
          <span>{{ t('versions.dialogTitle') }}</span>
        </v-card-title>
        <v-card-text class="version-dialog-content">
          <div
            v-for="warning in versionWarnings"
            :key="warning.key"
            class="version-warning-block"
          >
            <div class="version-warning-title">{{ warning.title }}</div>
            <div class="version-warning-message">{{ warning.message }}</div>
          </div>
        </v-card-text>
        <v-card-actions class="version-dialog-actions">
          <v-btn
            :href="docsHref('faq.html')"
            target="_blank"
            rel="noopener noreferrer"
            variant="text"
            prepend-icon="mdi-help-circle-outline"
          >
            {{ t('versions.faq') }}
          </v-btn>
          <v-spacer />
          <v-btn
            color="primary"
            variant="text"
            @click="versionDialogVisible = false"
          >
            {{ t('versions.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style lang="scss">
.login-card {
  width: 400px;
}

.login-version-info {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.56);
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 4px 8px;
  justify-content: center;
  line-height: 1.45;
  padding: 0 14px 10px;
  text-align: center;
}

.login-version-item {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.login-version-label {
  margin-right: 4px;
}

.version-help-btn {
  color: rgba(var(--v-theme-warning), 0.95);
  margin-left: -2px;
}

.version-dialog-card {
  border-radius: 8px;
}

.version-dialog-title {
  align-items: center;
  display: flex;
  font-size: 17px;
  gap: 8px;
  line-height: 1.35;
  padding-bottom: 8px;
}

.version-dialog-content {
  padding-top: 4px;
}

.version-warning-block + .version-warning-block {
  margin-top: 14px;
}

.version-warning-title {
  color: rgba(var(--v-theme-on-surface), 0.88);
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
}

.version-warning-message {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 13px;
  line-height: 1.65;
}

.version-dialog-actions {
  padding-top: 0;
}
</style>
