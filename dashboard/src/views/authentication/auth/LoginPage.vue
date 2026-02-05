<script setup lang="ts">
import AuthLogin from "../authForms/AuthLogin.vue";
import LanguageSwitcher from "@/components/shared/LanguageSwitcher.vue";
import { onMounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useApiStore } from "@/stores/api";
import { useRouter } from "vue-router";
import { useCustomizerStore } from "@/stores/customizer";
import { useModuleI18n } from "@/i18n/composables";
import { useTheme } from "vuetify";

const cardVisible = ref(false);
const router = useRouter();
const authStore = useAuthStore();
const apiStore = useApiStore();
const customizer = useCustomizerStore();
const { tm: t } = useModuleI18n("features/auth");
const theme = useTheme();

const serverConfigDialog = ref(false);
const apiUrl = ref(apiStore.apiBaseUrl);

function saveApiUrl() {
  apiStore.setApiBaseUrl(apiUrl.value);
  serverConfigDialog.value = false;
  window.location.reload();
}

// 主题切换函数
function toggleTheme() {
  const newTheme =
    customizer.uiTheme === "PurpleThemeDark"
      ? "PurpleTheme"
      : "PurpleThemeDark";
  customizer.SET_UI_THEME(newTheme);
  theme.global.name.value = newTheme;
}

onMounted(() => {
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
    <v-card class="login-card" elevation="1">
      <v-card-title>
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
                border-color: rgba(180, 148, 246, 0.8) !important;
              "
            ></v-divider>

            <v-btn
              @click="serverConfigDialog = true"
              icon
              variant="text"
              size="small"
            >
              <v-icon
                size="18"
                :color="
                  useCustomizerStore().uiTheme === 'PurpleTheme'
                    ? '#5e35b1'
                    : '#d7c5fa'
                "
              >
                mdi-server
              </v-icon>
              <v-tooltip activator="parent" location="top">
                {{ t("serverConfig.tooltip") }}
              </v-tooltip>
            </v-btn>

            <v-btn
              @click="toggleTheme"
              class="theme-toggle-btn"
              icon
              variant="text"
              size="small"
            >
              <v-icon
                size="18"
                :color="
                  useCustomizerStore().uiTheme === 'PurpleTheme'
                    ? '#5e35b1'
                    : '#d7c5fa'
                "
              >
                mdi-white-balance-sunny
              </v-icon>
              <v-tooltip activator="parent" location="top">
                {{ t("theme.switchToLight") }}
              </v-tooltip>
            </v-btn>
          </div>
        </div>
        <div class="ml-2" style="font-size: 26px">{{ t("logo.title") }}</div>
        <div class="mt-2 ml-2" style="font-size: 14px; color: grey">
          {{ t("logo.subtitle") }}
        </div>
      </v-card-title>
      <v-card-text>
        <AuthLogin />
      </v-card-text>
    </v-card>

    <v-dialog v-model="serverConfigDialog" max-width="450">
      <v-card>
        <v-card-title>{{ t("serverConfig.title") }}</v-card-title>
        <v-card-text>
          <div class="text-body-2 text-medium-emphasis mb-4">
            {{ t("serverConfig.description") }}
          </div>

          <div
            v-if="apiStore.presets && apiStore.presets.length > 0"
            class="mb-4"
          >
            <div class="text-caption text-medium-emphasis mb-2">
              {{ t("serverConfig.presetLabel") }}
            </div>
            <v-chip-group column>
              <v-chip
                v-for="preset in apiStore.presets"
                :key="preset.name"
                size="small"
                @click="apiUrl = preset.url"
                :variant="apiUrl === preset.url ? 'flat' : 'tonal'"
                :color="apiUrl === preset.url ? 'primary' : undefined"
              >
                {{ preset.name }}
              </v-chip>
            </v-chip-group>
          </div>

          <v-text-field
            v-model="apiUrl"
            :label="t('serverConfig.label')"
            :placeholder="t('serverConfig.placeholder')"
            :hint="t('serverConfig.hint')"
            persistent-hint
            variant="outlined"
            density="compact"
          ></v-text-field>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="serverConfigDialog = false">{{
            t("serverConfig.cancel")
          }}</v-btn>
          <v-btn color="primary" variant="flat" @click="saveApiUrl">{{
            t("serverConfig.save")
          }}</v-btn>
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
</style>
