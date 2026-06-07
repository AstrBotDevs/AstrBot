import { defineStore } from 'pinia';
import config, { type ThemeMode } from '@/config';

const DARK_THEMES: ReadonlySet<string> = new Set(['PurpleThemeDark']);

function resolveUiThemeFromMode(mode: ThemeMode): string {
  if (mode === 'dark') return 'PurpleThemeDark';
  if (mode === 'light') return 'PurpleTheme';
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'PurpleThemeDark' : 'PurpleTheme';
}

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

    /**
     * 保留原有 action，兼容未改动的调用方。
     * 调用方传入 'PurpleTheme' 或 'PurpleThemeDark' 时，同时把
     * themeMode 推断并更新，保持两个字段一致。
     */
    SET_UI_THEME(payload: string) {
      this.uiTheme = payload;
      localStorage.setItem('uiTheme', payload);
      // 同步推断 themeMode（仅在直接调用此 action 时用作兜底）
      const mode: ThemeMode = payload === 'PurpleThemeDark' ? 'dark' : 'light';
      this.themeMode = mode;
      localStorage.setItem('themeMode', mode);
    },

    /**
     * 新 action：切换主题意图
     * 同时更新 themeMode、uiTheme 和 localStorage，Vuetify theme 由调用方负责。
     */
    SET_THEME_MODE(mode: ThemeMode) {
      this.themeMode = mode;
      localStorage.setItem('themeMode', mode);
      const uiTheme = resolveUiThemeFromMode(mode);
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
