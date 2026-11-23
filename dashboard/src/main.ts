import { createPinia } from "pinia";
import { createApp, watch } from "vue";
import print from "vue3-print-nb";
import App from "./App.vue";
import { setupHttpClient } from "./api/http";
import { resolveUiTheme } from "./config";
import { setupI18n } from "./i18n/composables";
import confirmPlugin from "./plugins/confirmPlugin";
import vuetify from "./plugins/vuetify";
import { router } from "./router";
import { type ApiPreset, useApiStore } from "./stores/api";
import { useCustomizerStore } from "./stores/customizer";
import { DARK_THEME_NAME, LIGHT_THEME_NAME } from "./theme/constants";
import { resolvePublicUrl, setApiBaseUrl } from "./utils/request";
import { waitForRouterReadyInBackground } from "./utils/routerReadiness.mjs";
import "@/scss/style.scss";

interface ApplicationConfig {
  apiBaseUrl?: string;
  presets?: ApiPreset[];
}

async function loadAppConfig(): Promise<ApplicationConfig> {
  try {
    const configUrl = new URL(resolvePublicUrl("config.json"));
    configUrl.searchParams.set("t", String(Date.now()));
    const response = await fetch(configUrl);
    if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
    return await response.json();
  } catch (error) {
    console.warn("Failed to load config.json; using saved or environment settings.", error);
    return {};
  }
}

function setupThemeSync(pinia: ReturnType<typeof createPinia>) {
  const customizer = useCustomizerStore(pinia);
  customizer.uiTheme = resolveUiTheme(customizer.themeMode);
  localStorage.setItem("uiTheme", customizer.uiTheme);

  const storedPrimary = localStorage.getItem("themePrimary");
  const storedSecondary = localStorage.getItem("themeSecondary");
  for (const name of [LIGHT_THEME_NAME, DARK_THEME_NAME]) {
    const theme = vuetify.theme.themes.value[name];
    if (!theme?.colors) continue;
    if (storedPrimary) {
      theme.colors.primary = storedPrimary;
      if (theme.colors.darkprimary) theme.colors.darkprimary = storedPrimary;
    }
    if (storedSecondary) {
      theme.colors.secondary = storedSecondary;
      if (theme.colors.darksecondary) theme.colors.darksecondary = storedSecondary;
    }
  }

  const stopThemeWatch = watch(
    () => customizer.uiTheme,
    (name) => {
      vuetify.theme.change(name);
      const setWindowTheme = window.astrbotDesktop?.setWindowTheme;
      if (typeof setWindowTheme === "function") {
        setWindowTheme(name === DARK_THEME_NAME ? "dark" : "light");
      }
    },
    { immediate: true },
  );

  const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const onSystemThemeChange = () => {
    if (customizer.themeMode !== "system") return;
    customizer.uiTheme = resolveUiTheme("system");
    localStorage.setItem("uiTheme", customizer.uiTheme);
  };
  mediaQuery.addEventListener("change", onSystemThemeChange);
  return () => {
    mediaQuery.removeEventListener("change", onSystemThemeChange);
    stopThemeWatch();
  };
}

async function initApp() {
  const config = await loadAppConfig();
  const savedApiUrl = localStorage.getItem("apiBaseUrl");
  const configuredApiUrl = typeof config.apiBaseUrl === "string" ? config.apiBaseUrl : "";
  setApiBaseUrl(savedApiUrl !== null ? savedApiUrl : configuredApiUrl || import.meta.env.VITE_API_BASE || "");
  setupHttpClient();

  const app = createApp(App);
  const pinia = createPinia();
  app.use(pinia);
  const apiStore = useApiStore(pinia);
  apiStore.setPresets(Array.isArray(config.presets) ? config.presets : []);
  apiStore.init();

  app.use(router);
  app.use(print);
  app.use(vuetify);
  app.use(confirmPlugin);

  let translationsReady = true;
  try {
    await setupI18n();
  } catch (error) {
    translationsReady = false;
    console.error("Failed to initialize translations; mounting with fallback labels.", error);
  }
  if (translationsReady) {
    await router.isReady();
  } else {
    waitForRouterReadyInBackground(router);
  }
  app.mount("#app");
  app.onUnmount(setupThemeSync(pinia));
}

void initApp().catch((error) => {
  console.error("Failed to initialize the dashboard.", error);
});
