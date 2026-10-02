<script setup lang="ts">
import AuthSetup from '../authForms/AuthSetup.vue';
import OnboardingSetup from '@/components/OnboardingSetup.vue';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import { computed, ref, watch } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRoute, useRouter } from 'vue-router';
import { useCustomizerStore } from '@/stores/customizer';
import { useModuleI18n } from '@/i18n/composables';
import { useTheme } from 'vuetify';
import { authApi } from '@/api/v1';

const router = useRouter();
const route = useRoute();
const isOnboarding = computed(() => route.name === 'Onboarding');
const ready = ref(false);
const authStore = useAuthStore();
const customizer = useCustomizerStore();
const { tm: t } = useModuleI18n('features/auth');
const { tm } = useModuleI18n('features/welcome');
const theme = useTheme();

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

watch(isOnboarding, async (onboarding, _, onCleanup) => {
  ready.value = false;
  let active = true;
  onCleanup(() => { active = false; });
  const hasToken = authStore.has_token();

  try {
    const setupStatus = await authApi.setupStatus();
    if (!active) return;
    if (setupStatus.data.status !== 'ok') throw new Error('Unable to check setup status');
    const setupRequired = !!setupStatus.data?.data?.setup_required;
    const canSkipDefaultPassword = !!setupStatus.data?.data?.skip_default_password_auth;
    if (onboarding) {
      if (!hasToken) router.replace('/auth/login');
      else if (setupRequired) router.replace('/auth/setup');
      else ready.value = true;
    } else if (
      !setupRequired ||
      (!hasToken && !canSkipDefaultPassword)
    ) {
      router.replace('/auth/login');
    } else {
      ready.value = true;
    }
  } catch {
    if (active) router.replace('/auth/login');
  }
}, { immediate: true });
</script>

<template>
  <div class="setup-page-container" :class="{ 'setup-page-container--onboarding': isOnboarding }">
    <v-progress-circular v-if="!ready" indeterminate color="primary" />
    <v-card v-else class="setup-card" :class="{ 'setup-card--onboarding': isOnboarding }" :elevation="isOnboarding ? 0 : 1">
      <v-card-title>
        <div class="setup-header">
          <div class="setup-brand">
            <img :width="isOnboarding ? 32 : 80" src="/favicon.svg" alt="AstrBot Logo">
            <span v-if="isOnboarding" class="setup-wordmark">AstrBot</span>
            <h1 v-if="isOnboarding" class="setup-title setup-title--inline">{{ tm('guide.title') }}</h1>
          </div>
          <div class="d-flex align-center gap-1 flex-shrink-0">
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
        <h1 v-if="!isOnboarding" class="setup-title">{{ t('setup.title') }}</h1>
        <div v-if="!isOnboarding" class="setup-subtitle">{{ t('setup.subtitle') }}</div>
      </v-card-title>
      <v-card-text>
        <OnboardingSetup v-if="isOnboarding" />
        <AuthSetup v-else />
      </v-card-text>
    </v-card>
  </div>
</template>

<style lang="scss" scoped>
.setup-page-container {
  background-color: rgb(var(--v-theme-containerBg));
  position: relative;
  width: 100%;
  min-height: 100dvh;
  padding: 24px 16px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.setup-card {
  width: 420px;
  max-width: 100%;
  padding: 8px;
}

.setup-page-container--onboarding { height: 100dvh; min-height: 0; overflow: hidden; align-items: stretch; padding: 32px 20px 0; background: rgb(var(--v-theme-surface)); }
.setup-card.setup-card--onboarding { display: flex; flex-direction: column; width: 1000px; min-height: 0; padding: 0; border-radius: 0; background: transparent; }
.setup-card--onboarding > .v-card-title, .setup-card--onboarding > .v-card-text { padding: 0; }
.setup-card--onboarding > .v-card-title { flex-shrink: 0; }
.setup-card--onboarding > .v-card-text { display: flex; flex: 1; min-height: 0; }
.setup-card--onboarding .setup-header { align-items: center; gap: 12px; }
.setup-card--onboarding .setup-title--inline { margin: 0 0 0 16px; padding-left: 16px; border-left: 1px solid rgba(var(--v-theme-on-surface), .16); font-size: 16px; font-weight: 500; line-height: 1.4; overflow-wrap: anywhere; }
.setup-wordmark { margin-left: 10px; font-weight: 600; font-size: 20px; flex-shrink: 0; }
.setup-card .v-card-title { white-space: normal; }

.setup-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
}

.setup-brand {
  display: flex;
  align-items: center;
  min-width: 0;
}

.setup-brand img {
  flex: 0 0 auto;
}

.setup-title {
  margin-top: 8px;
  color: rgba(var(--v-theme-on-surface), 0.92);
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
}

.setup-subtitle {
  margin-top: 6px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 14px;
  line-height: 1.35;
}

@media (max-width: 600px) {
  .setup-page-container--onboarding { padding: 20px 12px 0; }
  .setup-card--onboarding .setup-brand img { width: 28px; }
  .setup-card--onboarding .setup-wordmark { font-size: 18px; margin-left: 8px; }
  .setup-card--onboarding .setup-title--inline { font-size: 14px; margin-left: 8px; padding-left: 8px; }
}
</style>
