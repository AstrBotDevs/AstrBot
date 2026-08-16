import { defineStore } from 'pinia';
import config, {
  getInitialSystemPrefersDark,
  type ThemeMode,
  resolveUiTheme,
} from '@/config';
import { themeNames } from '@/design/theme';

const DARK_THEMES: ReadonlySet<string> = new Set([themeNames.dark]);

export const useCustomizerStore = defineStore('customizer', {
  state: () => ({
    Sidebar_drawer: config.Sidebar_drawer,
    Customizer_drawer: config.Customizer_drawer,
    mini_sidebar: config.mini_sidebar,
    themeMode: config.themeMode,
    systemPrefersDark: getInitialSystemPrefersDark(),
    inputBg: config.inputBg,
    chatSidebarOpen: false, // chat mode mobile sidebar state
  }),

  getters: {
    uiTheme: (state) => {
      if (state.themeMode !== 'system') {
        return resolveUiTheme(state.themeMode);
      }
      return state.systemPrefersDark ? themeNames.dark : themeNames.light;
    },
    isDark(): boolean {
      return DARK_THEMES.has(this.uiTheme);
    },
  },

  actions: {
    SET_SIDEBAR_DRAWER() {
      this.Sidebar_drawer = !this.Sidebar_drawer;
    },
    SET_MINI_SIDEBAR(payload: boolean) {
      this.mini_sidebar = payload;
    },
    SET_THEME_MODE(mode: ThemeMode) {
      this.themeMode = mode;
      localStorage.setItem('themeMode', mode);
    },

    SET_SYSTEM_PREFERS_DARK(prefersDark: boolean) {
      this.systemPrefersDark = prefersDark;
    },

    TOGGLE_CHAT_SIDEBAR() {
      this.chatSidebarOpen = !this.chatSidebarOpen;
    },
    SET_CHAT_SIDEBAR(payload: boolean) {
      this.chatSidebarOpen = payload;
    },
  },
});
