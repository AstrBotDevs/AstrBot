<script setup lang="ts">
import AuthSetup from '../authForms/AuthSetup.vue';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import { onMounted, ref } from 'vue';
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

function toggleTheme() {
  const newTheme = customizer.uiTheme === 'PurpleThemeDark' ? 'PurpleTheme' : 'PurpleThemeDark';
  customizer.SET_UI_THEME(newTheme);
  theme.global.name.value = newTheme;
}

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
        <div class="d-flex justify-space-between align-center w-100">
          <img width="80" src="@/assets/images/icon-no-shadow.svg" alt="AstrBot Logo">
          <div class="d-flex align-center gap-1">
            <LanguageSwitcher />
            <v-divider vertical class="mx-1"
              style="height: 24px !important; opacity: 0.9 !important; align-self: center !important; border-color: rgba(var(--v-theme-primary), 0.45) !important;"></v-divider>
            <v-btn @click="toggleTheme" class="theme-toggle-btn" icon variant="text" size="small">
              <v-icon size="18" :color="'rgb(var(--v-theme-primary))'">
                {{ customizer.uiTheme === 'PurpleThemeDark' ? 'mdi-white-balance-sunny' : 'mdi-weather-night' }}
              </v-icon>
              <v-tooltip activator="parent" location="top">
                {{ customizer.uiTheme === 'PurpleThemeDark' ? t('theme.switchToLight') : t('theme.switchToDark') }}
              </v-tooltip>
            </v-btn>
          </div>
        </div>
        <div class="ml-2" style="font-size: 26px;">{{ t('setup.title') }}</div>
        <div class="mt-2 ml-2" style="font-size: 14px; color: grey;">{{ t('setup.subtitle') }}</div>
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
</style>
