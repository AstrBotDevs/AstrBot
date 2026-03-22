import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import vuetify from "./plugins/vuetify";
import confirmPlugin from "./plugins/confirmPlugin";
import { setupI18n } from "./i18n/composables";
import "@/scss/style.scss";
import VueApexCharts from "vue3-apexcharts";

import print from "vue3-print-nb";
import { loader } from "@guolao/vue-monaco-editor";
import {
  getApiBaseUrl,
  resolveApiUrl,
  resolvePublicUrl,
  setApiBaseUrl,
} from "@/utils/request";
import { waitForRouterReadyInBackground } from "./utils/routerReadiness.mjs";
import { LIGHT_THEME_NAME, DARK_THEME_NAME } from "@/theme/constants";

// 1. 定义加载配置的函数
async function loadAppConfig() {
  try {
    // 加上时间戳防止浏览器缓存 config.json
    const configUrl = new URL(resolvePublicUrl("config.json"));
    configUrl.searchParams.set("t", `${Date.now()}`);
    const response = await fetch(configUrl.toString());
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.warn("Failed to load config.json, falling back to default.", error);
    return {};
  }
}

async function mountApp(app: any, pinia: any, waitForRouter = true) {
  if (waitForRouter) {
    await router.isReady();
  } else {
    waitForRouterReadyInBackground(router);
  }
  app.mount("#app");

  // 挂载后同步 Vuetify 主题
  import("./stores/customizer").then(({ useCustomizerStore }) => {
    const customizer = useCustomizerStore(pinia);
    vuetify.theme.global.name.value = customizer.uiTheme;
    const storedPrimary = localStorage.getItem("themePrimary");
    const storedSecondary = localStorage.getItem("themeSecondary");
    if (storedPrimary || storedSecondary) {
      const themes = vuetify.theme.themes.value;
      [LIGHT_THEME_NAME, DARK_THEME_NAME].forEach((name) => {
        const theme = themes[name];
        if (!theme?.colors) return;
        if (storedPrimary) theme.colors.primary = storedPrimary;
        if (storedSecondary) theme.colors.secondary = storedSecondary;
        if (storedPrimary && theme.colors.darkprimary)
          theme.colors.darkprimary = storedPrimary;
        if (storedSecondary && theme.colors.darksecondary)
          theme.colors.darksecondary = storedSecondary;
      });
    }
  });
}

async function initApp() {
  // 等待配置加载
  const config = await loadAppConfig();
  const configApiUrl = config.apiBaseUrl || "";
  const presets = config.presets || [];
  const envApiUrl = import.meta.env.VITE_API_BASE || "";

  // 优先使用 localStorage 中的配置，其次是 config.json，最后是空字符串
  const localApiUrl = localStorage.getItem("apiBaseUrl");
  const apiBaseUrl =
    localApiUrl !== null ? localApiUrl : configApiUrl || envApiUrl;

  if (apiBaseUrl) {
    console.log(
      `API Base URL set to: ${apiBaseUrl} (Local: ${localApiUrl}, Config: ${configApiUrl})`,
    );
  }

  setApiBaseUrl(apiBaseUrl);

  // Keep fetch() calls consistent with axios by automatically attaching the JWT.
  // Some parts of the UI use fetch directly; without this, those requests will 401.
  // Also handle apiBaseUrl for fetch
  const _origFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    let url = input;

    // 如果是字符串路径且以 /api 开头，并且配置了 Base URL，则拼接
    if (typeof input === "string" && input.startsWith("/api")) {
      url = resolveApiUrl(input, getApiBaseUrl());
    }

    const token = localStorage.getItem("token");

    const headers = new Headers(
      init?.headers ||
        (typeof input !== "string" && "headers" in input
          ? input.headers
          : undefined),
    );
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const locale = localStorage.getItem("astrbot-locale");
    if (locale && !headers.has("Accept-Language")) {
      headers.set("Accept-Language", locale);
    }

    return _origFetch(url, { ...init, headers });
  };

  loader.config({
    paths: {
      vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.54.0/min/vs",
    },
  });

  // 初始化新的i18n系统，等待完成后再挂载应用
  setupI18n()
    .then(async () => {
      console.log("🌍 新i18n系统初始化完成");

      const app = createApp(App);
      app.use(router);
      const pinia = createPinia();
      app.use(pinia);

      // Initialize API Store with presets
      const { useApiStore } = await import("@/stores/api");
      const apiStore = useApiStore(pinia);
      apiStore.setPresets(presets);
      apiStore.init();

      app.use(print);
      app.use(VueApexCharts);
      app.use(vuetify);
      app.use(confirmPlugin);

      mountApp(app, pinia, true);
    })
    .catch(async (error) => {
      console.error("❌ 新i18n系统初始化失败:", error);

      // 即使i18n初始化失败，也要挂载应用（使用回退机制）
      const app = createApp(App);
      app.use(router);
      const pinia = createPinia();
      app.use(pinia);

      // Initialize API Store with presets
      const { useApiStore } = await import("@/stores/api");
      const apiStore = useApiStore(pinia);
      apiStore.setPresets(presets);
      apiStore.init();

      app.use(print);
      app.use(VueApexCharts);
      app.use(vuetify);
      app.use(confirmPlugin);

      mountApp(app, pinia, false);
    });
}

// 启动应用
initApp();
