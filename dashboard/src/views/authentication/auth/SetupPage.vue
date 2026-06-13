<script setup lang="ts">
import AuthSetup from '../authForms/AuthSetup.vue';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import { computed, onMounted, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { useCustomizerStore } from '@/stores/customizer';
import { useModuleI18n } from '@/i18n/composables';
import { useTheme } from 'vuetify';
import axios from 'axios';

const router = useRouter();
const authStore = useAuthStore();
const customizer = useCustomizerStore();
const { tm: t } = useModuleI18n('features/auth');
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

onMounted(async () => {
  const hasToken = authStore.has_token();

  try {
    const setupStatus = await axios.get('/api/auth/setup-status');
    const setupRequired = !!setupStatus.data?.data?.setup_required;
    const canSkipDefaultPassword = !!setupStatus.data?.data?.skip_default_password_auth;
    if (
      !setupRequired ||
      (!hasToken && !canSkipDefaultPassword)
    ) {
      router.push('/auth/login');
    }
  } catch {
    router.push('/auth/login');
  }
});
</script>

<template>
  <div class="setup-page-container">
    <v-card class="setup-card" elevation="1">
      <v-card-title>
        <div class="setup-header">
          <div class="setup-brand">
            <img width="80" src="@/assets/images/plugin_icon.png" alt="AstrBot Logo">
          </div>
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
        <div class="setup-title">{{ t('setup.title') }}</div>
        <div class="setup-subtitle">{{ t('setup.subtitle') }}</div>
      </v-card-title>
      <v-card-text>
        <AuthSetup />
      </v-card-text>
    </v-card>
  </div>
</template>

<style lang="scss">
.setup-page-container {
  background-color: rgb(var(--v-theme-containerBg));
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
}

.setup-card {
  width: 420px;
  padding: 8px;
}

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
  color: #000000;
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
}

.setup-subtitle {
  margin-top: 6px;
  color: grey;
  font-size: 14px;
  line-height: 1.35;
}
</style>
