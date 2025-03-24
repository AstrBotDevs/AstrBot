import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { router } from './router';
import vuetify from './plugins/vuetify';
import confirmPlugin from './plugins/confirmPlugin';
import '@/scss/style.scss';
import VueApexCharts from 'vue3-apexcharts';

import print from 'vue3-print-nb';
import { loader } from '@guolao/vue-monaco-editor'
import axios from 'axios';

const app = createApp(App);
app.use(router);
app.use(createPinia());
app.use(print);
app.use(VueApexCharts);
app.use(vuetify);
app.use(confirmPlugin);
app.mount('#app');


axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

loader.config({
  paths: {
    vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.43.0/min/vs',
  },
})