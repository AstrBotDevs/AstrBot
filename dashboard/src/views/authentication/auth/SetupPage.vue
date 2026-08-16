<script setup lang="ts">
import AuthSetup from '../authForms/AuthSetup.vue';
import AuthAppearanceMenu from '@/components/auth/AuthAppearanceMenu.vue';
import { onMounted } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { useModuleI18n } from '@/i18n/composables';
import { authApi } from '@/api/v1';

const router = useRouter();
const authStore = useAuthStore();
const { tm: t } = useModuleI18n('features/auth');

onMounted(async () => {
  const hasToken = authStore.has_token();

  try {
    const setupStatus = await authApi.setupStatus();
    const setupRequired = Boolean(setupStatus.data?.data?.setup_required);
    const canSkipDefaultPassword = Boolean(
      setupStatus.data?.data?.skip_default_password_auth,
    );
    if (!setupRequired || (!hasToken && !canSkipDefaultPassword)) {
      void router.push('/auth/login');
    }
  } catch {
    void router.push('/auth/login');
  }
});
</script>

<template>
  <div class="auth-page-container">
    <v-card class="auth-card setup-card" elevation="0">
      <v-card-title>
        <div class="auth-header">
          <div class="auth-header__brand">
            <img
              width="80"
              src="@/assets/images/plugin_icon.png"
              alt="AstrBot Logo"
            />
          </div>
          <AuthAppearanceMenu />
        </div>
        <div class="auth-header__title">{{ t('setup.title') }}</div>
        <div class="auth-header__subtitle">{{ t('setup.subtitle') }}</div>
      </v-card-title>
      <v-card-text>
        <AuthSetup />
      </v-card-text>
    </v-card>
  </div>
</template>
