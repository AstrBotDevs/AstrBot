import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { router } from './router';
import vuetify from './plugins/vuetify';
import confirmPlugin from './plugins/confirmPlugin';
import { setupI18n } from './i18n/composables';
import '@/scss/style.scss';
import VueApexCharts from 'vue3-apexcharts';

import print from 'vue3-print-nb';
import { loader } from '@guolao/vue-monaco-editor'
import axios from 'axios';

// 初始化新的i18n系统，等待完成后再挂载应用
setupI18n().then(() => {
  console.log('🌍 新i18n系统初始化完成');
  
  const app = createApp(App);
  app.use(router);
  const pinia = createPinia();
  app.use(pinia);
  app.use(print);
  app.use(VueApexCharts);
  app.use(vuetify);
  app.use(confirmPlugin);
  app.mount('#app');
  
  // 挂载后同步 Vuetify 主题
  import('./stores/customizer').then(({ useCustomizerStore }) => {
    const customizer = useCustomizerStore(pinia);
    vuetify.theme.global.name.value = customizer.uiTheme;
    const storedPrimary = localStorage.getItem('themePrimary');
    const storedSecondary = localStorage.getItem('themeSecondary');
    if (storedPrimary || storedSecondary) {
      const themes = vuetify.theme.themes.value;
      ['PurpleTheme', 'PurpleThemeDark'].forEach((name) => {
        const theme = themes[name];
        if (!theme?.colors) return;
        if (storedPrimary) theme.colors.primary = storedPrimary;
        if (storedSecondary) theme.colors.secondary = storedSecondary;
        if (storedPrimary && theme.colors.darkprimary) theme.colors.darkprimary = storedPrimary;
        if (storedSecondary && theme.colors.darksecondary) theme.colors.darksecondary = storedSecondary;
      });
    }
  });
}).catch(error => {
  console.error('❌ 新i18n系统初始化失败:', error);
  
  // 即使i18n初始化失败，也要挂载应用（使用回退机制）
  const app = createApp(App);
  app.use(router);
  const pinia = createPinia();
  app.use(pinia);
  app.use(print);
  app.use(VueApexCharts);
  app.use(vuetify);
  app.use(confirmPlugin);
  app.mount('#app');
  
  // 挂载后同步 Vuetify 主题
  import('./stores/customizer').then(({ useCustomizerStore }) => {
    const customizer = useCustomizerStore(pinia);
    vuetify.theme.global.name.value = customizer.uiTheme;
    const storedPrimary = localStorage.getItem('themePrimary');
    const storedSecondary = localStorage.getItem('themeSecondary');
    if (storedPrimary || storedSecondary) {
      const themes = vuetify.theme.themes.value;
      ['PurpleTheme', 'PurpleThemeDark'].forEach((name) => {
        const theme = themes[name];
        if (!theme?.colors) return;
        if (storedPrimary) theme.colors.primary = storedPrimary;
        if (storedSecondary) theme.colors.secondary = storedSecondary;
        if (storedPrimary && theme.colors.darkprimary) theme.colors.darkprimary = storedPrimary;
        if (storedSecondary && theme.colors.darksecondary) theme.colors.darksecondary = storedSecondary;
      });
    }
  });
});


axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

// Keep fetch() calls consistent with axios by automatically attaching the JWT.
// Some parts of the UI use fetch directly; without this, those requests will 401.
const _origFetch = window.fetch.bind(window);
window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
  const token = localStorage.getItem('token');
  if (!token) return _origFetch(input, init);

  const headers = new Headers(init?.headers || (typeof input !== 'string' && 'headers' in input ? (input as Request).headers : undefined));
  if (!headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return _origFetch(input, { ...init, headers });
};

loader.config({
  paths: {
    vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.54.0/min/vs',
  },
})
