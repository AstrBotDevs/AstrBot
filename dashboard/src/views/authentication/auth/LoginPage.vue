<script setup lang="ts">
import AuthLogin from '../authForms/AuthLogin.vue';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import { computed, onMounted, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { useCustomizerStore } from "@/stores/customizer";
import { useModuleI18n } from '@/i18n/composables';
import { useTheme } from 'vuetify';
import { authApi } from '@/api/v1';

const cardVisible = ref(false);
const router = useRouter();
const authStore = useAuthStore();
const customizer = useCustomizerStore();
const { tm: t } = useModuleI18n('features/auth');
const theme = useTheme();
const authLoginRef = ref<InstanceType<typeof AuthLogin> | null>(null);

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

onMounted(async () => {
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
    </v-card>
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
</style>
