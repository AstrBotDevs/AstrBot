<script setup lang="ts">
import AuthLogin from '../authForms/AuthLogin.vue';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import { computed, onMounted, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { useCustomizerStore } from "@/stores/customizer";
import { useModuleI18n } from '@/i18n/composables';
import { useTheme } from 'vuetify';
import { authApi, publicApi, type PublicVersionData } from '@/api/v1';

const cardVisible = ref(false);
const router = useRouter();
const authStore = useAuthStore();
const customizer = useCustomizerStore();
const { tm: t } = useModuleI18n('features/auth');
const theme = useTheme();
const authLoginRef = ref<InstanceType<typeof AuthLogin> | null>(null);
const publicVersions = ref<PublicVersionData | null>(null);
const versionDialogVisible = ref(false);
type VersionItem = { key: string; label: string; value: string };
type VersionWarning = { key: string; title: string; message: string };

const logoTitle = computed(() => {
  if (authLoginRef.value?.stage === 'totp' || authLoginRef.value?.stage === 'recovery') {
    return t('logo.totpTitle');
  }
  return t('logo.title');
});

const themeOptions = [
  { mode: 'light'  as const, icon: 'mdi-white-balance-sunny', labelKey: 'theme.light'  },
  { mode: 'dark'   as const, icon: 'mdi-weather-night',       labelKey: 'theme.dark'   },
  { mode: 'system' as const, icon: 'mdi-sync',                labelKey: 'theme.system' },
] as const;

function setThemeMode(mode: 'light' | 'dark' | 'system') {
  customizer.SET_THEME_MODE(mode);
  theme.global.name.value = customizer.uiTheme;
}

const currentThemeIcon = computed(() => {
  if (customizer.themeMode === 'dark') return 'mdi-weather-night';
  if (customizer.themeMode === 'system') return 'mdi-sync';
  return 'mdi-white-balance-sunny';
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

const normalizedVersionValues = computed(() => {
  return {
    webui: versionValues.value.webui.replace(/^v/i, ''),
    runtime: versionValues.value.runtime.replace(/^v/i, ''),
    code: versionValues.value.code.replace(/^v/i, ''),
  };
});

const versionWarnings = computed(() => {
  const normalized = normalizedVersionValues.value;
  const warnings: VersionWarning[] = [];

  if (normalized.webui && normalized.runtime && normalized.webui !== normalized.runtime) {
    warnings.push({
      key: 'webui-runtime',
      title: t('versions.webuiMismatchTitle'),
      message: t('versions.webuiMismatchMessage'),
    });
  }
  if (normalized.runtime && normalized.code && normalized.runtime !== normalized.code) {
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
    items.push({
      key: 'webui',
      label: t('versions.webui'),
      value: webui,
    });
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
  publicApi.versions()
    .then((res) => {
      publicVersions.value = res.data?.data || null;
    })
    .catch((error) => {
      if (import.meta.env.DEV) {
        console.warn('Failed to load public versions:', error);
      }
    });

  // 检查用户是否已登录，如果已登录则重定向
  if (authStore.has_token()) {
    const onboardingCompleted = await authStore.checkOnboardingCompleted();
    if (onboardingCompleted) {
      router.push('/dashboard/default');
    } else {
      router.push('/welcome');
    }
    return;
  }

  try {
    const setupStatus = await authApi.setupStatus();
    if (
      setupStatus.data?.data?.setup_required &&
      setupStatus.data?.data?.skip_default_password_auth
    ) {
      router.push('/auth/setup');
      return;
    }
  } catch {
    // Keep the normal login flow if setup status is unavailable.
  }

  // 添加一个小延迟以获得更好的动画效果
  setTimeout(() => {
    cardVisible.value = true;
  }, 100);
});
</script>

<template>
  <div class="login-page-container">
    <v-card class="login-card" elevation="1">
      <v-card-title>
        <div class="d-flex justify-space-between align-center w-100">
          <img width="80" src="@/assets/images/icon-no-shadow.svg" alt="AstrBot Logo">
          <div class="d-flex align-center gap-1">
            <LanguageSwitcher />
            <v-divider vertical class="mx-1"
              style="height: 24px !important; opacity: 0.9 !important; align-self: center !important; border-color: rgba(var(--v-theme-primary), 0.45) !important;"></v-divider>

            <!-- 主题切换下拉菜单 -->
            <v-menu
              open-on-click
              location="bottom center"
              offset="6"
            >
              <template v-slot:activator="{ props: themeMenuProps }">
                <v-btn
                  v-bind="themeMenuProps"
                  class="theme-toggle-btn"
                  icon
                  variant="text"
                  size="small"
                >
                  <v-icon size="18" :color="'rgb(var(--v-theme-primary))'">
                    {{ currentThemeIcon }}
                  </v-icon>
                  <v-tooltip activator="parent" location="top">
                    {{ t('theme.title') }}
                  </v-tooltip>
                </v-btn>
              </template>

              <v-card
                class="styled-menu-card"
                style="min-width: 150px"
                elevation="8"
                rounded="lg"
              >
                <v-list density="compact" class="styled-menu-list pa-1">
                  <v-list-item
                    v-for="option in themeOptions"
                    :key="option.mode"
                    @click="setThemeMode(option.mode)"
                    :class="{
                      'styled-menu-item-active': customizer.themeMode === option.mode,
                    }"
                    class="styled-menu-item"
                    rounded="md"
                  >
                    <template v-slot:prepend>
                      <v-icon size="16" style="margin-right: 8px; opacity: 0.85;">{{ option.icon }}</v-icon>
                    </template>
                    <v-list-item-title>{{ t(option.labelKey) }}</v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-card>
            </v-menu>
          </div>
        </div>
        <div class="ml-2" style="font-size: 26px;">{{ logoTitle }}</div>
        <div v-if="authLoginRef?.stage !== 'totp' && authLoginRef?.stage !== 'recovery'" class="mt-2 ml-2" style="font-size: 14px; color: grey;">{{ t('logo.subtitle') }}</div>
      </v-card-title>
      <v-card-text>
        <AuthLogin ref="authLoginRef" />
      </v-card-text>
      <div v-if="versionItems.length" class="login-version-info">
        <span v-for="item in versionItems" :key="item.key" class="login-version-item">
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
      <v-card class="version-dialog-card">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 version-dialog-title">
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
            href="https://docs.astrbot.app/faq.html"
            target="_blank"
            rel="noopener noreferrer"
            variant="text"
            prepend-icon="mdi-help-circle-outline"
          >
            {{ t('versions.faq') }}
          </v-btn>
          <v-spacer />
          <v-btn color="primary" variant="text" @click="versionDialogVisible = false">
            {{ t('versions.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style lang="scss">
.login-page-container {
  background-color: rgb(var(--v-theme-containerBg));
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
}

.login-card {
  width: 400px;
  padding: 8px;
}

.login-version-info {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.56);
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  justify-content: center;
  line-height: 1.45;
  padding: 0 14px 10px;
  text-align: center;
  font-size: 12px;
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
  border-radius: 8px !important;
}

.version-dialog-title {
  align-items: center;
  display: flex;
  gap: 8px;
}

.version-dialog-content {
  padding-top: 4px !important;
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
