import { readFileSync } from 'fs';
import { fileURLToPath, URL } from 'url';
import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import vuetify from 'vite-plugin-vuetify';
import { runMdiSubset } from './scripts/subset-mdi-font.mjs';

const t2iShikiRuntimePath = fileURLToPath(
  new URL(
    '../astrbot/core/utils/t2i/template/shiki_runtime.iife.js',
    import.meta.url,
  ),
);
const dashboardApiPort = process.env.ASTRBOT_DASHBOARD_API_PORT ?? '6185';

// Vite plugin: run MDI icon font subsetting (build only)
function mdiSubset() {
  return {
    name: 'vite-plugin-mdi-subset',
    async buildStart() {
      console.log('\n🔧 Running MDI icon font subsetting...');
      await runMdiSubset();
    },
  };
}

function t2iShikiRuntimeAsset(): Plugin {
  return {
    name: 'vite-plugin-t2i-shiki-runtime',
    configureServer(server) {
      server.middlewares.use('/t2i/shiki_runtime.iife.js', (_req, res) => {
        try {
          res.statusCode = 200;
          res.setHeader('Content-Type', 'text/javascript; charset=utf-8');
          res.end(readFileSync(t2iShikiRuntimePath));
        } catch (error) {
          res.statusCode = 404;
          res.end(
            `T2I Shiki runtime not found: ${error instanceof Error ? error.message : String(error)}`,
          );
        }
      });
    },
    generateBundle() {
      try {
        this.emitFile({
          type: 'asset',
          fileName: 't2i/shiki_runtime.iife.js',
          source: readFileSync(t2iShikiRuntimePath),
        });
      } catch (error) {
        this.warn(
          `Skipping T2I Shiki runtime asset because it could not be read: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }
    },
  };
}

function resolveVendorChunk(id: string): string | undefined {
  const normalized = id.replace(/\\/g, '/');
  if (!normalized.includes('/node_modules/')) {
    return undefined;
  }

  if (normalized.includes('/node_modules/vuetify/')) {
    return 'vendor-vuetify';
  }

  if (
    normalized.includes('/node_modules/vue/') ||
    normalized.includes('/node_modules/@vue/') ||
    normalized.includes('/node_modules/pinia/') ||
    normalized.includes('/node_modules/vue-router/') ||
    normalized.includes('/node_modules/axios/') ||
    normalized.includes('/node_modules/event-source-polyfill/')
  ) {
    return 'vendor-core';
  }

  return undefined;
}

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [
    // Only run MDI subsetting during production builds, skip in dev server
    ...(command === 'build' ? [mdiSubset()] : []),
    t2iShikiRuntimeAsset(),
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => ['v-list-recognize-title'].includes(tag),
        },
      },
    }),
    vuetify({
      autoImport: true,
      styles: {
        configFile: 'src/scss/settings.scss',
      },
    }),
  ],
  resolve: {
    alias: [
      {
        find: /^shiki$/,
        replacement: fileURLToPath(
          new URL('./src/utils/shikiLimitedBundle.ts', import.meta.url),
        ),
      },
      {
        find: /^stream-monaco$/,
        replacement: fileURLToPath(
          new URL('./src/utils/streamMonacoDisabled.ts', import.meta.url),
        ),
      },
      {
        find: 'mermaid',
        replacement: 'mermaid/dist/mermaid.js',
      },
      {
        find: '@',
        replacement: fileURLToPath(new URL('./src', import.meta.url)),
      },
    ],
  },
  css: {
    preprocessorOptions: {
      scss: {},
    },
  },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 1024 * 1024, // Set the limit to 1 MB
    rollupOptions: {
      output: {
        manualChunks(id) {
          return resolveVendorChunk(id);
        },
      },
    },
  },
  optimizeDeps: {
    exclude: ['vuetify'],
    entries: ['./src/**/*.vue'],
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${dashboardApiPort}/`,
        changeOrigin: true,
        ws: true,
      },
    },
  },
}));
