<script setup lang="ts">
import AuthLogin from "../authForms/AuthLogin.vue";
import DailyQuote from "@/components/shared/DailyQuote.vue";
import DiamondBg from "@/components/auth/DiamondBg.vue";
import LanguageSwitcher from "@/components/shared/LanguageSwitcher.vue";
import { onMounted, ref, computed } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useApiStore } from "@/stores/api";
import { useRouter } from "vue-router";
import { useCustomizerStore } from "@/stores/customizer";
import { useTheme } from "vuetify";

const vuetifyTheme = useTheme();
const isDark = computed(
  () => vuetifyTheme.global.name.value === "BlueBusinessDarkTheme",
);
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { useToast } from "@/utils/toast";
import { getApiBaseUrlValidationError } from "@/utils/request";

const cardVisible = ref(false);
const router = useRouter();
const authStore = useAuthStore();
const apiStore = useApiStore();
const customizer = useCustomizerStore();
const { locale } = useI18n();
const { tm: t } = useModuleI18n("features/auth");
const toast = useToast();

const serverConfigDialog = ref(false);
const apiUrl = ref(apiStore.apiBaseUrl);

// URL parameter handling for shareable config
function applyUrlParams() {
  const params = new URLSearchParams(window.location.search);
  const apiUrlParam = params.get("api_url");
  const usernameParam = params.get("username");
  if (apiUrlParam) {
    apiUrl.value = apiUrlParam;
    const validationError = getApiBaseUrlValidationError(apiUrlParam);
    if (!validationError) {
      apiStore.setApiBaseUrl(apiUrlParam);
    }
  }
  if (usernameParam) {
    window.dispatchEvent(
      new CustomEvent("astrbot-url-param-username", {
        detail: { username: usernameParam },
      }),
    );
  }
}

function getShareableUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set("api_url", apiUrl.value);
  return url.toString();
}

async function copyShareableUrl() {
  try {
    await navigator.clipboard.writeText(getShareableUrl());
    toast.success(t("linkCopied"));
  } catch {
    toast.error(t("linkCopyFailed"));
  }
}

const showAddPreset = ref(false);
const newPresetName = ref("");
const newPresetUrl = ref("");

function saveApiUrl() {
  const validationError = getApiBaseUrlValidationError(apiUrl.value);
  if (validationError) {
    toast.error(validationError);
    return;
  }

  apiStore.setApiBaseUrl(apiUrl.value);
  serverConfigDialog.value = false;
  window.location.reload();
}

function savePreset() {
  if (!newPresetName.value || !newPresetUrl.value) return;
  apiStore.addPreset({
    name: newPresetName.value,
    url: newPresetUrl.value,
  });
  showAddPreset.value = false;
  newPresetName.value = "";
  newPresetUrl.value = "";
}

function isCustomPreset(name: string) {
  return apiStore.customPresets.some((p) => p.name === name);
}

// 主题切换函数
function toggleTheme() {
  customizer.TOGGLE_DARK_MODE();
}

onMounted(() => {
  // 应用URL参数（用于分享预设配置）
  applyUrlParams();

  // 检查用户是否已登录，如果已登录则重定向
  if (authStore.has_token()) {
    router.push(authStore.returnUrl || "/");
    return;
  }

  // 添加一个小延迟以获得更好的动画效果
  setTimeout(() => {
    cardVisible.value = true;
  }, 100);
});
</script>

<template>
  <div class="login-page-container">
    <DiamondBg v-if="isDark" />
    <v-card class="login-card" elevation="1">
      <v-card-title :key="locale">
        <div class="d-flex justify-space-between align-center w-100">
          <img
            width="80"
            src="@/assets/images/icon-no-shadow.svg"
            alt="AstrBot Logo"
          />
          <div class="d-flex align-center gap-1">
            <LanguageSwitcher />
            <v-divider
              vertical
              class="mx-1"
              style="
                height: 24px !important;
                opacity: 0.9 !important;
                align-self: center !important;
                border-color: rgba(var(--v-theme-primary), 0.45) !important;
              "
            />

            <v-btn
              icon
              variant="text"
              size="small"
              @click="serverConfigDialog = true"
            >
              <v-icon size="18" :color="'rgb(var(--v-theme-primary))'">
                mdi-server
              </v-icon>
              <v-tooltip activator="parent" location="top">
                {{ t("serverConfig.tooltip") }}
              </v-tooltip>
            </v-btn>

            <v-btn
              class="theme-toggle-btn"
              icon
              variant="text"
              size="small"
              @click="toggleTheme"
            >
              <v-icon size="18" :color="'rgb(var(--v-theme-primary))'">
                {{
                  customizer.isDarkTheme
                    ? "mdi-weather-night"
                    : "mdi-white-balance-sunny"
                }}
              </v-icon>
              <v-tooltip activator="parent" location="top">
                {{
                  customizer.isDarkTheme
                    ? t("theme.switchToLight")
                    : t("theme.switchToDark")
                }}
              </v-tooltip>
            </v-btn>
          </div>
        </div>
        <div class="ml-2" style="font-size: 26px">
          {{ t("logo.title") }}
        </div>
        <div
          class="mt-2 ml-2"
          style="font-size: 14px; color: var(--v-theme-on-surface-variant)"
        >
          <DailyQuote />
        </div>
      </v-card-title>
      <v-card-text>
        <AuthLogin @open-server-config="serverConfigDialog = true" />
      </v-card-text>
    </v-card>

    <v-dialog v-model="serverConfigDialog" max-width="450">
      <v-card>
        <v-card-title>{{ t("serverConfig.title") }}</v-card-title>
        <v-card-text class="pt-0">
          <div class="text-body-2 text-medium-emphasis mb-4">
            {{ t("serverConfig.description") }}
          </div>

          <!-- Presets section -->
          <div class="mb-4">
            <div class="d-flex justify-space-between align-center mb-2">
              <div class="text-caption text-medium-emphasis">
                {{ t("serverConfig.presetLabel") }}
              </div>
            </div>

            <v-chip-group
              v-if="
                apiStore.presets.length > 0 || apiStore.customPresets.length > 0
              "
              column
              class="mb-2"
            >
              <v-chip
                v-for="preset in apiStore.presets"
                :key="preset.name"
                size="small"
                :variant="apiUrl === preset.url ? 'flat' : 'tonal'"
                :color="apiUrl === preset.url ? 'primary' : undefined"
                :closable="isCustomPreset(preset.name)"
                @click="apiUrl = preset.url"
                @click:close="apiStore.removePreset(preset.name)"
              >
                {{ preset.name }}
              </v-chip>
            </v-chip-group>

            <!-- Add preset inline form -->
            <div v-if="showAddPreset" class="preset-add-form rounded pa-3 mb-2">
              <div class="d-flex align-center gap-2 mb-2">
                <v-text-field
                  v-model="newPresetName"
                  :label="t('presetName')"
                  density="compact"
                  hide-details
                  variant="outlined"
                  class="flex-1"
                />
                <v-text-field
                  v-model="newPresetUrl"
                  :label="t('presetUrl')"
                  density="compact"
                  hide-details
                  variant="outlined"
                  class="flex-1"
                />
                <v-btn
                  size="small"
                  color="primary"
                  variant="flat"
                  icon
                  @click="savePreset"
                >
                  <v-icon size="18">mdi-check</v-icon>
                </v-btn>
                <v-btn
                  size="small"
                  variant="text"
                  icon
                  @click="showAddPreset = false"
                >
                  <v-icon size="18">mdi-close</v-icon>
                </v-btn>
              </div>
            </div>

            <v-btn
              v-if="!showAddPreset"
              size="x-small"
              variant="tonal"
              prepend-icon="mdi-plus"
              @click="showAddPreset = true"
            >
              {{ t("addPreset") }}
            </v-btn>
          </div>

          <!-- API URL field -->
          <v-text-field
            v-model="apiUrl"
            :label="t('serverConfig.label')"
            :placeholder="t('serverConfig.placeholder')"
            :hint="t('serverConfig.hint')"
            persistent-hint
            variant="outlined"
            density="compact"
            class="mb-3"
          />

          <!-- Share link button -->
          <v-btn
            variant="tonal"
            size="small"
            block
            class="mb-3"
            prepend-icon="mdi-share-variant"
            @click="copyShareableUrl"
          >
            {{ t("shareLink") }}
          </v-btn>

          <!-- Auto theme switch -->
          <div
            class="d-flex align-center justify-space-between preset-auto-switch"
          >
            <div class="text-caption">{{ t("autoTheme") }}</div>
            <v-switch
              v-model="customizer.autoSwitchTheme"
              color="primary"
              density="compact"
              hide-details
              inset
              @update:model-value="customizer.SET_AUTO_SYNC($event)"
            />
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="serverConfigDialog = false">
            {{ t("serverConfig.cancel") }}
          </v-btn>
          <v-btn color="primary" variant="flat" @click="saveApiUrl">
            {{ t("serverConfig.save") }}
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

// Dark mode: radial mask + DiamondBg
.v-theme--bluebusinessdarktheme .login-page-container {
  background-color: rgb(var(--v-theme-containerBg));
  mask-image: radial-gradient(
    ellipse 60% 70% at 50% 50%,
    black 30%,
    transparent 70%
  );
  -webkit-mask-image: radial-gradient(
    ellipse 60% 70% at 50% 50%,
    black 30%,
    transparent 70%
  );
}

// Light mode: pure white
.v-theme--bluebusinesstheme .login-page-container {
  background-color: #ffffff;
  mask-image: none;
  -webkit-mask-image: none;
}

.login-card {
  width: 400px;
  padding: 8px;
  background: var(--v-theme-surface) !important;
  backdrop-filter: blur(28px) saturate(1.1);
  border: 1px solid rgba(var(--v-theme-primary), 0.2);
  box-shadow:
    0 0 80px rgba(var(--v-theme-on-surface), 0.3),
    0 0 120px rgba(var(--v-theme-on-surface), 0.15),
    inset 0 0 20px rgba(0, 0, 0, 0.1);
}

// Light mode: clean white card
.v-theme--bluebusinesstheme .login-card {
  background: #ffffff !important;
  border: 1px solid rgba(0, 49, 83, 0.12) !important;
  box-shadow: 0 4px 24px rgba(0, 49, 83, 0.08) !important;
  backdrop-filter: none;
}

// Dark mode: preset add form
.v-theme--bluebusinessdarktheme .preset-add-form {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(0, 242, 255, 0.15);
}

// Light mode: preset add form
.v-theme--bluebusinesstheme .preset-add-form {
  background: rgba(0, 49, 83, 0.04);
  border: 1px solid rgba(0, 49, 83, 0.12);
}

// Auto switch row
.preset-auto-switch {
  padding: 8px 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.02);
}
</style>
