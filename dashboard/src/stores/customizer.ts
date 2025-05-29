import { defineStore } from 'pinia';
import config from '@/config';

export const useCustomizerStore = defineStore({
  id: 'customizer',
  state: () => ({
    Sidebar_drawer: config.Sidebar_drawer,
    Customizer_drawer: config.Customizer_drawer,
    mini_sidebar: config.mini_sidebar,
    fontTheme: "Poppins",
    uiTheme: config.uiTheme,
    inputBg: config.inputBg
  }),

  getters: {},
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
  }
});
