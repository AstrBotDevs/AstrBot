import { defineStore } from "pinia";
import config from "@/config";
import { LIGHT_THEME_NAME, DARK_THEME_NAME } from "@/theme/constants";

export const useCustomizerStore = defineStore({
  id: "customizer",
  state: () => ({
    Sidebar_drawer: config.Sidebar_drawer,
    Customizer_drawer: config.Customizer_drawer,
    mini_sidebar: config.mini_sidebar,
    fontTheme: "Poppins",
    uiTheme: config.uiTheme,
    inputBg: config.inputBg,
    viewMode: (localStorage.getItem("viewMode") as "bot" | "chat") || "bot", // 'bot' 或 'chat'
    chatSidebarOpen: false, // chat mode mobile sidebar state
    autoSwitchTheme: localStorage.getItem("autoSwitchTheme") === "true", // 自动同步主题
  }),

  getters: {
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
      this.uiTheme = payload;
      localStorage.setItem("uiTheme", payload);
    },
    SET_VIEW_MODE(payload: "bot" | "chat") {
      this.viewMode = payload;
      localStorage.setItem("viewMode", payload);
    },
    SET_AUTO_SYNC(payload: boolean) {
      this.autoSwitchTheme = payload;
      localStorage.setItem("autoSwitchTheme", String(payload));
    },
    // 新增：手动切换主题（同时关闭自动同步）
    TOGGLE_DARK_MODE() {
      // 手动切换时禁用自动同步
      this.SET_AUTO_SYNC(false);
      const newTheme = this.isDarkTheme ? LIGHT_THEME_NAME : DARK_THEME_NAME;
      this.SET_UI_THEME(newTheme);
    },
    // 新增：应用系统主题（用于自动同步）
    APPLY_SYSTEM_THEME() {
      if (typeof window === "undefined") return;
      const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const themeToApply = isDark ? DARK_THEME_NAME : LIGHT_THEME_NAME;
      this.SET_UI_THEME(themeToApply);
    },
    TOGGLE_CHAT_SIDEBAR() {
      this.chatSidebarOpen = !this.chatSidebarOpen;
    },
    SET_CHAT_SIDEBAR(payload: boolean) {
      this.chatSidebarOpen = payload;
    },
  },
});
