import { defineStore } from "pinia";
import config, { resolveUiTheme, type ThemeMode } from "@/config";
import vuetify from "@/plugins/vuetify";
import { DARK_THEME_NAME } from "@/theme/constants";
import { chatPreferences } from "@/utils/chatPreferences";

function applyUiTheme(theme: string) {
  if (typeof vuetify.theme.change === "function") {
    vuetify.theme.change(theme);
  } else {
    vuetify.theme.global.name.value = theme;
  }
}

export const useCustomizerStore = defineStore("customizer", {
  state: () => ({
    Sidebar_drawer: config.Sidebar_drawer,
    Customizer_drawer: config.Customizer_drawer,
    mini_sidebar: config.mini_sidebar,
    fontTheme: config.fontTheme,
    uiTheme: config.uiTheme,
    themeMode: config.themeMode as ThemeMode,
    inputBg: config.inputBg,
    viewMode: localStorage.getItem("viewMode") === "chat" ? ("chat" as const) : ("bot" as const),
    autoSwitchTheme: config.themeMode === "system",
    chatNavigationInSidebar: chatPreferences().global.navigationInSidebar === true,
    chatSidebarOpen: false,
    chatSidebarCollapsed: false,
  }),

  getters: {
    isDark: (state) => state.uiTheme === DARK_THEME_NAME,
    isDarkTheme: (state) => state.uiTheme === DARK_THEME_NAME,
  },

  actions: {
    SET_SIDEBAR_DRAWER() {
      this.Sidebar_drawer = !this.Sidebar_drawer;
    },
    SET_MINI_SIDEBAR(payload: boolean) {
      this.mini_sidebar = payload;
    },
    SET_FONT(payload: string) {
      this.fontTheme = payload;
    },
    SET_UI_THEME(payload: string) {
      this.SET_THEME_MODE(payload === DARK_THEME_NAME ? "dark" : "light");
    },
    SET_THEME_MODE(mode: ThemeMode) {
      this.themeMode = mode;
      this.autoSwitchTheme = mode === "system";
      localStorage.setItem("themeMode", mode);
      localStorage.setItem("autoSwitchTheme", String(this.autoSwitchTheme));
      this.uiTheme = resolveUiTheme(mode);
      localStorage.setItem("uiTheme", this.uiTheme);
      applyUiTheme(this.uiTheme);
    },
    SET_VIEW_MODE(payload: "bot" | "chat") {
      this.viewMode = payload;
      localStorage.setItem("viewMode", payload);
    },
    SET_AUTO_SYNC(payload: boolean) {
      this.SET_THEME_MODE(payload ? "system" : this.isDark ? "dark" : "light");
    },
    TOGGLE_DARK_MODE() {
      this.SET_THEME_MODE(this.isDark ? "light" : "dark");
    },
    APPLY_SYSTEM_THEME() {
      if (this.themeMode !== "system" || typeof window === "undefined") return;
      this.uiTheme = resolveUiTheme("system");
      localStorage.setItem("uiTheme", this.uiTheme);
      applyUiTheme(this.uiTheme);
    },
    SET_CHAT_NAVIGATION_IN_SIDEBAR(payload: boolean) {
      this.chatNavigationInSidebar = payload;
      chatPreferences((preferences) => {
        preferences.global.navigationInSidebar = payload;
      });
    },
    TOGGLE_CHAT_SIDEBAR() {
      this.chatSidebarOpen = !this.chatSidebarOpen;
    },
    SET_CHAT_SIDEBAR(payload: boolean) {
      this.chatSidebarOpen = payload;
    },
    SET_CHAT_SIDEBAR_COLLAPSED(payload: boolean) {
      this.chatSidebarCollapsed = payload;
    },
  },
});
