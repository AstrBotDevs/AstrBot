import { fileURLToPath, URL } from 'url';
import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import vuetify from 'vite-plugin-vuetify';
import webfontDl from 'vite-plugin-webfont-dl';

// Vite plugin: run MDI icon font subsetting (build only)
function mdiSubset() {
  return {
    name: 'vite-plugin-mdi-subset',
    async buildStart() {
      const { runMdiSubset } = await import('./scripts/subset-mdi-font.mjs');
      console.log('\n🔧 Running MDI icon font subsetting...');
      await runMdiSubset();
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const basePath = env.VITE_BASE_PATH || process.env.BASE_PATH || '/';

  return {
    base: command === 'build' ? basePath : '/',

    plugins: [
      // Only run MDI subsetting during production builds, skip in dev server
      ...(command === 'build' ? [mdiSubset()] : []),
      vue({
        template: {
          compilerOptions: {
            isCustomElement: (tag) => ["v-list-recognize-title"].includes(tag),
          },
        },
      }),
      vuetify({
        autoImport: true
      }),
      webfontDl()
    ],
    resolve: {
      alias: {
        mermaid: "mermaid/dist/mermaid.js",
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    css: {
      preprocessorOptions: {
        scss: {},
      },
    },
    build: {
      sourcemap: false,
      chunkSizeWarningLimit: 1024 * 1024, // Set the limit to 1 MB
    },
    optimizeDeps: {
      exclude: ["vuetify"],
      entries: ["./src/**/*.vue"],
    },
    server: {
      host: "::",
      port: 3000,
      proxy: {
        "/api": {
          target: env.VITE_DEV_API_PROXY_TARGET || "http://127.0.0.1:6185",
          changeOrigin: true,
          ws: true
        }
      }
    }
  };
});
