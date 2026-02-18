import { fileURLToPath, URL } from 'url';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import vuetify from 'vite-plugin-vuetify';

const normalizeNestedTypeSelectorPlugin = {
  postcssPlugin: 'normalize-nested-type-selector',
  Rule(rule: { parent?: { type?: string }; selector?: string }) {
    if (rule.parent?.type !== 'rule' || typeof rule.selector !== 'string') {
      return;
    }

    const segments = rule.selector
      .split(',')
      .map((segment) => segment.trim())
      .filter(Boolean);
    if (!segments.length) {
      return;
    }

    const typeOnlyPattern = /^[a-zA-Z][\w-]*$/;
    if (!segments.every((segment) => typeOnlyPattern.test(segment))) {
      return;
    }

    rule.selector = segments.map((segment) => `:is(${segment})`).join(', ');
  }
};

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => ['v-list-recognize-title'].includes(tag)
        }
      }
    }),
    vuetify({
      autoImport: true
    })
  ],
  resolve: {
    alias: {
      mermaid: 'mermaid/dist/mermaid.js',
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  css: {
    postcss: {
      plugins: [normalizeNestedTypeSelectorPlugin]
    },
    preprocessorOptions: {
      scss: {}
    }
  },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 1024 * 1024 // Set the limit to 1 MB
  },
  optimizeDeps: {
    exclude: ['vuetify'],
    entries: ['./src/**/*.vue']
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:6185/',
        changeOrigin: true,
      }
    }
  }
});
