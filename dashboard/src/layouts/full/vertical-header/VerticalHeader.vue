<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { useCustomizerStore } from "@/stores/customizer";
import axios from "axios";
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
import { useTheme } from "vuetify";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import { useLanguageSwitcher } from "@/i18n/composables";
import type { Locale } from "@/i18n/types";
import AboutPage from "@/views/AboutPage.vue";
import { getDesktopRuntimeInfo } from "@/utils/desktopRuntime";

enableKatex();
enableMermaid();

const customizer = useCustomizerStore();
const commonStore = useCommonStore();
const theme = useTheme();
const { t } = useI18n();
const route = useRoute();
const LAST_BOT_ROUTE_KEY = "astrbot:last_bot_route";
const LAST_CHAT_ROUTE_KEY = "astrbot:last_chat_route";
let dialog = ref(false);
let accountWarning = ref(false);
let accountWarningLegacy = ref(false);
let accountWarningUpgrade = ref(false);
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
let releases = ref([]);
let releasesLoading = ref(false);
let updatingDashboardLoading = ref(false);
let installLoading = ref(false);
let showAdvancedUpdateSettings = ref(false);
let restartWaiting = ref(false);
let restartStartTime = ref<number | string | null>(null);
let restartPollTimer: ReturnType<typeof setInterval> | null = null;
type DownloadStageStatus = "pending" | "running" | "done" | "error";
type DownloadStage = {
  status: DownloadStageStatus;
  downloaded: number;
  total: number;
  percent: number;
  speed: number;
};
type UpdateProgress = {
  id: string;
  status: "idle" | "running" | "success" | "error";
  stage: string;
  version: string;
  message: string;
  overall_percent: number;
  stages: Record<string, DownloadStage>;
};
const createEmptyDownloadStage = (
  status: DownloadStageStatus = "pending",
): DownloadStage => ({
  status,
  downloaded: 0,
  total: 0,
  percent: 0,
  speed: 0,
});
const createEmptyUpdateProgress = (): UpdateProgress => ({
  id: "",
  status: "idle",
  stage: "preparing",
  version: "",
  message: "",
  overall_percent: 0,
  stages: {
    dashboard: createEmptyDownloadStage(),
    core: createEmptyDownloadStage(),
  },
});
let updateProgress = ref<UpdateProgress>(createEmptyUpdateProgress());
let updateProgressTimer: ReturnType<typeof setInterval> | null = null;
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
const isChatPath = computed(
  () => route.path === "/chat" || route.path.startsWith("/chat/"),
);
const getAppUpdaterBridge = (): AstrBotAppUpdaterBridge | null => {
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
  { title: t("core.header.updateDialog.table.actions"), key: "switch" },
]);
const firstReleasePageItems = computed(() => releases.value.slice(0, 6));
const firstReleasePageHasPreRelease = computed(() =>
  firstReleasePageItems.value.some((item: any) => isPreRelease(item.tag_name)),
);
const updateStageItems = computed(() => [
  {
    key: "dashboard",
    title: t("core.header.updateDialog.progress.dashboard"),
    progress:
      updateProgress.value.stages.dashboard || createEmptyDownloadStage(),
  },
  {
    key: "core",
    title: t("core.header.updateDialog.progress.core"),
    progress: updateProgress.value.stages.core || createEmptyDownloadStage(),
  },
]);
const updateProgressMessage = computed(() => {
  if (updateProgress.value.status === "error") {
    return (
      updateProgress.value.message ||
      t("core.header.updateDialog.progress.failed")
    );
  }
  if (updateProgress.value.status === "success") {
    return (
      updateProgress.value.message ||
      t("core.header.updateDialog.progress.completed")
    );
  }
  if (updateProgress.value.stage === "dependencies") {
    return t("core.header.updateDialog.progress.dependencies");
  }
  if (updateProgress.value.stage === "restart") {
    return t("core.header.updateDialog.progress.restart");
  }
  return (
    updateProgress.value.message ||
    t("core.header.updateDialog.progress.preparing")
  );
});
// Form validation
const formValid = ref(true);
const passwordRules = computed(() => [
  (v: string) =>
    !!v || t("core.header.accountDialog.validation.passwordRequired"),
  (v: string) =>
    v.length >= 8 ||
    t("core.header.accountDialog.validation.passwordMinLength"),
  (v: string) =>
    /[A-Z]/.test(v) ||
    t("core.header.accountDialog.validation.passwordUppercase"),
  (v: string) =>
    /[a-z]/.test(v) ||
    t("core.header.accountDialog.validation.passwordLowercase"),
  (v: string) =>
    /\d/.test(v) || t("core.header.accountDialog.validation.passwordDigit"),
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

// 账户修改
function accountEdit() {
  accountEditStatus.value.loading = true;
  accountEditStatus.value.error = false;
  accountEditStatus.value.success = false;

  const currentPasswordValue = password.value ? password.value : "";
  const newPasswordValue = newPassword.value ? newPassword.value : "";
  const confirmPasswordValue = confirmPassword.value
    ? confirmPassword.value
    : "";

  axios
    .post("/api/auth/account/edit", {
      password: currentPasswordValue,
      new_password: newPasswordValue,
      confirm_password: confirmPasswordValue,
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
      commonStore.setAstrBotVersion(
        res.data.data.version,
        res.data.data?.dashboard_version,
      );
      const change_pwd_hint = res.data.data?.change_pwd_hint;
      const legacy_pwd_hint = res.data.data?.legacy_pwd_hint;
      const password_upgrade_required =
        res.data.data?.password_upgrade_required;
      if (change_pwd_hint || legacy_pwd_hint || password_upgrade_required) {
        dialog.value = true;
        accountWarning.value = true;
        accountWarningUpgrade.value = !!password_upgrade_required;
        accountWarningLegacy.value =
          !!legacy_pwd_hint && !password_upgrade_required;
        if (
          change_pwd_hint ||
          (legacy_pwd_hint && !password_upgrade_required)
        ) {
          localStorage.setItem("change_pwd_hint", "true");
        } else {
          localStorage.removeItem("change_pwd_hint");
        }
        if (legacy_pwd_hint && !password_upgrade_required) {
          localStorage.setItem("legacy_pwd_hint", "true");
        } else {
          localStorage.removeItem("legacy_pwd_hint");
        }
        if (password_upgrade_required) {
          localStorage.setItem("password_upgrade_required", "true");
        } else {
          localStorage.removeItem("password_upgrade_required");
        }
      } else {
        accountWarningLegacy.value = false;
        accountWarningUpgrade.value = false;
        localStorage.removeItem("change_pwd_hint");
        localStorage.removeItem("legacy_pwd_hint");
        localStorage.removeItem("password_upgrade_required");
      }
    })
    .catch((err) => {
      console.log(err);
    });
}

function initPasswordWarningFromStorage() {
  const hasChangePwdHint = localStorage.getItem("change_pwd_hint") === "true";
  const hasLegacyPwdHint = localStorage.getItem("legacy_pwd_hint") === "true";
  const hasPasswordUpgradeRequired =
    localStorage.getItem("password_upgrade_required") === "true";
  if (hasChangePwdHint || hasLegacyPwdHint || hasPasswordUpgradeRequired) {
    dialog.value = true;
    accountWarning.value = true;
    accountWarningUpgrade.value = hasPasswordUpgradeRequired;
    accountWarningLegacy.value =
      hasLegacyPwdHint && !hasPasswordUpgradeRequired;
  }
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
  releasesLoading.value = true;
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
    })
    .finally(() => {
      releasesLoading.value = false;
    });
}

function formatDownloadSize(value: number) {
  if (!value || value <= 0) {
    return "-";
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDownloadSpeed(value: number) {
  if (!value || value <= 0) {
    return "-";
  }
  if (value < 1024) {
    return `${value.toFixed(1)} KB/s`;
  }
  return `${(value / 1024).toFixed(1)} MB/s`;
}

function getStageStatusColor(status: DownloadStageStatus) {
  if (status === "done") {
    return "success";
  }
  if (status === "running") {
    return "primary";
  }
  if (status === "error") {
    return "error";
  }
  return "grey";
}

function getStageStatusIcon(status: DownloadStageStatus) {
  if (status === "done") {
    return "mdi-check-circle";
  }
  if (status === "running") {
    return "mdi-progress-download";
  }
  if (status === "error") {
    return "mdi-alert-circle";
  }
  return "mdi-circle-outline";
}

function stopUpdateProgressPolling() {
  if (updateProgressTimer) {
    clearInterval(updateProgressTimer);
    updateProgressTimer = null;
  }
}

function stopRestartPolling() {
  if (restartPollTimer) {
    clearInterval(restartPollTimer);
    restartPollTimer = null;
  }
}

async function fetchAstrBotStartTime() {
  const res = await axios.get("/api/stat/start-time", { timeout: 3000 });
  const startTime = res.data?.data?.start_time ?? null;
  commonStore.startTime = startTime;
  return startTime;
}

function waitForAstrBotRestart(initialStartTime: number | string | null) {
  if (restartWaiting.value) {
    return;
  }
  stopRestartPolling();
  restartWaiting.value = true;
  restartStartTime.value = initialStartTime;
  updateProgress.value = {
    ...updateProgress.value,
    stage: "restart",
    status: "success",
    message: t("core.header.updateDialog.progress.restarting"),
    overall_percent: 100,
  };

  const poll = async () => {
    try {
      const currentStartTime = await fetchAstrBotStartTime();
      if (
        initialStartTime !== null &&
        currentStartTime !== null &&
        currentStartTime !== initialStartTime
      ) {
        stopRestartPolling();
        restartWaiting.value = false;
        window.location.reload();
      }
    } catch (_error) {
      // Backend may be unavailable while the process is restarting.
    }
  };

  restartPollTimer = setInterval(() => {
    void poll();
  }, 1000);
}

function applyUpdateProgress(payload: UpdateProgress) {
  updateProgress.value = {
    ...createEmptyUpdateProgress(),
    ...payload,
    stages: {
      ...createEmptyUpdateProgress().stages,
      ...(payload.stages || {}),
    },
  };
  if (payload.status === "success" || payload.status === "error") {
    stopUpdateProgressPolling();
  }
  if (payload.status === "success") {
    waitForAstrBotRestart(restartStartTime.value);
  }
}

function startUpdateProgressPolling(progressId: string) {
  stopUpdateProgressPolling();
  const poll = () => {
    axios
      .get("/api/update/progress", { params: { id: progressId } })
      .then((res) => {
        if (res.data?.data) {
          applyUpdateProgress(res.data.data);
        }
      })
      .catch((err) => {
        console.log(err);
      });
  };
  poll();
  updateProgressTimer = setInterval(poll, 800);
}

async function switchVersion(targetVersion: string) {
  const progressId =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  let initialStartTime: number | string | null = null;
  updateProgress.value = {
    ...createEmptyUpdateProgress(),
    id: progressId,
    status: "running",
    version: targetVersion,
    message: t("core.header.updateDialog.progress.preparing"),
  } as UpdateProgress;
  updateStatus.value = t("core.header.updateDialog.status.switching");
  installLoading.value = true;

  try {
    initialStartTime = await fetchAstrBotStartTime();
  } catch (_error) {
    initialStartTime = commonStore.getStartTime();
  }
  restartStartTime.value = initialStartTime;
  startUpdateProgressPolling(progressId);

  axios
    .post("/api/update/do", {
      version: targetVersion,
      proxy: getSelectedGitHubProxy(),
      progress_id: progressId,
    })
    .then((res) => {
      updateStatus.value = res.data.message;
      updateProgress.value = {
        ...updateProgress.value,
        status:
          res.data.status === "ok" ? "success" : updateProgress.value.status,
        message: res.data.message,
        overall_percent:
          res.data.status === "ok" ? 100 : updateProgress.value.overall_percent,
      };
      if (res.data.status == "ok") {
        waitForAstrBotRestart(initialStartTime);
      }
    })
    .catch((err) => {
      console.log(err);
      updateStatus.value = err;
      updateProgress.value = {
        ...updateProgress.value,
        status: "error",
        message:
          err?.response?.data?.message ||
          err?.message ||
          t("core.header.updateDialog.progress.failed"),
      };
    })
    .finally(() => {
      installLoading.value = false;
      stopUpdateProgressPolling();
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

function toggleDarkMode() {
  const newTheme =
    customizer.uiTheme === "PurpleThemeDark"
      ? "PurpleTheme"
      : "PurpleThemeDark";
  customizer.SET_UI_THEME(newTheme);
  theme.global.name.value = newTheme;
}

function openReleaseNotesDialog(body: string, tag: string) {
  selectedReleaseNotes.value = body;
  selectedReleaseTag.value = tag;
  releaseNotesDialog.value = true;
}

function handleLogoClick() {
  if (isChatPath.value) {
    aboutDialog.value = true;
  } else {
    router.push("/about");
  }
}

getVersion();
checkUpdate();
initPasswordWarningFromStorage();

commonStore.createEventSource(); // log
commonStore.getStartTime();

onUnmounted(() => {
  stopUpdateProgressPolling();
  stopRestartPolling();
});

// 视图模式切换
onMounted(() => {
  // 初次加載時保存當前路由
  if (typeof window !== "undefined") {
    if (isChatPath.value) {
      // 保存 chat ID
      const parts = route.fullPath.split("/");
      const sessionId = parts[2];
      if (sessionId) {
        sessionStorage.setItem(LAST_CHAT_ROUTE_KEY, sessionId);
        console.log("Initial save chat ID:", sessionId);
      }
    } else {
      // 保存 bot 路由（非 chat 頁面）
      sessionStorage.setItem(LAST_BOT_ROUTE_KEY, route.fullPath);
      console.log("Initial save bot route:", route.fullPath);
    }
  }
});

// 监听 viewMode 变化，切换到 bot 模式时跳转到首页
// 保存 bot 模式的最後路由
// 監聽 route 變化，保存最後一次 bot 路由
watch(
  () => route.fullPath,
  (newPath) => {
    if (typeof window === "undefined") return;
    console.log("Route changed:", {
      newPath,
      isChat: isChatPath.value,
      currentChatId: route.params.id,
    });
    try {
      // 使用現有的 isChatPath 計算屬性來避免名稱衝突
      const isChat = isChatPath.value; // 這裡使用已經計算好的 isChatPath

      // ✅ bot：只存「非 chat 頁」
      if (!isChat) {
        sessionStorage.setItem(LAST_BOT_ROUTE_KEY, newPath);
      }

      // ✅ chat：只存 sessionId
      if (isChat) {
        const parts = newPath.split("/");
        const sessionId = parts[2];

        if (sessionId) {
          sessionStorage.setItem(LAST_CHAT_ROUTE_KEY, sessionId);
        }
      }
    } catch (e) {
      console.error("Failed to save route:", e);
    }
  },
);

const currentMode = computed({
  get: () => (isChatPath.value ? "chat" : "bot"),
  set: (val: "chat" | "bot") => {
    try {
      // 檢查 window 和 sessionStorage 是否存在
      if (
        typeof window === "undefined" ||
        typeof sessionStorage === "undefined"
      ) {
        // 如果在非瀏覽器環境中，不做任何 sessionStorage 操作
        console.warn("sessionStorage is not available in this environment");
        return;
      }

      if (val === "chat") {
        const lastSessionId = sessionStorage.getItem(LAST_CHAT_ROUTE_KEY);
        router.push(lastSessionId ? `/chat/${lastSessionId}` : "/chat");
      } else {
        let lastBotRoute = sessionStorage.getItem(LAST_BOT_ROUTE_KEY) || "/";
        if (lastBotRoute.startsWith("/chat")) {
          lastBotRoute = "/";
        }
        router.push(lastBotRoute);
      }
    } catch (e) {
      // 在受限隱私模式等環境中，sessionStorage 操作可能會拋出 SecurityError
      console.warn("Failed to access sessionStorage in currentMode setter:", e);
    }
  },
});

// Merry Christmas! 🎄
const isChristmas = computed(() => {
  const today = new Date();
  const month = today.getMonth() + 1; // getMonth() 返回 0-11
  const day = today.getDate();
  return month === 12 && day === 25;
});

// 语言切换相关
const mainMenuOpen = ref(false);
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
  mainMenuOpen.value = false;
};

onMounted(async () => {
  const runtimeInfo = await getDesktopRuntimeInfo();
  isDesktopReleaseMode.value = runtimeInfo.isDesktopRuntime;
  if (isDesktopReleaseMode.value) {
    dashboardHasNewVersion.value = false;
  }
});
</script>

<template>
  <v-app-bar elevation="0" height="50" class="top-header">
    <!-- 桌面端 menu 按钮 - 仅在 bot 模式下显示 -->
    <v-btn
      v-if="!isChatPath"
      style="margin-left: 16px"
      class="hidden-md-and-down"
      icon
      rounded="sm"
      variant="flat"
      @click.stop="customizer.SET_MINI_SIDEBAR(!customizer.mini_sidebar)"
    >
      <v-icon>mdi-menu</v-icon>
    </v-btn>

    <!-- 移动端 menu 按钮 -->
    <v-btn
      v-if="!isChatPath"
      class="hidden-lg-and-up ms-3"
      icon
      rounded="sm"
      variant="flat"
      @click.stop="customizer.SET_SIDEBAR_DRAWER"
    >
      <v-icon>mdi-menu</v-icon>
    </v-btn>

    <v-btn
      v-if="isChatPath"
      class="hidden-lg-and-up ms-1"
      icon
      rounded="sm"
      variant="flat"
      @click.stop="customizer.TOGGLE_CHAT_SIDEBAR()"
    >
      <v-icon>mdi-menu</v-icon>
    </v-btn>

    <div
      class="logo-container"
      :class="{
        'mobile-logo': $vuetify.display.xs,
        'chat-mode-logo': isChatPath,
      }"
      @click="handleLogoClick"
    >
      <span class="logo-text Outfit"
        >Astr<span class="logo-text bot-text-wrapper"
          >Bot
          <img
            v-if="isChristmas"
            src="@/assets/images/xmas-hat.png"
            alt="Christmas hat"
            class="xmas-hat"
          /> </span
      ></span>
      <span
        class="logo-text logo-text-light Outfit"
        style="color: grey"
        v-if="isChatPath"
        >ChatUI</span
      >
      <span class="version-text hidden-xs">{{ botCurrVersion }}</span>
    </div>

    <v-spacer />

    <!-- 版本提示信息 - 在手机上隐藏 -->
    <div class="mr-4 hidden-xs">
      <small v-if="hasNewVersion">
        {{ t("core.header.version.hasNewVersion") }}
      </small>
      <small v-else-if="dashboardHasNewVersion && !isDesktopReleaseMode">
        {{ t("core.header.version.dashboardHasNewVersion") }}
      </small>
    </div>

    <!-- Bot/Chat 模式切换按钮 - 手机端隐藏，移入 ... 菜单 -->
    <v-btn-toggle
      v-model="currentMode"
      mandatory
      variant="outlined"
      density="compact"
      class="mr-4 hidden-xs"
      color="primary"
    >
      <v-btn value="bot" size="small">
        <v-icon start>mdi-robot</v-icon>
        Bot
      </v-btn>
      <v-btn value="chat" size="small">
        <v-icon start>mdi-chat</v-icon>
        Chat
      </v-btn>
    </v-btn-toggle>

    <!-- 功能菜单 -->
    <StyledMenu v-model="mainMenuOpen" offset="12" location="bottom end">
      <template v-slot:activator="{ props: activatorProps }">
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
            v-model="currentMode"
            mandatory
            variant="outlined"
            density="compact"
            class="mobile-mode-toggle"
            color="primary"
          >
            <v-btn value="bot" size="small">
              <v-icon start>mdi-robot</v-icon>
              Bot
            </v-btn>
            <v-btn value="chat" size="small">
              <v-icon start>mdi-chat</v-icon>
              Chat
            </v-btn>
          </v-btn-toggle>
        </div>
        <v-divider class="my-1" />
      </template>

      <!-- 语言切换分组 -->
      <v-menu
        open-on-click
        :open-on-hover="!$vuetify.display.xs"
        :open-delay="!$vuetify.display.xs ? 60 : 0"
        :close-delay="!$vuetify.display.xs ? 120 : 0"
        :location="$vuetify.display.xs ? 'bottom' : 'start center'"
        offset="8"
      >
        <template v-slot:activator="{ props: languageMenuProps }">
          <v-list-item
            v-bind="languageMenuProps"
            @click.stop
            class="styled-menu-item language-group-trigger"
            rounded="md"
          >
            <template v-slot:prepend>
              <v-icon>mdi-translate</v-icon>
            </template>
            <v-list-item-title>{{
              t("core.common.language")
            }}</v-list-item-title>
            <template v-slot:append>
              <span class="language-group-current">{{
                currentLanguage?.flag
              }}</span>
              <v-icon size="18" class="language-group-arrow"
                >mdi-chevron-right</v-icon
              >
            </template>
          </v-list-item>
        </template>

        <v-card
          class="styled-menu-card"
          style="min-width: 180px"
          elevation="8"
          rounded="lg"
        >
          <v-list density="compact" class="styled-menu-list pa-1">
            <v-list-item
              v-for="lang in languages"
              :key="lang.code"
              :value="lang.code"
              @click="changeLanguage(lang.code)"
              :class="{
                'styled-menu-item-active': currentLocale === lang.code,
              }"
              class="styled-menu-item"
              rounded="md"
            >
              <template v-slot:prepend>
                <span class="language-flag">{{ lang.flag }}</span>
              </template>
              <v-list-item-title>{{ lang.name }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card>
      </v-menu>

      <!-- 主题切换 -->
      <v-list-item
        @click="toggleDarkMode()"
        class="styled-menu-item"
        rounded="md"
      >
        <template v-slot:prepend>
          <v-icon>
            {{
              useCustomizerStore().uiTheme === "PurpleThemeDark"
                ? "mdi-weather-night"
                : "mdi-white-balance-sunny"
            }}
          </v-icon>
        </template>
        <v-list-item-title>
          {{
            useCustomizerStore().uiTheme === "PurpleThemeDark"
              ? t("core.header.buttons.theme.light")
              : t("core.header.buttons.theme.dark")
          }}
        </v-list-item-title>
      </v-list-item>

      <!-- 更新按钮 -->
      <v-list-item
        @click="handleUpdateClick"
        class="styled-menu-item"
        rounded="md"
      >
        <template v-slot:prepend>
          <v-icon>mdi-arrow-up-circle</v-icon>
        </template>
        <v-list-item-title>{{
          t("core.header.updateDialog.title")
        }}</v-list-item-title>
        <template
          v-slot:append
          v-if="
            hasNewVersion || (dashboardHasNewVersion && !isDesktopReleaseMode)
          "
        >
          <v-chip size="x-small" color="primary" variant="tonal" class="ml-2"
            >!</v-chip
          >
        </template>
      </v-list-item>

      <!-- 账户按钮 -->
      <v-list-item @click="dialog = true" class="styled-menu-item" rounded="md">
        <template v-slot:prepend>
          <v-icon>mdi-account</v-icon>
        </template>
        <v-list-item-title>{{
          t("core.header.accountDialog.title")
        }}</v-list-item-title>
      </v-list-item>
    </StyledMenu>

    <!-- 更新对话框 -->
    <v-dialog
      v-model="updateStatusDialog"
      :width="$vuetify.display.smAndDown ? '100%' : '920'"
      :fullscreen="$vuetify.display.xs"
    >
      <v-card>
        <v-card-title class="mobile-card-title">
          <span class="text-h3 pa-4">{{
            t("core.header.updateDialog.title")
          }}</span>
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
            <div class="update-summary">
              <div>
                <div class="text-caption text-medium-emphasis">
                  {{ t("core.header.updateDialog.currentVersion") }}
                </div>
                <div class="text-h2 font-weight-bold">{{ botCurrVersion }}</div>
              </div>
              <v-chip
                :color="hasNewVersion ? 'primary' : 'success'"
                variant="tonal"
                size="small"
              >
                {{
                  hasNewVersion
                    ? t("core.header.version.hasNewVersion")
                    : updateStatus
                }}
              </v-chip>
            </div>

            <div
              v-if="installLoading || updateProgress.status !== 'idle'"
              class="update-progress-panel mt-5"
            >
              <div v-if="restartWaiting" class="restart-waiting-panel">
                <v-progress-circular
                  indeterminate
                  color="primary"
                  size="42"
                  width="4"
                ></v-progress-circular>
                <div class="text-subtitle-1 font-weight-medium">
                  {{ t("core.header.updateDialog.progress.restarting") }}
                </div>
              </div>

              <template v-else>
                <div class="d-flex align-center justify-space-between mb-2">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">
                      {{ updateProgressMessage }}
                    </div>
                    <div class="text-caption text-medium-emphasis">
                      {{ t("core.header.updateDialog.progress.target") }}
                      {{ updateProgress.version || "latest" }}
                    </div>
                  </div>
                  <div class="text-h6 font-weight-bold">
                    {{ updateProgress.overall_percent }}%
                  </div>
                </div>
                <v-progress-linear
                  :model-value="updateProgress.overall_percent"
                  height="8"
                  rounded
                  color="primary"
                ></v-progress-linear>

                <div class="update-stage-list mt-4">
                  <div
                    v-for="stage in updateStageItems"
                    :key="stage.key"
                    class="update-stage-row"
                  >
                    <v-icon
                      :icon="getStageStatusIcon(stage.progress.status)"
                      :color="getStageStatusColor(stage.progress.status)"
                      size="22"
                    ></v-icon>
                    <div class="update-stage-content">
                      <div class="d-flex align-center justify-space-between">
                        <span class="font-weight-medium">{{
                          stage.title
                        }}</span>
                        <span class="text-caption">
                          {{ stage.progress.percent }}%
                        </span>
                      </div>
                      <v-progress-linear
                        :model-value="stage.progress.percent"
                        height="5"
                        rounded
                        :color="getStageStatusColor(stage.progress.status)"
                        class="mt-2"
                      ></v-progress-linear>
                      <div class="update-stage-meta">
                        <span>
                          {{ formatDownloadSize(stage.progress.downloaded) }} /
                          {{ formatDownloadSize(stage.progress.total) }}
                        </span>
                        <span>{{
                          formatDownloadSpeed(stage.progress.speed)
                        }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </div>

            <div v-if="releaseMessage && !installLoading" class="mt-5">
              <div class="d-flex align-center justify-space-between mb-2">
                <h3 class="text-subtitle-1 font-weight-medium">
                  {{ t("core.header.updateDialog.releaseNotes.title") }}
                </h3>
                <v-btn
                  variant="text"
                  size="small"
                  @click="
                    openReleaseNotesDialog(
                      releaseMessage,
                      t('core.header.updateDialog.releaseNotes.latestLabel'),
                    )
                  "
                >
                  {{ t("core.header.updateDialog.table.view") }}
                </v-btn>
              </div>
              <div class="release-message-preview">
                <MarkdownRender
                  :content="releaseMessage"
                  :typewriter="false"
                  class="markdown-content"
                />
              </div>
            </div>

            <!-- 发行版 -->
            <div class="mt-5">
              <v-alert
                v-if="!installLoading && firstReleasePageHasPreRelease"
                type="warning"
                variant="tonal"
                border="start"
                density="compact"
                class="mb-4"
              >
                <template v-slot:prepend>
                  <v-icon>mdi-alert-circle-outline</v-icon>
                </template>
                <div class="text-body-2">
                  <strong>{{
                    t("core.header.updateDialog.preReleaseWarning.title")
                  }}</strong>
                  <br />
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
                :items-per-page="6"
                density="comfortable"
                :loading="releasesLoading"
              >
                <template v-slot:item.tag_name="{ item }: { item: any }">
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
                  v-slot:item.body="{
                    item,
                  }: {
                    item: { body: string; tag_name: string };
                  }"
                >
                  <v-btn
                    @click="openReleaseNotesDialog(item.body, item.tag_name)"
                    rounded="xl"
                    variant="tonal"
                    color="primary"
                    size="x-small"
                    >{{ t("core.header.updateDialog.table.view") }}</v-btn
                  >
                </template>
                <template
                  v-slot:item.switch="{ item }: { item: { tag_name: string } }"
                >
                  <v-btn
                    @click="switchVersion(item.tag_name)"
                    variant="tonal"
                    color="primary"
                    size="small"
                    :disabled="installLoading"
                  >
                    {{ t("core.header.updateDialog.table.switch") }}
                  </v-btn>
                </template>
              </v-data-table>
            </div>

            <div v-if="!installLoading" class="advanced-update-settings mt-5">
              <button
                class="advanced-settings-toggle"
                type="button"
                @click="
                  showAdvancedUpdateSettings = !showAdvancedUpdateSettings
                "
              >
                <span>{{
                  t("core.header.updateDialog.advancedSettings")
                }}</span>
                <v-icon
                  :icon="
                    showAdvancedUpdateSettings
                      ? 'mdi-chevron-down'
                      : 'mdi-chevron-right'
                  "
                  size="20"
                ></v-icon>
              </button>

              <div
                v-if="showAdvancedUpdateSettings"
                class="dashboard-update-banner mt-3"
              >
                <div>
                  <div class="font-weight-medium">
                    {{ t("core.header.updateDialog.dashboardUpdate.title") }}
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    {{
                      t(
                        "core.header.updateDialog.dashboardUpdate.currentVersion",
                      )
                    }}
                    {{ dashboardCurrentVersion }}
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    {{
                      dashboardHasNewVersion
                        ? t(
                            "core.header.updateDialog.dashboardUpdate.hasNewVersion",
                          )
                        : t("core.header.updateDialog.dashboardUpdate.fallback")
                    }}
                  </div>
                </div>
                <v-btn
                  color="primary"
                  variant="tonal"
                  @click="updateDashboard()"
                  :loading="updatingDashboardLoading"
                >
                  {{
                    t(
                      "core.header.updateDialog.dashboardUpdate.downloadAndUpdate",
                    )
                  }}
                </v-btn>
              </div>
            </div>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
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
    <v-dialog v-model="releaseNotesDialog" max-width="800">
      <v-card>
        <v-card-title class="text-h3 pa-4">
          {{ t("core.header.updateDialog.releaseNotes.title") }}:
          {{ selectedReleaseTag }}
        </v-card-title>
        <v-card-text
          style="font-size: 14px; max-height: 400px; overflow-y: auto"
        >
          <MarkdownRender
            :content="selectedReleaseNotes"
            :typewriter="false"
            class="markdown-content"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
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

    <v-dialog v-model="desktopUpdateDialog" max-width="460">
      <v-card>
        <v-card-title class="text-h3 pa-4 pl-6 pb-0">
          {{ t("core.header.updateDialog.desktopApp.title") }}
        </v-card-title>
        <v-card-text>
          <div class="mb-3">
            {{ t("core.header.updateDialog.desktopApp.message") }}
          </div>
          <v-alert type="info" variant="tonal" density="compact">
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
          <v-spacer></v-spacer>
          <v-btn
            color="grey"
            variant="text"
            @click="cancelDesktopUpdate"
            :disabled="desktopUpdateInstalling"
          >
            {{ t("core.common.dialog.cancelButton") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            @click="confirmDesktopUpdate"
            :loading="desktopUpdateInstalling"
            :disabled="
              desktopUpdateChecking ||
              desktopUpdateInstalling ||
              !desktopUpdateHasNewVersion
            "
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
          <div class="d-flex flex-column align-start mb-6">
            <logo
              :title="t('core.header.logoTitle')"
              :subtitle="t('core.header.accountDialog.title')"
            ></logo>
          </div>
          <v-alert
            v-if="accountWarning"
            type="warning"
            variant="tonal"
            border="start"
            class="mb-4"
          >
            <strong>{{
              t(
                accountWarningUpgrade
                  ? "core.header.accountDialog.securityWarningUpgrade"
                  : accountWarningLegacy
                  ? "core.header.accountDialog.securityWarningLegacy"
                  : "core.header.accountDialog.securityWarning",
              )
            }}</strong>
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

          <v-form v-model="formValid" @submit.prevent="accountEdit">
            <v-text-field
              v-model="password"
              :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
              :type="showPassword ? 'text' : 'password'"
              :label="t('core.header.accountDialog.form.currentPassword')"
              variant="outlined"
              required
              clearable
              @click:append-inner="showPassword = !showPassword"
              prepend-inner-icon="mdi-lock-outline"
              hide-details="auto"
              class="mb-4"
            ></v-text-field>

            <v-text-field
              v-model="newPassword"
              :append-inner-icon="showNewPassword ? 'mdi-eye-off' : 'mdi-eye'"
              :type="showNewPassword ? 'text' : 'password'"
              :rules="passwordRules"
              :label="t('core.header.accountDialog.form.newPassword')"
              variant="outlined"
              clearable
              @click:append-inner="showNewPassword = !showNewPassword"
              prepend-inner-icon="mdi-lock-plus-outline"
              :hint="t('core.header.accountDialog.form.passwordHint')"
              persistent-hint
              class="mb-4"
            ></v-text-field>

            <v-text-field
              v-model="confirmPassword"
              :append-inner-icon="
                showConfirmPassword ? 'mdi-eye-off' : 'mdi-eye'
              "
              :type="showConfirmPassword ? 'text' : 'password'"
              :rules="confirmPasswordRules"
              :label="t('core.header.accountDialog.form.confirmPassword')"
              variant="outlined"
              clearable
              @click:append-inner="showConfirmPassword = !showConfirmPassword"
              prepend-inner-icon="mdi-lock-check-outline"
              :hint="t('core.header.accountDialog.form.confirmPasswordHint')"
              persistent-hint
              class="mb-4"
            ></v-text-field>

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
            ></v-text-field>
          </v-form>

          <div class="text-caption text-medium-emphasis mt-2">
            {{ t("core.header.accountDialog.form.defaultCredentials") }}
          </div>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn
            v-if="!accountWarning"
            variant="tonal"
            color="secondary"
            @click="dialog = false"
            :disabled="accountEditStatus.loading"
          >
            {{ t("core.header.accountDialog.actions.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            @click="accountEdit"
            :loading="accountEditStatus.loading"
            :disabled="!formValid"
            prepend-icon="mdi-content-save"
          >
            {{ t("core.header.accountDialog.actions.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- About 对话框 - 仅在 chat mode 下使用 -->
    <v-dialog v-model="aboutDialog" width="600">
      <v-card>
        <v-card-text style="overflow-y: auto">
          <AboutPage />
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-app-bar>
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

.account-dialog-header {
  .theme-toggle-btn {
    opacity: 0.85;

    &:hover {
      opacity: 1;
    }
  }
}

.theme-toggle-btn {
  margin-left: 0;
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

.update-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.update-progress-panel,
.dashboard-update-banner,
.release-message-preview {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 16px;
}

.release-message-preview {
  max-height: 220px;
  overflow: hidden;
  position: relative;
}

.release-message-preview::after {
  content: "";
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 56px;
  background: linear-gradient(
    to bottom,
    rgba(var(--v-theme-surface), 0),
    rgb(var(--v-theme-surface))
  );
  pointer-events: none;
}

.dashboard-update-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.advanced-settings-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  font: inherit;
  font-weight: 500;
  padding: 8px 0;
  text-align: left;
}

.advanced-settings-toggle:hover {
  color: rgb(var(--v-theme-primary));
}

.restart-waiting-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 18px 0 22px;
}

.update-stage-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.update-stage-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.update-stage-content {
  flex: 1;
  min-width: 0;
}

.update-stage-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 6px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
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

  .update-summary,
  .dashboard-update-banner {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
