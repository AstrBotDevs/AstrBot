import { defineStore } from 'pinia';
import config, { type ThemeMode, resolveUiTheme } from '@/config';

const DARK_THEMES: ReadonlySet<string> = new Set(['PurpleThemeDark']);


export const useCustomizerStore = defineStore('customizer', {
  state: () => ({
    Sidebar_drawer: config.Sidebar_drawer,
    Customizer_drawer: config.Customizer_drawer,
    mini_sidebar: config.mini_sidebar,
    fontTheme: 'Noto Sans SC',
    uiTheme: config.uiTheme,
    themeMode: config.themeMode as ThemeMode,
    inputBg: config.inputBg,
    chatSidebarOpen: false, // chat mode mobile sidebar state
  }),

  getters: {
    isDark: (state) => state.uiTheme ? DARK_THEMES.has(state.uiTheme) : false,
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
      localStorage.setItem('uiTheme', payload);
      const mode: ThemeMode = payload === 'PurpleThemeDark' ? 'dark' : 'light';
      this.themeMode = mode;
      localStorage.setItem('themeMode', mode);
    },

    SET_THEME_MODE(mode: ThemeMode) {
      this.themeMode = mode;
      localStorage.setItem('themeMode', mode);
      const uiTheme = resolveUiTheme(mode);
      this.uiTheme = uiTheme;
      localStorage.setItem('uiTheme', uiTheme);
    },

    TOGGLE_CHAT_SIDEBAR() {
      this.chatSidebarOpen = !this.chatSidebarOpen;
    },
    SET_CHAT_SIDEBAR(payload: boolean) {
      this.chatSidebarOpen = payload;
    },
  },
});
