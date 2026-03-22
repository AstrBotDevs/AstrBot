<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useCustomizerStore } from "@/stores/customizer";
import axios from "@/utils/request";
import Logo from "@/components/shared/Logo.vue";
import { useAuthStore } from "@/stores/auth";
import { useCommonStore } from "@/stores/common";
import { MarkdownRender, enableKatex, enableMermaid } from "markstream-vue";
import "markstream-vue/index.css";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github.css";
import { useI18n } from "@/i18n/composables";
import { router } from "@/router";
import { useRoute } from "vue-router";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import { useLanguageSwitcher } from "@/i18n/composables";
import type { Locale } from "@/i18n/types";
import AboutPage from "@/views/AboutPage.vue";
import { getDesktopRuntimeInfo } from "@/utils/desktopRuntime";

enableKatex();
enableMermaid();

const customizer = useCustomizerStore();
const authStore = useAuthStore();
const { t } = useI18n();

const { languageOptions, currentLanguage, switchLanguage, locale } =
  useLanguageSwitcher();

const languages = computed(() =>
  languageOptions.value.map((lang) => ({
    code: lang.value,
    name: lang.label,
    flag: lang.flag,
  })),
);

const currentLocale = computed(() => locale.value);

const changeLanguage = async (langCode: string) => {
  await switchLanguage(langCode as Locale);
};

const route = useRoute();
const LAST_BOT_ROUTE_KEY = "astrbot:last_bot_route";
let dialog = ref(false);
let accountWarning = ref(false);
let updateStatusDialog = ref(false);
let aboutDialog = ref(false);
const username = localStorage.getItem("user");
let password = ref("");
let newPassword = ref("");
let confirmPassword = ref("");
let newUsername = ref("");
let status = ref("");
let updateStatus = ref("");
let releaseMessage = ref("");
let hasNewVersion = ref(false);
let botCurrVersion = ref("");
let dashboardHasNewVersion = ref(false);
let dashboardCurrentVersion = ref("");
let version = ref("");
let releases = ref([]);
let updatingDashboardLoading = ref(false);
let installLoading = ref(false);
const isDesktopReleaseMode = ref(
  typeof window !== "undefined" && !!window.astrbotDesktop?.isDesktop,
);
const desktopUpdateDialog = ref(false);
const desktopUpdateChecking = ref(false);
const desktopUpdateInstalling = ref(false);
const desktopUpdateHasNewVersion = ref(false);
const desktopUpdateCurrentVersion = ref("-");
const desktopUpdateLatestVersion = ref("-");
const desktopUpdateStatus = ref("");

const getAppUpdaterBridge = (): NonNullable<Window["astrbotAppUpdater"]> | null => {
  if (typeof window === "undefined") {
    return null;
  }
  const bridge = window.astrbotAppUpdater;
  if (
    bridge &&
    typeof bridge.checkForAppUpdate === "function" &&
    typeof bridge.installAppUpdate === "function"
  ) {
    return bridge;
  }
  return null;
};

const getSelectedGitHubProxy = () => {
  if (typeof window === "undefined" || !window.localStorage) return "";
  return localStorage.getItem("githubProxyRadioValue") === "1"
    ? localStorage.getItem("selectedGitHubProxy") || ""
    : "";
};

// Release Notes Modal
let releaseNotesDialog = ref(false);
let selectedReleaseNotes = ref("");
let selectedReleaseTag = ref("");

const releasesHeader = computed(() => [
  { title: t("core.header.updateDialog.table.tag"), key: "tag_name" },
  {
    title: t("core.header.updateDialog.table.publishDate"),
    key: "published_at",
  },
  { title: t("core.header.updateDialog.table.content"), key: "body" },
  { title: t("core.header.updateDialog.table.sourceUrl"), key: "zipball_url" },
  { title: t("core.header.updateDialog.table.actions"), key: "switch" },
]);
// Form validation
const formValid = ref(true);
const passwordRules = computed(() => [
  (v: string) =>
    !!v || t("core.header.accountDialog.validation.passwordRequired"),
  (v: string) =>
    v.length >= 8 ||
    t("core.header.accountDialog.validation.passwordMinLength"),
]);
const confirmPasswordRules = computed(() => [
  (v: string) =>
    !newPassword.value ||
    !!v ||
    t("core.header.accountDialog.validation.passwordRequired"),
  (v: string) =>
    !newPassword.value ||
    v === newPassword.value ||
    t("core.header.accountDialog.validation.passwordMatch"),
]);
const usernameRules = computed(() => [
  (v: string) =>
    !v ||
    v.length >= 3 ||
    t("core.header.accountDialog.validation.usernameMinLength"),
]);

// 显示密码相关
const showPassword = ref(false);
const showNewPassword = ref(false);
const showConfirmPassword = ref(false);

// 账户修改状态
const accountEditStatus = ref({
  loading: false,
  success: false,
  error: false,
  message: "",
});

function cancelDesktopUpdate() {
  if (desktopUpdateInstalling.value) {
    return;
  }
  desktopUpdateDialog.value = false;
}

async function openDesktopUpdateDialog() {
  desktopUpdateDialog.value = true;
  desktopUpdateChecking.value = true;
  desktopUpdateInstalling.value = false;
  desktopUpdateHasNewVersion.value = false;
  desktopUpdateCurrentVersion.value = "-";
  desktopUpdateLatestVersion.value = "-";
  desktopUpdateStatus.value = t("core.header.updateDialog.desktopApp.checking");

  const bridge = getAppUpdaterBridge();
  if (!bridge) {
    desktopUpdateChecking.value = false;
    desktopUpdateStatus.value = t(
      "core.header.updateDialog.desktopApp.checkFailed",
    );
    return;
  }

  try {
    const result = await bridge.checkForAppUpdate();
    if (!result?.ok) {
      desktopUpdateCurrentVersion.value = result?.currentVersion || "-";
      desktopUpdateLatestVersion.value =
        result?.latestVersion || result?.currentVersion || "-";
      desktopUpdateStatus.value =
        result?.reason || t("core.header.updateDialog.desktopApp.checkFailed");
      return;
    }

    desktopUpdateCurrentVersion.value = result.currentVersion || "-";
    desktopUpdateLatestVersion.value =
      result.latestVersion || result.currentVersion || "-";
    desktopUpdateHasNewVersion.value = !!result.hasUpdate;
    desktopUpdateStatus.value = result.hasUpdate
      ? t("core.header.updateDialog.desktopApp.hasNewVersion")
      : t("core.header.updateDialog.desktopApp.isLatest");
  } catch (error) {
    console.error(error);
    desktopUpdateStatus.value = t(
      "core.header.updateDialog.desktopApp.checkFailed",
    );
  } finally {
    desktopUpdateChecking.value = false;
  }
}

async function confirmDesktopUpdate() {
  if (!desktopUpdateHasNewVersion.value || desktopUpdateInstalling.value) {
    return;
  }

  const bridge = getAppUpdaterBridge();
  if (!bridge) {
    desktopUpdateStatus.value = t(
      "core.header.updateDialog.desktopApp.installFailed",
    );
    return;
  }

  desktopUpdateInstalling.value = true;
  desktopUpdateStatus.value = t(
    "core.header.updateDialog.desktopApp.installing",
  );

  try {
    const result = await bridge.installAppUpdate();
    if (result?.ok) {
      desktopUpdateDialog.value = false;
      return;
    }
    desktopUpdateStatus.value =
      result?.reason || t("core.header.updateDialog.desktopApp.installFailed");
  } catch (error) {
    console.error(error);
    desktopUpdateStatus.value = t(
      "core.header.updateDialog.desktopApp.installFailed",
    );
  } finally {
    desktopUpdateInstalling.value = false;
  }
}

function handleUpdateClick() {
  if (isDesktopReleaseMode.value) {
    void openDesktopUpdateDialog();
    return;
  }
  checkUpdate();
  getReleases();
  updateStatusDialog.value = true;
}

// 检测是否为预发布版本
const isPreRelease = (version: string) => {
  const preReleaseKeywords = ["alpha", "beta", "rc", "pre", "preview", "dev"];
  const lowerVersion = version.toLowerCase();
  return preReleaseKeywords.some((keyword) => lowerVersion.includes(keyword));
};

// 退出登录
function handleLogout() {
  if (confirm(t("core.common.dialog.confirmMessage"))) {
    authStore.logout();
  }
}

// 账户修改
async function accountEdit() {
  accountEditStatus.value.loading = true;
  accountEditStatus.value.error = false;
  accountEditStatus.value.success = false;

  axios
    .post("/api/auth/account/edit", {
      password: password.value,
      new_password: newPassword.value,
      confirm_password: confirmPassword.value,
      new_username: newUsername.value ? newUsername.value : username,
    })
    .then((res) => {
      if (res.data.status == "error") {
        accountEditStatus.value.error = true;
        accountEditStatus.value.message = res.data.message;
        password.value = "";
        newPassword.value = "";
        confirmPassword.value = "";
        return;
      }
      accountEditStatus.value.success = true;
      accountEditStatus.value.message = res.data.message;
      setTimeout(() => {
        dialog.value = !dialog.value;
        const authStore = useAuthStore();
        authStore.logout();
      }, 2000);
    })
    .catch((err) => {
      console.log(err);
      accountEditStatus.value.error = true;
      accountEditStatus.value.message =
        typeof err === "string"
          ? err
          : t("core.header.accountDialog.messages.updateFailed");
      password.value = "";
      newPassword.value = "";
      confirmPassword.value = "";
    })
    .finally(() => {
      accountEditStatus.value.loading = false;
    });
}

function getVersion() {
  axios
    .get("/api/stat/version")
    .then((res) => {
      botCurrVersion.value = "v" + res.data.data.version;
      dashboardCurrentVersion.value = res.data.data?.dashboard_version;
      let change_pwd_hint = res.data.data?.change_pwd_hint;
      if (change_pwd_hint) {
        dialog.value = true;
        accountWarning.value = true;
        localStorage.setItem("change_pwd_hint", "true");
      } else {
        localStorage.removeItem("change_pwd_hint");
      }
    })
    .catch((err) => {
      console.log(err);
    });
}

function checkUpdate() {
  updateStatus.value = t("core.header.updateDialog.status.checking");
  axios
    .get("/api/update/check")
    .then((res) => {
      hasNewVersion.value = res.data.data.has_new_version;

      if (res.data.data.has_new_version) {
        releaseMessage.value = res.data.message;
        updateStatus.value = t("core.header.version.hasNewVersion");
      } else {
        updateStatus.value = res.data.message;
      }
      dashboardHasNewVersion.value = isDesktopReleaseMode.value
        ? false
        : res.data.data.dashboard_has_new_version;
    })
    .catch((err) => {
      if (err.response && err.response.status == 401) {
        console.log("401");
        const authStore = useAuthStore();
        authStore.logout();
        return;
      }
      console.log(err);
      updateStatus.value = err;
    });
}

function getReleases() {
  return axios
    .get("/api/update/releases")
    .then((res) => {
      releases.value = res.data.data.map((item: any) => {
        item.published_at = new Date(item.published_at).toLocaleString();
        return item;
      });
    })
    .catch((err) => {
      console.log(err);
    });
}

function switchVersion(version: string) {
  updateStatus.value = t("core.header.updateDialog.status.switching");
  installLoading.value = true;
  axios
    .post("/api/update/do", {
      version: version,
      proxy: getSelectedGitHubProxy(),
    })
    .then((res) => {
      updateStatus.value = res.data.message;
      if (res.data.status == "ok") {
        setTimeout(() => {
          window.location.reload();
        }, 1000);
      }
    })
    .catch((err) => {
      console.log(err);
      updateStatus.value = err;
    })
    .finally(() => {
      installLoading.value = false;
    });
}

function updateDashboard() {
  updatingDashboardLoading.value = true;
  updateStatus.value = t("core.header.updateDialog.status.updating");
  axios
    .post("/api/update/dashboard")
    .then((res) => {
      updateStatus.value = res.data.message;
      if (res.data.status == "ok") {
        setTimeout(() => {
          window.location.reload();
        }, 1000);
      }
    })
    .catch((err) => {
      console.log(err);
      updateStatus.value = err;
    })
    .finally(() => {
      updatingDashboardLoading.value = false;
    });
}

// 修改：使用状态管理切换主题
function toggleTheme() {
  customizer.TOGGLE_DARK_MODE();
}

function autoSwitchTheme() {
  // 根据浏览器主题同步页面主题
  customizer.APPLY_SYSTEM_THEME();
}

function autoSwitchThemeListener(e: MediaQueryListEvent) {
  if (customizer.autoSwitchTheme) {
    autoSwitchTheme();
  }
}

// 通过 watch 变量来添加和移除监听器
watch(() => customizer.autoSwitchTheme, (isAuto) => {
  if (typeof window === 'undefined') return;
  
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  
  if (isAuto) {
    autoSwitchTheme();
    mediaQuery.addEventListener('change', autoSwitchThemeListener);
  } else {
    mediaQuery.removeEventListener('change', autoSwitchThemeListener);
  }
}, { immediate: true });

function openReleaseNotesDialog(body: string, tag: string) {
  selectedReleaseNotes.value = body;
  selectedReleaseTag.value = tag;
  releaseNotesDialog.value = true;
}

function handleLogoClick() {
  if (customizer.viewMode === "chat") {
    aboutDialog.value = true;
  } else {
    router.push("/about");
  }
}

getVersion();
checkUpdate();

const commonStore = useCommonStore();
commonStore.createEventSource(); // log
commonStore.getStartTime();

// 视图模式切换
const viewMode = computed({
  get: () => customizer.viewMode,
  set: (value: "bot" | "chat") => {
    customizer.SET_VIEW_MODE(value);
  },
});

// 保存 bot 模式的最後路由
// 監聽 route 變化，保存最後一次 bot 路由
watch(
  () => route.fullPath,
  (newPath) => {
    if (customizer.viewMode === "bot" && typeof window !== "undefined") {
      try {
        localStorage.setItem(LAST_BOT_ROUTE_KEY, newPath);
      } catch (e) {
        console.error("Failed to save last bot route to localStorage:", e);
      }
    }
  },
);

// 監聽 viewMode 切換
watch(
  () => customizer.viewMode,
  (newMode, oldMode) => {
    if (
      newMode === "bot" &&
      oldMode === "chat" &&
      typeof window !== "undefined"
    ) {
      // 從 chat 切換回 bot，跳轉到最後一次的 bot 路由
      let lastBotRoute = "/";
      try {
        lastBotRoute = localStorage.getItem(LAST_BOT_ROUTE_KEY) || "/";
      } catch (e) {
        console.error("Failed to read last bot route from localStorage:", e);
      }
      router.push(lastBotRoute);
    }
  },
);

// Merry Christmas! 🎄
const isChristmas = computed(() => {
  const today = new Date();
  const month = today.getMonth() + 1; // getMonth() 返回 0-11
  const day = today.getDate();
  return month === 12 && day === 25;
});

</script>

<template>
  <v-app-bar
    elevation="0"
    :priority="0"
    height="70"
    class="px-0"
    app
  >
    <div class="fill-height d-flex align-center w-100 px-4">
      <!-- 桌面端标题栏拖拽区域 -->
      <div
        v-if="isDesktopReleaseMode"
        style="
          -webkit-app-region: drag;
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 30px;
          z-index: 9999;
        "
      />

      <div class="d-flex align-center">
        <!-- 桌面端 menu 按钮 - 仅在 bot 模式下显示 -->
        <v-btn
          v-if="customizer.viewMode === 'bot'"
          class="hidden-md-and-down mr-3"
          icon
          rounded="sm"
          variant="flat"
          @click.stop="customizer.SET_MINI_SIDEBAR(!customizer.mini_sidebar)"
        >
          <v-icon>mdi-menu</v-icon>
        </v-btn>
        <!-- 移动端 menu 按钮 - 仅在 bot 模式下显示 -->
        <v-btn
          v-if="customizer.viewMode === 'bot'"
          class="hidden-lg-and-up mr-3"
          icon
          rounded="sm"
          variant="flat"
          @click.stop="customizer.SET_SIDEBAR_DRAWER"
        >
          <v-icon>mdi-menu</v-icon>
        </v-btn>
      </div>

      <div
        class="logo-container"
        :class="{
          'mobile-logo': $vuetify.display.xs,
          'chat-mode-logo': customizer.viewMode === 'chat',
        }"
        @click="handleLogoClick"
      >
        <span class="logo-text Outfit">Astr<span class="logo-text bot-text-wrapper">Bot
          <img
            v-if="isChristmas"
            src="@/assets/images/xmas-hat.png"
            alt="Christmas hat"
            class="xmas-hat"
          > </span></span>
        <span
          v-if="customizer.viewMode === 'chat'"
          class="logo-text logo-text-light Outfit"
          style="color: grey"
        >ChatUI</span>
        <span class="version-text hidden-xs">{{ botCurrVersion }}</span>
      </div>

      <v-spacer />

      <!-- Bot/Chat 模式切换按钮 - 手机端隐藏，移入 ... 菜单 -->
      <div class="hidden-sm-and-down mr-4">
        <v-btn-toggle
          v-model="viewMode"
          color="primary"
          rounded="xl"
          group
          density="compact"
        >
          <v-btn
            value="chat"
            prepend-icon="mdi-chat-processing"
          >
            Chat
          </v-btn>
          <v-btn
            value="bot"
            prepend-icon="mdi-robot"
          >
            Bot
          </v-btn>
        </v-btn-toggle>
      </div>

      <div class="mr-3">
        <v-chip
          v-if="hasNewVersion"
          color="error"
          variant="flat"
          size="small"
          class="cursor-pointer"
          @click="updateStatusDialog = true"
        >
          {{ t("core.header.updateAvailable") }}
        </v-chip>
      </div>

      <!-- 功能菜单 -->
      <StyledMenu
        offset="12"
        location="bottom end"
      >
        <template #activator="{ props: activatorProps }">
          <v-btn
            v-bind="activatorProps"
            size="small"
            class="action-btn mr-4"
            color="var(--v-theme-surface)"
            variant="flat"
            rounded="sm"
            icon
          >
            <v-icon>mdi-dots-vertical</v-icon>
          </v-btn>
        </template>

        <!-- Bot/Chat 模式切换 - 仅在手机端显示 -->
        <template v-if="$vuetify.display.xs">
          <div class="mobile-mode-toggle-wrapper">
            <v-btn-toggle
              v-model="viewMode"
              mandatory
              variant="outlined"
              density="compact"
              color="primary"
              class="mobile-mode-toggle"
            >
              <v-btn
                value="bot"
                size="small"
              >
                <v-icon start>
                  mdi-robot
                </v-icon>
                Bot
              </v-btn>
              <v-btn
                value="chat"
                size="small"
              >
                <v-icon start>
                  mdi-chat
                </v-icon>
                Chat
              </v-btn>
            </v-btn-toggle>
          </div>
          <v-divider class="my-1" />
        </template>

        <!-- 语言切换分组 -->
        <v-menu
          :open-on-hover="!$vuetify.display.xs"
          :open-on-click="$vuetify.display.xs"
          :open-delay="!$vuetify.display.xs ? 60 : 0"
          :close-delay="!$vuetify.display.xs ? 120 : 0"
          :location="$vuetify.display.xs ? 'bottom' : 'start center'"
          offset="8"
        >
          <template #activator="{ props: languageMenuProps }">
            <v-list-item
              v-bind="languageMenuProps"
              class="styled-menu-item language-group-trigger"
              rounded="md"
            >
              <template #prepend>
                <v-icon>mdi-translate</v-icon>
              </template>
              <v-list-item-title>
                {{
                  t("core.common.language")
                }}
              </v-list-item-title>
              <template #append>
                <span class="language-group-current">{{
                  currentLanguage?.flag
                }}</span>
                <v-icon
                  size="18"
                  class="language-group-arrow"
                >
                  mdi-chevron-right
                </v-icon>
              </template>
            </v-list-item>
          </template>

          <v-card
            class="styled-menu-card"
            style="min-width: 180px"
            elevation="8"
            rounded="lg"
          >
            <v-list
              density="compact"
              class="styled-menu-list pa-1"
            >
              <v-list-item
                v-for="lang in languages"
                :key="lang.code"
                :value="lang.code"
                :class="{
                  'styled-menu-item-active': currentLocale === lang.code,
                }"
                class="styled-menu-item"
                rounded="md"
                @click="changeLanguage(lang.code)"
              >
                <template #prepend>
                  <span class="language-flag">{{ lang.flag }}</span>
                </template>
                <v-list-item-title>{{ lang.name }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>

        <!-- 主题切换 -->
        <v-list-item
          class="styled-menu-item"
          rounded="md"
          @click="toggleTheme()"
        >
          <template #prepend>
            <v-icon>
              {{
                useCustomizerStore().isDarkTheme
                  ? "mdi-weather-night"
                  : "mdi-white-balance-sunny"
              }}
            </v-icon>
          </template>
          <v-list-item-title>
            {{
              useCustomizerStore().isDarkTheme
                ? t("core.header.buttons.theme.light")
                : t("core.header.buttons.theme.dark")
            }}
          </v-list-item-title>
        </v-list-item>

        <!-- 更新按钮 -->
        <v-list-item
          class="styled-menu-item"
          rounded="md"
          @click="handleUpdateClick"
        >
          <template #prepend>
            <v-icon>mdi-arrow-up-circle</v-icon>
          </template>
          <v-list-item-title>
            {{
              t("core.header.updateDialog.title")
            }}
          </v-list-item-title>
          <template
            v-if="
              hasNewVersion || (dashboardHasNewVersion && !isDesktopReleaseMode)
            "
            #append
          >
            <v-chip
              size="x-small"
              color="primary"
              variant="tonal"
              class="ml-2"
            >
              !
            </v-chip>
          </template>
        </v-list-item>

        <!-- 账户按钮 -->
        <v-list-item
          class="styled-menu-item"
          rounded="md"
          @click="dialog = true"
        >
          <template #prepend>
            <v-icon>mdi-account</v-icon>
          </template>
          <v-list-item-title>
            {{
              t("core.header.accountDialog.title")
            }}
          </v-list-item-title>
        </v-list-item>

        <!-- 退出登录 -->
        <v-list-item
          class="styled-menu-item"
          rounded="md"
          @click="handleLogout"
        >
          <template #prepend>
            <v-icon>mdi-export</v-icon>
          </template>
          <v-list-item-title>
            {{
              t("core.header.buttons.logout")
            }}
          </v-list-item-title>
        </v-list-item>
      </StyledMenu>
    </div>
  </v-app-bar>

  <!-- 更新对话框 -->
  <v-dialog
    v-model="updateStatusDialog"
    :width="$vuetify.display.smAndDown ? '100%' : '1200'"
    :fullscreen="$vuetify.display.xs"
  >
    <v-card>
      <v-card-title class="mobile-card-title">
        <span class="text-h5">{{ t("core.header.updateDialog.title") }}</span>
        <v-btn
          v-if="$vuetify.display.xs"
          icon
          @click="updateStatusDialog = false"
        >
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-card-text>
        <v-container>
          <v-progress-linear
            v-show="installLoading"
            class="mb-4"
            indeterminate
            color="primary"
          />

          <div>
            <h1 style="display: inline-block">
              {{ botCurrVersion }}
            </h1>
            <small style="margin-left: 4px">{{ updateStatus }}</small>
          </div>

          <div
            v-if="releaseMessage"
            style="
              background-color: #646cff24;
              padding: 16px;
              border-radius: 10px;
              font-size: 14px;
              max-height: 400px;
              overflow-y: auto;
            "
          >
            <MarkdownRender
              :content="releaseMessage"
              :typewriter="false"
              class="markdown-content"
            />
          </div>

          <div class="mb-4 mt-4">
            <small>{{ t("core.header.updateDialog.tip") }}
              {{ t("core.header.updateDialog.tipContinue") }}</small>
          </div>

          <!-- 发行版 -->
          <div>
            <div class="mb-4">
              <small>{{ t("core.header.updateDialog.dockerTip") }}
                <a href="https://containrrr.dev/watchtower/usage-overview/">{{
                  t("core.header.updateDialog.dockerTipLink")
                }}</a>
                {{ t("core.header.updateDialog.dockerTipContinue") }}</small>
            </div>

            <v-alert
              v-if="
                releases.some((item: any) => isPreRelease(item['tag_name']))
              "
              type="warning"
              variant="tonal"
              border="start"
            >
              <template #prepend>
                <v-icon>mdi-alert-circle-outline</v-icon>
              </template>
              <div class="text-body-2">
                <strong>{{
                  t("core.header.updateDialog.preReleaseWarning.title")
                }}</strong>
                <br>
                {{
                  t("core.header.updateDialog.preReleaseWarning.description")
                }}
                <a
                  href="https://github.com/AstrBotDevs/AstrBot/issues"
                  target="_blank"
                  class="text-decoration-none"
                >
                  {{
                    t("core.header.updateDialog.preReleaseWarning.issueLink")
                  }}
                </a>
              </div>
            </v-alert>

            <v-data-table
              :headers="releasesHeader"
              :items="releases"
              item-key="name"
              :items-per-page="8"
            >
              <template #item.tag_name="{ item }: { item: any }">
                <div class="d-flex align-center">
                  <span>{{ item.tag_name }}</span>
                  <v-chip
                    v-if="isPreRelease(item.tag_name)"
                    size="x-small"
                    color="warning"
                    variant="tonal"
                    class="ml-2"
                  >
                    {{ t("core.header.updateDialog.preRelease") }}
                  </v-chip>
                </div>
              </template>
              <template
                #item.body="{
                  item,
                }: {
                  item: { body: string; tag_name: string };
                }"
              >
                <v-btn
                  rounded="xl"
                  variant="tonal"
                  color="primary"
                  size="x-small"
                  @click="openReleaseNotesDialog(item.body, item.tag_name)"
                >
                  {{ t("core.header.updateDialog.table.view") }}
                </v-btn>
              </template>
              <template
                #item.switch="{ item }: { item: { tag_name: string } }"
              >
                <v-btn
                  rounded="xl"
                  variant="plain"
                  color="primary"
                  @click="switchVersion(item.tag_name)"
                >
                  {{ t("core.header.updateDialog.table.switch") }}
                </v-btn>
              </template>
            </v-data-table>
          </div>

          <v-divider class="mt-4 mb-4" />
          <div style="margin-top: 16px">
            <h3 class="mb-4">
              {{ t("core.header.updateDialog.dashboardUpdate.title") }}
            </h3>
            <div class="mb-4">
              <small>{{
                       t("core.header.updateDialog.dashboardUpdate.currentVersion")
                     }}
                {{ dashboardCurrentVersion }}</small>
              <br>
            </div>

            <div class="mb-4">
              <p v-if="dashboardHasNewVersion">
                {{
                  t("core.header.updateDialog.dashboardUpdate.hasNewVersion")
                }}
              </p>
              <p v-else>
                {{ t("core.header.updateDialog.dashboardUpdate.isLatest") }}
              </p>
            </div>

            <v-btn
              color="primary"
              style="border-radius: 10px"
              :disabled="!dashboardHasNewVersion"
              :loading="updatingDashboardLoading"
              @click="updateDashboard()"
            >
              {{
                t("core.header.updateDialog.dashboardUpdate.downloadAndUpdate")
              }}
            </v-btn>
          </div>
        </v-container>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          color="blue-darken-1"
          variant="text"
          @click="updateStatusDialog = false"
        >
          {{ t("core.common.close") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Release Notes Modal -->
  <v-dialog
    v-model="releaseNotesDialog"
    max-width="800"
  >
    <v-card>
      <v-card-title class="text-h5">
        {{ t("core.header.updateDialog.releaseNotes.title") }}:
        {{ selectedReleaseTag }}
      </v-card-title>
      <v-card-text style="font-size: 14px; max-height: 400px; overflow-y: auto">
        <MarkdownRender
          :content="selectedReleaseNotes"
          :typewriter="false"
          class="markdown-content"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          color="blue-darken-1"
          variant="text"
          @click="releaseNotesDialog = false"
        >
          {{ t("core.common.close") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog
    v-model="desktopUpdateDialog"
    max-width="460"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pl-6 pb-0">
        {{ t("core.header.updateDialog.desktopApp.title") }}
      </v-card-title>
      <v-card-text>
        <div class="mb-3">
          {{ t("core.header.updateDialog.desktopApp.message") }}
        </div>
        <v-alert
          type="info"
          variant="tonal"
          density="compact"
        >
          <div>
            {{ t("core.header.updateDialog.desktopApp.currentVersion") }}
            <strong>{{ desktopUpdateCurrentVersion }}</strong>
          </div>
          <div>
            {{ t("core.header.updateDialog.desktopApp.latestVersion") }}
            <strong v-if="!desktopUpdateChecking">{{
              desktopUpdateLatestVersion
            }}</strong>
            <v-progress-circular
              v-else
              indeterminate
              size="16"
              width="2"
              class="ml-1"
            />
          </div>
        </v-alert>
        <div class="text-caption mt-3">
          {{ desktopUpdateStatus }}
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          color="grey"
          variant="text"
          :disabled="desktopUpdateInstalling"
          @click="cancelDesktopUpdate"
        >
          {{ t("core.common.dialog.cancelButton") }}
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="desktopUpdateInstalling"
          :disabled="
            desktopUpdateChecking ||
              desktopUpdateInstalling ||
              !desktopUpdateHasNewVersion
          "
          @click="confirmDesktopUpdate"
        >
          {{ t("core.common.dialog.confirmButton") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 账户对话框 -->
  <v-dialog
    v-model="dialog"
    persistent
    :max-width="$vuetify.display.xs ? '90%' : '500'"
  >
    <v-card class="account-dialog">
      <v-card-text class="py-6">
        <div class="d-flex flex-column align-center mb-6">
          <Logo
            :title="t('core.header.logoTitle')"
            :subtitle="t('core.header.accountDialog.title')"
          />
        </div>
        <v-alert
          v-if="accountWarning"
          type="warning"
          variant="tonal"
          border="start"
          class="mb-4"
        >
          <strong>{{ t("core.header.accountDialog.securityWarning") }}</strong>
        </v-alert>

        <v-alert
          v-if="accountEditStatus.success"
          type="success"
          variant="tonal"
          border="start"
          class="mb-4"
        >
          {{ accountEditStatus.message }}
        </v-alert>

        <v-alert
          v-if="accountEditStatus.error"
          type="error"
          variant="tonal"
          border="start"
          class="mb-4"
        >
          {{ accountEditStatus.message }}
        </v-alert>

        <v-form
          v-model="formValid"
          @submit.prevent="accountEdit"
        >
          <v-text-field
            v-model="password"
            :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
            :type="showPassword ? 'text' : 'password'"
            :label="t('core.header.accountDialog.form.currentPassword')"
            variant="outlined"
            required
            clearable
            prepend-inner-icon="mdi-lock-outline"
            hide-details="auto"
            class="mb-4"
            @click:append-inner="showPassword = !showPassword"
          />

          <v-text-field
            v-model="newPassword"
            :append-inner-icon="showNewPassword ? 'mdi-eye-off' : 'mdi-eye'"
            :type="showNewPassword ? 'text' : 'password'"
            :rules="passwordRules"
            :label="t('core.header.accountDialog.form.newPassword')"
            variant="outlined"
            clearable
            prepend-inner-icon="mdi-lock-plus-outline"
            :hint="t('core.header.accountDialog.form.passwordHint')"
            persistent-hint
            class="mb-4"
            @click:append-inner="showNewPassword = !showNewPassword"
          />

          <v-text-field
            v-model="confirmPassword"
            :append-inner-icon="showConfirmPassword ? 'mdi-eye-off' : 'mdi-eye'"
            :type="showConfirmPassword ? 'text' : 'password'"
            :rules="confirmPasswordRules"
            :label="t('core.header.accountDialog.form.confirmPassword')"
            variant="outlined"
            clearable
            prepend-inner-icon="mdi-lock-check-outline"
            :hint="t('core.header.accountDialog.form.confirmPasswordHint')"
            persistent-hint
            class="mb-4"
            @click:append-inner="showConfirmPassword = !showConfirmPassword"
          />

          <v-text-field
            v-model="newUsername"
            :rules="usernameRules"
            :label="t('core.header.accountDialog.form.newUsername')"
            variant="outlined"
            clearable
            prepend-inner-icon="mdi-account-edit-outline"
            :hint="t('core.header.accountDialog.form.usernameHint')"
            persistent-hint
            class="mb-3"
          />
        </v-form>

        <div class="text-caption text-medium-emphasis mt-2">
          {{ t("core.header.accountDialog.form.defaultCredentials") }}
        </div>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn
          v-if="!accountWarning"
          variant="tonal"
          color="secondary"
          :disabled="accountEditStatus.loading"
          @click="dialog = false"
        >
          {{ t("core.header.accountDialog.actions.cancel") }}
        </v-btn>
        <v-btn
          color="primary"
          :loading="accountEditStatus.loading"
          :disabled="!formValid"
          prepend-icon="mdi-content-save"
          @click="accountEdit"
        >
          {{ t("core.header.accountDialog.actions.save") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- About 对话框 - 仅在 chat mode 下使用 -->
  <v-dialog
    v-model="aboutDialog"
    width="600"
  >
    <v-card>
      <v-card-text style="overflow-y: auto">
        <AboutPage />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style>
.markdown-content h1 {
  font-size: 1.3em;
}

.markdown-content ol {
  padding-left: 24px;
  /* Adds indentation to ordered lists */
  margin-top: 8px;
  margin-bottom: 8px;
}

.markdown-content ul {
  padding-left: 24px;
  /* Adds indentation to unordered lists */
  margin-top: 8px;
  margin-bottom: 8px;
}

.account-dialog .v-card-text {
  padding-top: 24px;
  padding-bottom: 24px;
}

.account-dialog .v-alert {
  margin-bottom: 20px;
}

.account-dialog .v-btn {
  text-transform: none;
  font-weight: 500;
  border-radius: 8px;
}

.account-dialog .v-avatar {
  transition: transform 0.3s ease;
}

.account-dialog .v-avatar:hover {
  transform: scale(1.05);
}

/* 响应式布局样式 */
.logo-container {
  margin-left: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.mobile-logo {
  margin-left: 8px;
  gap: 4px;
}

.chat-mode-logo {
  margin-left: 22px;
}

.mobile-logo.chat-mode-logo {
  margin-left: 4px;
}

.logo-text {
  font-size: 24px;
  font-weight: 1000;
}

.logo-text-light {
  font-weight: normal;
}

.bot-text-wrapper {
  position: relative;
  display: inline-block;
}

.xmas-hat {
  position: absolute;
  top: -3px;
  right: -14px;
  width: 24px;
  height: 24px;
  z-index: 1;
}

.version-text {
  font-size: 12px;
  color: gray;
  margin-left: 4px;
}

.action-btn {
  margin-right: 6px;
}

.language-flag {
  font-size: 16px;
  margin-right: 8px;
}

.language-group-trigger :deep(.v-list-item__append) {
  display: flex;
  align-items: center;
  gap: 6px;
}

.language-group-current {
  font-size: 16px;
  line-height: 1;
}

.language-group-arrow {
  opacity: 0.7;
}

.language-submenu-card {
  min-width: 180px;
}

.mobile-mode-toggle-wrapper {
  display: flex;
  justify-content: center;
  padding: 8px 12px 4px;
}

.mobile-mode-toggle {
  width: 100%;
}

.mobile-mode-toggle .v-btn {
  flex: 1;
}

/* 移动端对话框标题样式 */
.mobile-card-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 移动端样式优化 */
@media (max-width: 600px) {
  .logo-text {
    font-size: 20px;
  }

  .action-btn {
    margin-right: 4px;
    min-width: 32px !important;
    width: 32px;
  }

  .v-card-title {
    padding: 12px 16px;
  }

  .v-card-text {
    padding: 16px;
  }

  .v-tabs .v-tab {
    padding: 0 10px;
    font-size: 0.9rem;
  }

  /* 移动端模式切换按钮样式 */
  .v-btn-toggle {
    margin-right: 8px;
  }

  .v-btn-toggle .v-btn {
    font-size: 0.75rem;
    padding: 0 8px;
  }

  .v-btn-toggle .v-icon {
    font-size: 16px;
  }
}
</style>
