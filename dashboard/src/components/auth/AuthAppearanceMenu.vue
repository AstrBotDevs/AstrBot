<script setup lang="ts">
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useModuleI18n } from '@/i18n/composables';
import { computed } from 'vue';

const customizer = useCustomizerStore();
const { tm: t } = useModuleI18n('features/auth');

const themeOptions = [
  {
    mode: 'light' as const,
    icon: 'mdi-white-balance-sunny',
    labelKey: 'theme.light',
  },
  { mode: 'dark' as const, icon: 'mdi-weather-night', labelKey: 'theme.dark' },
  { mode: 'system' as const, icon: 'mdi-sync', labelKey: 'theme.system' },
] as const;

const currentThemeIcon = computed(() => {
  if (customizer.themeMode === 'dark') return 'mdi-weather-night';
  if (customizer.themeMode === 'system') return 'mdi-sync';
  return 'mdi-white-balance-sunny';
});

function setThemeMode(mode: 'light' | 'dark' | 'system') {
  customizer.SET_THEME_MODE(mode);
}
</script>

<template>
  <div class="auth-appearance-menu">
    <LanguageSwitcher />
    <v-divider vertical class="auth-appearance-menu__divider" />
    <v-menu open-on-click location="bottom center" offset="8">
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          :aria-label="t('theme.title')"
          class="auth-appearance-menu__toggle"
          icon
          variant="text"
        >
          <v-icon size="18" color="primary">{{ currentThemeIcon }}</v-icon>
        </v-btn>
      </template>

      <v-card class="styled-menu-card auth-appearance-menu__card" elevation="4">
        <v-list density="compact" class="styled-menu-list pa-1">
          <v-list-item
            v-for="option in themeOptions"
            :key="option.mode"
            :class="{
              'styled-menu-item-active': customizer.themeMode === option.mode,
            }"
            class="styled-menu-item"
            @click="setThemeMode(option.mode)"
          >
            <template #prepend>
              <v-icon size="16" class="auth-appearance-menu__item-icon">
                {{ option.icon }}
              </v-icon>
            </template>
            <v-list-item-title>{{ t(option.labelKey) }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-card>
    </v-menu>
  </div>
</template>

<style scoped>
.auth-appearance-menu {
  display: flex;
  align-items: center;
  gap: 4px;
}

.auth-appearance-menu__divider {
  align-self: center;
  height: 24px;
  opacity: 0.9;
}

.auth-appearance-menu__card {
  min-width: 150px;
}

.auth-appearance-menu__item-icon {
  margin-right: 8px;
  opacity: 0.85;
}
</style>
