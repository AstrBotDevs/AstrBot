import { fileURLToPath, URL } from 'url';
import { defineConfig } from 'vite';
import { execFileSync } from 'child_process';
import vue from '@vitejs/plugin-vue';
import vuetify from 'vite-plugin-vuetify';
import webfontDl from 'vite-plugin-webfont-dl';

// Vite plugin: run MDI icon font subsetting before each build
function mdiSubset() {
  return {
    name: 'vite-plugin-mdi-subset',
    buildStart() {
      console.log('\n🔧 Running MDI icon font subsetting...');
      execFileSync('node', ['scripts/subset-mdi-font.mjs'], {
        cwd: fileURLToPath(new URL('.', import.meta.url)),
        stdio: 'inherit',
      });
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    mdiSubset(),
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => ['v-list-recognize-title'].includes(tag)
        }
      }
    }),
    vuetify({
      autoImport: true
    }),
    webfontDl()
  ],
  resolve: {
    alias: {
      mermaid: 'mermaid/dist/mermaid.js',
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  css: {
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
        ws: true
      }
    }
  }
});
