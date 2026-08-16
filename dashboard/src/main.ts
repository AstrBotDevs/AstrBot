import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { watch } from 'vue';
import App from './App.vue';
import { router } from './router';
import vuetify from './plugins/vuetify';
import confirmPlugin from './plugins/confirmPlugin';
import { setupI18n } from './i18n/composables';
import '@/scss/style.scss';
import '@/assets/fonts/fonts.css';
import { setupHttpClient } from './api/http';
import { waitForRouterReadyInBackground } from './utils/routerReadiness';
import { applyUserThemeColors } from './design/theme';

setupHttpClient();

/**
 * 挂载后初始化主题并注册全局系统主题监听器。
 * 职责：
 *   - 同步 Vuetify theme 名称与 store 的派生 uiTheme
 *   - 监听系统色彩模式变化并更新 store 的系统偏好输入
 *   - 应用自定义 primary/secondary 色
 * 注意：VerticalHeader.vue / ThemeSwitcher.vue 不再自行注册 matchMedia 监听器，
 *       避免与此处产生竞态。
 */
function setupThemeSync(pinia: ReturnType<typeof createPinia>) {
  void import('./stores/customizer').then(({ useCustomizerStore }) => {
    const customizer = useCustomizerStore(pinia);
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    customizer.SET_SYSTEM_PREFERS_DARK(mediaQuery.matches);

    watch(
      () => customizer.uiTheme,
      (themeName) => {
        void vuetify.theme.change(themeName);
      },
      { immediate: true },
    );

    // 2. 应用用户自定义色
    const storedPrimary = localStorage.getItem('themePrimary');
    const storedSecondary = localStorage.getItem('themeSecondary');
    if (storedPrimary || storedSecondary) {
      applyUserThemeColors(
        vuetify.theme.themes.value,
        storedPrimary,
        storedSecondary,
      );
    }

    // 3. 全局唯一 matchMedia 监听器：维护系统主题输入
    mediaQuery.addEventListener('change', (e) => {
      customizer.SET_SYSTEM_PREFERS_DARK(e.matches);
    });
  });
}

// 初始化新的i18n系统，等待完成后再挂载应用
void setupI18n()
  .then(async () => {
    console.log('🌍 新i18n系统初始化完成');

    const app = createApp(App);
    const pinia = createPinia();
    app.use(pinia);
    app.use(router);
    app.use(vuetify);
    app.use(confirmPlugin);
    await router.isReady();
    app.mount('#app');

    setupThemeSync(pinia);
  })
  .catch((error) => {
    console.error('❌ 新i18n系统初始化失败:', error);

    // 即使i18n初始化失败，也要挂载应用（使用回退机制）
    const app = createApp(App);
    const pinia = createPinia();
    app.use(pinia);
    app.use(router);
    app.use(vuetify);
    app.use(confirmPlugin);
    app.mount('#app');
    waitForRouterReadyInBackground(router);

    setupThemeSync(pinia);
  });
