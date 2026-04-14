<template>
  <!-- Row 1: Preset selector + theme mode -->
  <div class="d-flex flex-wrap align-center ga-4 mb-4 ml-3">
    <v-select v-model="selectedThemePreset" :items="presetOptions" :label="tm('theme.customize.preset')" hide-details
      variant="outlined" density="compact" style="min-width: 200px; max-width: 280px"
      @update:model-value="applyThemePreset" />
    <v-btn-toggle v-model="themeMode" mandatory density="compact" color="primary">
      <v-btn value="light" size="small">
        <v-icon class="mr-1" size="18">mdi-white-balance-sunny</v-icon>
        {{ tm("theme.customize.light") }}
      </v-btn>
      <v-btn value="dark" size="small">
        <v-icon class="mr-1" size="18">mdi-moon-waning-crescent</v-icon>
        {{ tm("theme.customize.dark") }}
      </v-btn>
      <v-btn value="auto" size="small">
        <v-icon class="mr-1" size="18">mdi-sync</v-icon>
        {{ tm("theme.customize.auto") }}
      </v-btn>
    </v-btn-toggle>
    <v-tooltip location="top">
      <template #activator="{ props }">
        <v-icon v-bind="props" size="16" color="primary" class="ml-1">mdi-help-circle-outline</v-icon>
      </template>
      <span>{{ tm("theme.customize.autoSwitchDesc") }}</span>
    </v-tooltip>
  </div>

  <!-- Row 2: Color pickers + reset -->
  <v-card variant="outlined" class="pa-3">
    <div class="text-body-2 text-medium-emphasis mb-3">
      {{ tm("theme.customize.colors") }}
    </div>
    <div class="d-flex flex-wrap align-center ga-4">
      <div class="d-flex align-center ga-3">
        <v-text-field v-model="primaryColor" type="color" :label="tm('theme.customize.primary')" hide-details
          variant="outlined" density="compact" style="width: 140px" />
        <div class="color-preview" :style="{ backgroundColor: primaryColor }" />
      </div>
      <div class="d-flex align-center ga-3">
        <v-text-field v-model="secondaryColor" type="color" :label="tm('theme.customize.secondary')" hide-details
          variant="outlined" density="compact" style="width: 140px" />
        <div class="color-preview" :style="{ backgroundColor: secondaryColor }" />
      </div>
      <v-btn size="small" variant="tonal" color="primary" @click="resetThemeColors">
        <v-icon class="mr-1" size="16">mdi-restore</v-icon>
        {{ tm("theme.customize.reset") }}
      </v-btn>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useModuleI18n } from "@/i18n/composables";
import { useTheme } from "vuetify";
import { PurpleTheme } from "@/theme/LightTheme";
import {
  LIGHT_THEME_NAME,
  DARK_THEME_NAME,
  themePresets,
} from "@/theme/constants";
import type { ThemeMode } from "@/types/theme";
import { useToastStore } from "@/stores/toast";
import { useCustomizerStore } from "@/stores/customizer";


const { tm } = useModuleI18n("features/settings");
const toastStore = useToastStore();
const theme = useTheme();
const customizer = useCustomizerStore();

// Theme mode toggle (light/dark/auto)
const themeMode = computed({
  get() {
    if (customizer.autoSwitchTheme) return "auto";
    return customizer.isDarkTheme ? "dark" : "light";
  },
  set(mode: ThemeMode) {
    if (mode === "auto") {
      customizer.SET_AUTO_SYNC(true);
      customizer.APPLY_SYSTEM_THEME();
      return;
    }

    customizer.SET_AUTO_SYNC(false);
    const newTheme = mode === "dark" ? DARK_THEME_NAME : LIGHT_THEME_NAME;
    customizer.SET_UI_THEME(newTheme);
  },
});

const getStoredColor = (key: string, fallback: string) => {
  const stored =
    typeof window !== "undefined" ? localStorage.getItem(key) : null;
  return stored || fallback;
};

const primaryColor = ref(
  getStoredColor("themePrimary", PurpleTheme.colors.primary),
);
const secondaryColor = ref(
  getStoredColor("themeSecondary", PurpleTheme.colors.secondary),
);

// Get stored preset or default to blue-business name
const selectedThemePreset = ref(
  localStorage.getItem("themePreset") || themePresets[0].name,
);

// Simple array for dropdown display
const presetOptions = themePresets.map((p) => p.name);

const applyThemePreset = (presetName: string) => {
  const preset = themePresets.find((p) => p.name === presetName);
  if (!preset) return;

  // Store the preset selection (store by name for display consistency)
  localStorage.setItem("themePreset", presetName);
  selectedThemePreset.value = presetName;

  // Update primary and secondary colors
  primaryColor.value = preset.primary;
  secondaryColor.value = preset.secondary;
  localStorage.setItem("themePrimary", preset.primary);
  localStorage.setItem("themeSecondary", preset.secondary);

  // Apply to themes
  applyThemeColors(preset.primary, preset.secondary);

  toastStore.add({
    message: tm("theme.customize.presetApplied") || "主题已应用",
    color: "success",
  });
};

const resolveThemes = () => {
  if (theme?.themes?.value) return theme.themes.value as Record<string, any>;
  return null;
};

const applyThemeColors = (primary: string, secondary: string) => {
  const themes = resolveThemes();
  if (!themes) return;
  [LIGHT_THEME_NAME, DARK_THEME_NAME].forEach((name) => {
    const themeDef = themes[name];
    if (!themeDef?.colors) return;
    if (primary) themeDef.colors.primary = primary;
    if (secondary) themeDef.colors.secondary = secondary;
    if (primary && themeDef.colors.darkprimary)
      themeDef.colors.darkprimary = primary;
    if (secondary && themeDef.colors.darksecondary)
      themeDef.colors.darksecondary = secondary;
  });
};

applyThemeColors(primaryColor.value, secondaryColor.value);

watch(primaryColor, (value) => {
  if (!value) return;
  localStorage.setItem("themePrimary", value);
  applyThemeColors(value, secondaryColor.value);
});

watch(secondaryColor, (value) => {
  if (!value) return;
  localStorage.setItem("themeSecondary", value);
  applyThemeColors(primaryColor.value, value);
});

const resetThemeColors = () => {
  primaryColor.value = PurpleTheme.colors.primary;
  secondaryColor.value = PurpleTheme.colors.secondary;
  localStorage.removeItem("themePrimary");
  localStorage.removeItem("themeSecondary");
  applyThemeColors(primaryColor.value, secondaryColor.value);
};

</script>
