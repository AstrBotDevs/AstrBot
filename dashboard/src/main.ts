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
import axios from "axios";

// 1. 定义加载配置的函数
async function loadAppConfig() {
  try {
    // 加上时间戳防止浏览器缓存 config.json
    const response = await fetch(`/config.json?t=${new Date().getTime()}`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.warn("Failed to load config.json, falling back to default.", error);
    return {};
  }
}

function mountApp(app: any, pinia: any) {
  app.mount("#app");

  // 挂载后同步 Vuetify 主题
  import("./stores/customizer").then(({ useCustomizerStore }) => {
    const customizer = useCustomizerStore(pinia);
    vuetify.theme.global.name.value = customizer.uiTheme;
    const storedPrimary = localStorage.getItem("themePrimary");
    const storedSecondary = localStorage.getItem("themeSecondary");
    if (storedPrimary || storedSecondary) {
      const themes = vuetify.theme.themes.value;
      ["PurpleTheme", "PurpleThemeDark"].forEach((name) => {
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

  // 优先使用 localStorage 中的配置，其次是 config.json，最后是空字符串
  const localApiUrl = localStorage.getItem("apiBaseUrl");
  const apiBaseUrl = localApiUrl !== null ? localApiUrl : configApiUrl;

  if (apiBaseUrl) {
    console.log(
      `API Base URL set to: ${apiBaseUrl} (Local: ${localApiUrl}, Config: ${configApiUrl})`,
    );
  }

  // 配置 Axios 全局 Base URL
  axios.defaults.baseURL = apiBaseUrl;

  axios.interceptors.request.use((config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
    return config;
  });

  // Keep fetch() calls consistent with axios by automatically attaching the JWT.
  // Some parts of the UI use fetch directly; without this, those requests will 401.
  // Also handle apiBaseUrl for fetch
  const _origFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    let url = input;

    // 动态获取当前的 Base URL (可能已被 Store 修改)
    const currentBaseUrl = axios.defaults.baseURL;

    // 如果是字符串路径且以 /api 开头，并且配置了 Base URL，则拼接
    if (
      typeof input === "string" &&
      input.startsWith("/api") &&
      currentBaseUrl
    ) {
      // 移除 apiBaseUrl 尾部的斜杠
      const cleanBase = currentBaseUrl.replace(/\/+$/, "");
      // 移除 input 开头的斜杠
      const cleanPath = input.replace(/^\/+/, "");
      url = `${cleanBase}/${cleanPath}`;
    }

    const token = localStorage.getItem("token");
    // 如果没有 token，但有 apiBaseUrl 修改，仍需使用新 url
    if (!token) return _origFetch(url, init);

    const headers = new Headers(
      init?.headers ||
        (typeof input !== "string" && "headers" in input
          ? (input as Request).headers
          : undefined),
    );
    if (!headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
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

      app.use(print);
      app.use(VueApexCharts);
      app.use(vuetify);
      app.use(confirmPlugin);

      mountApp(app, pinia);
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

      app.use(print);
      app.use(VueApexCharts);
      app.use(vuetify);
      app.use(confirmPlugin);

      mountApp(app, pinia);
    });
}

// 启动应用
initApp();
